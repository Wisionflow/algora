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

    # Serialize to JSON
    data = []
    for p in all_products:
        d = p.model_dump()
        d["collected_at"] = d["collected_at"].isoformat()
        data.append(d)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Cached {} products to {}", len(data), cache_path)


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
