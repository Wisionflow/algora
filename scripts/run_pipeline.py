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
from src.collect.json_file_source import JsonFileCollector
from src.collect.wb_analytics import get_wb_market_data
from src.analyze.scoring import analyze_product
from src.analyze.ai_analysis import generate_insight
from src.analyze.keywords import generate_keywords
from src.compose.telegram_post import compose_post
from src.compose.vk_post import compose_vk_post
from src.publish.telegram_bot import send_post, send_post_to_channel
from src.publish.vk_bot import send_vk_post
from src.config import VK_API_TOKEN, PREMIUM_ENABLED, TELEGRAM_PREMIUM_CHANNEL_ID, get_cny_to_rub
from src.db import (
    init_db,
    save_raw_product,
    save_analyzed_product,
    save_published_post,
    save_published_vk_post,
    save_post_engagement,
    is_already_published,
    is_image_already_published,
    is_product_recently_published,
)
from src.models import AnalyzedProduct

# Fallback WB average prices by category (when WB API is unavailable)
# Based on typical marketplace pricing for each product type
_CATEGORY_WB_FALLBACK: dict[str, tuple[float, int]] = {
    # (avg_price_rub, estimated_competitors)
    "electronics": (3500, 40),
    "gadgets": (2000, 35),
    "home": (1500, 50),
    "phone_accessories": (800, 60),
    "car_accessories": (1200, 30),
    "led_lighting": (900, 40),
    "beauty_devices": (2500, 25),
    "smart_home": (2000, 30),
    "outdoor": (1800, 35),
    "toys": (1000, 50),
    "health": (2000, 30),
    "kitchen": (1200, 45),
    "pet": (1800, 35),
    "sport": (2200, 40),
    "office": (800, 50),
    "kids": (1200, 45),
    "bags": (2500, 50),
    "jewelry": (600, 60),
    "tools": (1500, 35),
    "stationery": (400, 45),
}


async def run(
    category: str = "electronics",
    dry_run: bool = False,
    source: str = "demo",
    top_n: int = 3,
) -> None:
    logger.info("=== ALGORA Pipeline START ===")
    logger.info("Source: {}, Category: {}, Dry run: {}", source, category, dry_run)
    logger.info("CNY/RUB rate: {:.2f} (CBR)", get_cny_to_rub())

    # Init DB
    init_db()

    # --- STEP 1: COLLECT ---
    logger.info("--- Step 1: COLLECT ---")
    raw_products = []

    if source == "demo":
        raw_products = await DemoCollector().collect(category=category, limit=20)
    elif source == "1688":
        # Cascading fallback: Apify → JSON cache → demo
        raw_products = await Collector1688().collect(category=category, limit=20)
        if not raw_products:
            logger.warning("Apify returned nothing, trying JSON cache...")
            raw_products = await JsonFileCollector().collect(category=category, limit=20)
        if not raw_products:
            logger.warning("JSON cache empty, falling back to demo data...")
            raw_products = await DemoCollector().collect(category=category, limit=20)
    elif source == "cache":
        raw_products = await JsonFileCollector().collect(category=category, limit=20)

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

        # Generate keywords (before WB fetch so we can use optimized keyword)
        try:
            keywords_result = await generate_keywords(raw)
            logger.debug(
                "Keywords: {} extracted, {} AI, optimized: '{}'",
                len(keywords_result["extracted"]),
                len(keywords_result["ai_suggested"]),
                keywords_result["wb_optimized"][:30],
            )
        except Exception as e:
            logger.warning("Keyword generation failed for {}: {}", raw.title_ru[:30], e)
            keywords_result = {
                "extracted": [],
                "ai_suggested": [],
                "wb_optimized": raw.wb_keyword,
            }

        # Get WB market data (use optimized keyword, fallback to wb_keyword)
        search_keyword = keywords_result["wb_optimized"] or raw.wb_keyword
        search_query = raw.title_ru[:50] if raw.title_ru else raw.title_cn[:30]
        wb_data = await get_wb_market_data(search_query, keyword=search_keyword)

        # If WB API failed, use fallback pricing
        wb_price = wb_data["avg_price"]
        wb_comps = wb_data["competitors"]
        if wb_price == 0:
            if raw.wb_est_price > 0:
                wb_price = raw.wb_est_price
                wb_comps = 30
            else:
                # Estimate WB price from landed cost with typical marketplace markup
                from src.analyze.scoring import estimate_costs
                landed = estimate_costs(raw)["total_landed_cost"]
                if landed > 0:
                    # Typical WB markup: 2.5-4x landed cost
                    wb_price = round(landed * 3.0, 2)
                else:
                    # Last resort: use category-based fallback
                    fallback = _CATEGORY_WB_FALLBACK.get(raw.category, (1500, 35))
                    wb_price = fallback[0]
                wb_comps = _CATEGORY_WB_FALLBACK.get(raw.category, (1500, 35))[1]
            logger.debug("Using fallback WB price: {}r (category: {})", wb_price, raw.category)

        # Never use WB images — audience will recognize them as fake
        # Keep original Chinese source_url — that's the value for the audience

        # Score the product
        product = analyze_product(
            raw,
            wb_avg_price=wb_price,
            wb_competitors=wb_comps,
        )

        # Add keyword enrichment
        product.keywords_extracted = keywords_result["extracted"]
        product.keywords_ai = keywords_result["ai_suggested"]
        product.wb_keyword_optimized = keywords_result["wb_optimized"]

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

        # Small delay between products (WB rate limiting is handled in wb_analytics)
        await asyncio.sleep(1.0)

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
    # Two-tier logic: when premium enabled, top products go to premium channel
    premium_count = 2  # top N go to premium
    published_count = 0
    for idx, product in enumerate(top, 1):
        # Skip recently published products (cross-platform dedup by offer_id)
        if is_product_recently_published(product.raw.source_url, days=14):
            logger.info("Skipping recently published: {}", product.raw.title_ru[:40])
            continue

        logger.info("--- Post {}/{}: AI INSIGHT ---", idx, len(top))
        product.ai_insight = await generate_insight(product)
        save_analyzed_product(product)

        # Check for duplicate images — better no photo than a repeated one
        if product.raw.image_url and is_image_already_published(product.raw.image_url):
            logger.warning("Duplicate image detected, removing: {}", product.raw.image_url[:60])
            product.raw.image_url = ""

        logger.info("--- Post {}/{}: COMPOSE ---", idx, len(top))
        post = compose_post(product)
        logger.info("Post {} composed ({} chars)", idx, len(post.text))

        # Determine target channel
        is_premium_post = (
            PREMIUM_ENABLED
            and TELEGRAM_PREMIUM_CHANNEL_ID
            and idx <= premium_count
        )
        channel_label = "PREMIUM" if is_premium_post else "FREE"

        # Print preview
        print("\n" + "=" * 60)
        print(f"PREVIEW [{idx}/{len(top)}] ({channel_label}):")
        print("=" * 60)
        preview = re.sub(r"<[^>]+>", "", post.text)
        print(preview)
        print("=" * 60 + "\n")

        if dry_run:
            logger.info("Dry run -- skipping publish ({})", channel_label)
        else:
            # --- Telegram ---
            if is_premium_post:
                logger.info("--- Post {}/{}: PUBLISH (Telegram PREMIUM) ---", idx, len(top))
                post = await send_post_to_channel(post, TELEGRAM_PREMIUM_CHANNEL_ID)
            else:
                logger.info("--- Post {}/{}: PUBLISH (Telegram FREE) ---", idx, len(top))
                post = await send_post(post)

            if post.published:
                save_published_post(
                    post, platform="telegram",
                    post_type="product", category=product.raw.category,
                    image_url=product.raw.image_url,
                )
                save_post_engagement(
                    message_id=post.message_id,
                    platform="telegram",
                    post_type="product",
                    category=product.raw.category,
                    total_score=product.total_score,
                )
                published_count += 1
                logger.info("Post {} published to Telegram ({})!", idx, channel_label)
            else:
                logger.error("Post {} failed to publish to Telegram", idx)

            # --- VK (always free) ---
            if VK_API_TOKEN:
                logger.info("--- Post {}/{}: PUBLISH (VK) ---", idx, len(top))
                vk_text = compose_vk_post(product)
                vk_result = await send_vk_post(
                    text=vk_text,
                    image_url=product.raw.image_url,
                    source_url=product.raw.source_url,
                )
                if vk_result["published"]:
                    save_published_vk_post(
                        product.raw.source_url, vk_text, vk_result["post_id"],
                        post_type="product", category=product.raw.category,
                        image_url=product.raw.image_url,
                    )
                    logger.info("Post {} published to VK!", idx)
                else:
                    logger.error("Post {} failed to publish to VK", idx)

            # Small delay between messages to avoid flood limits
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
        default="all",
        help="Product category: electronics, gadgets, home, phone_accessories, "
             "car_accessories, led_lighting, beauty_devices, smart_home, outdoor, "
             "toys, health, kitchen, pet, sport, office, kids, bags, jewelry, "
             "tools, stationery, or 'all' (default: all)",
    )
    parser.add_argument(
        "--source",
        default="1688",
        choices=["demo", "1688", "cache"],
        help="Data source: 1688 (Apify with fallback, default), demo, cache (local JSON)",
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
