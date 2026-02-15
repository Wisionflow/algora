"""Algora configuration — loads settings from .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Load .env
load_dotenv(ROOT_DIR / ".env")

# Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")

# Premium channel (disabled until 1K+ free subscribers)
TELEGRAM_PREMIUM_CHANNEL_ID = os.getenv("TELEGRAM_PREMIUM_CHANNEL_ID", "")
PREMIUM_ENABLED = os.getenv("PREMIUM_ENABLED", "false").lower() in ("true", "1", "yes")

# VK (VKontakte)
VK_API_TOKEN = os.getenv("VK_API_TOKEN", "")       # Community access token
VK_GROUP_ID = os.getenv("VK_GROUP_ID", "")          # Group ID (without minus)
VK_API_VERSION = "5.199"

# Apify (1688.com data)
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
APIFY_1688_ACTOR_ID = os.getenv("APIFY_1688_ACTOR_ID", "devcake/1688-com-products-scraper")

# Database
DB_PATH = DATA_DIR / "algora.db"

# Parsing
REQUEST_DELAY = 2.0  # seconds between requests
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# Exchange rates
CNY_TO_RUB_FALLBACK = 12.5  # used when CBR API is unreachable
_cny_rate_cache: dict = {}  # {"rate": float, "fetched_at": datetime}


def get_cny_to_rub() -> float:
    """Get current CNY/RUB rate from CBR API with 24h cache.

    Falls back to CNY_TO_RUB_FALLBACK if API is unreachable.
    """
    import xml.etree.ElementTree as ET
    from datetime import datetime, timedelta, timezone

    import httpx

    # Check cache (valid for 24 hours)
    if _cny_rate_cache:
        age = datetime.now(timezone.utc) - _cny_rate_cache["fetched_at"]
        if age < timedelta(hours=24):
            return _cny_rate_cache["rate"]

    try:
        resp = httpx.get("https://www.cbr.ru/scripts/XML_daily.asp", timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        for valute in root.findall("Valute"):
            char_code = valute.findtext("CharCode", "")
            if char_code == "CNY":
                nominal = int(valute.findtext("Nominal", "1"))
                value_str = valute.findtext("Value", "0").replace(",", ".")
                rate = float(value_str) / nominal
                _cny_rate_cache["rate"] = rate
                _cny_rate_cache["fetched_at"] = datetime.now(timezone.utc)
                return rate

    except Exception:
        pass

    return _cny_rate_cache.get("rate", CNY_TO_RUB_FALLBACK)


# Legacy constant — modules that import CNY_TO_RUB still work,
# but scoring.py now uses get_cny_to_rub() for live rates
CNY_TO_RUB = CNY_TO_RUB_FALLBACK

# Scoring weights
TREND_WEIGHT = 0.35
COMPETITION_WEIGHT = 0.25
MARGIN_WEIGHT = 0.30
RELIABILITY_WEIGHT = 0.10

# Content
MAX_POSTS_PER_DAY = 3
POST_MAX_LENGTH = 1500
