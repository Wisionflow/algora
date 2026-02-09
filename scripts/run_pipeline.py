"""Algora Pipeline — full run: Collect -> Analyze -> Compose -> Publish.

Usage:
    python -m scripts.run_pipeline --dry-run
    python -m scripts.run_pipeline --dry-run --source demo
    python -m scripts.run_pipeline --category electronics
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

# Fix Windows console encoding
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.collect.alibaba_1688 import Collector1688
from src.collect.demo_source import DemoCollector
from src.collect.wb_analytics import get_wb_market_data
from src.analyze.scoring import analyze_product
from src.analyze.ai_analysis import generate_insight
from src.compose.telegram_post import compose_post
from src.publish.telegram_bot import send_post
from src.db import (
    init_db,
    save_raw_product,
    save_analyzed_product,
    save_published_post,
    is_already_published,
)
from src.models import AnalyzedProduct


async def run(
    category: str = "electronics",
    dry_run: bool = False,
    source: str = "demo",
    top_n: int = 3,
) -> None:
    logger.info("=== ALGORA Pipeline START ===")
    logger.info("Source: {}, Category: {}, Dry run: {}", source, category, dry_run)

    # Init DB
    init_db()

    # --- STEP 1: COLLECT ---
    logger.info("--- Step 1: COLLECT ---")
    if source == "demo":
        collector = DemoCollector()
    else:
        collector = Collector1688()

    raw_products = await collector.collect(category=category, limit=20)

    if not raw_products:
        logger.warning("No products collected.")
        return

    logger.info("Collected {} products", len(raw_products))

    # Save raw products
    for p in raw_products:
        save_raw_product(p)

    # --- STEP 2: ANALYZE ---
    logger.info("--- Step 2: ANALYZE ---")
    analyzed: list[AnalyzedProduct] = []

    for raw in raw_products:
        # Skip already published
        if is_already_published(raw.source_url):
            logger.debug("Skipping already published: {}", raw.title_ru[:40])
            continue

        # Get WB market data (use wb_keyword if available, fallback to title)
        search_query = raw.title_ru[:50] if raw.title_ru else raw.title_cn[:30]
        wb_data = await get_wb_market_data(search_query, keyword=raw.wb_keyword)

        # If WB API failed, use estimated fallback price
        wb_price = wb_data["avg_price"]
        wb_comps = wb_data["competitors"]
        if wb_price == 0 and raw.wb_est_price > 0:
            wb_price = raw.wb_est_price
            wb_comps = 30  # assume moderate competition as fallback
            logger.debug("Using fallback WB price: {}r", wb_price)

        # Set image URL from WB if available
        if wb_data.get("image_url"):
            raw.image_url = wb_data["image_url"]
        # Update source_url to actual WB product page if available
        if wb_data.get("product_url"):
            raw.source_url = wb_data["product_url"]

        # Score the product
        product = analyze_product(
            raw,
            wb_avg_price=wb_price,
            wb_competitors=wb_comps,
        )
        analyzed.append(product)
        save_analyzed_product(product)

        logger.info(
            "  [{}/{}] {} -> score={}, margin={}%",
            len(analyzed),
            len(raw_products),
            raw.title_ru[:35],
            product.total_score,
            product.margin_pct,
        )

        # Delay to avoid WB rate limits (429)
        await asyncio.sleep(5.0)

    if not analyzed:
        logger.warning("No new products to analyze.")
        return

    # Sort by total score
    analyzed.sort(key=lambda p: p.total_score, reverse=True)
    top = analyzed[:top_n]

    logger.info("Top {} products selected for publishing:", len(top))
    for i, p in enumerate(top, 1):
        logger.info(
            "  {}. {} (score={}, margin={}%)",
            i,
            p.raw.title_ru[:45],
            p.total_score,
            p.margin_pct,
        )

    # --- STEP 3-5: AI INSIGHT + COMPOSE + PUBLISH (for each top product) ---
    published_count = 0
    for idx, product in enumerate(top, 1):
        logger.info("--- Post {}/{}: AI INSIGHT ---", idx, len(top))
        product.ai_insight = await generate_insight(product)
        save_analyzed_product(product)

        logger.info("--- Post {}/{}: COMPOSE ---", idx, len(top))
        post = compose_post(product)
        logger.info("Post {} composed ({} chars)", idx, len(post.text))

        # Print preview
        print("\n" + "=" * 60)
        print(f"PREVIEW [{idx}/{len(top)}]:")
        print("=" * 60)
        preview = re.sub(r"<[^>]+>", "", post.text)
        print(preview)
        print("=" * 60 + "\n")

        if dry_run:
            logger.info("Dry run -- skipping Telegram publish")
        else:
            logger.info("--- Post {}/{}: PUBLISH ---", idx, len(top))
            post = await send_post(post)
            if post.published:
                save_published_post(post)
                published_count += 1
                logger.info("Post {} published!", idx)
            else:
                logger.error("Post {} failed to publish", idx)

            # Small delay between Telegram messages to avoid flood limits
            if idx < len(top):
                await asyncio.sleep(3.0)

    # --- SUMMARY ---
    logger.info("=== Pipeline DONE ===")
    logger.info("Products collected: {}", len(raw_products))
    logger.info("Products analyzed: {}", len(analyzed))
    if not dry_run:
        logger.info("Posts published: {}/{}", published_count, len(top))
    logger.info("Top 5 by score:")
    for i, p in enumerate(analyzed[:5], 1):
        logger.info(
            "  {}. {} -- score={}, margin={}%",
            i,
            p.raw.title_ru[:40] or p.raw.title_cn[:40],
            p.total_score,
            p.margin_pct,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Algora Pipeline")
    parser.add_argument(
        "--category",
        default="electronics",
        help="Product category (default: electronics)",
    )
    parser.add_argument(
        "--source",
        default="demo",
        choices=["demo", "1688"],
        help="Data source (default: demo)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without publishing to Telegram",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=3,
        help="Number of top products to publish (default: 3)",
    )
    args = parser.parse_args()

    asyncio.run(run(
        category=args.category,
        dry_run=args.dry_run,
        source=args.source,
        top_n=args.top,
    ))


if __name__ == "__main__":
    main()
