"""Actor — sends replies via Telethon with limits and random delays."""

import asyncio
import random
from datetime import datetime

from loguru import logger
from telethon import TelegramClient

from . import config, db
from .models import Message, BrainDecision, Response


class Actor:
    def __init__(self, client: TelegramClient):
        self._client = client

    async def act(self, message: Message, decision: BrainDecision) -> bool:
        """
        Send reply if decision says so and limits allow.
        Returns True if message was sent.
        """
        if not decision.should_respond or not decision.response_text:
            return False

        # Check schedule limits
        allowed = await db.is_chat_allowed(message.chat_id)
        if not allowed:
            logger.info(
                "Skipping reply in chat {} — limit reached or cooldown active",
                message.chat_id
            )
            return False

        # Random human-like delay
        delay = random.randint(
            config.MIN_DELAY_BEFORE_REPLY_SEC,
            config.MAX_DELAY_BEFORE_REPLY_SEC,
        )
        logger.debug("Waiting {} sec before reply...", delay)
        await asyncio.sleep(delay)

        # Get telegram_id of the chat
        chats = await db.get_active_chats()
        chat_map = {c["id"]: c["telegram_id"] for c in chats}
        tg_chat_id = chat_map.get(message.chat_id)
        if not tg_chat_id:
            logger.error("Cannot find telegram_id for chat_id={}", message.chat_id)
            return False

        # Send reply
        try:
            await self._client.send_message(
                entity=tg_chat_id,
                message=decision.response_text,
                reply_to=message.telegram_message_id,
            )
        except Exception as e:
            logger.error("Failed to send message in chat {}: {}", tg_chat_id, e)
            return False

        # Log to DB
        resp = Response(
            message_id=message.id,
            chat_id=message.chat_id,
            response_text=decision.response_text,
            included_channel_link=decision.include_channel_link,
            llm_model=decision.llm_model,
            llm_cost=decision.llm_cost,
            sent_at=datetime.utcnow(),
            reaction="unknown",
        )
        await db.save_response(resp)
        await db.increment_messages_today(message.chat_id)

        logger.info(
            "Replied in chat {} (link={}) | {}",
            tg_chat_id, decision.include_channel_link, decision.response_text[:80]
        )
        return True
