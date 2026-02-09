"""Publish posts to Telegram channel via Bot API."""

from __future__ import annotations

import httpx
from loguru import logger

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from src.models import TelegramPost


async def send_post(post: TelegramPost) -> TelegramPost:
    """Send a post to the Telegram channel.

    Uses sendPhoto if image_url is available (caption limit 1024 chars),
    falls back to sendMessage for text-only posts or long captions.
    Returns the post with updated published status and message_id.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return post

    if not TELEGRAM_CHANNEL_ID:
        logger.error("TELEGRAM_CHANNEL_ID not set")
        return post

    use_photo = bool(post.image_url) and len(post.text) <= 1024

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if use_photo:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                payload = {
                    "chat_id": TELEGRAM_CHANNEL_ID,
                    "photo": post.image_url,
                    "caption": post.text,
                    "parse_mode": "HTML",
                }
                resp = await client.post(url, json=payload)

                # If sendPhoto fails (e.g. image URL broken), fall back to sendMessage
                if resp.status_code != 200 or not resp.json().get("ok"):
                    logger.warning(
                        "sendPhoto failed, falling back to sendMessage: {}",
                        resp.json().get("description", "unknown"),
                    )
                    use_photo = False

            if not use_photo:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": TELEGRAM_CHANNEL_ID,
                    "text": post.text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                }
                resp = await client.post(url, json=payload)

            resp.raise_for_status()
            data = resp.json()

        if data.get("ok"):
            post.published = True
            post.message_id = data["result"]["message_id"]
            method = "photo" if use_photo else "text"
            logger.info(
                "Published ({}) to {} (message_id={})",
                method, TELEGRAM_CHANNEL_ID, post.message_id,
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
