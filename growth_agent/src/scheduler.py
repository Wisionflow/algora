"""Daily maintenance and stats collection for Growth Agent.

- 00:00 UTC: reset messages_today counters
- 00:05 UTC: collect daily metrics (channel subscribers, activity stats)
"""

import asyncio
from datetime import datetime, date, time, timedelta, timezone

from loguru import logger

from . import db, config
from .models import Metrics


async def _wait_until(target: time) -> None:
    """Sleep until next occurrence of target UTC time."""
    now = datetime.now(timezone.utc)
    target_dt = datetime.combine(now.date(), target, tzinfo=timezone.utc)
    if target_dt <= now:
        target_dt += timedelta(days=1)
    wait_sec = (target_dt - now).total_seconds()
    logger.info("Scheduler: next task at {} UTC ({:.0f}s)", target_dt, wait_sec)
    await asyncio.sleep(wait_sec)


async def _collect_daily_metrics() -> None:
    """Collect and save daily metrics snapshot."""
    try:
        pool = db._pool_or_raise()
        today = date.today()

        # Count responses sent today
        row = await pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM responses WHERE sent_at::date = $1", today)
        messages_sent = row["cnt"]

        # Count active chats
        row = await pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM schedule WHERE is_active = true")
        chats_active = row["cnt"]

        # Find best performing chat (most responses today)
        best = await pool.fetchrow("""
            SELECT chat_id, COUNT(*) as cnt FROM responses
            WHERE sent_at::date = $1
            GROUP BY chat_id ORDER BY cnt DESC LIMIT 1
        """, today)
        best_chat_id = best["chat_id"] if best else None

        # Count DMs
        dms = await pool.fetchrow("""
            SELECT COUNT(*) as total,
                   COUNT(*) FILTER (WHERE responded) as responded
            FROM dm_interactions WHERE created_at::date = $1
        """, today)

        metrics = Metrics(
            date=today,
            channel_subscribers=0,  # will be filled by external script or Telegram API
            new_subscribers=0,
            messages_sent=messages_sent,
            chats_active=chats_active,
            best_chat_id=best_chat_id,
            total_llm_cost=0.0,
        )
        await db.upsert_metrics(metrics)

        logger.info(
            "Daily metrics saved: responses={}, active_chats={}, dms={}/{}",
            messages_sent, chats_active,
            dms["total"] if dms else 0, dms["responded"] if dms else 0
        )
    except Exception as e:
        logger.error("Failed to collect daily metrics: {}", e)


async def run_daily_tasks() -> None:
    """Background coroutine: runs daily maintenance at 00:00 UTC."""
    RESET_AT = time(0, 0, 0)
    METRICS_AT = time(0, 5, 0)
    while True:
        await _wait_until(RESET_AT)
        logger.info("Running daily maintenance...")
        await db.reset_daily_counters()

        # Wait 5 more minutes, then collect metrics
        await asyncio.sleep(300)
        await _collect_daily_metrics()
