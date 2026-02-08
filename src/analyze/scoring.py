"""Automatic scoring of products — no AI needed here, pure math."""

from __future__ import annotations

from loguru import logger

from src.config import (
    CNY_TO_RUB,
    COMPETITION_WEIGHT,
    MARGIN_WEIGHT,
    RELIABILITY_WEIGHT,
    TREND_WEIGHT,
)
from src.models import AnalyzedProduct, RawProduct


def estimate_costs(product: RawProduct, cny_rate: float = CNY_TO_RUB) -> dict:
    """Estimate landed cost in Russia for a product."""
    price_rub = product.price_cny * cny_rate

    # Rough delivery estimate: 15-25% of product cost for small electronics
    delivery_pct = 0.20
    delivery_cost = price_rub * delivery_pct

    # Customs duty: ~15% average for electronics (duty + VAT simplified)
    customs_pct = 0.15
    customs_duty = price_rub * customs_pct

    total = price_rub + delivery_cost + customs_duty

    return {
        "price_rub": round(price_rub, 2),
        "delivery_cost_est": round(delivery_cost, 2),
        "customs_duty_est": round(customs_duty, 2),
        "total_landed_cost": round(total, 2),
    }


def compute_scores(
    product: RawProduct,
    total_landed_cost: float,
    wb_avg_price: float,
    wb_competitors: int,
) -> dict:
    """Compute individual scores (0-10) and total weighted score."""

    # Trend score: based on sales volume (as proxy for trend)
    if product.sales_volume >= 10000:
        trend = 10.0
    elif product.sales_volume >= 5000:
        trend = 8.0
    elif product.sales_volume >= 1000:
        trend = 6.0
    elif product.sales_volume >= 500:
        trend = 4.0
    elif product.sales_volume >= 100:
        trend = 2.0
    else:
        trend = 1.0

    # Competition score: fewer WB competitors = better
    if wb_competitors == 0:
        competition = 9.0  # no data or truly empty niche
    elif wb_competitors <= 5:
        competition = 8.0
    elif wb_competitors <= 20:
        competition = 6.0
    elif wb_competitors <= 50:
        competition = 4.0
    elif wb_competitors <= 100:
        competition = 2.0
    else:
        competition = 1.0

    # Margin score
    margin_pct = 0.0
    margin_rub = 0.0
    if total_landed_cost > 0 and wb_avg_price > 0:
        margin_rub = wb_avg_price - total_landed_cost
        margin_pct = (margin_rub / wb_avg_price) * 100

    if margin_pct >= 60:
        margin = 10.0
    elif margin_pct >= 45:
        margin = 8.0
    elif margin_pct >= 30:
        margin = 6.0
    elif margin_pct >= 15:
        margin = 4.0
    elif margin_pct > 0:
        margin = 2.0
    else:
        margin = 0.0

    # Reliability score: years on platform + rating
    reliability = min(10.0, product.supplier_years * 1.5 + product.rating * 1.5)

    # Total weighted score
    total = (
        trend * TREND_WEIGHT
        + competition * COMPETITION_WEIGHT
        + margin * MARGIN_WEIGHT
        + reliability * RELIABILITY_WEIGHT
    )

    return {
        "trend_score": round(trend, 1),
        "competition_score": round(competition, 1),
        "margin_score": round(margin, 1),
        "reliability_score": round(reliability, 1),
        "total_score": round(total, 2),
        "margin_pct": round(margin_pct, 1),
        "margin_rub": round(margin_rub, 2),
    }


def analyze_product(
    product: RawProduct,
    wb_avg_price: float = 0,
    wb_competitors: int = 0,
) -> AnalyzedProduct:
    """Full analysis pipeline for a single product."""
    costs = estimate_costs(product)
    scores = compute_scores(
        product,
        costs["total_landed_cost"],
        wb_avg_price,
        wb_competitors,
    )

    return AnalyzedProduct(
        raw=product,
        price_rub=costs["price_rub"],
        delivery_cost_est=costs["delivery_cost_est"],
        customs_duty_est=costs["customs_duty_est"],
        total_landed_cost=costs["total_landed_cost"],
        wb_avg_price=wb_avg_price,
        wb_competitors=wb_competitors,
        margin_pct=scores["margin_pct"],
        margin_rub=scores["margin_rub"],
        trend_score=scores["trend_score"],
        competition_score=scores["competition_score"],
        margin_score=scores["margin_score"],
        reliability_score=scores["reliability_score"],
        total_score=scores["total_score"],
    )
