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
            source_url TEXT NOT NULL UNIQUE,
            post_text TEXT NOT NULL,
            message_id INTEGER,
            published_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS channel_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            subscribers INTEGER DEFAULT 0,
            posts_total INTEGER DEFAULT 0,
            recorded_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
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


def save_published_post(post: TelegramPost) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO published_posts
            (source_url, post_text, message_id, published_at)
            VALUES (?, ?, ?, ?)""",
            (
                post.product.raw.source_url,
                post.text,
                post.message_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def is_already_published(source_url: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM published_posts WHERE source_url = ?", (source_url,)
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
