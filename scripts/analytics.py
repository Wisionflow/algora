"""Algora Analytics — channel stats, engagement, and product performance.

Usage:
    python -X utf8 -m scripts.analytics                     # quick stats
    python -X utf8 -m scripts.analytics --save               # save daily snapshot
    python -X utf8 -m scripts.analytics --report             # full weekly report
    python -X utf8 -m scripts.analytics --update-engagement  # fetch real views/likes
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
    get_posts_for_engagement_update,
    update_post_engagement,
    get_engagement_summary,
    get_engagement_by_post_type,
    get_engagement_by_category,
    get_top_posts_by_views,
)
from src.engagement import fetch_telegram_views, fetch_vk_engagement
from src.publish.telegram_bot import get_channel_info


# ---------------------------------------------------------------------------
# Engagement update
# ---------------------------------------------------------------------------

async def update_engagement() -> None:
    """Fetch real engagement metrics for all tracked posts."""
    init_db()
    posts = get_posts_for_engagement_update()

    if not posts:
        logger.info("No posts to update engagement for")
        return

    logger.info("Updating engagement for {} posts...", len(posts))
    updated = 0

    for post in posts:
        msg_id = post["message_id"]
        platform = post["platform"]

        if platform == "telegram":
            data = await fetch_telegram_views(msg_id)
            if data:
                update_post_engagement(
                    message_id=msg_id,
                    platform="telegram",
                    views=data.get("views", 0),
                )
                old_views = post["views"]
                new_views = data["views"]
                if new_views != old_views:
                    logger.info("  TG msg={}: {} → {} views", msg_id, old_views, new_views)
                updated += 1

        elif platform == "vk":
            data = await fetch_vk_engagement(msg_id)
            if data:
                update_post_engagement(
                    message_id=msg_id,
                    platform="vk",
                    views=data.get("views", 0),
                    forwards=data.get("reposts", 0),
                    reactions=data.get("likes", 0),
                )
                updated += 1
                logger.info(
                    "  VK post={}: {} views, {} likes, {} reposts",
                    msg_id, data.get("views", 0),
                    data.get("likes", 0), data.get("reposts", 0),
                )

        # Rate limiting: small delay between requests
        await asyncio.sleep(0.5)

    logger.info("Engagement updated for {}/{} posts", updated, len(posts))


# ---------------------------------------------------------------------------
# Analytics display
# ---------------------------------------------------------------------------

TYPE_LABELS = {
    "product": "Находка дня",
    "niche_review": "Обзор ниши",
    "weekly_top": "Топ недели",
    "beginner_mistake": "Ошибка новичка",
    "product_of_week": "Товар недели",
}


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

    # Engagement summary
    eng = get_engagement_summary()
    if eng and eng.get("total_views"):
        print(f"\n  --- Вовлечённость ---")
        print(f"  Всего просмотров: {eng['total_views']:,}")
        print(f"  Средние просмотры: {eng['avg_views']:.0f}/пост")
        print(f"  Макс просмотры: {eng['max_views']}")
        if eng.get("total_forwards"):
            print(f"  Пересылки: {eng['total_forwards']}")

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
    """Full weekly report: growth, engagement, posts by type, categories, top products."""
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

    # --- ENGAGEMENT ---
    eng = get_engagement_summary()
    if eng and eng.get("total_views"):
        print(f"\n  --- Вовлечённость (Telegram) ---")
        print(f"  Всего просмотров: {eng['total_views']:,}")
        print(f"  Средние просмотры/пост: {eng['avg_views']:.0f}")
        print(f"  Макс просмотры: {eng['max_views']}")
        if eng.get("total_forwards"):
            print(f"  Пересылки: {eng['total_forwards']}")
        if eng.get("total_reactions"):
            print(f"  Реакции: {eng['total_reactions']}")

    # Engagement by post type
    eng_by_type = get_engagement_by_post_type()
    if eng_by_type:
        print(f"\n  --- Просмотры по типам постов ---")
        print(f"  {'Тип':<25} {'Постов':>7} {'Ср.просм.':>10} {'Макс':>7}")
        print(f"  {'-'*25} {'-'*7} {'-'*10} {'-'*7}")
        for row in eng_by_type:
            label = TYPE_LABELS.get(row["post_type"], row["post_type"] or "Другое")
            print(f"  {label:<25} {row['cnt']:>7} {row['avg_views']:>10.0f} {row['max_views']:>7}")

    # Engagement by category
    eng_by_cat = get_engagement_by_category()
    if eng_by_cat:
        print(f"\n  --- Просмотры по категориям ---")
        print(f"  {'Категория':<25} {'Постов':>7} {'Ср.просм.':>10}")
        print(f"  {'-'*25} {'-'*7} {'-'*10}")
        for row in eng_by_cat[:10]:
            print(f"  {row['category']:<25} {row['cnt']:>7} {row['avg_views']:>10.0f}")

    # Top posts by views
    top_viewed = get_top_posts_by_views(5)
    if top_viewed:
        print(f"\n  --- Топ-5 постов по просмотрам ---")
        for i, p in enumerate(top_viewed, 1):
            ptype = TYPE_LABELS.get(p["post_type"], p["post_type"] or "?")
            cat = p["category"] or ""
            print(f"  {i}. {p['views']} просм. | {ptype} | {cat} | score={p['total_score']:.1f}")

    # Posts by type (count)
    by_type = get_posts_by_type()
    if by_type:
        print(f"\n  --- Посты по типам ---")
        for row in by_type:
            label = TYPE_LABELS.get(row["post_type"], row["post_type"] or "Без типа")
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
    parser.add_argument(
        "--update-engagement",
        action="store_true",
        help="Fetch real views/likes/reposts from Telegram and VK",
    )
    args = parser.parse_args()

    if args.update_engagement:
        asyncio.run(update_engagement())
        print()  # separator

    if args.report:
        asyncio.run(show_weekly_report(save_snapshot=args.save))
    elif not args.update_engagement:
        asyncio.run(show_analytics(save_snapshot=args.save))


if __name__ == "__main__":
    main()
