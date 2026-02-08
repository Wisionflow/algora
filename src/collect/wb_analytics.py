"""Wildberries market data collector.

Fetches competition data and average prices from WB search API
to estimate market conditions for a given product.
"""

from __future__ import annotations

import httpx
from loguru import logger


async def get_wb_market_data(query: str) -> dict:
    """Search Wildberries for a product and return market stats.

    Returns:
        dict with keys: avg_price (float), competitors (int), min_price, max_price
    """
    if not query:
        return {"avg_price": 0, "competitors": 0, "min_price": 0, "max_price": 0}

    url = "https://search.wb.ru/exactmatch/ru/common/v7/search"
    params = {
        "ab_testing": "false",
        "appType": "1",
        "curr": "rub",
        "dest": "-1257786",
        "query": query,
        "resultset": "catalog",
        "sort": "popular",
        "spp": "30",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("WB search failed for '{}': {}", query, e)
        return {"avg_price": 0, "competitors": 0, "min_price": 0, "max_price": 0}

    products = data.get("data", {}).get("products", [])
    if not products:
        return {"avg_price": 0, "competitors": 0, "min_price": 0, "max_price": 0}

    # Take first 50 results for stats
    prices = []
    for p in products[:50]:
        # WB returns price in kopecks
        sale_price = p.get("salePriceU", 0) / 100
        if sale_price > 0:
            prices.append(sale_price)

    if not prices:
        return {"avg_price": 0, "competitors": 0, "min_price": 0, "max_price": 0}

    return {
        "avg_price": round(sum(prices) / len(prices), 2),
        "competitors": len(products),
        "min_price": min(prices),
        "max_price": max(prices),
    }
