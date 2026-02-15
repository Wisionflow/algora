"""AI-powered analysis using Claude API.

Takes the top scored products and generates actionable insights.
"""

from __future__ import annotations

import anthropic
from loguru import logger

from src.config import ANTHROPIC_API_KEY
from src.models import AnalyzedProduct

SYSTEM_PROMPT = """Ты — аналитик трендов товаров из Китая для российских селлеров маркетплейсов (Wildberries, Ozon).
Твоя задача — дать краткий, конкретный инсайт по товару.

Правила:
- Пиши на русском языке
- Максимум 2 предложения, не больше 200 символов
- Только факты и конкретные рекомендации
- Никакой воды, общих фраз и мотивации
- НЕ используй Markdown (звёздочки, жирный текст и т.д.) — пиши чистым текстом
- НЕ начинай с "Инсайт:" — сразу по делу
- Укажи: для кого товар + главный риск или преимущество
- Если маржа отрицательная — честно скажи об этом"""


def _build_product_prompt(product: AnalyzedProduct) -> str:
    return f"""Проанализируй этот товар для российского селлера маркетплейсов:

Товар: {product.raw.title_ru} ({product.raw.title_cn})
Категория: {product.raw.category}
Цена FOB (Китай): ¥{product.raw.price_cny} (~{product.price_rub}₽)
Мин. заказ: {product.raw.min_order} шт
Объём продаж в Китае: {product.raw.sales_volume} шт/мес
Себестоимость в РФ (ориентир): ~{product.total_landed_cost}₽/шт
Средняя цена на WB: {product.wb_avg_price}₽
Конкурентов на WB: {product.wb_competitors}
Расчётная маржа: {product.margin_pct}%
Поставщик: {product.raw.supplier_name}, {product.raw.supplier_years} лет на площадке

Скоринг: тренд={product.trend_score}, конкуренция={product.competition_score}, маржа={product.margin_score}, надёжность={product.reliability_score}

Дай краткий инсайт (2-3 предложения): почему интересен, для кого, какие риски."""


async def generate_insight(product: AnalyzedProduct) -> str:
    """Generate AI insight for a product using Claude.

    Returns empty string on any failure — errors must NEVER leak into posts.
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set, skipping AI analysis")
        return ""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_product_prompt(product)}],
        )
        insight = message.content[0].text.strip()
        logger.debug("AI insight generated: {}...", insight[:80])
        return insight
    except Exception as e:
        logger.error("Claude API error: {}", e)
        return ""
