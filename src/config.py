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

# Database
DB_PATH = DATA_DIR / "algora.db"

# Parsing
REQUEST_DELAY = 2.0  # seconds between requests
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# Exchange rates (will be updated dynamically later)
CNY_TO_RUB = 12.5  # fallback rate

# Scoring weights
TREND_WEIGHT = 0.35
COMPETITION_WEIGHT = 0.25
MARGIN_WEIGHT = 0.30
RELIABILITY_WEIGHT = 0.10

# Content
MAX_POSTS_PER_DAY = 2
POST_MAX_LENGTH = 1500
