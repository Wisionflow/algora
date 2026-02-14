"""Post 'Beginner Mistake' — educational content based on a real product.

Picks a product and generates an AI analysis of a common mistake
that beginners make with this type of product.

Usage:
    python -X utf8 -m scripts.post_beginner_mistake --source 1688
    python -X utf8 -m scripts.post_beginner_mistake --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic
from loguru import logger

from src.collect.demo_source import DemoCollector
from src.collect.alibaba_1688 import Collector1688
from src.collect.json_file_source import JsonFileCollector
from src.collect.wb_analytics import get_wb_market_data
from src.analyze.scoring import analyze_product
from src.compose.telegram_post import compose_beginner_mistake
from src.compose.vk_post import compose_vk_beginner_mistake
from src.publish.telegram_bot import send_post
from src.publish.vk_bot import send_vk_post
from src.config import ANTHROPIC_API_KEY, VK_API_TOKEN
from src.db import init_db, save_raw_product, save_analyzed_product, save_post_engagement
from src.models import TelegramPost


MISTAKE_PROMPT = """Ты — опытный наставник для начинающих селлеров маркетплейсов (WB, Ozon).

На основе данных о товаре напиши пост «Ошибка новичка» — разбор типичной ошибки,
которую делают начинающие при работе с таким товаром.

Товар: {title}
Категория: {category}
FOB Китай: ¥{price_cny} (~{price_rub}₽)
Себестоимость в РФ: ~{landed}₽
Цена на WB: ~{wb_price}₽
Конкурентов: {competitors}
Маржа: ~{margin}%

Формат поста:
1. Начни с «❌ Ошибка:» — кратко опиши ошибку (1 предложение)
2. Затем «Почему это плохо:» — объясни последствия (1-2 предложения)
3. Затем «✅ Как правильно:» — дай конкретный совет (2-3 предложения)

Правила:
- Пиши на русском
- Максимум 500 символов
- Без Markdown (звёздочек, жирного) — чистый текст
- Будь конкретен: используй цифры из данных товара
- Типичные ошибки: не учёл таможню, не проверил сертификацию, заказал слишком большую партию,
  не посчитал комиссию маркетплейса, не учёл сезонность, выбрал нишу с 100+ конкурентами,
  не сделал тестовую закупку, использовал фото поставщика вместо своих"""


async def post_beginner_mistake(
    source: str = "demo",
    dry_run: bool = False,
) -> None:
    logger.info("=== Beginner Mistake Post ===")
    init_db()

    # Pick a random category
    categories = [
        "electronics", "gadgets", "home", "phone_accessories",
        "car_accessories", "beauty_devices", "smart_home",
        "outdoor", "toys", "kitchen",
    ]
    category = random.choice(categories)
    logger.info("Category: {}", category)

    # Collect products
    if source == "demo":
        raw_products = await DemoCollector().collect(category=category, limit=10)
    elif source == "1688":
        raw_products = await Collector1688().collect(category=category, limit=10)
        if not raw_products:
            raw_products = await JsonFileCollector().collect(category=category, limit=10)
        if not raw_products:
            raw_products = await DemoCollector().collect(category=category, limit=10)
    else:
        raw_products = await JsonFileCollector().collect(category=category, limit=10)

    if not raw_products:
        logger.error("No products collected")
        return

    # Pick one random product and analyze it
    raw = random.choice(raw_products)
    save_raw_product(raw)

    search_query = raw.title_ru[:50] if raw.title_ru else raw.title_cn[:30]
    wb_data = await get_wb_market_data(search_query, keyword=raw.wb_keyword)
    wb_price = wb_data["avg_price"] or raw.wb_est_price or 1000
    wb_comps = wb_data["competitors"] or 30

    product = analyze_product(raw, wb_avg_price=wb_price, wb_competitors=wb_comps)
    save_analyzed_product(product)

    logger.info("Product: {} (score={}, margin={}%)",
                raw.title_ru[:40], product.total_score, product.margin_pct)

    # Generate mistake analysis via AI
    mistake_text = ""
    if ANTHROPIC_API_KEY:
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            prompt = MISTAKE_PROMPT.format(
                title=raw.title_ru or raw.title_cn,
                category=category,
                price_cny=raw.price_cny,
                price_rub=product.price_rub,
                landed=product.total_landed_cost,
                wb_price=product.wb_avg_price,
                competitors=product.wb_competitors,
                margin=product.margin_pct,
            )
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            mistake_text = message.content[0].text.strip()
        except Exception as e:
            logger.error("AI generation failed: {}", e)
            mistake_text = (
                "❌ Ошибка: Не учитывать все расходы при расчёте маржи.\n\n"
                "Почему это плохо: Многие считают только FOB-цену, забывая про доставку, "
                "таможню, комиссию маркетплейса (15-25%) и возвраты.\n\n"
                "✅ Как правильно: Всегда считайте полную себестоимость: "
                "FOB + доставка + таможня + упаковка + комиссия WB. "
                "Маржа должна быть минимум 30% после всех расходов."
            )
    else:
        mistake_text = (
            "❌ Ошибка: Заказывать большую партию без тестовой закупки.\n\n"
            "Почему это плохо: Без тестовой партии вы рискуете получить брак, "
            "несоответствие описанию или проблемы с сертификацией.\n\n"
            "✅ Как правильно: Начните с минимальной партии (20-50 шт). "
            "Проверьте качество, сделайте фото, запустите продажи. "
            "Только после первых 30+ продаж масштабируйте заказ."
        )

    # Compose post
    text = compose_beginner_mistake(product, mistake_text)

    print("\n" + "=" * 60)
    print("PREVIEW:")
    print("=" * 60)
    print(text.replace("<b>", "").replace("</b>", "").replace("<a href=\"", "[").replace("\">", "](").replace("</a>", ")"))
    print("=" * 60 + "\n")

    if dry_run:
        logger.info("Dry run — skipping publish")
    else:
        # Telegram
        post = TelegramPost(product=product, text=text, image_url="")
        post = await send_post(post)
        if post.published:
            save_post_engagement(
                message_id=post.message_id,
                platform="telegram",
                post_type="beginner_mistake",
                category=category,
            )
            logger.info("Beginner mistake published to Telegram!")
        else:
            logger.error("Failed to publish to Telegram")

        # VK
        if VK_API_TOKEN:
            vk_text = compose_vk_beginner_mistake(product, mistake_text)
            vk_result = await send_vk_post(text=vk_text)
            if vk_result["published"]:
                logger.info("Beginner mistake published to VK!")
            else:
                logger.error("Failed to publish to VK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Post beginner mistake")
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

    asyncio.run(post_beginner_mistake(
        source=args.source,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
