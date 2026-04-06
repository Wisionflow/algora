"""Brain — LLM decision engine (via Claude API).

For each relevant message decides:
  1. Should we respond? (yes/no + reason)
  2. What to write? (NO channel links in chat — links get deleted by admins)
  3. After chat response — generate follow-up DM with channel link
"""

import json
import re
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


# Prompts loaded once at import time.
SYSTEM_PROMPT = _load_prompt("system_prompt.txt")
DECISION_PROMPT = _load_prompt("decision_prompt.txt")
DM_SYSTEM_PROMPT = _load_prompt("dm_system_prompt.txt")
DM_RESPONSE_PROMPT = _load_prompt("dm_response_prompt.txt")
FOLLOWUP_DM_PROMPT = _load_prompt("followup_dm_prompt.txt")


async def _call_llm(messages: list[dict], system: str = "") -> str:
    """Call Claude API directly."""
    if _client is None:
        raise RuntimeError("Claude client not initialized. Call brain.init_client() first.")

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


_JSON_BLOCK_RE = re.compile(r'```(?:json)?\s*(\{.*?\})\s*```', re.DOTALL)


def _parse_json_response(raw: str) -> dict:
    """Extract JSON from LLM response, handling ```json blocks and trailing commentary."""
    stripped = raw.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    m = _JSON_BLOCK_RE.search(stripped)
    if m:
        return json.loads(m.group(1))

    start = stripped.find('{')
    end = stripped.rfind('}')
    if start != -1 and end > start:
        return json.loads(stripped[start:end + 1])

    raise ValueError("No JSON found in response")


async def think(message: Message) -> BrainDecision:
    """Main decision function for chat messages. NEVER includes channel link."""
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

    prompt_text = DECISION_PROMPT.format(
        text=message.text,
        sender=message.sender_name,
        context=context_str,
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

    try:
        data = _parse_json_response(raw)
    except (json.JSONDecodeError, ValueError):
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

    # Safety: strip any accidental channel link from chat response
    if config.CHANNEL_LINK in response_text:
        response_text = response_text.replace(config.CHANNEL_LINK, "").strip()

    logger.info(
        "Brain decision: respond=True reason={} | {}",
        reason, response_text[:80]
    )

    return BrainDecision(
        should_respond=True,
        reason=reason,
        response_text=response_text,
        include_channel_link=False,  # NEVER in chat
        llm_model=config.CLAUDE_MODEL,
    )


async def think_followup_dm(question: str, chat_response: str) -> Optional[str]:
    """Generate a follow-up DM to send after answering in chat.

    Returns DM text with channel link, or None if generation fails.
    """
    if _client is None:
        return None

    prompt_text = FOLLOWUP_DM_PROMPT.format(
        question=question,
        chat_response=chat_response,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt_text},
    ]

    try:
        raw = await _call_llm(messages)
    except Exception as e:
        logger.error("Follow-up DM LLM failed: {}", e)
        return None

    try:
        data = _parse_json_response(raw)
        dm_text = data.get("dm_text") or None
    except (json.JSONDecodeError, ValueError):
        logger.warning("Follow-up DM non-JSON: {}", raw[:200])
        return None

    if not dm_text:
        return None

    # Ensure channel link is present
    if config.CHANNEL_LINK not in dm_text:
        dm_text = f"{dm_text}\n\n{config.CHANNEL_LINK}"

    logger.info("Follow-up DM generated: {}", dm_text[:80])
    return dm_text


async def think_dm(sender_name: str, text: str) -> tuple[Optional[str], str]:
    """Decide how to reply to an incoming private message.

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
        data = _parse_json_response(raw)
        response_text = data.get("response") or None
        dm_type = data.get("dm_type", "unknown")
    except (json.JSONDecodeError, ValueError):
        logger.warning("DM Brain returned non-JSON: {}", raw[:200])
        return None, "unknown"

    logger.info("DM type={} for {} | response: {}", dm_type, sender_name,
                (response_text or "none")[:80])
    return response_text, dm_type
