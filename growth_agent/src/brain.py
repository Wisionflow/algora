"""Brain — LLM decision engine (via NATS AI Proxy).

For each relevant message decides:
  1. Should we respond? (yes/no + reason)
  2. What to write?
  3. Include channel link? (not more often than 1 in N responses)
"""

import json
import uuid
import asyncio
from typing import Optional

from loguru import logger

from . import config, db
from .models import Message, BrainDecision

# Global NATS connection (initialized by run_agent.py)
_nc = None


def init_nats(nc) -> None:
    """Set the NATS connection for LLM calls."""
    global _nc
    _nc = nc


SYSTEM_PROMPT = f"""Ты эксперт по импорту товаров из Китая для продажи на российских маркетплейсах (Wildberries, Ozon).
Тебя зовут {config.AGENT_NAME}. Ты участник чата.

Правила:
1. Отвечай ТОЛЬКО если можешь дать конкретную пользу (цифры, факты, опыт)
2. Не отвечай на оффтоп, политику, конфликты, шутки
3. Не рекламируй канал напрямую. Если спросят откуда знаешь — скажи "веду канал {config.CHANNEL_LINK}, там ежедневная аналитика"
4. Не отвечай чаще 3 раз в день в одном чате
5. Пиши коротко (2-5 предложений), по делу, с цифрами где возможно
6. Тон: профессиональный, уверенный, без эмодзи-спама"""

DECISION_PROMPT = """Ты получил сообщение из Telegram-чата.

Сообщение: "{text}"

Ответь строго в JSON:
{{
  "should_respond": true/false,
  "reason": "краткая причина",
  "response": "текст ответа (только если should_respond=true, иначе null)"
}}

Критерии для should_respond=true:
- Вопрос по теме импорта/маркетплейсов, на который есть конкретный полезный ответ
- Есть что добавить фактами или цифрами

Критерии для should_respond=false:
- Оффтоп, политика, шутки, флуд
- Вопрос слишком общий или личный
- Уже есть хороший ответ в чате"""


async def _call_llm(messages: list[dict]) -> str:
    """Call LLM via NATS AI Proxy using request-reply pattern."""
    if _nc is None:
        raise RuntimeError("NATS not initialized. Call brain.init_nats(nc) first.")

    request_id = str(uuid.uuid4())
    request = {
        "request_id": request_id,
        "agent": "cmo_growth",
        "model": config.OPENROUTER_MODEL,
        "messages": messages,
        "max_tokens": 300,
        "temperature": 0.7,
    }
    payload = json.dumps(request, ensure_ascii=False).encode()
    logger.debug("LLM request sending: id={}", request_id)

    # Use NATS request-reply (AI Proxy uses msg.respond())
    response = await _nc.request("algora.ai.request", payload, timeout=30)
    data = json.loads(response.data)
    logger.debug("LLM response received: id={} success={}", request_id, data.get("success"))

    if not data.get("success"):
        raise RuntimeError(f"AI Proxy error: {data.get('error')} - {data.get('message')}")

    return data["content"]


async def _should_include_link(chat_id: int) -> bool:
    """Return True if we should include channel link in this response."""
    links_in_last_n = await db.count_responses_for_link_ratio(
        chat_id, last_n=config.CHANNEL_LINK_EVERY_N_RESPONSES
    )
    return links_in_last_n == 0


async def think(message: Message) -> BrainDecision:
    """Main decision function. Returns BrainDecision."""
    if _nc is None:
        logger.warning("NATS not connected — skipping Brain")
        return BrainDecision(should_respond=False, reason="no_nats")

    prompt_text = DECISION_PROMPT.format(text=message.text)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt_text},
    ]

    try:
        raw = await _call_llm(messages)
    except Exception as e:
        ename = type(e).__name__
        if "timeout" in ename.lower() or isinstance(e, asyncio.TimeoutError):
            logger.error("LLM call timed out after 30s (no response from AI Proxy): {}", ename)
            return BrainDecision(should_respond=False, reason="llm_timeout")
        logger.error("LLM call failed: {} ({})", e, ename)
        return BrainDecision(should_respond=False, reason=f"llm_error:{ename}:{e}")

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
            llm_model=config.OPENROUTER_MODEL,
        )

    # Decide whether to append channel link
    include_link = await _should_include_link(message.chat_id)
    if include_link:
        response_text = f"{response_text}\n\nБольше аналитики — {config.CHANNEL_LINK}"

    logger.info(
        "Brain decision: respond={} link={} reason={} | {}",
        should_respond, include_link, reason, response_text[:80]
    )

    return BrainDecision(
        should_respond=True,
        reason=reason,
        response_text=response_text,
        include_channel_link=include_link,
        llm_model=config.OPENROUTER_MODEL,
    )
