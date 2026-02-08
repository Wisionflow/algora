"""Compose Telegram posts from analyzed products."""

from __future__ import annotations

from src.models import AnalyzedProduct, TelegramPost


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


def compose_post(product: AnalyzedProduct) -> TelegramPost:
    """Build a Telegram post from an analyzed product."""
    p = product
    r = product.raw

    title = r.title_ru or r.title_cn
    trend_icon = _trend_emoji(p.trend_score)
    margin_icon = _margin_emoji(p.margin_pct)

    lines = [
        f"🔍 <b>ALGORA | Находка дня</b>",
        "",
        f"📦 <b>{title}</b>",
    ]

    if r.category:
        lines.append(f"📂 Категория: {r.category}")

    lines.append("")
    lines.append(f"💰 Цена FOB: ¥{r.price_cny:.0f} (~{p.price_rub:.0f}₽)")
    if r.min_order > 1:
        lines.append(f"📦 Мин. заказ: {r.min_order} шт")
    lines.append(f"🚚 Себестоимость в РФ: ~{p.total_landed_cost:.0f}₽/шт")

    lines.append("")
    lines.append("📊 <b>Аналитика:</b>")

    if r.sales_volume > 0:
        lines.append(f"• Продажи в Китае: {r.sales_volume:,} шт/мес {trend_icon}")

    if p.wb_competitors > 0:
        lines.append(
            f"• На WB: {p.wb_competitors} конкурентов, средняя цена {p.wb_avg_price:.0f}₽"
        )

    if p.margin_pct != 0:
        lines.append(f"• Расчётная маржа: ~{p.margin_pct:.0f}% {margin_icon}")

    if p.ai_insight:
        lines.append("")
        lines.append(f"💡 <b>Инсайт:</b>")
        lines.append(p.ai_insight)

    if r.supplier_name:
        lines.append("")
        supplier_info = f"🏭 Поставщик: {r.supplier_name}"
        if r.supplier_years > 0:
            supplier_info += f", {r.supplier_years} лет"
        lines.append(supplier_info)

    if r.source_url:
        lines.append(f'🔗 <a href="{r.source_url}">Источник</a>')

    text = "\n".join(lines)

    return TelegramPost(product=product, text=text)
