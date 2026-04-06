"""Configuration for Algora Growth Agent. Loads from .env file."""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# --- Telegram userbot (Telethon) ---
TG_API_ID: int = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH: str = os.getenv("TG_API_HASH", "")
TG_PHONE: str = os.getenv("TG_PHONE", "")           # +7XXXXXXXXXX
TG_SESSION_NAME: str = os.getenv("TG_SESSION_NAME", "growth_agent")

# --- Agent identity ---
AGENT_NAME: str = os.getenv("AGENT_NAME", "Максим")
CHANNEL_LINK: str = os.getenv("CHANNEL_LINK", "@algora_trends")

# --- Claude API (direct) ---
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# --- PostgreSQL ---
POSTGRES_DSN: str = os.getenv("POSTGRES_DSN", "")

# --- Behaviour limits ---
MAX_MESSAGES_PER_CHAT_PER_DAY: int = int(os.getenv("MAX_MESSAGES_PER_DAY", "2"))
MIN_DELAY_BEFORE_REPLY_SEC: int = 60
MAX_DELAY_BEFORE_REPLY_SEC: int = 300
MIN_INTERVAL_BETWEEN_REPLIES_SEC: int = int(os.getenv("MIN_INTERVAL_SEC", "3600"))  # 1 hour
CHANNEL_LINK_EVERY_N_RESPONSES: int = 3   # legacy, no longer used for chat (links moved to DMs)

# --- Relevance filter keywords ---
# Set via RELEVANCE_KEYWORDS in .env as comma-separated list.
# Default: marketplace seller keywords (WB/Ozon/China import).
_kw_env = os.getenv("RELEVANCE_KEYWORDS", "")
if _kw_env.strip():
    RELEVANCE_KEYWORDS: list[str] = [k.strip() for k in _kw_env.split(",") if k.strip()]
else:
    RELEVANCE_KEYWORDS = [
        "маржа", "маржинальность", "товар", "товары",
        "китай", "1688", "alibaba", "поставщик", "поставщики",
        "закупка", "закупать", "фабрика", "завод",
        "импорт", "wb", "wildberries", "ozon", "озон",
        "продавец", "селлер", "маркетплейс",
        "карточка", "ниша", "конкуренция", "сток",
    ]

# Minimum relevance score to process a message (0.0–1.0)
MIN_RELEVANCE_SCORE: float = 0.3
