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
    "kitchen": "厨房用品 爆款 小工具",
    "pet": "宠物用品 爆款 智能",
    "sport": "运动装备 健身 爆款",
    "office": "办公用品 创意 桌面",
    "kids": "儿童用品 益智 爆款",
}

_translator = GoogleTranslator(source="zh-CN", target="ru")

# Short exact stopwords (prepositions, particles, connectors)
_RU_STOP_EXACT = frozenset(
    "для с и в на от из по к о не без при до через под над хит мини "
    "все это тот эта как что где или его".split()
)

# Stem prefixes for Chinese marketing jargon — matches any word starting with these
_RU_JUNK_STEMS = (
    "трансгранич", "популярн", "креативн", "интернет-знаменитост",
    "продаж", "фабрик", "оптов", "красив", "уникальн",
    "европейск", "британск", "американск", "стандартн",
    "интеллектуальн", "продаваем", "горяч", "товар",
    "продукт", "новых", "новый", "новая", "новое", "новые",
    "подходит", "подходящ", "применяет", "применим",
    "бестселлер", "считанн", "модн", "классическ",
    "второ", "изменени", "однотонн", "волнист",
    "готов", "прямые", "заводск",
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


def _trim_title(title_ru: str, max_words: int = 10) -> str:
    """Trim translated title: strip marketing jargon prefixes, limit length."""
    cleaned = title_ru
    # Remove leading marketing jargon — apply repeatedly to catch stacked prefixes
    junk_prefixes = [
        r"^прямые продажи с фабрики\s*",
        r"^трансграничн\w*\s+(горяч\w*\s+продаж\w*|хит\s+продаж|товар\w*)\s*",
        r"^трансграничн\w*\s*",
        r"^хит\s+продаж[,.\s]*",
        r"^интернет-знаменитости[,.\s]*",
        r"^горяч\w*\s+",
        r"^креативн\w*\s+",
        r"^популярн\w*\s+",
        r"^британск\w*\s+стандартн\w*\s*",
        r"^европейск\w*\s+стандартн\w*\s*",
        r"^американск\w*\s+стандартн\w*\s*",
    ]
    for _ in range(3):  # repeat to catch stacked junk
        prev = cleaned
        for pattern in junk_prefixes:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        if cleaned == prev:
            break
    # Remove leading commas/dots left after cleanup
    cleaned = cleaned.lstrip(",. ")
    # Capitalize first letter
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    # Trim to max words
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words])
    return cleaned


def _is_junk_word(word: str) -> bool:
    """Check if a word is a stopword or matches a junk stem."""
    if word in _RU_STOP_EXACT:
        return True
    return any(word.startswith(stem) for stem in _RU_JUNK_STEMS)


def _extract_wb_keyword(title_ru: str) -> str:
    """Extract a short WB search keyword from Russian product title.

    Strategy: take first 2 unique meaningful words as they appear in the title,
    preserving natural Russian word order (e.g. "стиральная машина", not "машина").
    """
    cleaned = re.sub(r"[,.()\[\]{}\"/\\!?;:]+", " ", title_ru.lower())
    seen = set()
    result = []

    for w in cleaned.split():
        if w in seen or len(w) <= 2 or w.isdigit() or _is_junk_word(w):
            continue
        seen.add(w)
        result.append(w)
        if len(result) >= 2:
            break

    return " ".join(result)


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
            "queries": [keyword],
            "maxItems": limit,
        }

        logger.debug("Running Apify actor '{}' with keyword '{}'", APIFY_1688_ACTOR_ID, keyword)

        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        run = await loop.run_in_executor(
            None,
            lambda: client.actor(APIFY_1688_ACTOR_ID).call(
                run_input=actor_input,
                timeout_secs=180,
            ),
        )

        # Fetch results from the default dataset
        dataset_items = client.dataset(run["defaultDatasetId"]).list_items().items
        logger.debug("Apify returned {} items", len(dataset_items))
        return dataset_items

    def _map_item(self, item: dict, category: str) -> RawProduct | None:
        """Map Apify JSON item to RawProduct (devcake/1688-com-products-scraper format)."""
        title_cn = item.get("title", "")
        if not title_cn:
            return None

        # URL
        source_url = item.get("detail_url", "") or item.get("detailUrl", "")
        if source_url and not source_url.startswith("http"):
            source_url = "https:" + source_url
        if not source_url:
            return None

        # Price — try multiple sources: integer+decimal, price string, quantity_prices
        price_cny = 0.0
        if item.get("price_integer") is not None:
            try:
                price_cny = float(str(item["price_integer"]) + str(item.get("price_decimal", "")))
            except (ValueError, TypeError):
                price_cny = 0.0
        if price_cny == 0.0:
            price_cny = _parse_price(item.get("price", 0))
        # Fallback: take price from quantity_prices list
        if price_cny == 0.0:
            qty_list = item.get("quantity_prices", [])
            if qty_list and isinstance(qty_list, list):
                price_cny = _parse_price(qty_list[0].get("price", 0))

        # Sales from order_count
        sales_volume = _parse_sales(item.get("order_count", 0))

        # Supplier info
        supplier_name = item.get("shop_name", "") or item.get("shopName", "")
        supplier_years = 0
        rating = 0.0

        # Repurchase rate as a proxy for reliability (e.g. "33%" -> 3.3)
        repurchase = item.get("repurchase_rate", "")
        if isinstance(repurchase, str) and "%" in repurchase:
            try:
                rating = float(repurchase.replace("%", "")) / 10.0
            except ValueError:
                pass

        # Image
        image_url = item.get("image_url", "") or item.get("imageUrl", "")
        if image_url and not image_url.startswith("http"):
            image_url = "https:" + image_url

        # Min order from quantity_prices
        min_order = 1
        qty_prices = item.get("quantity_prices", [])
        if qty_prices and isinstance(qty_prices, list):
            qty_str = qty_prices[0].get("quantity", "")
            m = re.search(r"(\d+)", str(qty_str))
            if m:
                min_order = int(m.group(1))

        # Skip products with no price — useless for analysis
        if price_cny <= 0:
            logger.debug("Skipping item with price=0: {}", title_cn[:40])
            return None

        # Translate title and trim to reasonable length
        title_ru = _translate(title_cn)
        title_ru = _trim_title(title_ru)

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
