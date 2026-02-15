"""SQLite database for Algora — stores products and published posts."""

import json
import sqlite3
from datetime import datetime, timezone

from loguru import logger

from src.config import DB_PATH
from src.models import AnalyzedProduct, RawProduct, TelegramPost


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS raw_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_url TEXT NOT NULL UNIQUE,
            title_cn TEXT,
            title_ru TEXT,
            category TEXT,
            price_cny REAL,
            min_order INTEGER,
            sales_volume INTEGER,
            sales_trend REAL,
            rating REAL,
            supplier_name TEXT,
            supplier_years INTEGER,
            image_url TEXT,
            specs TEXT,
            collected_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS analyzed_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_url TEXT NOT NULL UNIQUE,
            raw_json TEXT NOT NULL,
            price_rub REAL,
            delivery_cost_est REAL,
            customs_duty_est REAL,
            total_landed_cost REAL,
            wb_avg_price REAL,
            wb_competitors INTEGER,
            margin_pct REAL,
            margin_rub REAL,
            trend_score REAL,
            competition_score REAL,
            margin_score REAL,
            reliability_score REAL,
            total_score REAL,
            ai_insight TEXT,
            analyzed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS published_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_url TEXT NOT NULL,
            post_text TEXT NOT NULL,
            message_id INTEGER,
            platform TEXT NOT NULL DEFAULT 'telegram',
            published_at TEXT NOT NULL,
            UNIQUE(source_url, platform)
        );

        CREATE TABLE IF NOT EXISTS channel_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            subscribers INTEGER DEFAULT 0,
            posts_total INTEGER DEFAULT 0,
            recorded_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS post_engagement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            platform TEXT NOT NULL DEFAULT 'telegram',
            post_type TEXT,
            category TEXT,
            total_score REAL,
            views INTEGER DEFAULT 0,
            forwards INTEGER DEFAULT 0,
            reactions INTEGER DEFAULT 0,
            checked_at TEXT NOT NULL,
            UNIQUE(message_id, platform)
        );
        """
    )
    conn.commit()

    # Migrate: add 'platform' column to existing published_posts table
    try:
        conn.execute("ALTER TABLE published_posts ADD COLUMN platform TEXT NOT NULL DEFAULT 'telegram'")
        conn.commit()
        logger.debug("Migrated published_posts: added platform column")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Migrate: recreate unique index to include platform
    try:
        conn.execute("DROP INDEX IF EXISTS sqlite_autoindex_published_posts_1")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_published_url_platform "
            "ON published_posts(source_url, platform)"
        )
        conn.commit()
        logger.debug("Migrated published_posts: updated unique index")
    except sqlite3.OperationalError:
        pass

    # Migrate: add 'post_type' column to published_posts
    try:
        conn.execute("ALTER TABLE published_posts ADD COLUMN post_type TEXT")
        conn.commit()
        logger.debug("Migrated published_posts: added post_type column")
    except sqlite3.OperationalError:
        pass

    # Migrate: add 'category' column to published_posts
    try:
        conn.execute("ALTER TABLE published_posts ADD COLUMN category TEXT")
        conn.commit()
        logger.debug("Migrated published_posts: added category column")
    except sqlite3.OperationalError:
        pass

    # Migrate: add 'image_url' column to published_posts (for photo dedup)
    try:
        conn.execute("ALTER TABLE published_posts ADD COLUMN image_url TEXT")
        conn.commit()
        logger.debug("Migrated published_posts: added image_url column")
    except sqlite3.OperationalError:
        pass

    conn.close()
    logger.info("Database initialized at {}", DB_PATH)


def save_raw_product(product: RawProduct) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO raw_products
            (source, source_url, title_cn, title_ru, category, price_cny,
             min_order, sales_volume, sales_trend, rating, supplier_name,
             supplier_years, image_url, specs, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                product.source,
                product.source_url,
                product.title_cn,
                product.title_ru,
                product.category,
                product.price_cny,
                product.min_order,
                product.sales_volume,
                product.sales_trend,
                product.rating,
                product.supplier_name,
                product.supplier_years,
                product.image_url,
                json.dumps(product.specs, ensure_ascii=False),
                product.collected_at.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_analyzed_product(product: AnalyzedProduct) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO analyzed_products
            (source_url, raw_json, price_rub, delivery_cost_est, customs_duty_est,
             total_landed_cost, wb_avg_price, wb_competitors, margin_pct, margin_rub,
             trend_score, competition_score, margin_score, reliability_score,
             total_score, ai_insight, analyzed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                product.raw.source_url,
                product.raw.model_dump_json(),
                product.price_rub,
                product.delivery_cost_est,
                product.customs_duty_est,
                product.total_landed_cost,
                product.wb_avg_price,
                product.wb_competitors,
                product.margin_pct,
                product.margin_rub,
                product.trend_score,
                product.competition_score,
                product.margin_score,
                product.reliability_score,
                product.total_score,
                product.ai_insight,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_published_post(
    post: TelegramPost,
    platform: str = "telegram",
    post_type: str = "product",
    category: str = "",
    image_url: str = "",
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO published_posts
            (source_url, post_text, message_id, platform, published_at, post_type, category, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                post.product.raw.source_url,
                post.text,
                post.message_id,
                platform,
                datetime.now(timezone.utc).isoformat(),
                post_type,
                category,
                image_url,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_published_vk_post(
    source_url: str,
    text: str,
    post_id: int | None = None,
    post_type: str = "product",
    category: str = "",
    image_url: str = "",
) -> None:
    """Save a VK wall post to the published_posts table."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO published_posts
            (source_url, post_text, message_id, platform, published_at, post_type, category, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_url,
                text,
                post_id,
                "vk",
                datetime.now(timezone.utc).isoformat(),
                post_type,
                category,
                image_url,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def is_image_already_published(image_url: str) -> bool:
    """Check if this image URL has already been used in a published post.

    Returns True if duplicate — post should go without photo.
    """
    if not image_url:
        return False
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM published_posts WHERE image_url = ? AND image_url != '' LIMIT 1",
            (image_url,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def is_already_published(source_url: str, platform: str = "telegram") -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM published_posts WHERE source_url = ? AND platform = ?",
            (source_url, platform),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def save_channel_stats(subscribers: int, posts_total: int) -> None:
    """Save daily channel statistics snapshot."""
    conn = get_connection()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        conn.execute(
            """INSERT OR REPLACE INTO channel_stats
            (date, subscribers, posts_total, recorded_at)
            VALUES (?, ?, ?, ?)""",
            (today, subscribers, posts_total, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_channel_stats_history(days: int = 30) -> list[dict]:
    """Get channel stats for the last N days."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT date, subscribers, posts_total
            FROM channel_stats
            ORDER BY date DESC
            LIMIT ?""",
            (days,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_published_posts_count() -> int:
    """Get total count of published posts."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM published_posts").fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def get_top_products(limit: int = 10) -> list[dict]:
    """Get top analyzed products by score."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT source_url, raw_json, total_score, margin_pct,
                      wb_avg_price, wb_competitors, ai_insight
            FROM analyzed_products
            ORDER BY total_score DESC
            LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def save_post_engagement(
    message_id: int,
    platform: str = "telegram",
    post_type: str = "",
    category: str = "",
    total_score: float = 0.0,
) -> None:
    """Record post metadata for engagement tracking."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO post_engagement
            (message_id, platform, post_type, category, total_score, checked_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                message_id,
                platform,
                post_type,
                category,
                total_score,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_post_engagement(
    message_id: int,
    platform: str = "telegram",
    views: int = 0,
    forwards: int = 0,
    reactions: int = 0,
) -> None:
    """Update real engagement metrics for a post."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE post_engagement
            SET views = ?, forwards = ?, reactions = ?,
                checked_at = ?
            WHERE message_id = ? AND platform = ?""",
            (
                views,
                forwards,
                reactions,
                datetime.now(timezone.utc).isoformat(),
                message_id,
                platform,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_posts_for_engagement_update() -> list[dict]:
    """Get all posts that need engagement metrics updated."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT pe.message_id, pe.platform, pe.post_type, pe.category,
                      pe.total_score, pe.views, pe.forwards, pe.reactions
            FROM post_engagement pe
            ORDER BY pe.checked_at DESC"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_engagement_summary() -> dict:
    """Get aggregate engagement stats for reporting."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT
                COUNT(*) as total_posts,
                SUM(views) as total_views,
                SUM(forwards) as total_forwards,
                SUM(reactions) as total_reactions,
                ROUND(AVG(CASE WHEN views > 0 THEN views END), 1) as avg_views,
                MAX(views) as max_views
            FROM post_engagement
            WHERE platform = 'telegram'"""
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def get_engagement_by_post_type() -> list[dict]:
    """Get average engagement grouped by post type."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT post_type,
                      COUNT(*) as cnt,
                      ROUND(AVG(views), 1) as avg_views,
                      SUM(views) as total_views,
                      MAX(views) as max_views
            FROM post_engagement
            WHERE platform = 'telegram' AND views > 0
            GROUP BY post_type
            ORDER BY avg_views DESC"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_engagement_by_category() -> list[dict]:
    """Get average engagement grouped by category."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT category,
                      COUNT(*) as cnt,
                      ROUND(AVG(views), 1) as avg_views,
                      SUM(views) as total_views
            FROM post_engagement
            WHERE platform = 'telegram' AND views > 0
                  AND category IS NOT NULL AND category != ''
            GROUP BY category
            ORDER BY avg_views DESC"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_top_posts_by_views(limit: int = 5) -> list[dict]:
    """Get top posts by view count, joined with published_posts for text."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT pe.message_id, pe.platform, pe.post_type, pe.category,
                      pe.views, pe.forwards, pe.reactions, pe.total_score,
                      pp.source_url
            FROM post_engagement pe
            LEFT JOIN published_posts pp
                ON pe.message_id = pp.message_id AND pe.platform = pp.platform
            WHERE pe.views > 0
            ORDER BY pe.views DESC
            LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_posts_by_type() -> list[dict]:
    """Get post counts grouped by post_type."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT post_type, COUNT(*) as cnt
            FROM published_posts
            WHERE post_type IS NOT NULL
            GROUP BY post_type
            ORDER BY cnt DESC"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_posts_by_category() -> list[dict]:
    """Get post counts grouped by category."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT category, COUNT(*) as cnt
            FROM published_posts
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category
            ORDER BY cnt DESC"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
