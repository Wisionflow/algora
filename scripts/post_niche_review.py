"""Post niche review — analyze a category and publish overview.

Usage:
    python -X utf8 -m scripts.post_niche_review --category electronics
    python -X utf8 -m scripts.post_niche_review --category home --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.collect.demo_source import DemoCollector
from src.collect.alibaba_1688 import Collector1688
from src.collect.json_file_source import JsonFileCollector
from src.analyze.scoring import analyze_product
from src.analyze.ai_analysis import generate_insight
from src.collect.wb_analytics import get_wb_market_data
from src.compose.telegram_post import compose_niche_review
from src.compose.vk_post import compose_vk_niche_review
from src.publish.telegram_bot import send_post
from src.publish.vk_bot import send_vk_post
from src.config import VK_API_TOKEN
from src.db import init_db, save_raw_product, save_analyzed_product
from src.models import TelegramPost


async def post_niche_review(
    category: str,
    source: str = "demo",
    dry_run: bool = False,
) -> None:
    logger.info("=== Niche Review: {} ===", category)
    init_db()

    # Collect products
    if source == "demo":
        raw_products = await DemoCollector().collect(category=category, limit=20)
    elif source == "1688":
        raw_products = await Collector1688().collect(category=category, limit=20)
        if not raw_products:
            raw_products = await JsonFileCollector().collect(category=category, limit=20)
    else:
        raw_products = await JsonFileCollector().collect(category=category, limit=20)

    if not raw_products:
        logger.error("No products collected")
        return

    logger.info("Collected {} products", len(raw_products))

    # Analyze all
    analyzed = []
    for raw in raw_products:
        save_raw_product(raw)
        search_query = raw.title_ru[:50] if raw.title_ru else raw.title_cn[:30]
        wb_data = await get_wb_market_data(search_query, keyword=raw.wb_keyword)
        wb_price = wb_data["avg_price"] or raw.wb_est_price or 1000
        wb_comps = wb_data["competitors"] or 30

        product = analyze_product(raw, wb_avg_price=wb_price, wb_competitors=wb_comps)
        analyzed.append(product)
        save_analyzed_product(product)
        await asyncio.sleep(1.0)

    logger.info("Analyzed {} products", len(analyzed))

    # Generate AI summary for the niche
    from src.analyze.ai_analysis import SYSTEM_PROMPT
    import anthropic
    from src.config import ANTHROPIC_API_KEY

    ai_summary = ""
    if ANTHROPIC_API_KEY:
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            avg_margin = sum(p.margin_pct for p in analyzed) / len(analyzed)
            avg_score = sum(p.total_score for p in analyzed) / len(analyzed)
            total_sales = sum(p.raw.sales_volume for p in analyzed)

            prompt = f"""Дай краткий обзор ниши "{category}" на основе анализа {len(analyzed)} товаров:
- Средняя маржа: {avg_margin:.0f}%
- Средний рейтинг: {avg_score:.1f}/10
- Суммарные продажи: {total_sales:,} шт/мес

Напиши 2-3 предложения: насколько перспективна ниша, для кого подходит, главные риски."""

            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            ai_summary = message.content[0].text.strip()
        except Exception as e:
            logger.warning("AI summary failed: {}", e)

    # Compose niche review
    text = compose_niche_review(category, analyzed, ai_summary)

    print("\n" + "=" * 60)
    print("PREVIEW:")
    print("=" * 60)
    print(text.replace("<b>", "").replace("</b>", "").replace("<a href=\"", "[").replace("\">", "](").replace("</a>", ")"))
    print("=" * 60 + "\n")

    if dry_run:
        logger.info("Dry run — skipping publish")
    else:
        # Telegram
        post = TelegramPost(product=analyzed[0], text=text, image_url="")
        post = await send_post(post)
        if post.published:
            logger.info("Niche review published to Telegram!")
        else:
            logger.error("Failed to publish to Telegram")

        # VK
        if VK_API_TOKEN:
            vk_text = compose_vk_niche_review(category, analyzed, ai_summary)
            vk_result = await send_vk_post(text=vk_text)
            if vk_result["published"]:
                logger.info("Niche review published to VK!")
            else:
                logger.error("Failed to publish to VK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Post niche review")
    parser.add_argument(
        "--category",
        required=True,
        help="Category to review",
    )
    parser.add_argument(
        "--source",
        default="demo",
        choices=["demo", "1688", "cache"],
        help="Data source",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, don't publish",
    )
    args = parser.parse_args()

    asyncio.run(post_niche_review(
        category=args.category,
        source=args.source,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
