"""Fetch real engagement metrics for published posts.

Telegram: scrapes the public embed widget (t.me/channel/msg_id?embed=1)
VK: uses wall.getById API
"""

from __future__ import annotations

import re

import httpx
from loguru import logger

from src.config import TELEGRAM_CHANNEL_ID, VK_API_TOKEN, VK_GROUP_ID, VK_API_VERSION


async def fetch_telegram_views(message_id: int) -> dict:
    """Fetch view count for a Telegram channel post via public embed widget.

    Returns {"views": int} or empty dict on failure.
    """
    channel = TELEGRAM_CHANNEL_ID.lstrip("@")
    if not channel:
        return {}

    url = f"https://t.me/{channel}/{message_id}?embed=1&userpic=false"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; AlgoraBot/1.0)",
            })

        if resp.status_code != 200:
            logger.debug("TG embed HTTP {}: msg={}", resp.status_code, message_id)
            return {}

        html = resp.text

        # Parse views: <span class="tgme_widget_message_views">123</span>
        m = re.search(r'tgme_widget_message_views">([^<]+)<', html)
        if not m:
            return {}

        views_text = m.group(1).strip()
        views = _parse_count(views_text)

        return {"views": views}

    except Exception as e:
        logger.debug("TG embed failed for msg={}: {}", message_id, e)
        return {}


async def fetch_vk_engagement(post_id: int) -> dict:
    """Fetch engagement metrics for a VK wall post via wall.getById.

    Returns {"views": int, "likes": int, "reposts": int, "comments": int}
    or empty dict on failure.
    """
    if not VK_API_TOKEN or not VK_GROUP_ID or not post_id:
        return {}

    owner_id = f"-{VK_GROUP_ID}"
    posts_param = f"{owner_id}_{post_id}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.vk.com/method/wall.getById",
                data={
                    "access_token": VK_API_TOKEN,
                    "v": VK_API_VERSION,
                    "posts": posts_param,
                },
            )
            data = resp.json()

        items = data.get("response", {}).get("items", [])
        if not items:
            # Fallback for older API response format
            items = data.get("response", [])

        if not items or not isinstance(items, list):
            logger.debug("VK wall.getById: no items for {}", posts_param)
            return {}

        post = items[0] if isinstance(items[0], dict) else {}

        return {
            "views": post.get("views", {}).get("count", 0),
            "likes": post.get("likes", {}).get("count", 0),
            "reposts": post.get("reposts", {}).get("count", 0),
            "comments": post.get("comments", {}).get("count", 0),
        }

    except Exception as e:
        logger.debug("VK engagement failed for {}: {}", posts_param, e)
        return {}


def _parse_count(text: str) -> int:
    """Parse compact view count: '3', '1.2K', '15K', '1.5M'."""
    text = text.strip().upper().replace(" ", "")
    if not text:
        return 0

    multiplier = 1
    if text.endswith("K"):
        multiplier = 1000
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]

    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0
