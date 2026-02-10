"""Algora Scheduler — automated posting on schedule.

Runs the pipeline automatically at configured times.
Posts 2 times per day with rotating categories.

Usage:
    python -X utf8 -m scripts.scheduler              # run scheduler
    python -X utf8 -m scripts.scheduler --once        # single run now, then exit
    python -X utf8 -m scripts.scheduler --test        # dry-run single post
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

import schedule
from loguru import logger

from scripts.run_pipeline import run as run_pipeline
from src.db import init_db, save_channel_stats, get_published_posts_count
from src.publish.telegram_bot import get_channel_info

# All available categories for rotation
ALL_CATEGORIES = [
    "electronics", "gadgets", "home", "phone_accessories",
    "car_accessories", "led_lighting", "beauty_devices", "smart_home",
    "outdoor", "toys", "health", "kitchen", "pet", "sport", "office", "kids",
]

# Posting schedule (Moscow time = UTC+3)
# Morning post: 10:00 MSK = 07:00 UTC
# Evening post: 18:00 MSK = 15:00 UTC
MORNING_UTC = "07:00"
EVENING_UTC = "15:00"

# Track which categories were used recently to avoid repeats
_recent_categories: list[str] = []


def _pick_category() -> str:
    """Pick a category that hasn't been used recently."""
    available = [c for c in ALL_CATEGORIES if c not in _recent_categories]
    if not available:
        _recent_categories.clear()
        available = ALL_CATEGORIES

    cat = random.choice(available)
    _recent_categories.append(cat)

    # Keep only last 8 to allow repeats after a while
    if len(_recent_categories) > 8:
        _recent_categories.pop(0)

    return cat


def _post_job(source: str = "1688", top_n: int = 1, dry_run: bool = False) -> None:
    """Run pipeline for a single post."""
    category = _pick_category()
    now = datetime.now().strftime("%H:%M:%S")
    logger.info("=== Scheduler job at {} | category={} source={} ===", now, category, source)

    try:
        asyncio.run(run_pipeline(
            category=category,
            dry_run=dry_run,
            source=source,
            top_n=top_n,
        ))
    except Exception as e:
        logger.error("Scheduler job failed: {}", e)

    # Save daily stats snapshot
    try:
        asyncio.run(_save_stats())
    except Exception as e:
        logger.debug("Stats snapshot failed: {}", e)


async def _save_stats() -> None:
    init_db()
    info = await get_channel_info()
    subscribers = info.get("subscribers", 0)
    posts = get_published_posts_count()
    if subscribers > 0:
        save_channel_stats(subscribers, posts)


def run_scheduler(source: str = "1688", dry_run: bool = False) -> None:
    """Start the scheduler loop."""
    logger.info("=== ALGORA Scheduler START ===")
    logger.info("Schedule: {} UTC (10:00 MSK) and {} UTC (18:00 MSK)", MORNING_UTC, EVENING_UTC)
    logger.info("Source: {} | Dry run: {}", source, dry_run)

    # Schedule jobs
    schedule.every().day.at(MORNING_UTC).do(_post_job, source=source, dry_run=dry_run)
    schedule.every().day.at(EVENING_UTC).do(_post_job, source=source, dry_run=dry_run)

    # Show next run
    next_run = schedule.next_run()
    logger.info("Next scheduled run: {}", next_run)

    # Keep running
    try:
        while True:
            schedule.run_pending()
            # Check every 30 seconds
            import time
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")


def main() -> None:
    parser = argparse.ArgumentParser(description="Algora Scheduler")
    parser.add_argument(
        "--source",
        default="1688",
        choices=["demo", "1688", "cache"],
        help="Data source (default: 1688)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once immediately and exit (no schedule loop)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Dry run: generate but don't publish",
    )
    args = parser.parse_args()

    init_db()

    if args.once or args.test:
        # Single run
        _post_job(source=args.source, top_n=1, dry_run=args.test)
    else:
        # Continuous scheduler
        run_scheduler(source=args.source, dry_run=False)


if __name__ == "__main__":
    main()
