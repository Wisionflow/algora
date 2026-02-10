"""Compose Telegram posts from analyzed products.

Post types:
- compose_post()         — "Находка дня" (single product)
- compose_niche_review() — "Обзор ниши" (category overview with top products)
- compose_weekly_top()   — "Топ недели" (best products across all categories)
"""

from __future__ import annotations

import re

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
}


def _trend_emoji(score: float) -> str:
    if score >= 8:
        return "🔥"
    if score >= 5:
        return "📈"
    return "➡️"


def _margin_emoji(pct: float) -> str:
    if pct >= 40:
        return "💰"
    if pct >= 20:
        return "✅"
    if pct > 0:
        return "⚠️"
    return "🚫"


def _score_bar(score: float) -> str:
    """Visual score bar: ████░░░░░░ 4/10."""
    filled = round(score)
    return "█" * filled + "░" * (10 - filled)


def _clean_insight(text: str) -> str:
    """Strip markdown artifacts from AI insight."""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"^[Ии]нсайт\s*:\s*", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Post type 1: "Находка дня" — single product spotlight
# ---------------------------------------------------------------------------


def compose_post(product: AnalyzedProduct) -> TelegramPost:
    """Build a Telegram post from an analyzed product."""
    p = product
    r = product.raw

    title = r.title_ru or r.title_cn
    trend_icon = _trend_emoji(p.trend_score)
    margin_icon = _margin_emoji(p.margin_pct)
    cat_name = CATEGORY_NAMES.get(r.category, r.category)
    cat_tag = CATEGORY_TAGS.get(r.category, f"#{r.category}")

    lines = [
        f"🔍 <b>ALGORA | Находка дня</b>",
        "",
        f"📦 <b>{title}</b>",
    ]

    if r.category:
        lines.append(f"📂 {cat_name}")

    lines.append("")

    price_line = f"💰 FOB: ¥{r.price_cny:.0f} (~{p.price_rub:.0f}₽)"
    if r.min_order > 1:
        price_line += f" | от {r.min_order} шт"
    lines.append(price_line)
    lines.append(f"🚚 В РФ: ~{p.total_landed_cost:.0f}₽/шт")

    lines.append("")
    lines.append("📊 <b>Аналитика:</b>")

    if r.sales_volume > 0:
        lines.append(f"• Продажи CN: {r.sales_volume:,} шт/мес {trend_icon}")

    if p.wb_competitors > 0:
        lines.append(
            f"• WB: {p.wb_competitors} конкурентов, ~{p.wb_avg_price:.0f}₽"
        )

    if p.margin_pct != 0:
        lines.append(f"• Маржа: ~{p.margin_pct:.0f}% {margin_icon}")

    lines.append(f"• Рейтинг: {_score_bar(p.total_score)} {p.total_score:.1f}/10")

    if p.ai_insight:
        insight = _clean_insight(p.ai_insight)
        lines.append("")
        lines.append(f"💡 {insight}")

    if r.supplier_name:
        lines.append("")
        supplier_info = f"🏭 {r.supplier_name}"
        if r.supplier_years > 0:
            supplier_info += f" ({r.supplier_years} лет)"
        lines.append(supplier_info)

    if r.source_url:
        lines.append(f'🔗 <a href="{r.source_url}">Смотреть на фабрике</a>')

    lines.append("")
    lines.append(f"{cat_tag} #китай #маркетплейс #wb #ozon")

    text = "\n".join(lines)
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
        f"📊 <b>ALGORA | Обзор ниши: {cat_name}</b>",
        "",
        f"Проанализировано товаров: {len(products)}",
        "",
        f"📈 <b>Ключевые метрики:</b>",
        f"• Средняя маржа: ~{avg_margin:.0f}% {_margin_emoji(avg_margin)}",
        f"• Средний рейтинг: {avg_score:.1f}/10",
        f"• Суммарные продажи CN: {total_sales:,} шт/мес",
        f"• Среднее конкурентов на WB: ~{avg_competitors:.0f}",
    ]

    # Top 3 products
    top = sorted(products, key=lambda p: p.total_score, reverse=True)[:3]
    if top:
        lines.append("")
        lines.append("🏆 <b>Топ-3 товара:</b>")
        for i, p in enumerate(top, 1):
            title = (p.raw.title_ru or p.raw.title_cn)[:45]
            lines.append(
                f"{i}. {title}\n"
                f"   Маржа: {p.margin_pct:.0f}% | {_score_bar(p.total_score)} {p.total_score:.1f}"
            )

    if ai_summary:
        summary = _clean_insight(ai_summary)
        lines.append("")
        lines.append(f"💡 {summary}")

    lines.append("")
    lines.append(f"{cat_tag} #обзорниши #китай #маркетплейс #wb #ozon")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post type 3: "Топ недели" — best products across all categories
# ---------------------------------------------------------------------------


def compose_weekly_top(products: list[AnalyzedProduct]) -> str:
    """Build a weekly top products post.

    Returns raw text. Takes already-sorted top products.
    """
    lines = [
        "🏆 <b>ALGORA | Топ недели</b>",
        "",
        "Лучшие находки за неделю по рейтингу и марже:",
        "",
    ]

    for i, p in enumerate(products[:5], 1):
        title = (p.raw.title_ru or p.raw.title_cn)[:40]
        cat_name = CATEGORY_NAMES.get(p.raw.category, p.raw.category)
        margin_icon = _margin_emoji(p.margin_pct)

        lines.append(
            f"<b>{i}. {title}</b>\n"
            f"   {cat_name} | Маржа: {p.margin_pct:.0f}% {margin_icon} | "
            f"{_score_bar(p.total_score)} {p.total_score:.1f}/10"
        )
        lines.append("")

    lines.append("Подробный разбор каждого товара — в постах канала выше ☝️")
    lines.append("")
    lines.append("#топнедели #китай #маркетплейс #wb #ozon")

    return "\n".join(lines)
