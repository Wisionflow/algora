"""Collector for 1688.com via Apify API.

Uses Apify's 1688 search scraper to get structured product data.
Translates titles from Chinese to Russian.
Falls back gracefully if Apify is unavailable.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

from deep_translator import GoogleTranslator
from loguru import logger

from src.config import APIFY_API_TOKEN, APIFY_1688_ACTOR_ID
from src.models import RawProduct

from .base import BaseCollector

# Category keywords for 1688 search (Chinese)
CATEGORY_KEYWORDS: dict[str, str] = {
    "electronics": "电子产品 爆款",
    "gadgets": "智能小家电 新款",
    "home": "家居用品 热销",
    "phone_accessories": "手机配件 爆款",
    "car_accessories": "汽车用品 热卖",
    "led_lighting": "LED灯 新款",
    "beauty_devices": "美容仪器 爆款",
    "smart_home": "智能家居 热销",
    "outdoor": "户外用品 新款",
    "toys": "玩具 爆款 新奇",
    "health": "健康 按摩 爆款",
}

_translator = GoogleTranslator(source="zh-CN", target="ru")

# Russian stopwords for wb_keyword extraction
_RU_STOPWORDS = frozenset(
    "для с и в на от из по к о не без при до через под над "
    "новый новая новое новые мини портативный портативная".split()
)


def _translate(text: str) -> str:
    """Translate Chinese text to Russian. Returns original on failure."""
    if not text:
        return ""
    try:
        return _translator.translate(text)
    except Exception:
        return text


def _parse_price(value) -> float:
    """Parse price from various formats: float, string, range."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return 0.0
    text = value.replace("¥", "").replace(",", "").replace(" ", "")
    try:
        return float(re.split(r"[-~]", text)[0].strip())
    except (ValueError, IndexError):
        return 0.0


def _parse_sales(value) -> int:
    """Parse sales from various formats: int, '1234笔', '5.2万笔'."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if not isinstance(value, str):
        return 0
    text = value.replace(",", "").replace(" ", "")
    m = re.search(r"([\d.]+)万", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"(\d+)", text)
    if m:
        return int(m.group(1))
    return 0


def _extract_wb_keyword(title_ru: str) -> str:
    """Extract a short WB search keyword from Russian product title."""
    words = [
        w for w in title_ru.lower().split()
        if w not in _RU_STOPWORDS and len(w) > 2
    ]
    return " ".join(words[:3])


class Collector1688(BaseCollector):
    """Collects trending products from 1688.com via Apify API."""

    async def collect(self, category: str, limit: int = 20) -> list[RawProduct]:
        keyword = CATEGORY_KEYWORDS.get(category, category)
        logger.info("Collecting from 1688 (Apify): category='{}', keyword='{}'", category, keyword)

        if not APIFY_API_TOKEN:
            logger.error("APIFY_API_TOKEN not set — cannot collect from 1688")
            return []

        try:
            items = await self._run_actor(keyword, limit)
        except Exception as e:
            logger.error("Apify actor failed: {}", e)
            return []

        if not items:
            logger.warning("Apify returned no results for '{}'", keyword)
            return []

        products = []
        for item in items[:limit]:
            try:
                product = self._map_item(item, category)
                if product:
                    products.append(product)
            except Exception as e:
                logger.debug("Skipping item: {}", e)
                continue

            # Delay between Google Translate calls
            await asyncio.sleep(0.5)

        logger.info("Collected {} products for '{}'", len(products), category)
        return products

    async def _run_actor(self, keyword: str, limit: int) -> list[dict]:
        """Run the Apify 1688 search actor and return results."""
        from apify_client import ApifyClient

        client = ApifyClient(APIFY_API_TOKEN)

        actor_input = {
            "keyword": keyword,
            "maxItems": limit,
        }

        logger.debug("Running Apify actor '{}' with keyword '{}'", APIFY_1688_ACTOR_ID, keyword)

        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        run = await loop.run_in_executor(
            None,
            lambda: client.actor(APIFY_1688_ACTOR_ID).call(
                run_input=actor_input,
                timeout_secs=120,
            ),
        )

        # Fetch results from the default dataset
        dataset_items = client.dataset(run["defaultDatasetId"]).list_items().items
        logger.debug("Apify returned {} items", len(dataset_items))
        return dataset_items

    def _map_item(self, item: dict, category: str) -> RawProduct | None:
        """Map Apify JSON item to RawProduct."""
        # Extract title (try common field names)
        title_cn = (
            item.get("title", "")
            or item.get("offerTitle", "")
            or item.get("name", "")
        )
        if not title_cn:
            return None

        # Extract URL
        source_url = (
            item.get("detailUrl", "")
            or item.get("url", "")
            or item.get("offerUrl", "")
            or item.get("link", "")
        )
        if source_url and not source_url.startswith("http"):
            source_url = "https:" + source_url
        if not source_url:
            return None

        # Price
        price_cny = _parse_price(
            item.get("price", 0)
            or item.get("priceRange", "")
            or item.get("originalPrice", 0)
        )

        # Sales
        sales_volume = _parse_sales(
            item.get("monthSales", 0)
            or item.get("totalSales", 0)
            or item.get("sales", 0)
            or item.get("repurchaseRate", 0)
        )

        # Supplier info
        supplier_name = (
            item.get("shopName", "")
            or item.get("companyName", "")
            or item.get("supplier", "")
        )
        supplier_years = int(item.get("shopYears", 0) or item.get("years", 0) or 0)
        rating = float(item.get("rating", 0) or item.get("score", 0) or 0)

        # Image
        image_url = (
            item.get("imageUrl", "")
            or item.get("image", "")
            or item.get("imgUrl", "")
        )
        if image_url and not image_url.startswith("http"):
            image_url = "https:" + image_url

        # Min order
        min_order = int(item.get("minOrder", 1) or item.get("quantityBegin", 1) or 1)

        # Translate title
        title_ru = _translate(title_cn)

        # Generate WB keyword from Russian title
        wb_keyword = _extract_wb_keyword(title_ru)

        return RawProduct(
            source="1688",
            source_url=source_url,
            title_cn=title_cn,
            title_ru=title_ru,
            category=category,
            price_cny=price_cny,
            min_order=min_order,
            sales_volume=sales_volume,
            sales_trend=0.0,
            rating=rating,
            supplier_name=supplier_name,
            supplier_years=supplier_years,
            image_url=image_url,
            wb_keyword=wb_keyword,
            wb_est_price=0.0,
            collected_at=datetime.now(timezone.utc),
        )
