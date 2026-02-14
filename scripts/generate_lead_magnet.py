"""Generate a lead magnet post from top-scoring products.

Queries the DB for the best products from the last 30 days
and creates a formatted Telegram-ready post.

Usage:
    python -X utf8 scripts/generate_lead_magnet.py
    python -X utf8 scripts/generate_lead_magnet.py --top 10
    python -X utf8 scripts/generate_lead_magnet.py --min-margin 40
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.config import DATA_DIR
from src.db import get_connection, init_db


def _get_top_products(limit: int = 20, min_margin: float = 30.0) -> list[dict]:
    """Get top products by score with margin filter."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT source_url, raw_json, total_score, margin_pct,
                      margin_rub, total_landed_cost, wb_avg_price,
                      wb_competitors, ai_insight
            FROM analyzed_products
            WHERE margin_pct >= ?
              AND analyzed_at >= date('now', '-30 days')
            ORDER BY total_score DESC
            LIMIT ?""",
            (min_margin, limit),
        ).fetchall()

        if not rows:
            # Fallback: get all-time top if last 30 days is empty
            rows = conn.execute(
                """SELECT source_url, raw_json, total_score, margin_pct,
                          margin_rub, total_landed_cost, wb_avg_price,
                          wb_competitors, ai_insight
                FROM analyzed_products
                WHERE margin_pct >= ?
                ORDER BY total_score DESC
                LIMIT ?""",
                (min_margin, limit),
            ).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


def generate_lead_magnet(top_n: int = 20, min_margin: float = 30.0) -> str:
    """Generate formatted lead magnet text."""
    products = _get_top_products(limit=top_n, min_margin=min_margin)

    if not products:
        logger.warning("No products found for lead magnet (min_margin={}%)", min_margin)
        return ""

    lines: list[str] = []

    # Header
    lines.append(f"TOP-{len(products)} ТОВАРОВ ИЗ КИТАЯ")
    lines.append(f"С МАРЖОЙ ОТ {min_margin:.0f}%")
    lines.append("")
    lines.append("Подборка лучших товаров для продажи")
    lines.append("на Wildberries и Ozon.")
    lines.append("Все товары проверены и оценены AI.")
    lines.append("")
    lines.append("-" * 35)

    for i, p in enumerate(products, 1):
        raw = json.loads(p["raw_json"])
        title = raw.get("title_ru") or raw.get("title_cn", "???")
        title = title[:60]

        category = raw.get("category", "")
        supplier = raw.get("supplier_name", "")
        price_cny = raw.get("price_cny", 0)

        score = p["total_score"]
        margin = p["margin_pct"]
        margin_rub = p["margin_rub"]
        landed_cost = p["total_landed_cost"]
        wb_price = p["wb_avg_price"]
        competitors = p["wb_competitors"]

        lines.append("")
        lines.append(f"{i}. {title}")

        details = []
        if landed_cost > 0:
            details.append(f"   Себестоимость: {landed_cost:,.0f} р")
        if wb_price > 0:
            details.append(f"   Цена на WB: {wb_price:,.0f} р")
        if margin > 0:
            details.append(f"   Маржа: {margin:.0f}% ({margin_rub:,.0f} р/шт)")
        if competitors > 0:
            details.append(f"   Конкурентов на WB: {competitors}")
        if price_cny > 0:
            details.append(f"   Цена 1688: {price_cny:.1f} CNY")
        if supplier:
            details.append(f"   Поставщик: {supplier[:30]}")
        if category:
            details.append(f"   Категория: {category}")
        details.append(f"   Рейтинг AI: {score:.1f}/10")

        lines.extend(details)

    lines.append("")
    lines.append("-" * 35)
    lines.append("")
    lines.append("Хотите получать такие подборки")
    lines.append("каждую неделю?")
    lines.append("")
    lines.append("Подписывайтесь: @algora_trends")
    lines.append("")
    lines.append("Algora - AI-аналитика трендов")
    lines.append("из Китая для маркетплейсов")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate lead magnet from top products")
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of top products to include (default: 20)",
    )
    parser.add_argument(
        "--min-margin",
        type=float,
        default=30.0,
        help="Minimum margin %% to include (default: 30)",
    )
    args = parser.parse_args()

    init_db()

    text = generate_lead_magnet(top_n=args.top, min_margin=args.min_margin)

    if not text:
        logger.error("Failed to generate lead magnet — no qualifying products in DB")
        return

    # Save to file
    output_path = DATA_DIR / "lead_magnet.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    logger.info("Lead magnet saved to {} ({} chars)", output_path, len(text))

    # Also print to stdout
    print("\n" + "=" * 40)
    print("  LEAD MAGNET PREVIEW")
    print("=" * 40)
    print()
    print(text)
    print()
    print("=" * 40)
    print(f"  Saved to: {output_path}")
    print("=" * 40 + "\n")


if __name__ == "__main__":
    main()
