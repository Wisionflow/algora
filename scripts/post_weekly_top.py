"""Post weekly top — best products from the last 7 days.

Usage:
    python -X utf8 -m scripts.post_weekly_top
    python -X utf8 -m scripts.post_weekly_top --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.compose.telegram_post import compose_weekly_top
from src.publish.telegram_bot import send_post
from src.db import init_db, get_connection
from src.models import AnalyzedProduct, RawProduct, TelegramPost


def get_weekly_top_products(limit: int = 5) -> list[AnalyzedProduct]:
    """Get top products from the last 7 days by score."""
    init_db()
    conn = get_connection()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    try:
        rows = conn.execute(
            """SELECT raw_json, price_rub, delivery_cost_est, customs_duty_est,
                      total_landed_cost, wb_avg_price, wb_competitors,
                      margin_pct, margin_rub, trend_score, competition_score,
                      margin_score, reliability_score, total_score, ai_insight
            FROM analyzed_products
            WHERE analyzed_at >= ?
            ORDER BY total_score DESC
            LIMIT ?""",
            (week_ago, limit),
        ).fetchall()

        products = []
        for row in rows:
            raw_dict = json.loads(row["raw_json"])
            raw = RawProduct(**raw_dict)

            product = AnalyzedProduct(
                raw=raw,
                price_rub=row["price_rub"],
                delivery_cost_est=row["delivery_cost_est"],
                customs_duty_est=row["customs_duty_est"],
                total_landed_cost=row["total_landed_cost"],
                wb_avg_price=row["wb_avg_price"],
                wb_competitors=row["wb_competitors"],
                margin_pct=row["margin_pct"],
                margin_rub=row["margin_rub"],
                trend_score=row["trend_score"],
                competition_score=row["competition_score"],
                margin_score=row["margin_score"],
                reliability_score=row["reliability_score"],
                total_score=row["total_score"],
                ai_insight=row["ai_insight"] or "",
            )
            products.append(product)

        return products
    finally:
        conn.close()


async def post_weekly_top(dry_run: bool = False) -> None:
    logger.info("=== Weekly Top ===")

    products = get_weekly_top_products(limit=5)

    if not products:
        logger.warning("No products found in the last 7 days")
        return

    logger.info("Found {} top products", len(products))

    text = compose_weekly_top(products)

    print("\n" + "=" * 60)
    print("PREVIEW:")
    print("=" * 60)
    print(text.replace("<b>", "").replace("</b>", ""))
    print("=" * 60 + "\n")

    if dry_run:
        logger.info("Dry run — skipping publish")
    else:
        # Publish (use first product as wrapper)
        post = TelegramPost(product=products[0], text=text, image_url="")
        post = await send_post(post)
        if post.published:
            logger.info("Weekly top published!")
        else:
            logger.error("Failed to publish")


def main() -> None:
    parser = argparse.ArgumentParser(description="Post weekly top")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, don't publish",
    )
    args = parser.parse_args()

    asyncio.run(post_weekly_top(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
