"""Collector for 1688.com — China's largest wholesale marketplace.

Parses trending products from 1688.com search results.
Translates titles from Chinese to Russian.
"""

from __future__ import annotations

import asyncio
import random
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from loguru import logger

from src.config import REQUEST_DELAY, USER_AGENTS
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
}

translator = GoogleTranslator(source="zh-CN", target="ru")


def _translate(text: str) -> str:
    """Translate Chinese text to Russian. Returns original on failure."""
    if not text:
        return ""
    try:
        return translator.translate(text)
    except Exception:
        return text


class Collector1688(BaseCollector):
    """Collects trending products from 1688.com."""

    def __init__(self) -> None:
        self.base_url = "https://s.1688.com/selloffer/offer_search.htm"

    async def collect(self, category: str, limit: int = 20) -> list[RawProduct]:
        keyword = CATEGORY_KEYWORDS.get(category, category)
        logger.info("Collecting from 1688: category='{}', keyword='{}'", category, keyword)

        products: list[RawProduct] = []
        try:
            products = await self._search(keyword, limit)
        except Exception as e:
            logger.error("Failed to collect from 1688: {}", e)

        logger.info("Collected {} products for '{}'", len(products), category)
        return products

    async def _search(self, keyword: str, limit: int) -> list[RawProduct]:
        """Search 1688 and parse results."""
        params = {
            "keywords": keyword,
            "sortType": "va_sales",  # sort by sales volume
            "button_click": "top",
            "n": "y",
        }
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(self.base_url, params=params, headers=headers)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        return self._parse_search_results(soup, limit)

    def _parse_search_results(self, soup: BeautifulSoup, limit: int) -> list[RawProduct]:
        """Parse product cards from 1688 search results page."""
        products: list[RawProduct] = []

        # 1688 renders product cards in divs with offer data
        # The structure changes periodically — we try multiple selectors
        cards = soup.select("div[data-offer-id]")
        if not cards:
            cards = soup.select(".sm-offer-item")
        if not cards:
            cards = soup.select('[class*="offer"]')
            cards = [c for c in cards if c.find("a", href=True)]

        logger.debug("Found {} raw cards on page", len(cards))

        for card in cards[:limit]:
            try:
                product = self._parse_card(card)
                if product:
                    products.append(product)
            except Exception as e:
                logger.debug("Skipping card: {}", e)
                continue

            # Delay between translations
            if products:
                asyncio.get_event_loop()  # just to keep async context
                import time
                time.sleep(0.3)

        return products

    def _parse_card(self, card) -> RawProduct | None:
        """Parse a single product card."""
        # Title
        title_el = card.select_one("a[title]") or card.select_one(".title a")
        if not title_el:
            return None
        title_cn = title_el.get("title", "") or title_el.get_text(strip=True)
        if not title_cn:
            return None

        # URL
        href = title_el.get("href", "")
        if href and not href.startswith("http"):
            href = "https:" + href
        if not href:
            return None

        # Price
        price_text = ""
        price_el = card.select_one(".sm-offer-priceNum") or card.select_one('[class*="price"]')
        if price_el:
            price_text = price_el.get_text(strip=True).replace("¥", "").replace(",", "")
        price_cny = 0.0
        try:
            # Handle range prices like "12.5 - 18.0" — take the lower
            price_cny = float(price_text.split("-")[0].split("~")[0].strip())
        except (ValueError, IndexError):
            pass

        # Sales volume
        sales_text = ""
        sales_el = card.select_one('[class*="sale"]') or card.select_one('[class*="deal"]')
        if sales_el:
            sales_text = sales_el.get_text(strip=True)
        sales_volume = self._parse_sales(sales_text)

        # Image
        img_el = card.select_one("img[src]") or card.select_one("img[data-src]")
        image_url = ""
        if img_el:
            image_url = img_el.get("data-src") or img_el.get("src") or ""
            if image_url and not image_url.startswith("http"):
                image_url = "https:" + image_url

        # Supplier
        supplier_el = card.select_one('[class*="company"]') or card.select_one('[class*="supplier"]')
        supplier_name = supplier_el.get_text(strip=True) if supplier_el else ""

        # Translate title
        title_ru = _translate(title_cn)

        return RawProduct(
            source="1688",
            source_url=href,
            title_cn=title_cn,
            title_ru=title_ru,
            category="",
            price_cny=price_cny,
            min_order=1,
            sales_volume=sales_volume,
            sales_trend=0.0,
            rating=0.0,
            supplier_name=supplier_name,
            supplier_years=0,
            image_url=image_url,
        )

    @staticmethod
    def _parse_sales(text: str) -> int:
        """Parse sales volume from text like '1234笔' or '5.2万笔'."""
        import re
        text = text.replace(",", "").replace(" ", "")
        # Try 万 (10k) format
        m = re.search(r"([\d.]+)万", text)
        if m:
            return int(float(m.group(1)) * 10000)
        # Try plain number
        m = re.search(r"(\d+)", text)
        if m:
            return int(m.group(1))
        return 0
