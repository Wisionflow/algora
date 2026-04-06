"""Brain — LLM decision engine (via Claude API).

For each relevant message decides:
  1. Should we respond? (yes/no + reason)
  2. What to write?
  3. Include channel link? (not more often than 1 in N responses)
"""

import json
import asyncio
from pathlib import Path
from typing import Optional

from anthropic import AsyncAnthropic
from loguru import logger

from . import config, db
from .models import Message, BrainDecision

_client: Optional[AsyncAnthropic] = None

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    """Load prompt from prompts/ directory and substitute {AGENT_NAME} / {CHANNEL_LINK}."""
    path = _PROMPTS_DIR / filename
    text = path.read_text(encoding="utf-8")
    return text.replace("{AGENT_NAME}", config.AGENT_NAME).replace("{CHANNEL_LINK}", config.CHANNEL_LINK)


def init_client() -> None:
    """Initialize the Claude API client."""
    global _client
    _client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)


# Prompts are loaded once at import time from prompts/ directory.
# Edit the .txt files to customise agent behaviour — no code changes needed.
SYSTEM_PROMPT = _load_prompt("system_prompt.txt")
DECISION_PROMPT = _load_prompt("decision_prompt.txt")
DM_SYSTEM_PROMPT = _load_prompt("dm_system_prompt.txt")
DM_RESPONSE_PROMPT = _load_prompt("dm_response_prompt.txt")


async def _call_llm(messages: list[dict], system: str = "") -> str:
    """Call Claude API directly."""
    if _client is None:
        raise RuntimeError("Claude client not initialized. Call brain.init_client() first.")

    # Claude API uses system as separate param, user/assistant in messages
    user_messages = [m for m in messages if m["role"] != "system"]

    response = await _client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=250,
        temperature=0.4,
        system=system or next((m["content"] for m in messages if m["role"] == "system"), ""),
        messages=user_messages,
    )
    text = response.content[0].text
    logger.debug("Claude response: model={} tokens={}", config.CLAUDE_MODEL, response.usage.output_tokens)
    return text


async def _should_include_link(chat_id: int) -> bool:
    """Return True if we should include channel link in this response."""
    links_in_last_n = await db.count_responses_for_link_ratio(
        chat_id, last_n=config.CHANNEL_LINK_EVERY_N_RESPONSES
    )
    return links_in_last_n == 0


async def think(message: Message) -> BrainDecision:
    """Main decision function. Returns BrainDecision."""
    if _client is None:
        logger.warning("Claude client not initialized — skipping Brain")
        return BrainDecision(should_respond=False, reason="no_client")

    # Build context from recent messages
    recent = await db.get_recent_messages(
        chat_id=message.chat_id, limit=5, before_id=message.id or 0
    )
    context_lines = []
    for m in recent:
        short_text = m["text"][:150]
        context_lines.append(f"{m['sender_name']}: {short_text}")
    context_str = "\n".join(context_lines) if context_lines else "(нет предыдущих сообщений)"

    # Decide whether to include channel link BEFORE LLM call
    include_link = await _should_include_link(message.chat_id)
    if include_link:
        link_instruction = (
            f"ВАЖНО: В этом ответе ОБЯЗАТЕЛЬНО упомяни канал {config.CHANNEL_LINK} — "
            "но ОРГАНИЧНО, через тему вопроса. Варианты:\n"
            f"- \"я это разбирал в {config.CHANNEL_LINK} с цифрами\"\n"
            f"- \"в {config.CHANNEL_LINK} у меня пост про [тема], глянь\"\n"
            f"- \"подпишись на {config.CHANNEL_LINK}, там как раз про это\"\n"
            "Выбери подходящий вариант или придумай свой. НЕ используй \"писал про это кст\"."
        )
    else:
        link_instruction = "В этом ответе НЕ упоминай канал."

    prompt_text = DECISION_PROMPT.format(
        text=message.text,
        sender=message.sender_name,
        context=context_str,
        link_instruction=link_instruction,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt_text},
    ]

    try:
        raw = await _call_llm(messages)
    except Exception as e:
        logger.error("Claude call failed: {}", e)
        return BrainDecision(should_respond=False, reason=f"llm_error:{e}")

    # Parse JSON response
    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(clean)
    except json.JSONDecodeError:
        logger.warning("Brain returned non-JSON: {}", raw[:200])
        return BrainDecision(should_respond=False, reason="parse_error")

    should_respond = bool(data.get("should_respond", False))
    reason = str(data.get("reason", ""))
    response_text: Optional[str] = data.get("response") or None

    if not should_respond or not response_text:
        return BrainDecision(
            should_respond=False,
            reason=reason,
            llm_model=config.CLAUDE_MODEL,
        )

    # Verify link was actually included if requested
    if include_link and config.CHANNEL_LINK not in response_text:
        response_text = f"{response_text}\n\n{config.CHANNEL_LINK} — там подробнее разбирал"

    logger.info(
        "Brain decision: respond={} link={} reason={} | {}",
        should_respond, include_link, reason, response_text[:80]
    )

    return BrainDecision(
        should_respond=True,
        reason=reason,
        response_text=response_text,
        include_channel_link=include_link,
        llm_model=config.CLAUDE_MODEL,
    )


async def think_dm(sender_name: str, text: str) -> tuple[Optional[str], str]:
    """Decide how to reply to a private message.

    Returns (response_text, dm_type).
    dm_type is one of: service_offer, question, collaboration, spam, unknown.
    """
    if _client is None:
        logger.warning("Claude client not initialized — skipping DM Brain")
        return None, "unknown"

    prompt_text = DM_RESPONSE_PROMPT.format(text=text)
    messages = [
        {"role": "system", "content": DM_SYSTEM_PROMPT},
        {"role": "user", "content": prompt_text},
    ]

    try:
        raw = await _call_llm(messages)
    except Exception as e:
        logger.error("DM Claude call failed: {}", e)
        return None, "unknown"

    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(clean)
        response_text = data.get("response") or None
        dm_type = data.get("dm_type", "unknown")
    except json.JSONDecodeError:
        logger.warning("DM Brain returned non-JSON: {}", raw[:200])
        return None, "unknown"

    logger.info("DM type={} for {} | response: {}", dm_type, sender_name,
                (response_text or "none")[:80])
    return response_text, dm_type
