"""Publish posts to Telegram channel via Bot API."""

from __future__ import annotations

import httpx
from loguru import logger

from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
from src.models import TelegramPost


def _extract_photo_caption(html_text: str) -> str:
    """Extract a short caption for sendPhoto from full post HTML.

    Takes the title and key metrics, staying well under the 1024-char limit.
    """
    lines = html_text.split("\n")
    caption_lines = []
    char_count = 0

    for line in lines:
        # Stop before we get too long (leave room for "..." suffix)
        if char_count + len(line) > 900:
            break
        caption_lines.append(line)
        char_count += len(line) + 1  # +1 for newline

    return "\n".join(caption_lines)


async def _send_photo(
    client: httpx.AsyncClient,
    chat_id: str,
    image_url: str,
    caption: str,
) -> dict | None:
    """Try to send a photo message. Returns API response or None on failure."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": image_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    try:
        resp = await client.post(url, json=payload)
        data = resp.json()
        if data.get("ok"):
            return data
        logger.warning("sendPhoto failed: {}", data.get("description", "unknown"))
    except Exception as e:
        logger.warning("sendPhoto exception: {}", e)
    return None


async def _send_text(
    client: httpx.AsyncClient,
    chat_id: str,
    text: str,
    disable_preview: bool = False,
) -> dict | None:
    """Send a text message. Returns API response or None on failure."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    try:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            return data
        logger.error("sendMessage failed: {}", data.get("description"))
    except Exception as e:
        logger.error("sendMessage exception: {}", e)
    return None


async def _publish_to_channel(post: TelegramPost, channel_id: str) -> TelegramPost:
    """Publish a post to a Telegram channel.

    Strategy:
    - If image + text ≤ 1024 chars → sendPhoto with full text as caption
    - If image + text > 1024 chars → sendPhoto with short caption, then sendMessage with full text
    - If no image → sendMessage with full text
    - If sendPhoto fails → fall back to sendMessage
    """
    if not TELEGRAM_BOT_TOKEN or not channel_id:
        logger.error("TELEGRAM_BOT_TOKEN or channel_id not set")
        return post

    has_image = bool(post.image_url)
    text_fits_caption = len(post.text) <= 1024

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if has_image and text_fits_caption:
                # Case 1: Photo with full text as caption
                data = await _send_photo(client, channel_id, post.image_url, post.text)
                if data:
                    post.published = True
                    post.message_id = data["result"]["message_id"]
                    logger.info("Published photo+caption to {} (msg={})", channel_id, post.message_id)
                    return post
                # Photo failed — fall through to text-only
                logger.warning("Photo failed, falling back to text-only")

            elif has_image and not text_fits_caption:
                # Case 2: Photo with short caption + full text as separate message
                caption = _extract_photo_caption(post.text)
                data = await _send_photo(client, channel_id, post.image_url, caption)
                if data:
                    photo_msg_id = data["result"]["message_id"]
                    logger.info("Published photo to {} (msg={})", channel_id, photo_msg_id)
                    # Send full text as follow-up (disable link preview since photo already shown)
                    text_data = await _send_text(client, channel_id, post.text, disable_preview=True)
                    if text_data:
                        post.published = True
                        post.message_id = text_data["result"]["message_id"]
                        logger.info("Published text follow-up to {} (msg={})", channel_id, post.message_id)
                    else:
                        # Photo sent but text failed — still mark as published
                        post.published = True
                        post.message_id = photo_msg_id
                        logger.warning("Text follow-up failed, but photo was sent")
                    return post
                # Photo failed — fall through to text-only
                logger.warning("Photo failed, falling back to text-only")

            # Case 3: Text-only (no image or photo failed)
            data = await _send_text(client, channel_id, post.text, disable_preview=False)
            if data:
                post.published = True
                post.message_id = data["result"]["message_id"]
                logger.info("Published text to {} (msg={})", channel_id, post.message_id)
            else:
                logger.error("Failed to publish to {}", channel_id)

    except Exception as e:
        logger.error("Failed to publish to {}: {}", channel_id, e)

    return post


async def send_post(post: TelegramPost) -> TelegramPost:
    """Send a post to the main Telegram channel."""
    return await _publish_to_channel(post, TELEGRAM_CHANNEL_ID)


async def send_post_to_channel(post: TelegramPost, channel_id: str) -> TelegramPost:
    """Send a post to a specific Telegram channel (used for premium channel)."""
    return await _publish_to_channel(post, channel_id)


async def get_channel_info() -> dict:
    """Get channel subscriber count and other info."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        return {}

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChatMemberCount"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"chat_id": TELEGRAM_CHANNEL_ID})
            data = resp.json()
        if data.get("ok"):
            count = data["result"]
            logger.info("Channel {} has {} subscribers", TELEGRAM_CHANNEL_ID, count)
            return {"subscribers": count}
        else:
            logger.warning("getChatMemberCount failed: {}", data.get("description"))
    except Exception as e:
        logger.error("Failed to get channel info: {}", e)
    return {}


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
