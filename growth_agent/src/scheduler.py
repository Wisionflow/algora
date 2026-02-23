"""Daily maintenance tasks for Growth Agent.

- Midnight: reset messages_today counters
- Can be extended to collect channel metrics, send summaries, etc.
"""

import asyncio
from datetime import datetime, time

from loguru import logger

from . import db


async def _wait_until(target: time) -> None:
    """Sleep until next occurrence of target UTC time."""
    now = datetime.utcnow()
    target_dt = datetime.combine(now.date(), target)
    if target_dt <= now:
        from datetime import timedelta
        target_dt += timedelta(days=1)
    wait_sec = (target_dt - now).total_seconds()
    logger.info("Scheduler: next reset at {} UTC ({:.0f}s)", target_dt, wait_sec)
    await asyncio.sleep(wait_sec)


async def run_daily_tasks() -> None:
    """Background coroutine: runs daily maintenance at 00:00 UTC."""
    RESET_AT = time(0, 0, 0)
    while True:
        await _wait_until(RESET_AT)
        logger.info("Running daily maintenance...")
        await db.reset_daily_counters()
