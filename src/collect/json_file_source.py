"""Fallback collector that reads products from a local JSON cache file.

The cache can be populated by scripts/update_product_cache.py or
by exporting Apify results manually.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from src.config import DATA_DIR
from src.models import RawProduct

from .base import BaseCollector

CACHE_PATH = DATA_DIR / "products_cache.json"


class JsonFileCollector(BaseCollector):
    """Reads products from a local JSON cache file."""

    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or CACHE_PATH

    async def collect(self, category: str, limit: int = 20) -> list[RawProduct]:
        if not self.file_path.exists():
            logger.warning("No cached products file at {}", self.file_path)
            return []

        try:
            with open(self.file_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to read cache file: {}", e)
            return []

        if not data:
            logger.warning("Cache file is empty")
            return []

        # Filter by category if specified
        if category != "all":
            filtered = [p for p in data if p.get("category") == category]
            if filtered:
                data = filtered

        # Shuffle to avoid always publishing the same products
        random.shuffle(data)
        selected = data[:limit]

        products = []
        for item in selected:
            try:
                # Handle datetime field
                if "collected_at" in item and isinstance(item["collected_at"], str):
                    item["collected_at"] = datetime.fromisoformat(item["collected_at"])
                elif "collected_at" not in item:
                    item["collected_at"] = datetime.now(timezone.utc)
                products.append(RawProduct(**item))
            except Exception as e:
                logger.debug("Skipping cached item: {}", e)
                continue

        logger.info("Loaded {} products from cache (category='{}')", len(products), category)
        return products
