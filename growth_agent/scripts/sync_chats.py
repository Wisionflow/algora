"""Sync Telegram group dialogs into the chats table.

Reads all groups/supergroups from the Telethon account and upserts them
into the PostgreSQL `chats` table with our_status='joined'.
The Growth Agent LISTENER monitors only chats present in this table.

Usage (inside Docker):
    python -m scripts.sync_chats

Usage (local with .env):
    python -X utf8 -m scripts.sync_chats
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timezone

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

load_dotenv()

TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_PHONE = os.getenv("TG_PHONE", "")
TG_SESSION_NAME = os.getenv("TG_SESSION_NAME", "growth_agent")
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "")


async def main():
    if not POSTGRES_DSN:
        print("ERROR: POSTGRES_DSN not set")
        sys.exit(1)
    if not TG_API_ID or not TG_API_HASH:
        print("ERROR: TG_API_ID / TG_API_HASH not set")
        sys.exit(1)

    import asyncpg

    conn = await asyncpg.connect(POSTGRES_DSN)
    client = TelegramClient(TG_SESSION_NAME, TG_API_ID, TG_API_HASH)
    await client.start(phone=TG_PHONE)

    try:
        dialogs = await client.get_dialogs()
        synced = 0

        for dialog in dialogs:
            entity = dialog.entity

            # Only groups and supergroups (not channels, not users)
            is_group = False
            if isinstance(entity, Channel) and entity.megagroup:
                is_group = True
            elif isinstance(entity, Chat):
                is_group = True

            if not is_group:
                continue

            telegram_id = dialog.id
            title = dialog.title or ""
            members = getattr(entity, "participants_count", 0) or 0

            row = await conn.fetchrow(
                "SELECT id, our_status FROM chats WHERE telegram_id = $1",
                telegram_id,
            )

            if row:
                # Update existing
                await conn.execute(
                    """UPDATE chats SET title = $1, member_count = $2,
                       last_activity = $3 WHERE telegram_id = $4""",
                    title, members, datetime.now(timezone.utc), telegram_id,
                )
                status = row["our_status"]
                print(f"  updated: {title} ({members} members) [{status}]")
            else:
                # Insert new as 'joined'
                await conn.execute(
                    """INSERT INTO chats (telegram_id, title, topic, member_count,
                       our_status, joined_at, last_activity)
                       VALUES ($1, $2, $3, $4, 'joined', $5, $5)""",
                    telegram_id, title, "T1", members,
                    datetime.now(timezone.utc),
                )
                print(f"  NEW: {title} ({members} members) [joined]")

            synced += 1

        # Summary
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM chats WHERE our_status = 'joined'"
        )
        print(f"\nSynced {synced} groups. Active chats in DB: {total}")

    finally:
        await client.disconnect()
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
