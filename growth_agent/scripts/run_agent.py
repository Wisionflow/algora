"""Entry point for Algora Growth Agent.

Usage:
    python -m scripts.run_agent           # Normal run
    python -m scripts.run_agent --mock    # Mock mode (no real TG, no real LLM)
"""

import asyncio
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from loguru import logger
from dotenv import load_dotenv

load_dotenv()

from src import config
from src.models import Message, BrainDecision


async def on_message(message: Message, actor) -> None:
    """Pipeline: Message → Brain → Actor."""
    from src.brain import think
    decision: BrainDecision = await think(message)
    await actor.act(message, decision)


async def run_mock() -> None:
    """Smoke-test without DB, Telegram, or NATS. Tests config + relevance."""
    logger.info("=== MOCK MODE (no DB, no Telegram, no NATS) ===")

    # Test 1: Config
    logger.info("Config check:")
    logger.info("  TG_API_ID: {}", config.TG_API_ID)
    logger.info("  TG_API_HASH: {}...", config.TG_API_HASH[:8] if config.TG_API_HASH else "NOT SET")
    logger.info("  TG_PHONE: {}", config.TG_PHONE)
    logger.info("  NATS_URL: {}", config.NATS_URL)
    logger.info("  OPENROUTER_MODEL: {}", config.OPENROUTER_MODEL)
    logger.info("  CHANNEL_LINK: {}", config.CHANNEL_LINK)
    logger.info("  RELEVANCE_KEYWORDS: {} keywords", len(config.RELEVANCE_KEYWORDS))

    assert config.TG_API_ID != 0, "TG_API_ID not set!"
    assert config.TG_API_HASH, "TG_API_HASH not set!"
    assert config.TG_PHONE, "TG_PHONE not set!"
    logger.info("  -> Config OK")

    # Test 2: Relevance scoring
    from src.relevance import compute_relevance as _compute_relevance
    test_cases = [
        ("Какая маржа сейчас на чехлах для телефонов на WB?", True),
        ("Всем привет, как дела?", False),
        ("Ищу поставщика с 1688, кто работает с электроникой?", True),
        ("Погода сегодня хорошая", False),
        ("Подскажите карго из Китая, нужно закупить товар для Ozon", True),
    ]
    logger.info("\nRelevance scoring test:")
    all_ok = True
    for text, expected_relevant in test_cases:
        score = _compute_relevance(text)
        is_relevant = score >= config.MIN_RELEVANCE_SCORE
        ok = is_relevant == expected_relevant
        if not ok:
            all_ok = False
        logger.info("  [{}] score={:.2f} relevant={} | {}", "OK" if ok else "FAIL", score, is_relevant, text[:60])
    logger.info("  -> Relevance {}", "OK" if all_ok else "HAS FAILURES")

    # Test 3: NATS + LLM (only if NATS_URL is not default placeholder)
    if config.NATS_URL and "nats:" in config.NATS_URL:
        try:
            import nats as nats_lib
            logger.info("\nNATS connection test:")
            nc = await nats_lib.connect(
                config.NATS_URL,
                max_reconnect_attempts=1,
                reconnect_time_wait=1,
            )
            logger.info("  NATS connected: {}", nc.is_connected)

            # Test LLM via NATS
            import json
            from src.brain import init_nats, _call_llm, SYSTEM_PROMPT, DECISION_PROMPT
            init_nats(nc)

            prompt_text = DECISION_PROMPT.format(text="Какая маржа сейчас на чехлах для телефонов на WB?")
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ]
            try:
                raw = await _call_llm(messages)
                clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                data = json.loads(clean)
                logger.info("  LLM response: {}", json.dumps(data, ensure_ascii=False, indent=2))
                logger.info("  -> LLM OK")
            except asyncio.TimeoutError:
                logger.warning("  LLM call timed out (NATS AI Proxy may not be reachable)")
            except Exception as e:
                logger.error("  LLM call failed: {}", e)

            await nc.drain()
        except Exception as e:
            logger.warning("\nNATS test: SKIPPED (cannot connect: {})", e)
    else:
        logger.info("\nNATS test: SKIPPED (NATS_URL not configured)")

    logger.info("\n=== Mock run complete ===")


async def run_live() -> None:
    """Full live run with Telethon + NATS + PostgreSQL."""
    import nats as nats_lib
    from src import db, brain
    from src.listener import Listener
    from src.actor import Actor
    from src.scheduler import run_daily_tasks

    if not config.TG_API_ID or not config.TG_API_HASH:
        logger.error("TG_API_ID and TG_API_HASH must be set in .env")
        logger.error("Get them at https://my.telegram.org")
        sys.exit(1)

    if not config.POSTGRES_DSN:
        logger.error("POSTGRES_DSN not set in .env")
        sys.exit(1)

    # Initialize DB
    await db.init_pool(config.POSTGRES_DSN)

    # Initialize NATS
    nc = await nats_lib.connect(
        config.NATS_URL,
        max_reconnect_attempts=-1,
        reconnect_time_wait=2,
    )
    brain.init_nats(nc)
    logger.info("NATS connected to {}", config.NATS_URL)

    # Initialize Listener (creates and connects Telethon client)
    listener = Listener(on_relevant_message=lambda msg: None)  # temp callback
    await listener.start()

    # Actor uses Listener's connected Telethon client
    actor = Actor(listener._client)

    async def message_handler(message: Message) -> None:
        await on_message(message, actor)

    listener._callback = message_handler

    logger.info("Growth Agent started. Monitoring chats...")

    try:
        await asyncio.gather(
            listener.run_until_disconnected(),
            run_daily_tasks(),
        )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await listener.stop()
        await nc.drain()
        await db.close_pool()


def main():
    parser = argparse.ArgumentParser(description="Algora Growth Agent")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (no real TG)")
    args = parser.parse_args()

    if args.mock:
        asyncio.run(run_mock())
    else:
        asyncio.run(run_live())


if __name__ == "__main__":
    main()
