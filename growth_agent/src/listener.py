"""Telegram userbot listener (Telethon).

Monitors chats from DB, filters relevant messages, saves to messages table.
Brain is called asynchronously for relevant messages.
"""

from datetime import datetime
from typing import Callable, Awaitable

from loguru import logger
from telethon import TelegramClient, events
from telethon.tl.types import Message as TgMessage

from . import config
from . import db
from .models import Message
from .relevance import compute_relevance as _compute_relevance


class Listener:
    def __init__(
        self,
        on_relevant_message: Callable[[Message], Awaitable[None]],
    ):
        """
        on_relevant_message: async callback called when a relevant message is saved.
        Passes the saved Message (with DB id) to Brain.
        """
        self._callback = on_relevant_message
        self._client: TelegramClient | None = None
        self._chat_ids: set[int] = set()  # telegram_id of monitored chats

    async def start(self) -> None:
        """Authenticate and connect Telethon client."""
        self._client = TelegramClient(
            config.TG_SESSION_NAME,
            config.TG_API_ID,
            config.TG_API_HASH,
        )
        await self._client.start(phone=config.TG_PHONE)
        logger.info("Telethon client started as {}", config.TG_PHONE)

        await self._refresh_chat_list()
        self._register_handlers()

    async def _refresh_chat_list(self) -> None:
        """Reload active chats from DB."""
        chats = await db.get_active_chats()
        self._chat_ids = {c["telegram_id"] for c in chats}
        logger.info("Monitoring {} chats", len(self._chat_ids))

    def _register_handlers(self) -> None:
        assert self._client is not None

        @self._client.on(events.NewMessage)
        async def handler(event: events.NewMessage.Event):
            msg: TgMessage = event.message

            # Only process chats we monitor
            chat_id_tg = event.chat_id
            if chat_id_tg not in self._chat_ids:
                return

            text = msg.message or ""
            if not text.strip():
                return

            score = _compute_relevance(text)
            is_relevant = score >= config.MIN_RELEVANCE_SCORE

            # Get internal chat_id from DB
            chats = await db.get_active_chats()
            chat_map = {c["telegram_id"]: c["id"] for c in chats}
            internal_chat_id = chat_map.get(chat_id_tg)
            if not internal_chat_id:
                return

            sender = await event.get_sender()
            sender_name = getattr(sender, "username", None) or getattr(sender, "first_name", "unknown")

            message = Message(
                chat_id=internal_chat_id,
                telegram_message_id=msg.id,
                sender_name=str(sender_name),
                text=text,
                is_relevant=is_relevant,
                relevance_score=score,
                created_at=datetime.utcnow(),
            )

            saved_id = await db.save_message(message)
            if saved_id == 0:
                return  # duplicate, skip

            message.id = saved_id

            if is_relevant:
                logger.debug(
                    "Relevant message (score={:.2f}) in chat {} from {}: {}",
                    score, chat_id_tg, sender_name, text[:80]
                )
                await self._callback(message)

    async def run_until_disconnected(self) -> None:
        assert self._client is not None
        await self._client.run_until_disconnected()

    async def stop(self) -> None:
        if self._client:
            await self._client.disconnect()
            logger.info("Telethon client disconnected")
