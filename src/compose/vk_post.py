"""Compose VK wall posts from analyzed products.

VK doesn't support HTML formatting, so we use plain text with emoji/unicode.
All 5 post types mirror Telegram versions but adapted for VK.
"""

from __future__ import annotations

import re

from src.models import AnalyzedProduct
from src.compose.telegram_post import (
    CATEGORY_NAMES,
    CATEGORY_TAGS,
    _trend_emoji,
    _margin_emoji,
    _score_bar,
    _clean_insight,
)


def _strip_html(text: str) -> str:
    """Remove HTML tags, convert <a href> to plain links."""
    # Convert <a href="url">text</a> to text (url)
    text = re.sub(r'<a href="([^"]+)">([^<]+)</a>', r"\2: \1", text)
    # Remove remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    return text


# ---------------------------------------------------------------------------
# Post type 1: "Находка дня" — single product spotlight
# ---------------------------------------------------------------------------


def compose_vk_post(product: AnalyzedProduct) -> str:
    """Build a VK wall post from an analyzed product."""
    p = product
    r = product.raw

    title = r.title_ru or r.title_cn
    trend_icon = _trend_emoji(p.trend_score)
    margin_icon = _margin_emoji(p.margin_pct)
    cat_name = CATEGORY_NAMES.get(r.category, r.category)
    cat_tag = CATEGORY_TAGS.get(r.category, f"#{r.category}")

    lines = [
        "🔍 ALGORA | Находка дня",
        "",
        f"📦 {title}",
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
    lines.append("📊 Аналитика:")

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
        lines.append(f"🔗 Смотреть на фабрике: {r.source_url}")

    lines.append("")
    lines.append(f"{cat_tag} #китай #маркетплейс #wb #ozon")
    lines.append("")
    lines.append("👉 Больше находок в нашем Telegram: t.me/algora_trends")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post type 2: "Обзор ниши" — category overview
# ---------------------------------------------------------------------------


def compose_vk_niche_review(
    category: str,
    products: list[AnalyzedProduct],
    ai_summary: str = "",
) -> str:
    """Build a VK niche review post for a category."""
    cat_name = CATEGORY_NAMES.get(category, category)
    cat_tag = CATEGORY_TAGS.get(category, f"#{category}")

    avg_margin = sum(p.margin_pct for p in products) / len(products) if products else 0
    avg_score = sum(p.total_score for p in products) / len(products) if products else 0
    total_sales = sum(p.raw.sales_volume for p in products)
    avg_competitors = (
        sum(p.wb_competitors for p in products) / len(products) if products else 0
    )

    lines = [
        f"📊 ALGORA | Обзор ниши: {cat_name}",
        "",
        f"Проанализировано товаров: {len(products)}",
        "",
        "📈 Ключевые метрики:",
        f"• Средняя маржа: ~{avg_margin:.0f}% {_margin_emoji(avg_margin)}",
        f"• Средний рейтинг: {avg_score:.1f}/10",
        f"• Суммарные продажи CN: {total_sales:,} шт/мес",
        f"• Среднее конкурентов на WB: ~{avg_competitors:.0f}",
    ]

    top = sorted(products, key=lambda p: p.total_score, reverse=True)[:3]
    if top:
        lines.append("")
        lines.append("🏆 Топ-3 товара:")
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
    lines.append("")
    lines.append("👉 Подписывайтесь на Telegram: t.me/algora_trends")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post type 3: "Топ недели" — best products across all categories
# ---------------------------------------------------------------------------


def compose_vk_weekly_top(products: list[AnalyzedProduct]) -> str:
    """Build a VK weekly top products post."""
    lines = [
        "🏆 ALGORA | Топ недели",
        "",
        "Лучшие находки за неделю по рейтингу и марже:",
        "",
    ]

    for i, p in enumerate(products[:5], 1):
        title = (p.raw.title_ru or p.raw.title_cn)[:40]
        cat_name = CATEGORY_NAMES.get(p.raw.category, p.raw.category)
        margin_icon = _margin_emoji(p.margin_pct)

        lines.append(
            f"{i}. {title}\n"
            f"   {cat_name} | Маржа: {p.margin_pct:.0f}% {margin_icon} | "
            f"{_score_bar(p.total_score)} {p.total_score:.1f}/10"
        )
        lines.append("")

    lines.append("Подробный разбор каждого товара — в нашем Telegram-канале!")
    lines.append("")
    lines.append("#топнедели #китай #маркетплейс #wb #ozon")
    lines.append("")
    lines.append("👉 t.me/algora_trends")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post type 4: "Ошибка новичка" — educational content
# ---------------------------------------------------------------------------


def compose_vk_beginner_mistake(product: AnalyzedProduct, mistake_text: str) -> str:
    """Build a VK 'beginner mistake' educational post."""
    p = product
    r = product.raw
    title = (r.title_ru or r.title_cn)[:50]
    cat_name = CATEGORY_NAMES.get(r.category, r.category)
    cat_tag = CATEGORY_TAGS.get(r.category, f"#{r.category}")

    lines = [
        "⚠️ ALGORA | Ошибка новичка",
        "",
        f"Разбираем на примере: {title}",
        f"📂 {cat_name}",
        "",
        f"💰 FOB: ¥{r.price_cny:.0f} (~{p.price_rub:.0f}₽) → В РФ: ~{p.total_landed_cost:.0f}₽",
    ]

    if p.wb_avg_price > 0:
        lines.append(f"📊 WB: ~{p.wb_avg_price:.0f}₽ | {p.wb_competitors} конкурентов")

    lines.append(f"📈 Маржа: ~{p.margin_pct:.0f}% {_margin_emoji(p.margin_pct)}")
    lines.append("")

    mistake = _clean_insight(mistake_text)
    lines.append(mistake)

    lines.append("")
    lines.append("💬 Сталкивались с такой ситуацией? Пишите в комментариях!")
    lines.append("")
    lines.append(f"{cat_tag} #ошибкановичка #обучение #маркетплейс #wb #ozon")
    lines.append("")
    lines.append("👉 Ещё больше разборов: t.me/algora_trends")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post type 5: "Товар недели" — deep-dive product analysis
# ---------------------------------------------------------------------------


def compose_vk_product_of_week(product: AnalyzedProduct, deep_analysis: str) -> str:
    """Build a VK detailed 'product of the week' post."""
    p = product
    r = product.raw
    title = r.title_ru or r.title_cn
    cat_name = CATEGORY_NAMES.get(r.category, r.category)
    cat_tag = CATEGORY_TAGS.get(r.category, f"#{r.category}")

    lines = [
        "🏅 ALGORA | Товар недели",
        "",
        f"📦 {title}",
        f"📂 {cat_name}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "💰 Экономика:",
        f"• FOB Китай: ¥{r.price_cny:.0f} (~{p.price_rub:.0f}₽)",
        f"• Доставка + таможня: ~{p.delivery_cost_est + p.customs_duty_est:.0f}₽",
        f"• Себестоимость в РФ: ~{p.total_landed_cost:.0f}₽",
        f"• Цена на WB: ~{p.wb_avg_price:.0f}₽",
        f"• Чистая маржа: ~{p.margin_pct:.0f}% ({p.margin_rub:.0f}₽/шт) {_margin_emoji(p.margin_pct)}",
    ]

    if r.min_order > 1:
        invest = r.min_order * p.total_landed_cost
        lines.append(f"• Мин. вход: {r.min_order} шт × {p.total_landed_cost:.0f}₽ = {invest:,.0f}₽")

    lines.append("")
    lines.append("📊 Рынок:")

    if r.sales_volume > 0:
        lines.append(f"• Продажи в Китае: {r.sales_volume:,} шт/мес {_trend_emoji(p.trend_score)}")

    lines.append(f"• Конкуренция на WB: {p.wb_competitors} продавцов")
    lines.append(f"• Общий рейтинг: {_score_bar(p.total_score)} {p.total_score:.1f}/10")

    if r.supplier_name:
        lines.append("")
        supplier_info = f"🏭 Поставщик: {r.supplier_name}"
        if r.supplier_years > 0:
            supplier_info += f" ({r.supplier_years} лет)"
        lines.append(supplier_info)

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    analysis = _clean_insight(deep_analysis)
    lines.append("🧠 Экспертный разбор:")
    lines.append(analysis)

    if r.source_url:
        lines.append("")
        lines.append(f"🔗 Смотреть на фабрике: {r.source_url}")

    lines.append("")
    lines.append("🔔 Сохрани пост, чтобы не потерять находку!")
    lines.append("")
    lines.append(f"{cat_tag} #товарнедели #разбор #китай #маркетплейс #wb #ozon")
    lines.append("")
    lines.append("👉 Подписывайтесь на Telegram: t.me/algora_trends")

    return "\n".join(lines)
