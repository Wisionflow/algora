"""Create all tables in algora_growth PostgreSQL database.

Run once before first launch:
    python -m scripts.setup_db
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DSN = os.getenv("POSTGRES_DSN", "")

SQL = """
CREATE TABLE IF NOT EXISTS chats (
    id              SERIAL PRIMARY KEY,
    telegram_id     BIGINT UNIQUE NOT NULL,
    title           TEXT NOT NULL,
    topic           TEXT NOT NULL,
    member_count    INT DEFAULT 0,
    rules_summary   TEXT,
    our_status      TEXT NOT NULL DEFAULT 'joined',
    joined_at       TIMESTAMPTZ DEFAULT NOW(),
    last_activity   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS messages (
    id                  SERIAL PRIMARY KEY,
    chat_id             INT NOT NULL REFERENCES chats(id),
    telegram_message_id BIGINT NOT NULL,
    sender_name         TEXT NOT NULL,
    text                TEXT NOT NULL,
    is_relevant         BOOLEAN DEFAULT FALSE,
    relevance_score     FLOAT DEFAULT 0.0,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (chat_id, telegram_message_id)
);

CREATE TABLE IF NOT EXISTS responses (
    id                    SERIAL PRIMARY KEY,
    message_id            INT NOT NULL REFERENCES messages(id),
    chat_id               INT NOT NULL REFERENCES chats(id),
    response_text         TEXT NOT NULL,
    included_channel_link BOOLEAN DEFAULT FALSE,
    llm_model             TEXT DEFAULT '',
    llm_cost              FLOAT DEFAULT 0.0,
    sent_at               TIMESTAMPTZ DEFAULT NOW(),
    reaction              TEXT DEFAULT 'unknown'
);

CREATE TABLE IF NOT EXISTS metrics (
    id                  SERIAL PRIMARY KEY,
    date                DATE UNIQUE NOT NULL,
    channel_subscribers INT DEFAULT 0,
    new_subscribers     INT DEFAULT 0,
    messages_sent       INT DEFAULT 0,
    chats_active        INT DEFAULT 0,
    best_chat_id        INT REFERENCES chats(id),
    total_llm_cost      FLOAT DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS schedule (
    id                    SERIAL PRIMARY KEY,
    chat_id               INT UNIQUE NOT NULL REFERENCES chats(id),
    max_messages_per_day  INT DEFAULT 3,
    messages_today        INT DEFAULT 0,
    last_message_at       TIMESTAMPTZ,
    is_active             BOOLEAN DEFAULT TRUE,
    cooldown_until        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_created ON messages(chat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_responses_chat_sent   ON responses(chat_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_metrics_date          ON metrics(date);
"""


async def main():
    if not DSN:
        print("ERROR: POSTGRES_DSN not set in .env")
        sys.exit(1)

    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute(SQL)
        print("All tables created (or already exist).")

        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        print("Tables in database:", [t["tablename"] for t in tables])
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
