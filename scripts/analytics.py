"""Algora Analytics — channel stats and product performance.

Usage:
    python -X utf8 -m scripts.analytics
    python -X utf8 -m scripts.analytics --save    # save daily snapshot
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.db import (
    init_db,
    get_channel_stats_history,
    get_published_posts_count,
    get_top_products,
    save_channel_stats,
)
from src.publish.telegram_bot import get_channel_info


async def show_analytics(save_snapshot: bool = False) -> None:
    init_db()

    print("\n" + "=" * 50)
    print("  ALGORA ANALYTICS")
    print("=" * 50)

    # Channel stats
    info = await get_channel_info()
    subscribers = info.get("subscribers", 0)
    posts_count = get_published_posts_count()

    print(f"\n📊 Канал: @algora_trends")
    print(f"👥 Подписчиков: {subscribers}")
    print(f"📝 Постов опубликовано: {posts_count}")

    # Save snapshot if requested
    if save_snapshot and subscribers > 0:
        save_channel_stats(subscribers, posts_count)
        print("💾 Снимок статистики сохранён")

    # History
    history = get_channel_stats_history(14)
    if history:
        print(f"\n📈 История (последние {len(history)} дней):")
        print(f"  {'Дата':<12} {'Подписчики':>12} {'Постов':>8}")
        print(f"  {'-'*12} {'-'*12} {'-'*8}")
        for row in reversed(history):
            print(f"  {row['date']:<12} {row['subscribers']:>12} {row['posts_total']:>8}")

        # Growth
        if len(history) >= 2:
            newest = history[0]["subscribers"]
            oldest = history[-1]["subscribers"]
            growth = newest - oldest
            sign = "+" if growth >= 0 else ""
            print(f"\n  Рост за период: {sign}{growth} подписчиков")

    # Top products
    top = get_top_products(5)
    if top:
        print(f"\n🏆 Топ-5 товаров по рейтингу:")
        for i, p in enumerate(top, 1):
            raw = json.loads(p["raw_json"])
            title = raw.get("title_ru", raw.get("title_cn", "???"))[:40]
            print(f"  {i}. {title}")
            print(f"     Score: {p['total_score']:.1f}/10 | Маржа: {p['margin_pct']:.0f}%")

    print("\n" + "=" * 50 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Algora Analytics")
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save daily stats snapshot to DB",
    )
    args = parser.parse_args()
    asyncio.run(show_analytics(save_snapshot=args.save))


if __name__ == "__main__":
    main()
