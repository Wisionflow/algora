"""Algora Analytics — channel stats and product performance.

Usage:
    python -X utf8 -m scripts.analytics
    python -X utf8 -m scripts.analytics --save    # save daily snapshot
    python -X utf8 -m scripts.analytics --report   # full weekly report
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
    get_posts_by_type,
    get_posts_by_category,
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

    print(f"\n  Канал: @algora_trends")
    print(f"  Подписчиков: {subscribers}")
    print(f"  Постов опубликовано: {posts_count}")

    # Save snapshot if requested
    if save_snapshot and subscribers > 0:
        save_channel_stats(subscribers, posts_count)
        print("  Снимок статистики сохранён")

    # History
    history = get_channel_stats_history(14)
    if history:
        print(f"\n  История (последние {len(history)} дней):")
        print(f"  {'Дата':<12} {'Подписчики':>12} {'Постов':>8} {'Дельта':>8}")
        print(f"  {'-'*12} {'-'*12} {'-'*8} {'-'*8}")
        reversed_history = list(reversed(history))
        for i, row in enumerate(reversed_history):
            delta = ""
            if i > 0:
                diff = row["subscribers"] - reversed_history[i - 1]["subscribers"]
                delta = f"+{diff}" if diff >= 0 else str(diff)
            print(f"  {row['date']:<12} {row['subscribers']:>12} {row['posts_total']:>8} {delta:>8}")

        # Growth summary
        if len(history) >= 2:
            newest = history[0]["subscribers"]
            oldest = history[-1]["subscribers"]
            growth = newest - oldest
            days = len(history)
            avg_daily = growth / days if days > 0 else 0
            sign = "+" if growth >= 0 else ""
            print(f"\n  Рост за {days} дней: {sign}{growth} подписчиков")
            print(f"  Среднедневной рост: {avg_daily:+.1f} подписчиков/день")

    # Top products
    top = get_top_products(5)
    if top:
        print(f"\n  Топ-5 товаров по рейтингу:")
        for i, p in enumerate(top, 1):
            raw = json.loads(p["raw_json"])
            title = raw.get("title_ru", raw.get("title_cn", "???"))[:40]
            print(f"  {i}. {title}")
            print(f"     Score: {p['total_score']:.1f}/10 | Маржа: {p['margin_pct']:.0f}%")

    print("\n" + "=" * 50 + "\n")


async def show_weekly_report(save_snapshot: bool = False) -> None:
    """Full weekly report: growth, posts by type, categories, top products."""
    init_db()

    print("\n" + "=" * 60)
    print("  ALGORA WEEKLY REPORT")
    print("=" * 60)

    # Channel stats
    info = await get_channel_info()
    subscribers = info.get("subscribers", 0)
    posts_count = get_published_posts_count()

    if save_snapshot and subscribers > 0:
        save_channel_stats(subscribers, posts_count)

    print(f"\n  Подписчиков: {subscribers}")
    print(f"  Всего постов: {posts_count}")

    # Subscriber growth
    history = get_channel_stats_history(30)
    if history:
        print(f"\n  --- Рост подписчиков (30 дней) ---")
        if len(history) >= 2:
            newest = history[0]["subscribers"]
            oldest = history[-1]["subscribers"]
            growth = newest - oldest
            days = len(history)
            avg_daily = growth / days if days > 0 else 0

            # Find best and worst days
            reversed_history = list(reversed(history))
            best_day = ("", 0)
            worst_day = ("", 0)
            for i in range(1, len(reversed_history)):
                diff = reversed_history[i]["subscribers"] - reversed_history[i - 1]["subscribers"]
                if diff > best_day[1]:
                    best_day = (reversed_history[i]["date"], diff)
                if diff < worst_day[1]:
                    worst_day = (reversed_history[i]["date"], diff)

            sign = "+" if growth >= 0 else ""
            print(f"  Общий рост: {sign}{growth}")
            print(f"  Средний/день: {avg_daily:+.1f}")
            if best_day[0]:
                print(f"  Лучший день: {best_day[0]} (+{best_day[1]})")
            if worst_day[0] and worst_day[1] < 0:
                print(f"  Худший день: {worst_day[0]} ({worst_day[1]})")
        else:
            print("  Недостаточно данных")

    # Posts by type
    by_type = get_posts_by_type()
    if by_type:
        print(f"\n  --- Посты по типам ---")
        type_labels = {
            "product": "Находка дня",
            "niche_review": "Обзор ниши",
            "weekly_top": "Топ недели",
            "beginner_mistake": "Ошибка новичка",
            "product_of_week": "Товар недели",
        }
        for row in by_type:
            label = type_labels.get(row["post_type"], row["post_type"] or "Без типа")
            print(f"  {label:<25} {row['cnt']:>5} постов")

    # Posts by category
    by_cat = get_posts_by_category()
    if by_cat:
        print(f"\n  --- Посты по категориям (топ-10) ---")
        for row in by_cat[:10]:
            cat = row["category"] or "Без категории"
            print(f"  {cat:<25} {row['cnt']:>5} постов")

    # Top products
    top = get_top_products(10)
    if top:
        print(f"\n  --- Топ-10 товаров по рейтингу ---")
        for i, p in enumerate(top, 1):
            raw = json.loads(p["raw_json"])
            title = raw.get("title_ru", raw.get("title_cn", "???"))[:35]
            print(f"  {i:>2}. {title}")
            print(f"      Score: {p['total_score']:.1f} | Маржа: {p['margin_pct']:.0f}% | Конкурентов: {p['wb_competitors']}")

    print("\n" + "=" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Algora Analytics")
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save daily stats snapshot to DB",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Show full weekly report",
    )
    args = parser.parse_args()

    if args.report:
        asyncio.run(show_weekly_report(save_snapshot=args.save))
    else:
        asyncio.run(show_analytics(save_snapshot=args.save))


if __name__ == "__main__":
    main()
