"""Data models for Algora pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class RawProduct(BaseModel):
    """Product data as collected from source."""

    source: str
    source_url: str
    title_cn: str = ""
    title_ru: str = ""
    category: str = ""
    price_cny: float = 0.0
    min_order: int = 1
    sales_volume: int = 0
    sales_trend: float = 0.0  # % growth over 30 days
    rating: float = 0.0
    supplier_name: str = ""
    supplier_years: int = 0
    image_url: str = ""
    specs: dict = Field(default_factory=dict)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalyzedProduct(BaseModel):
    """Product after analysis and scoring."""

    raw: RawProduct

    # Calculated costs
    price_rub: float = 0.0
    delivery_cost_est: float = 0.0
    customs_duty_est: float = 0.0
    total_landed_cost: float = 0.0

    # WB/Ozon market data
    wb_avg_price: float = 0.0
    wb_competitors: int = 0

    # Margins
    margin_pct: float = 0.0
    margin_rub: float = 0.0

    # Scores (0-10)
    trend_score: float = 0.0
    competition_score: float = 0.0
    margin_score: float = 0.0
    reliability_score: float = 0.0
    total_score: float = 0.0

    # AI insight
    ai_insight: str = ""


class TelegramPost(BaseModel):
    """Ready-to-publish Telegram post."""

    product: AnalyzedProduct
    text: str
    published: bool = False
    published_at: Optional[datetime] = None
    message_id: Optional[int] = None
