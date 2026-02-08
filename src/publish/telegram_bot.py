"""Publish posts to Telegram channel via Bot API."""

from __future__ import annotations

import httpx
from loguru import logger

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from src.models import TelegramPost


async def send_post(post: TelegramPost) -> TelegramPost:
    """Send a post to the Telegram channel.

    Returns the post with updated published status and message_id.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return post

    if not TELEGRAM_CHANNEL_ID:
        logger.error("TELEGRAM_CHANNEL_ID not set")
        return post

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": post.text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if data.get("ok"):
            post.published = True
            post.message_id = data["result"]["message_id"]
            logger.info(
                "Published to {} (message_id={})",
                TELEGRAM_CHANNEL_ID,
                post.message_id,
            )
        else:
            logger.error("Telegram API error: {}", data.get("description"))

    except Exception as e:
        logger.error("Failed to send to Telegram: {}", e)

    return post


async def test_connection() -> bool:
    """Test if the bot token is valid and can post to the channel."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            data = resp.json()
        if data.get("ok"):
            bot_name = data["result"]["username"]
            logger.info("Bot connected: @{}", bot_name)
            return True
        else:
            logger.error("Bot auth failed: {}", data.get("description"))
            return False
    except Exception as e:
        logger.error("Connection test failed: {}", e)
        return False
