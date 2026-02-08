"""Quick test to verify all components are configured correctly.

Usage:
    python -m scripts.test_setup
"""

from __future__ import annotations

import asyncio
import sys
import os
from pathlib import Path

# Fix Windows console encoding
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, DB_PATH
from src.db import init_db
from src.publish.telegram_bot import test_connection


async def main() -> None:
    print("=" * 50)
    print("ALGORA — Setup Test")
    print("=" * 50)
    all_ok = True

    # 1. Check .env
    print("\n[1] Checking .env configuration...")

    if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY.startswith("sk-"):
        print("  ✓ ANTHROPIC_API_KEY is set")
    else:
        print("  ✗ ANTHROPIC_API_KEY missing or invalid")
        all_ok = False

    if TELEGRAM_BOT_TOKEN and ":" in TELEGRAM_BOT_TOKEN:
        print("  ✓ TELEGRAM_BOT_TOKEN is set")
    else:
        print("  ✗ TELEGRAM_BOT_TOKEN missing or invalid")
        all_ok = False

    if TELEGRAM_CHANNEL_ID:
        print(f"  ✓ TELEGRAM_CHANNEL_ID = {TELEGRAM_CHANNEL_ID}")
    else:
        print("  ✗ TELEGRAM_CHANNEL_ID missing")
        all_ok = False

    # 2. Check database
    print("\n[2] Checking database...")
    try:
        init_db()
        print(f"  ✓ Database ready at {DB_PATH}")
    except Exception as e:
        print(f"  ✗ Database error: {e}")
        all_ok = False

    # 3. Test Telegram bot
    print("\n[3] Testing Telegram bot connection...")
    if TELEGRAM_BOT_TOKEN:
        ok = await test_connection()
        if ok:
            print("  ✓ Bot is connected")
        else:
            print("  ✗ Bot connection failed")
            all_ok = False
    else:
        print("  - Skipped (no token)")

    # 4. Test Claude API
    print("\n[4] Testing Claude API...")
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=50,
                messages=[{"role": "user", "content": "Say 'OK' if you can read this."}],
            )
            response = msg.content[0].text.strip()
            print(f"  ✓ Claude API works (response: {response})")
        except Exception as e:
            print(f"  ✗ Claude API error: {e}")
            all_ok = False
    else:
        print("  - Skipped (no key)")

    # Summary
    print("\n" + "=" * 50)
    if all_ok:
        print("ALL CHECKS PASSED ✓")
        print("\nRun the pipeline:")
        print("  python -m scripts.run_pipeline --dry-run")
    else:
        print("SOME CHECKS FAILED ✗")
        print("\nFix the issues above, then re-run this test.")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
