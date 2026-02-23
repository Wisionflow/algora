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
AGENT_NAME: str = os.getenv("AGENT_NAME", "Алгора")
CHANNEL_LINK: str = os.getenv("CHANNEL_LINK", "@algora_trends")

# --- NATS (AI Proxy) ---
NATS_URL: str = os.getenv("NATS_URL", "nats://nats:4222")

# --- LLM model (via NATS AI Proxy) ---
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

# --- PostgreSQL ---
POSTGRES_DSN: str = os.getenv("POSTGRES_DSN", "")

# --- Behaviour limits ---
MAX_MESSAGES_PER_CHAT_PER_DAY: int = int(os.getenv("MAX_MESSAGES_PER_DAY", "3"))
MIN_DELAY_BEFORE_REPLY_SEC: int = 30
MAX_DELAY_BEFORE_REPLY_SEC: int = 120
CHANNEL_LINK_EVERY_N_RESPONSES: int = 5   # include link not more often than 1 in 5

# --- Relevance filter keywords (Russian) ---
RELEVANCE_KEYWORDS: list[str] = [
    "маржа", "маржинальность", "товар", "товары",
    "китай", "1688", "alibaba", "поставщик", "поставщики",
    "закупка", "закупать", "фабрика", "завод",
    "импорт", "wb", "wildberries", "ozon", "озон",
    "продавец", "селлер", "маркетплейс",
    "карточка", "ниша", "конкуренция", "сток",
]

# Minimum relevance score to process a message (0.0–1.0)
MIN_RELEVANCE_SCORE: float = 0.3
