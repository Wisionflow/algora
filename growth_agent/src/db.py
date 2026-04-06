"""PostgreSQL CRUD operations for Algora Growth Agent.

Uses asyncpg for async access. Connection pool is initialized once on startup.
"""

from datetime import datetime, date, timezone
from typing import Optional

import asyncpg
from loguru import logger

from .models import Chat, Message, Response, Metrics, Schedule

_pool: Optional[asyncpg.Pool] = None


async def init_pool(dsn: str) -> None:
    """Initialize connection pool. Call once at startup."""
    global _pool
    _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
    logger.info("DB pool initialized")


async def close_pool() -> None:
    if _pool:
        await _pool.close()
        logger.info("DB pool closed")


def _pool_or_raise() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call init_pool() first.")
    return _pool


# --- CHATS ---

async def upsert_chat(chat: Chat) -> int:
    """Insert or update chat by telegram_id. Returns internal id."""
    pool = _pool_or_raise()
    row = await pool.fetchrow("""
        INSERT INTO chats (telegram_id, title, topic, member_count, rules_summary,
                           our_status, joined_at, last_activity)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (telegram_id) DO UPDATE SET
            title = EXCLUDED.title,
            member_count = EXCLUDED.member_count,
            our_status = EXCLUDED.our_status,
            last_activity = EXCLUDED.last_activity
        RETURNING id
    """,
        chat.telegram_id, chat.title, chat.topic, chat.member_count,
        chat.rules_summary, chat.our_status,
        chat.joined_at or datetime.now(timezone.utc), chat.last_activity
    )
    return row["id"]


async def get_active_chats() -> list[dict]:
    """Return all chats with our_status='joined'."""
    pool = _pool_or_raise()
    rows = await pool.fetch("SELECT * FROM chats WHERE our_status = 'joined'")
    return [dict(r) for r in rows]


async def update_chat_status(telegram_id: int, status: str) -> None:
    pool = _pool_or_raise()
    await pool.execute(
        "UPDATE chats SET our_status = $1 WHERE telegram_id = $2",
        status, telegram_id
    )


# --- MESSAGES ---

async def save_message(msg: Message) -> int:
    """Save incoming message. Returns internal id."""
    pool = _pool_or_raise()
    row = await pool.fetchrow("""
        INSERT INTO messages (chat_id, telegram_message_id, sender_name, text,
                              is_relevant, relevance_score, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT DO NOTHING
        RETURNING id
    """,
        msg.chat_id, msg.telegram_message_id, msg.sender_name, msg.text,
        msg.is_relevant, msg.relevance_score, msg.created_at or datetime.now(timezone.utc)
    )
    return row["id"] if row else 0


async def get_message_by_id(message_id: int) -> Optional[dict]:
    pool = _pool_or_raise()
    row = await pool.fetchrow("SELECT * FROM messages WHERE id = $1", message_id)
    return dict(row) if row else None


async def get_recent_messages(chat_id: int, limit: int = 5, before_id: int = 0) -> list[dict]:
    """Get recent messages in a chat for context. Returns oldest-first."""
    pool = _pool_or_raise()
    if before_id > 0:
        rows = await pool.fetch("""
            SELECT sender_name, text FROM messages
            WHERE chat_id = $1 AND id < $2
            ORDER BY id DESC LIMIT $3
        """, chat_id, before_id, limit)
    else:
        rows = await pool.fetch("""
            SELECT sender_name, text FROM messages
            WHERE chat_id = $1
            ORDER BY id DESC LIMIT $2
        """, chat_id, limit)
    return [dict(r) for r in reversed(rows)]


# --- RESPONSES ---

async def save_response(resp: Response) -> int:
    """Log sent response. Returns internal id."""
    pool = _pool_or_raise()
    row = await pool.fetchrow("""
        INSERT INTO responses (message_id, chat_id, response_text, included_channel_link,
                               llm_model, llm_cost, sent_at, reaction)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
    """,
        resp.message_id, resp.chat_id, resp.response_text, resp.included_channel_link,
        resp.llm_model, resp.llm_cost, resp.sent_at or datetime.now(timezone.utc), resp.reaction
    )
    return row["id"]


async def count_responses_today(chat_id: int) -> int:
    """Count responses sent to this chat today."""
    pool = _pool_or_raise()
    row = await pool.fetchrow("""
        SELECT COUNT(*) as cnt FROM responses
        WHERE chat_id = $1 AND sent_at >= CURRENT_DATE
    """, chat_id)
    return row["cnt"]


async def count_responses_for_link_ratio(chat_id: int, last_n: int = 5) -> int:
    """Count how many of last N responses included the channel link."""
    pool = _pool_or_raise()
    row = await pool.fetchrow("""
        SELECT COUNT(*) as cnt FROM (
            SELECT included_channel_link FROM responses
            WHERE chat_id = $1
            ORDER BY sent_at DESC
            LIMIT $2
        ) sub WHERE included_channel_link = true
    """, chat_id, last_n)
    return row["cnt"]


# --- METRICS ---

async def upsert_metrics(m: Metrics) -> None:
    pool = _pool_or_raise()
    await pool.execute("""
        INSERT INTO metrics (date, channel_subscribers, new_subscribers, messages_sent,
                             chats_active, best_chat_id, total_llm_cost)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (date) DO UPDATE SET
            channel_subscribers = EXCLUDED.channel_subscribers,
            new_subscribers = EXCLUDED.new_subscribers,
            messages_sent = metrics.messages_sent + EXCLUDED.messages_sent,
            chats_active = EXCLUDED.chats_active,
            best_chat_id = EXCLUDED.best_chat_id,
            total_llm_cost = metrics.total_llm_cost + EXCLUDED.total_llm_cost
    """,
        m.date, m.channel_subscribers, m.new_subscribers, m.messages_sent,
        m.chats_active, m.best_chat_id, m.total_llm_cost
    )


# --- SCHEDULE ---

async def get_or_create_schedule(chat_id: int) -> dict:
    """Get schedule for chat, create default if missing."""
    pool = _pool_or_raise()
    row = await pool.fetchrow("SELECT * FROM schedule WHERE chat_id = $1", chat_id)
    if row:
        return dict(row)
    await pool.execute(
        "INSERT INTO schedule (chat_id) VALUES ($1) ON CONFLICT DO NOTHING",
        chat_id
    )
    row = await pool.fetchrow("SELECT * FROM schedule WHERE chat_id = $1", chat_id)
    return dict(row)


async def increment_messages_today(chat_id: int) -> None:
    pool = _pool_or_raise()
    await pool.execute("""
        UPDATE schedule
        SET messages_today = messages_today + 1,
            last_message_at = NOW()
        WHERE chat_id = $1
    """, chat_id)


async def reset_daily_counters() -> None:
    """Reset messages_today for all chats. Call at midnight."""
    pool = _pool_or_raise()
    await pool.execute("UPDATE schedule SET messages_today = 0")
    logger.info("Daily message counters reset")


async def set_cooldown(chat_id: int, until: datetime) -> None:
    """Temporarily pause activity in a chat (e.g. after ban warning)."""
    pool = _pool_or_raise()
    await pool.execute(
        "UPDATE schedule SET cooldown_until = $1 WHERE chat_id = $2",
        until, chat_id
    )


async def deactivate_chat(chat_id: int, reason: str = "") -> None:
    """Permanently disable a chat (e.g. after ban — will never retry)."""
    pool = _pool_or_raise()
    await pool.execute(
        "UPDATE schedule SET is_active = false WHERE chat_id = $1",
        chat_id
    )
    await pool.execute(
        "UPDATE chats SET our_status = 'banned' WHERE id = $1",
        chat_id
    )
    logger.warning("Chat {} permanently deactivated: {}", chat_id, reason)


# --- DM INTERACTIONS ---

async def save_dm(sender_id: int, sender_name: str, message_text: str,
                  dm_type: str = "unknown", response_text: str | None = None,
                  responded: bool = False) -> int:
    """Save a DM interaction. Returns internal id."""
    pool = _pool_or_raise()
    row = await pool.fetchrow("""
        INSERT INTO dm_interactions (sender_id, sender_name, message_text, dm_type,
                                     response_text, responded, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        RETURNING id
    """, sender_id, sender_name, message_text, dm_type, response_text, responded)
    return row["id"]


async def get_last_dm_response_time(sender_id: int) -> Optional[datetime]:
    """Get timestamp of last DM response to this user. Returns None if never responded."""
    pool = _pool_or_raise()
    row = await pool.fetchrow("""
        SELECT created_at FROM dm_interactions
        WHERE sender_id = $1 AND responded = true
        ORDER BY created_at DESC LIMIT 1
    """, sender_id)
    return row["created_at"] if row else None


async def count_outbound_dms_today() -> int:
    """Count outbound follow-up DMs sent today (to limit daily volume)."""
    pool = _pool_or_raise()
    row = await pool.fetchrow("""
        SELECT COUNT(*) as cnt FROM dm_interactions
        WHERE dm_type = 'followup' AND created_at >= CURRENT_DATE
    """)
    return row["cnt"]


async def get_dm_stats() -> dict:
    """Get DM interaction statistics."""
    pool = _pool_or_raise()
    total = await pool.fetchrow("SELECT COUNT(*) as cnt FROM dm_interactions")
    responded = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM dm_interactions WHERE responded = true")
    by_type = await pool.fetch("""
        SELECT dm_type, COUNT(*) as cnt FROM dm_interactions
        GROUP BY dm_type ORDER BY cnt DESC
    """)
    return {
        "total_dms": total["cnt"],
        "responded": responded["cnt"],
        "by_type": {r["dm_type"]: r["cnt"] for r in by_type},
    }


# --- ANALYTICS QUERIES ---

async def get_agent_stats(days: int = 30) -> dict:
    """Get comprehensive agent performance stats for the last N days."""
    pool = _pool_or_raise()
    since = f"NOW() - INTERVAL '{days} days'"

    # Messages seen
    msgs = await pool.fetchrow(f"""
        SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE is_relevant) as relevant
        FROM messages WHERE created_at >= {since}
    """)

    # Responses sent
    resps = await pool.fetchrow(f"""
        SELECT COUNT(*) as total,
               COUNT(*) FILTER (WHERE included_channel_link) as with_link
        FROM responses WHERE sent_at >= {since}
    """)

    # Responses by chat
    by_chat = await pool.fetch(f"""
        SELECT c.title, c.member_count, COUNT(r.id) as responses,
               COUNT(r.id) FILTER (WHERE r.included_channel_link) as links
        FROM responses r JOIN chats c ON c.id = r.chat_id
        WHERE r.sent_at >= {since}
        GROUP BY c.title, c.member_count
        ORDER BY responses DESC
    """)

    # Active chats
    active = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM schedule WHERE is_active = true")

    # Banned chats
    banned = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM chats WHERE our_status = 'banned'")

    # DMs
    dms = await pool.fetchrow(f"""
        SELECT COUNT(*) as total,
               COUNT(*) FILTER (WHERE responded) as responded
        FROM dm_interactions WHERE created_at >= {since}
    """)

    # Daily breakdown (last 7 days)
    daily = await pool.fetch("""
        SELECT d.day,
               COALESCE(m.msgs, 0) as messages_seen,
               COALESCE(m.relevant, 0) as relevant_messages,
               COALESCE(r.responses, 0) as responses_sent,
               COALESCE(dm.dms, 0) as dms_received
        FROM generate_series(CURRENT_DATE - 6, CURRENT_DATE, '1 day'::interval) d(day)
        LEFT JOIN (
            SELECT created_at::date as day, COUNT(*) as msgs,
                   COUNT(*) FILTER (WHERE is_relevant) as relevant
            FROM messages GROUP BY day
        ) m ON m.day = d.day
        LEFT JOIN (
            SELECT sent_at::date as day, COUNT(*) as responses
            FROM responses GROUP BY day
        ) r ON r.day = d.day
        LEFT JOIN (
            SELECT created_at::date as day, COUNT(*) as dms
            FROM dm_interactions GROUP BY day
        ) dm ON dm.day = d.day
        ORDER BY d.day
    """)

    # Metrics history
    metrics_hist = await pool.fetch("""
        SELECT date, channel_subscribers, new_subscribers
        FROM metrics ORDER BY date DESC LIMIT 30
    """)

    return {
        "period_days": days,
        "messages_seen": msgs["total"],
        "messages_relevant": msgs["relevant"],
        "responses_sent": resps["total"],
        "responses_with_link": resps["with_link"],
        "active_chats": active["cnt"],
        "banned_chats": banned["cnt"],
        "dms_total": dms["total"] if dms["total"] else 0,
        "dms_responded": dms["responded"] if dms["responded"] else 0,
        "by_chat": [dict(r) for r in by_chat],
        "daily": [{"day": str(r["day"]), "messages_seen": r["messages_seen"],
                    "relevant": r["relevant_messages"],
                    "responses": r["responses_sent"],
                    "dms": r["dms_received"]} for r in daily],
        "subscriber_history": [{"date": str(r["date"]),
                                "subscribers": r["channel_subscribers"],
                                "new": r["new_subscribers"]} for r in metrics_hist],
    }


async def is_chat_allowed(chat_id: int) -> bool:
    """Check if we can send to this chat right now."""
    from . import config

    sched = await get_or_create_schedule(chat_id)
    if not sched["is_active"]:
        return False
    if sched["cooldown_until"] and sched["cooldown_until"] > datetime.now(timezone.utc):
        return False
    if sched["messages_today"] >= sched["max_messages_per_day"]:
        return False
    # Enforce minimum interval between replies in the same chat
    if sched["last_message_at"]:
        elapsed = (datetime.now(timezone.utc) - sched["last_message_at"]).total_seconds()
        if elapsed < config.MIN_INTERVAL_BETWEEN_REPLIES_SEC:
            return False
    return True
