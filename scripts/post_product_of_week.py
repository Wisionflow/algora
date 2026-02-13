"""Post 'Product of the Week' — deep-dive into the best product.

Finds the highest-scored product from the last 7 days
and publishes a detailed analysis.

Usage:
    python -X utf8 -m scripts.post_product_of_week --source 1688
    python -X utf8 -m scripts.post_product_of_week --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
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
from src.compose.telegram_post import compose_product_of_week
from src.compose.vk_post import compose_vk_product_of_week
from src.publish.telegram_bot import send_post
from src.publish.vk_bot import send_vk_post
from src.config import ANTHROPIC_API_KEY, VK_API_TOKEN
from src.db import init_db, get_connection, save_raw_product, save_analyzed_product
from src.models import AnalyzedProduct, RawProduct, TelegramPost


DEEP_ANALYSIS_PROMPT = """Ты — эксперт по товарному бизнесу на маркетплейсах (WB, Ozon) с опытом закупок из Китая.

Напиши экспертный разбор этого товара для начинающих и опытных селлеров.

Товар: {title}
Категория: {category}
FOB Китай: ¥{price_cny} (~{price_rub}₽)
Мин. заказ: {min_order} шт
Себестоимость в РФ: ~{landed}₽
Цена на WB: ~{wb_price}₽
Конкурентов на WB: {competitors}
Продажи в Китае: {sales} шт/мес
Маржа: ~{margin}% ({margin_rub}₽/шт)
Поставщик: {supplier}, {years} лет на площадке
Рейтинг: {score}/10

Формат (строго):
1. «Почему выбрали:» — 1-2 предложения, главные преимущества
2. «Риски:» — 2-3 конкретных риска с цифрами
3. «План входа:» — пошаговая рекомендация (3-4 шага)
4. «Вердикт:» — одно предложение-вывод

Правила:
- Русский язык, максимум 600 символов
- Без Markdown — чистый текст
- Будь конкретен: используй цифры из данных
- Учитывай комиссию WB (15-20%), возвраты (5-10%), логистику"""


def _get_best_from_db() -> AnalyzedProduct | None:
    """Get the best product from the last 7 days."""
    init_db()
    conn = get_connection()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    try:
        row = conn.execute(
            """SELECT raw_json, price_rub, delivery_cost_est, customs_duty_est,
                      total_landed_cost, wb_avg_price, wb_competitors,
                      margin_pct, margin_rub, trend_score, competition_score,
                      margin_score, reliability_score, total_score, ai_insight
            FROM analyzed_products
            WHERE analyzed_at >= ?
            ORDER BY total_score DESC
            LIMIT 1""",
            (week_ago,),
        ).fetchone()

        if not row:
            return None

        raw = RawProduct(**json.loads(row["raw_json"]))
        return AnalyzedProduct(
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
    finally:
        conn.close()


async def _collect_fresh_product(source: str) -> AnalyzedProduct | None:
    """Collect and analyze a fresh product if DB is empty."""
    categories = [
        "electronics", "gadgets", "home", "smart_home",
        "beauty_devices", "car_accessories",
    ]
    category = random.choice(categories)

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
        return None

    # Analyze all and pick the best
    best = None
    for raw in raw_products:
        save_raw_product(raw)
        search_query = raw.title_ru[:50] if raw.title_ru else raw.title_cn[:30]
        wb_data = await get_wb_market_data(search_query, keyword=raw.wb_keyword)
        wb_price = wb_data["avg_price"] or raw.wb_est_price or 1000
        wb_comps = wb_data["competitors"] or 30

        product = analyze_product(raw, wb_avg_price=wb_price, wb_competitors=wb_comps)
        save_analyzed_product(product)

        if best is None or product.total_score > best.total_score:
            best = product

        await asyncio.sleep(1.0)

    return best


async def post_product_of_week(
    source: str = "demo",
    dry_run: bool = False,
) -> None:
    logger.info("=== Product of the Week ===")
    init_db()

    # Try to get best from DB first
    product = _get_best_from_db()

    if product:
        logger.info("Found best from DB: {} (score={})",
                     (product.raw.title_ru or product.raw.title_cn)[:40],
                     product.total_score)
    else:
        logger.info("No recent products in DB, collecting fresh...")
        product = await _collect_fresh_product(source)

    if not product:
        logger.error("No products available")
        return

    r = product.raw
    logger.info("Product of week: {} | score={} | margin={}%",
                (r.title_ru or r.title_cn)[:40], product.total_score, product.margin_pct)

    # Generate deep analysis via AI
    deep_analysis = ""
    if ANTHROPIC_API_KEY:
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            prompt = DEEP_ANALYSIS_PROMPT.format(
                title=r.title_ru or r.title_cn,
                category=r.category,
                price_cny=r.price_cny,
                price_rub=product.price_rub,
                min_order=r.min_order,
                landed=product.total_landed_cost,
                wb_price=product.wb_avg_price,
                competitors=product.wb_competitors,
                sales=r.sales_volume,
                margin=product.margin_pct,
                margin_rub=product.margin_rub,
                supplier=r.supplier_name or "Неизвестен",
                years=r.supplier_years,
                score=product.total_score,
            )
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            deep_analysis = message.content[0].text.strip()
        except Exception as e:
            logger.error("AI generation failed: {}", e)

    if not deep_analysis:
        deep_analysis = (
            f"Почему выбрали: Высокий рейтинг {product.total_score:.1f}/10 "
            f"и маржа {product.margin_pct:.0f}% делают товар привлекательным для входа.\n\n"
            f"Риски: {product.wb_competitors} конкурентов на WB, "
            f"необходимость сертификации, зависимость от одного поставщика.\n\n"
            f"План входа: 1) Заказать тестовую партию. "
            f"2) Сделать свои фото и инфографику. "
            f"3) Запустить на WB с ценой чуть ниже рынка. "
            f"4) После 30 продаж — масштабировать.\n\n"
            f"Вердикт: Рекомендуем для тестовой закупки с бюджетом от "
            f"{r.min_order * product.total_landed_cost:,.0f}₽."
        )

    text = compose_product_of_week(product, deep_analysis)

    print("\n" + "=" * 60)
    print("PREVIEW:")
    print("=" * 60)
    preview = text.replace("<b>", "").replace("</b>", "")
    preview = preview.replace("<a href=\"", "[").replace("\">", "](").replace("</a>", ")")
    print(preview)
    print("=" * 60 + "\n")

    if dry_run:
        logger.info("Dry run — skipping publish")
    else:
        # Telegram
        post = TelegramPost(product=product, text=text, image_url="")
        post = await send_post(post)
        if post.published:
            logger.info("Product of the week published to Telegram!")
        else:
            logger.error("Failed to publish to Telegram")

        # VK
        if VK_API_TOKEN:
            vk_text = compose_vk_product_of_week(product, deep_analysis)
            vk_result = await send_vk_post(
                text=vk_text, image_url=r.image_url
            )
            if vk_result["published"]:
                logger.info("Product of the week published to VK!")
            else:
                logger.error("Failed to publish to VK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Post product of the week")
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

    asyncio.run(post_product_of_week(
        source=args.source,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
