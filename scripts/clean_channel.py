"""Clean up test posts from Telegram channel.

This script will list all posts and allow deletion of test/placeholder posts.

Usage:
    python -X utf8 scripts/clean_channel.py --list
    python -X utf8 scripts/clean_channel.py --delete <message_id>
    python -X utf8 scripts/clean_channel.py --delete-range <start_id> <end_id>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
API = f"https://api.telegram.org/bot{TOKEN}"


async def list_recent_posts(client: httpx.AsyncClient, limit: int = 20):
    """List recent posts from the channel."""
    print(f"\n📋 Recent posts in {CHANNEL}:")
    print("=" * 70)

    # Get channel info to find the latest message_id
    resp = await client.get(f"{API}/getChat", params={"chat_id": CHANNEL})
    data = resp.json()

    if not data.get("ok"):
        print(f"[ERROR] Failed to get chat info: {data.get('description')}")
        return

    # Try to get recent messages by iterating backwards
    # Note: Telegram Bot API doesn't have a direct "get all messages" method
    # We'll try to get messages by forwarding them to ourselves (read-only check)

    print("\n⚠️  Note: To see all posts, check the channel directly.")
    print("    Bot API has limited message retrieval capabilities.")
    print("\nTo delete a specific message, use:")
    print("    python -X utf8 scripts/clean_channel.py --delete <message_id>")
    print("\nTo delete multiple messages, use:")
    print("    python -X utf8 scripts/clean_channel.py --delete-range <start> <end>")
    print("=" * 70)


async def delete_message(client: httpx.AsyncClient, message_id: int):
    """Delete a specific message from the channel."""
    print(f"\n🗑️  Deleting message {message_id}...")

    resp = await client.post(
        f"{API}/deleteMessage",
        json={"chat_id": CHANNEL, "message_id": message_id},
    )
    data = resp.json()

    if data.get("ok"):
        print(f"[OK] Message {message_id} deleted")
        return True
    else:
        print(f"[ERROR] Failed to delete message {message_id}: {data.get('description')}")
        return False


async def delete_message_range(client: httpx.AsyncClient, start_id: int, end_id: int):
    """Delete a range of messages."""
    print(f"\n🗑️  Deleting messages from {start_id} to {end_id}...")

    deleted_count = 0
    failed_count = 0

    for msg_id in range(start_id, end_id + 1):
        success = await delete_message(client, msg_id)
        if success:
            deleted_count += 1
        else:
            failed_count += 1
        # Small delay to avoid rate limits
        await asyncio.sleep(0.5)

    print("\n" + "=" * 70)
    print(f"✓ Deleted: {deleted_count} messages")
    if failed_count > 0:
        print(f"✗ Failed: {failed_count} messages")
    print("=" * 70)


async def delete_all_except_pinned(client: httpx.AsyncClient):
    """Delete all messages except pinned ones."""
    print("\n⚠️  This will delete ALL messages except pinned ones!")
    print("This feature is not fully implemented due to API limitations.")
    print("Please use --delete or --delete-range for specific messages.")


async def main():
    parser = argparse.ArgumentParser(description="Clean up Telegram channel posts")
    parser.add_argument("--list", action="store_true", help="List recent posts")
    parser.add_argument("--delete", type=int, metavar="MESSAGE_ID", help="Delete specific message")
    parser.add_argument("--delete-range", nargs=2, type=int, metavar=("START", "END"), help="Delete range of messages")
    parser.add_argument("--delete-all-except-pinned", action="store_true", help="Delete all except pinned messages")

    args = parser.parse_args()

    if not TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN not set")
        return
    if not CHANNEL:
        print("[ERROR] TELEGRAM_CHANNEL_ID not set")
        return

    async with httpx.AsyncClient(timeout=30) as client:
        # Verify bot access
        resp = await client.get(f"{API}/getMe")
        bot_data = resp.json()
        if not bot_data.get("ok"):
            print(f"[ERROR] Bot auth failed: {bot_data.get('description')}")
            return

        print("=" * 70)
        print("ALGORA — Channel Cleanup")
        print(f"Bot: @{bot_data['result']['username']}")
        print(f"Channel: {CHANNEL}")
        print("=" * 70)

        if args.list:
            await list_recent_posts(client)
        elif args.delete:
            await delete_message(client, args.delete)
        elif args.delete_range:
            await delete_message_range(client, args.delete_range[0], args.delete_range[1])
        elif args.delete_all_except_pinned:
            await delete_all_except_pinned(client)
        else:
            print("\n[INFO] No action specified. Use --help to see options.")
            print("\nQuick commands:")
            print("  --list                        List recent posts")
            print("  --delete MESSAGE_ID           Delete one message")
            print("  --delete-range START END      Delete message range")


if __name__ == "__main__":
    asyncio.run(main())
