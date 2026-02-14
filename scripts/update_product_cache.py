"""Update the local product cache from Apify 1688 data.

Runs the Apify collector across multiple categories and saves
results to data/products_cache.json for offline/fallback use.

Usage:
    python -X utf8 scripts/update_product_cache.py
    python -X utf8 scripts/update_product_cache.py --categories electronics gadgets
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.collect.alibaba_1688 import CATEGORY_KEYWORDS, Collector1688
from src.collect.wb_analytics import get_wb_market_data
from src.config import DATA_DIR


async def main(categories: list[str], limit_per_cat: int = 30):
    cache_path = DATA_DIR / "products_cache.json"
    collector = Collector1688()

    all_products = []

    for cat in categories:
        logger.info("Fetching category: {}", cat)
        products = await collector.collect(category=cat, limit=limit_per_cat)
        all_products.extend(products)
        logger.info("  Got {} products for '{}'", len(products), cat)

        # Pause between categories
        if cat != categories[-1]:
            await asyncio.sleep(5)

    if not all_products:
        logger.warning("No products collected — cache not updated")
        return

    # Pre-populate wb_est_price for each product
    logger.info("Pre-populating WB prices for {} products...", len(all_products))
    for p in all_products:
        if p.wb_est_price > 0:
            continue
        search_query = p.title_ru[:50] if p.title_ru else p.title_cn[:30]
        wb_data = await get_wb_market_data(search_query, keyword=p.wb_keyword)
        if wb_data["avg_price"] > 0:
            p.wb_est_price = wb_data["avg_price"]
            logger.debug("  WB price for '{}': {}r", p.title_ru[:30], p.wb_est_price)
        await asyncio.sleep(1.0)

    # Serialize to JSON
    data = []
    for p in all_products:
        d = p.model_dump()
        d["collected_at"] = d["collected_at"].isoformat()
        data.append(d)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    wb_populated = sum(1 for p in all_products if p.wb_est_price > 0)
    logger.info("Cached {} products ({} with WB prices) to {}", len(data), wb_populated, cache_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update product cache from Apify")
    parser.add_argument(
        "--categories",
        nargs="+",
        default=list(CATEGORY_KEYWORDS.keys()),
        help="Categories to fetch (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Products per category (default: 30)",
    )
    args = parser.parse_args()

    asyncio.run(main(categories=args.categories, limit_per_cat=args.limit))
