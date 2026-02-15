"""Compose Telegram posts from analyzed products.

Brand style: ALGORA — AI-аналитик китайского рынка.
Tone: эксперт + партнёр. Уверенный, конкретный, без воды.
Говорим цифрами, фактами, выгодой. Не говорим мотивацией.

Post types:
- compose_post()              — "Находка дня" (single product)
- compose_niche_review()      — "Обзор ниши" (category overview with top products)
- compose_weekly_top()        — "Топ недели" (best products across all categories)
- compose_beginner_mistake()  — "Ошибка новичка" (educational: common mistake + how to avoid)
- compose_product_of_week()   — "Товар недели" (deep dive into one best product)
"""

from __future__ import annotations

import re

from src.config import PREMIUM_ENABLED, TELEGRAM_PREMIUM_CHANNEL_ID
from src.models import AnalyzedProduct, TelegramPost

# Russian category names for display
CATEGORY_NAMES: dict[str, str] = {
    "electronics": "Электроника",
    "gadgets": "Гаджеты",
    "home": "Дом и быт",
    "phone_accessories": "Аксессуары для телефона",
    "car_accessories": "Автотовары",
    "led_lighting": "LED-освещение",
    "beauty_devices": "Красота и уход",
    "smart_home": "Умный дом",
    "outdoor": "Отдых и туризм",
    "toys": "Игрушки",
    "health": "Здоровье",
    "kitchen": "Кухня",
    "pet": "Товары для питомцев",
    "sport": "Спорт",
    "office": "Офис",
    "kids": "Детские товары",
    "bags": "Сумки и рюкзаки",
    "jewelry": "Украшения",
    "tools": "Инструменты",
    "stationery": "Канцелярия",
}

# Hashtags per category
CATEGORY_TAGS: dict[str, str] = {
    "electronics": "#электроника",
    "gadgets": "#гаджеты",
    "home": "#дом",
    "phone_accessories": "#аксессуары",
    "car_accessories": "#авто",
    "led_lighting": "#освещение",
    "beauty_devices": "#красота",
    "smart_home": "#умныйдом",
    "outdoor": "#туризм",
    "toys": "#игрушки",
    "health": "#здоровье",
    "kitchen": "#кухня",
    "pet": "#питомцы",
    "sport": "#спорт",
    "office": "#офис",
    "kids": "#дети",
    "bags": "#сумки",
    "jewelry": "#украшения",
    "tools": "#инструменты",
    "stationery": "#канцелярия",
}

# Brand separator for consistent header style
_BRAND_SEP = "▸"
_SECTION_LINE = "─ ─ ─ ─ ─ ─ ─ ─ ─ ─"


def _premium_cta() -> str:
    """Return CTA footer for free channel posts when premium is enabled."""
    if not PREMIUM_ENABLED or not TELEGRAM_PREMIUM_CHANNEL_ID:
        return ""
    channel = TELEGRAM_PREMIUM_CHANNEL_ID.lstrip("@")
    return f"\n\n🔒 Лучшие находки — в Algora PRO: @{channel}"


def _trend_emoji(score: float) -> str:
    if score >= 8:
        return "🔥"
    if score >= 5:
        return "📈"
    return "→"


def _margin_emoji(pct: float) -> str:
    if pct >= 40:
        return "✅"
    if pct >= 20:
        return "▲"
    if pct > 0:
        return "⚠️"
    return "✕"


def _score_bar(score: float) -> str:
    """Visual score bar: ████░░░░░░ 4/10."""
    filled = round(score)
    return "█" * filled + "░" * (10 - filled)


def _clean_insight(text: str) -> str:
    """Strip markdown artifacts from AI insight."""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"^[Ии]нсайт\s*:\s*", "", text)
    return text.strip()


def _is_valid_insight(text: str | None) -> bool:
    """Check that ai_insight is a real insight, not an error or empty.

    Error messages must NEVER appear in published posts.
    """
    if not text or not text.strip():
        return False
    _ERROR_MARKERS = [
        "недоступен", "Error", "error", "API ключ", "authentication",
        "401", "403", "500", "timeout", "Traceback",
    ]
    return not any(marker in text for marker in _ERROR_MARKERS)


def _brand_footer(cat_tag: str) -> str:
    """Consistent brand footer for all post types."""
    return f"{cat_tag} #китай #1688 #wb #ozon #algora"


# ---------------------------------------------------------------------------
# Post type 1: "Находка дня" — single product spotlight
# ---------------------------------------------------------------------------


def _compose_compact(product: AnalyzedProduct) -> str:
    """Compact post text that fits within Telegram's 1024-char photo caption limit."""
    p = product
    r = product.raw
    title = (r.title_ru or r.title_cn)[:50]
    margin_icon = _margin_emoji(p.margin_pct)
    cat_name = CATEGORY_NAMES.get(r.category, r.category)

    lines = [
        f"<b>ALGORA {_BRAND_SEP} Находка дня</b>",
        "",
        f"<b>{title}</b>",
        f"{cat_name}",
        "",
        f"Закупка: ¥{r.price_cny:.0f} (~{p.price_rub:.0f}₽)",
        f"Себестоимость в РФ: ~{p.total_landed_cost:.0f}₽",
    ]

    if p.wb_competitors > 0:
        lines.append(f"WB: {p.wb_competitors} продавцов · ~{p.wb_avg_price:.0f}₽")

    lines.append(f"Маржа: {p.margin_pct:.0f}% {margin_icon} · {_score_bar(p.total_score)} {p.total_score:.1f}/10")

    if _is_valid_insight(p.ai_insight):
        insight = _clean_insight(p.ai_insight)[:120]
        lines.append(f"\n{insight}")

    if r.source_url:
        lines.append(f'\n<a href="{r.source_url}">Смотреть на фабрике →</a>')

    return "\n".join(lines)


def compose_post(product: AnalyzedProduct) -> TelegramPost:
    """Build a Telegram post from an analyzed product.

    If image_url is available and text fits 1024 chars, uses compact format
    for sendPhoto. Otherwise uses full format for sendMessage.
    """
    p = product
    r = product.raw

    # Try compact format first if there's an image
    if r.image_url:
        compact = _compose_compact(product) + _premium_cta()
        if len(compact) <= 1024:
            return TelegramPost(product=product, text=compact, image_url=r.image_url)

    # Full format (when compact doesn't fit 1024 chars)
    # Keep image_url — publish layer will handle photo+text split
    title = r.title_ru or r.title_cn
    trend_icon = _trend_emoji(p.trend_score)
    margin_icon = _margin_emoji(p.margin_pct)
    cat_name = CATEGORY_NAMES.get(r.category, r.category)
    cat_tag = CATEGORY_TAGS.get(r.category, f"#{r.category}")

    lines = [
        f"<b>ALGORA {_BRAND_SEP} Находка дня</b>",
        "",
        f"<b>{title}</b>",
    ]

    if r.category:
        lines.append(f"{cat_name}")

    lines.append("")
    lines.append(_SECTION_LINE)
    lines.append("")

    # --- Экономика ---
    lines.append("<b>Экономика:</b>")
    lines.append(f"FOB Китай: ¥{r.price_cny:.0f} (~{p.price_rub:.0f}₽)")

    delivery_customs = p.delivery_cost_est + p.customs_duty_est
    if delivery_customs > 0:
        lines.append(f"Доставка + таможня: ~{delivery_customs:.0f}₽")

    lines.append(f"Себестоимость в РФ: ~{p.total_landed_cost:.0f}₽")

    if p.wb_avg_price > 0:
        lines.append(f"Цена на WB: ~{p.wb_avg_price:.0f}₽")

    margin_line = f"<b>Чистая маржа: ~{p.margin_pct:.0f}%"
    if p.margin_rub != 0:
        margin_line += f" ({p.margin_rub:.0f}₽/шт)"
    margin_line += f"</b> {margin_icon}"
    lines.append(margin_line)

    if r.min_order > 1:
        invest = r.min_order * p.total_landed_cost
        lines.append(f"Мин. вход: {r.min_order} шт × {p.total_landed_cost:.0f}₽ = {invest:,.0f}₽")

    lines.append("")

    # --- Рынок ---
    lines.append("<b>Рынок:</b>")

    if r.sales_volume > 0:
        lines.append(f"Продажи в Китае: {r.sales_volume:,} шт/мес {trend_icon}")

    if p.wb_competitors > 0:
        lines.append(f"Конкуренция на WB: {p.wb_competitors} продавцов")

    lines.append(f"Рейтинг: {_score_bar(p.total_score)} {p.total_score:.1f}/10")

    # --- Поставщик ---
    if r.supplier_name:
        lines.append("")
        supplier_info = f"<b>Поставщик:</b> {r.supplier_name}"
        if r.supplier_years > 0:
            supplier_info += f" ({r.supplier_years} лет)"
        lines.append(supplier_info)

    lines.append("")
    lines.append(_SECTION_LINE)
    lines.append("")

    # --- AI insight ---
    if _is_valid_insight(p.ai_insight):
        insight = _clean_insight(p.ai_insight)
        lines.append(f"💡 {insight}")
        lines.append("")

    if r.source_url:
        lines.append(f'<a href="{r.source_url}">Смотреть на фабрике →</a>')
        lines.append("")

    lines.append("Сохрани — пригодится при выборе ниши")
    lines.append("")
    lines.append(_brand_footer(cat_tag))

    text = "\n".join(lines) + _premium_cta()
    return TelegramPost(product=product, text=text, image_url=r.image_url)


# ---------------------------------------------------------------------------
# Post type 2: "Обзор ниши" — category overview
# ---------------------------------------------------------------------------


def compose_niche_review(
    category: str,
    products: list[AnalyzedProduct],
    ai_summary: str = "",
) -> str:
    """Build a niche review post for a category.

    Returns raw text (not TelegramPost) since it's not tied to one product.
    """
    cat_name = CATEGORY_NAMES.get(category, category)
    cat_tag = CATEGORY_TAGS.get(category, f"#{category}")

    # Aggregate stats
    avg_margin = sum(p.margin_pct for p in products) / len(products) if products else 0
    avg_score = sum(p.total_score for p in products) / len(products) if products else 0
    total_sales = sum(p.raw.sales_volume for p in products)
    avg_competitors = (
        sum(p.wb_competitors for p in products) / len(products) if products else 0
    )

    lines = [
        f"<b>ALGORA {_BRAND_SEP} Обзор ниши: {cat_name}</b>",
        "",
        f"Проанализировано: {len(products)} товаров",
        "",
        _SECTION_LINE,
        "",
        f"<b>Ключевые метрики:</b>",
        f"Средняя маржа: ~{avg_margin:.0f}% {_margin_emoji(avg_margin)}",
        f"Средний рейтинг: {avg_score:.1f}/10",
        f"Продажи в Китае: {total_sales:,} шт/мес",
        f"Конкуренция на WB: ~{avg_competitors:.0f} продавцов",
    ]

    # Top 3 products
    top = sorted(products, key=lambda p: p.total_score, reverse=True)[:3]
    if top:
        lines.append("")
        lines.append(f"<b>Топ-3 товара:</b>")
        for i, p in enumerate(top, 1):
            title = (p.raw.title_ru or p.raw.title_cn)[:45]
            lines.append(
                f"{i}. {title}\n"
                f"   Маржа: {p.margin_pct:.0f}% · {_score_bar(p.total_score)} {p.total_score:.1f}"
            )

    if _is_valid_insight(ai_summary):
        summary = _clean_insight(ai_summary)
        lines.append("")
        lines.append(f"💡 {summary}")

    lines.append("")
    lines.append(_brand_footer(cat_tag))

    return "\n".join(lines) + _premium_cta()


# ---------------------------------------------------------------------------
# Post type 3: "Топ недели" — best products across all categories
# ---------------------------------------------------------------------------


def compose_weekly_top(products: list[AnalyzedProduct]) -> str:
    """Build a weekly top products post.

    Returns raw text. Takes already-sorted top products.
    """
    lines = [
        f"<b>ALGORA {_BRAND_SEP} Топ недели</b>",
        "",
        "Лучшие находки за неделю по рейтингу и марже:",
        "",
        _SECTION_LINE,
        "",
    ]

    for i, p in enumerate(products[:5], 1):
        title = (p.raw.title_ru or p.raw.title_cn)[:40]
        cat_name = CATEGORY_NAMES.get(p.raw.category, p.raw.category)
        margin_icon = _margin_emoji(p.margin_pct)

        lines.append(
            f"<b>{i}. {title}</b>\n"
            f"   {cat_name} · Маржа: {p.margin_pct:.0f}% {margin_icon} · "
            f"{_score_bar(p.total_score)} {p.total_score:.1f}/10"
        )
        lines.append("")

    lines.append("Подробный расчёт по каждому — в постах выше")
    lines.append("")
    lines.append("#топнедели #китай #1688 #wb #ozon #algora")

    return "\n".join(lines) + _premium_cta()


# ---------------------------------------------------------------------------
# Post type 4: "Ошибка новичка" — educational content about common mistakes
# ---------------------------------------------------------------------------


def compose_beginner_mistake(product: AnalyzedProduct, mistake_text: str) -> str:
    """Build a 'beginner mistake' educational post based on a real product.

    Uses AI-generated mistake_text that explains what could go wrong
    and how to avoid it.
    Returns raw text.
    """
    p = product
    r = product.raw
    title = (r.title_ru or r.title_cn)[:50]
    cat_name = CATEGORY_NAMES.get(r.category, r.category)
    cat_tag = CATEGORY_TAGS.get(r.category, f"#{r.category}")

    lines = [
        f"<b>ALGORA {_BRAND_SEP} Ошибка новичка</b>",
        "",
        f"Разбираем на примере: <b>{title}</b>",
        f"{cat_name}",
        "",
        _SECTION_LINE,
        "",
        f"Закупка: ¥{r.price_cny:.0f} (~{p.price_rub:.0f}₽) → В РФ: ~{p.total_landed_cost:.0f}₽",
    ]

    if p.wb_avg_price > 0:
        lines.append(f"WB: ~{p.wb_avg_price:.0f}₽ · {p.wb_competitors} продавцов")

    lines.append(f"Маржа: ~{p.margin_pct:.0f}% {_margin_emoji(p.margin_pct)}")
    lines.append("")

    # AI-generated mistake analysis
    if _is_valid_insight(mistake_text):
        mistake = _clean_insight(mistake_text)
        lines.append(mistake)
        lines.append("")

    lines.append("Сталкивались? Делитесь опытом в комментариях")
    lines.append("")
    lines.append(f"{cat_tag} #ошибкановичка #китай #1688 #wb #ozon #algora")

    return "\n".join(lines) + _premium_cta()


# ---------------------------------------------------------------------------
# Post type 5: "Товар недели" — deep-dive into one best product
# ---------------------------------------------------------------------------


def compose_product_of_week(product: AnalyzedProduct, deep_analysis: str) -> str:
    """Build a detailed 'product of the week' post.

    Takes the best product and an AI-generated deep analysis.
    Returns raw text.
    """
    p = product
    r = product.raw
    title = r.title_ru or r.title_cn
    cat_name = CATEGORY_NAMES.get(r.category, r.category)
    cat_tag = CATEGORY_TAGS.get(r.category, f"#{r.category}")

    lines = [
        f"<b>ALGORA {_BRAND_SEP} Товар недели</b>",
        "",
        f"<b>{title}</b>",
        f"{cat_name}",
        "",
        _SECTION_LINE,
        "",
        "<b>Экономика:</b>",
        f"FOB Китай: ¥{r.price_cny:.0f} (~{p.price_rub:.0f}₽)",
        f"Доставка + таможня: ~{p.delivery_cost_est + p.customs_duty_est:.0f}₽",
        f"Себестоимость в РФ: ~{p.total_landed_cost:.0f}₽",
        f"Цена на WB: ~{p.wb_avg_price:.0f}₽",
        f"<b>Чистая маржа: ~{p.margin_pct:.0f}% ({p.margin_rub:.0f}₽/шт)</b> {_margin_emoji(p.margin_pct)}",
    ]

    if r.min_order > 1:
        invest = r.min_order * p.total_landed_cost
        lines.append(f"Мин. вход: {r.min_order} шт × {p.total_landed_cost:.0f}₽ = {invest:,.0f}₽")

    lines.append("")
    lines.append("<b>Рынок:</b>")

    if r.sales_volume > 0:
        lines.append(f"Продажи в Китае: {r.sales_volume:,} шт/мес {_trend_emoji(p.trend_score)}")

    lines.append(f"Конкуренция на WB: {p.wb_competitors} продавцов")
    lines.append(f"Рейтинг AI: {_score_bar(p.total_score)} {p.total_score:.1f}/10")

    if r.supplier_name:
        lines.append("")
        supplier_info = f"<b>Поставщик:</b> {r.supplier_name}"
        if r.supplier_years > 0:
            supplier_info += f" ({r.supplier_years} лет)"
        lines.append(supplier_info)

    lines.append("")
    lines.append(_SECTION_LINE)
    lines.append("")

    # AI deep analysis
    if _is_valid_insight(deep_analysis):
        analysis = _clean_insight(deep_analysis)
        lines.append(f"<b>Экспертный разбор:</b>")
        lines.append(analysis)

    if r.source_url:
        lines.append("")
        lines.append(f'<a href="{r.source_url}">Смотреть на фабрике →</a>')

    lines.append("")
    lines.append("Сохраняй — пригодится при выборе ниши")
    lines.append("")
    lines.append(f"{cat_tag} #товарнедели #китай #1688 #wb #ozon #algora")

    return "\n".join(lines) + _premium_cta()
