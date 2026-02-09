"""Wildberries market data collector.

Fetches competition data and average prices from WB search API
to estimate market conditions for a given product.
Uses a persistent session and retry with exponential backoff for rate limits (429).
"""

from __future__ import annotations

import asyncio
import time

import httpx
from loguru import logger

_EMPTY = {"avg_price": 0, "competitors": 0, "min_price": 0, "max_price": 0, "image_url": "", "product_url": ""}

MAX_RETRIES = 3
BASE_DELAY = 8.0  # seconds before first retry
MIN_REQUEST_GAP = 10.0  # minimum seconds between any WB requests

# Module-level rate limiter
_last_request_at: float = 0.0

# In-memory cache for WB results (avoid duplicate queries)
_wb_cache: dict[str, dict] = {}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
}

# Module-level persistent client (reuse connections)
_client: httpx.AsyncClient | None = None


def _wb_image_url(product_id: int) -> str:
    """Construct WB CDN image URL from product ID."""
    vol = product_id // 100000
    part = product_id // 1000
    if vol <= 143:
        basket = "01"
    elif vol <= 287:
        basket = "02"
    elif vol <= 431:
        basket = "03"
    elif vol <= 719:
        basket = "04"
    elif vol <= 1007:
        basket = "05"
    elif vol <= 1061:
        basket = "06"
    elif vol <= 1115:
        basket = "07"
    elif vol <= 1169:
        basket = "08"
    elif vol <= 1313:
        basket = "09"
    elif vol <= 1601:
        basket = "10"
    elif vol <= 1655:
        basket = "11"
    elif vol <= 1919:
        basket = "12"
    elif vol <= 2045:
        basket = "13"
    elif vol <= 2189:
        basket = "14"
    elif vol <= 2405:
        basket = "15"
    elif vol <= 2621:
        basket = "16"
    elif vol <= 2837:
        basket = "17"
    else:
        basket = "18"
    return f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{product_id}/images/big/1.webp"


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=15, headers=_HEADERS)
    return _client


async def get_wb_market_data(query: str, keyword: str = "") -> dict:
    """Search Wildberries for a product and return market stats.

    Args:
        query: Full product title (used as fallback).
        keyword: Short optimized WB search term (preferred).

    Uses keyword if provided, otherwise first 2 words of query.
    Retries up to 3 times with exponential backoff on 429.
    """
    # Prefer explicit keyword over auto-shortened query
    search_term = keyword.strip() if keyword else " ".join(query.split()[:2])

    if not search_term:
        return _EMPTY

    # Check cache to avoid duplicate WB requests
    if search_term in _wb_cache:
        logger.debug("WB cache hit for '{}'", search_term)
        return _wb_cache[search_term]

    url = "https://search.wb.ru/exactmatch/ru/common/v7/search"
    params = {
        "ab_testing": "false",
        "appType": "1",
        "curr": "rub",
        "dest": "-1257786",
        "query": search_term,
        "resultset": "catalog",
        "sort": "popular",
        "spp": "30",
    }

    client = await _get_client()

    global _last_request_at

    for attempt in range(MAX_RETRIES):
        # Enforce minimum gap between any WB requests
        now = time.monotonic()
        wait = MIN_REQUEST_GAP - (now - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)

        try:
            _last_request_at = time.monotonic()
            resp = await client.get(url, params=params)

            if resp.status_code == 429:
                delay = BASE_DELAY * (2 ** attempt)
                logger.debug(
                    "WB 429 for '{}', retry {}/{} in {}s",
                    search_term, attempt + 1, MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            data = resp.json()

        except httpx.HTTPStatusError:
            logger.warning("WB HTTP error for '{}'", search_term)
            _wb_cache[search_term] = _EMPTY
            return _EMPTY
        except Exception as e:
            logger.warning("WB request failed for '{}': {}", search_term, e)
            _wb_cache[search_term] = _EMPTY
            return _EMPTY

        # Parse response
        products = data.get("data", {}).get("products", [])
        if not products:
            logger.debug("WB: no results for '{}'", search_term)
            _wb_cache[search_term] = _EMPTY
            return _EMPTY

        prices = []
        for p in products[:50]:
            sale_price = p.get("salePriceU", 0) / 100
            if sale_price > 0:
                prices.append(sale_price)

        if not prices:
            _wb_cache[search_term] = _EMPTY
            return _EMPTY

        # Extract image and product page URL from the top result
        top_id = products[0].get("id", 0)
        image_url = _wb_image_url(top_id) if top_id else ""
        product_url = f"https://www.wildberries.ru/catalog/{top_id}/detail.aspx" if top_id else ""

        result = {
            "avg_price": round(sum(prices) / len(prices), 2),
            "competitors": len(products),
            "min_price": min(prices),
            "max_price": max(prices),
            "image_url": image_url,
            "product_url": product_url,
        }
        logger.debug(
            "WB '{}': avg={}r, {} competitors",
            search_term, result["avg_price"], result["competitors"],
        )
        _wb_cache[search_term] = result
        return result

    # All retries exhausted
    logger.warning("WB: all retries exhausted for '{}'", search_term)
    _wb_cache[search_term] = _EMPTY
    return _EMPTY
