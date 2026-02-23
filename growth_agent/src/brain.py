"""Brain — LLM decision engine (OpenRouter).

For each relevant message decides:
  1. Should we respond? (yes/no + reason)
  2. What to write?
  3. Include channel link? (not more often than 1 in N responses)
"""

import json
from typing import Optional

import httpx
from loguru import logger

from . import config, db
from .models import Message, BrainDecision

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


async def _call_openrouter(messages: list[dict]) -> tuple[str, float]:
    """Call OpenRouter API. Returns (response_text, cost_usd)."""
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.OPENROUTER_MODEL,
        "messages": messages,
        "max_tokens": 300,
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{config.OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    text = data["choices"][0]["message"]["content"].strip()

    # Rough cost estimate from usage tokens (OpenRouter prices vary by model)
    usage = data.get("usage", {})
    total_tokens = usage.get("total_tokens", 0)
    cost = total_tokens * 0.000003  # ~$3 per 1M tokens (Sonnet estimate)

    return text, cost


async def _should_include_link(chat_id: int) -> bool:
    """Return True if we should include channel link in this response."""
    links_in_last_n = await db.count_responses_for_link_ratio(
        chat_id, last_n=config.CHANNEL_LINK_EVERY_N_RESPONSES
    )
    return links_in_last_n == 0


async def think(message: Message) -> BrainDecision:
    """Main decision function. Returns BrainDecision."""
    if not config.OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY not set — skipping Brain")
        return BrainDecision(should_respond=False, reason="no_api_key")

    prompt_text = DECISION_PROMPT.format(text=message.text)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt_text},
    ]

    try:
        raw, cost = await _call_openrouter(messages)
    except Exception as e:
        logger.error("OpenRouter call failed: {}", e)
        return BrainDecision(should_respond=False, reason=f"llm_error:{e}")

    # Parse JSON response
    try:
        # Strip markdown code fences if model wraps in ```json
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
            llm_cost=cost,
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
        llm_cost=cost,
    )
