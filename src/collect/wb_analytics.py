"""Wildberries market data collector.

Fetches competition data and average prices from WB search API
to estimate market conditions for a given product.
Uses a persistent session and retry with exponential backoff for rate limits (429).
"""

from __future__ import annotations

import asyncio

import httpx
from loguru import logger

_EMPTY = {"avg_price": 0, "competitors": 0, "min_price": 0, "max_price": 0}

MAX_RETRIES = 3
BASE_DELAY = 5.0  # seconds before first retry

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

    for attempt in range(MAX_RETRIES):
        try:
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
            return _EMPTY
        except Exception as e:
            logger.warning("WB request failed for '{}': {}", search_term, e)
            return _EMPTY

        # Parse response
        products = data.get("data", {}).get("products", [])
        if not products:
            logger.debug("WB: no results for '{}'", search_term)
            return _EMPTY

        prices = []
        for p in products[:50]:
            sale_price = p.get("salePriceU", 0) / 100
            if sale_price > 0:
                prices.append(sale_price)

        if not prices:
            return _EMPTY

        result = {
            "avg_price": round(sum(prices) / len(prices), 2),
            "competitors": len(products),
            "min_price": min(prices),
            "max_price": max(prices),
        }
        logger.debug(
            "WB '{}': avg={}r, {} competitors",
            search_term, result["avg_price"], result["competitors"],
        )
        return result

    # All retries exhausted
    logger.warning("WB: all retries exhausted for '{}'", search_term)
    return _EMPTY
