"""Trend detection and market opportunity classification."""

from __future__ import annotations


def detect_trend_status(sales_volume: int) -> tuple[str, str]:
    """Detect product trend status based on sales volume.

    Args:
        sales_volume: Monthly sales volume in China (1688 data)

    Returns:
        Tuple of (status_text, emoji)
        - "TRENDING UP", "🔥" — high sales (>= 5000/month)
        - "GROWING", "📈" — good sales (>= 1000/month)
        - "STABLE", "→" — moderate sales (>= 100/month)
        - "DECLINING", "📉" — low sales (< 100/month)
        - "", "" — no data (sales_volume == 0)

    Example:
        >>> detect_trend_status(8500)
        ("TRENDING UP", "🔥")
        >>> detect_trend_status(350)
        ("STABLE", "→")
    """
    if sales_volume == 0:
        return ("", "")

    if sales_volume >= 5000:
        return ("TRENDING UP", "🔥")
    elif sales_volume >= 1000:
        return ("GROWING", "📈")
    elif sales_volume >= 100:
        return ("STABLE", "→")
    else:
        return ("DECLINING", "📉")


def detect_market_opportunity(
    sales_volume: int,
    competitors: int,
    margin_pct: float,
) -> tuple[str, str]:
    """Detect market opportunity based on sales, competition, and margin.

    Blue Ocean Strategy: High demand + low competition + good margins

    Args:
        sales_volume: Monthly sales in China
        competitors: Number of sellers on WB
        margin_pct: Profit margin percentage

    Returns:
        Tuple of (opportunity_text, emoji)
        - "BLUE OCEAN", "💎" — high sales, low competition, good margin
        - "NICHE", "🎯" — good sales, low competition
        - "SATURATED", "🏅" — high competition
        - "", "" — insufficient data or neutral market

    Example:
        >>> detect_market_opportunity(8500, 12, 45.0)
        ("BLUE OCEAN", "💎")
        >>> detect_market_opportunity(500, 120, 25.0)
        ("SATURATED", "🏅")
    """
    # Not enough data to classify
    if sales_volume == 0 and competitors == 0:
        return ("", "")

    # Blue Ocean: high sales + low competition + good margin
    if sales_volume >= 1000 and competitors < 20 and margin_pct > 30:
        return ("BLUE OCEAN", "💎")

    # Niche opportunity: decent sales + low competition
    if sales_volume >= 500 and competitors < 30:
        return ("NICHE", "🎯")

    # Saturated market: too many sellers
    if competitors > 50:
        return ("SATURATED", "🏅")

    # Neutral market
    return ("", "")


def calculate_trend_confidence(
    has_sales_data: bool,
    has_wb_data: bool,
    has_margin_data: bool,
) -> float:
    """Calculate confidence score (0-1) for trend detection.

    Confidence is based on data completeness:
    - Sales data available: +0.4
    - WB competitor data available: +0.3
    - Margin data available: +0.3

    Args:
        has_sales_data: Whether sales_volume > 0
        has_wb_data: Whether wb_competitors > 0
        has_margin_data: Whether margin_pct calculated

    Returns:
        Float confidence score (0.0 - 1.0)

    Example:
        >>> calculate_trend_confidence(True, True, True)
        1.0
        >>> calculate_trend_confidence(True, False, True)
        0.7
    """
    confidence = 0.0

    if has_sales_data:
        confidence += 0.4

    if has_wb_data:
        confidence += 0.3

    if has_margin_data:
        confidence += 0.3

    return min(confidence, 1.0)


def detect_trends(
    sales_volume: int,
    competitors: int,
    margin_pct: float,
) -> dict:
    """Detect all trend indicators for a product.

    This is the main entry point for trend detection.

    Args:
        sales_volume: Monthly sales in China
        competitors: Number of WB sellers
        margin_pct: Profit margin percentage

    Returns:
        Dict with:
            - trending_status: str
            - trending_emoji: str
            - market_opportunity: str
            - market_emoji: str
            - trend_confidence: float (0-1)

    Example:
        >>> detect_trends(8500, 12, 45.0)
        {
            "trending_status": "TRENDING UP",
            "trending_emoji": "🔥",
            "market_opportunity": "BLUE OCEAN",
            "market_emoji": "💎",
            "trend_confidence": 1.0
        }
    """
    trending_status, trending_emoji = detect_trend_status(sales_volume)
    market_opportunity, market_emoji = detect_market_opportunity(
        sales_volume, competitors, margin_pct
    )

    confidence = calculate_trend_confidence(
        has_sales_data=sales_volume > 0,
        has_wb_data=competitors > 0,
        has_margin_data=margin_pct != 0.0,
    )

    return {
        "trending_status": trending_status,
        "trending_emoji": trending_emoji,
        "market_opportunity": market_opportunity,
        "market_emoji": market_emoji,
        "trend_confidence": confidence,
    }
