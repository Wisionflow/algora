"""Graceful exit для Telethon-аккаунта Maxim (resumable freeze).

Запускается ВНУТРИ работающего контейнера algora_cmo_agent:
    docker exec algora_cmo_agent python -m scripts.graceful_exit

Использует ту же Telethon-сессию, что и listener (config.TG_SESSION_NAME),
поэтому не требует SMS-кода.

Шаги:
1. iter_dialogs() → data/dialogs_snapshot.json (initial state)
2. Для каждой группы / супергруппы / канала: LeaveChannelRequest
   или DeleteChatUserRequest (для basic groups).
3. Для каждого DM: send_read_acknowledge (mark-as-read, без удаления истории).
4. Все действия → data/exit_log.json (chat_id, title, type, action, timestamp).
5. Финальный iter_dialogs → data/dialogs_post_exit.json (verification).
6. .session НЕ удаляется — нужен для resume в другом проекте.

Resumable философия: список диалогов сохранён, session жива, история
DM на стороне собеседников нетронута. Maxim может быть перезапущен
позже с тем же аккаунтом и восстановить контекст.

Exit code 0 → handoff archive (.session, .env, prompts/, PG dump) может стартовать.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from loguru import logger
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserNotParticipantError
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.messages import DeleteChatUserRequest
from telethon.tl.types import Channel, Chat, User

from src import config

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

SNAPSHOT_FILE = DATA_DIR / "dialogs_snapshot.json"
EXIT_LOG_FILE = DATA_DIR / "exit_log.json"
POST_EXIT_FILE = DATA_DIR / "dialogs_post_exit.json"

SLEEP_BETWEEN_ACTIONS_SEC = 2.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify(entity) -> str:
    if isinstance(entity, User):
        return "dm"
    if isinstance(entity, Chat):
        return "basic_group"
    if isinstance(entity, Channel):
        if getattr(entity, "megagroup", False):
            return "supergroup"
        if getattr(entity, "broadcast", False):
            return "channel"
        return "channel_other"
    return "unknown"


def _serialize(dialog) -> dict:
    return {
        "id": dialog.id,
        "name": dialog.name or "",
        "type": _classify(dialog.entity),
        "is_user": dialog.is_user,
        "is_group": dialog.is_group,
        "is_channel": dialog.is_channel,
        "unread_count": dialog.unread_count,
    }


async def _leave(client: TelegramClient, dialog, me_id: int) -> tuple[str, str | None]:
    entity = dialog.entity
    try:
        if isinstance(entity, Channel):
            await client(LeaveChannelRequest(entity))
            return "ok", None
        if isinstance(entity, Chat):
            await client(DeleteChatUserRequest(chat_id=entity.id, user_id=me_id))
            return "ok", None
        return "skip", "unknown_entity_type"
    except FloodWaitError as e:
        logger.warning("FloodWait {}s while leaving {}", e.seconds, dialog.name)
        await asyncio.sleep(e.seconds + 1)
        return "fail", f"flood_wait_{e.seconds}s"
    except UserNotParticipantError:
        return "skip", "not_participant"
    except Exception as e:
        return "fail", f"{type(e).__name__}: {e}"


async def _mark_dm_read(client: TelegramClient, dialog) -> tuple[str, str | None]:
    try:
        await client.send_read_acknowledge(dialog.entity)
        return "ok", None
    except FloodWaitError as e:
        logger.warning("FloodWait {}s on DM {}", e.seconds, dialog.name)
        await asyncio.sleep(e.seconds + 1)
        return "fail", f"flood_wait_{e.seconds}s"
    except Exception as e:
        return "fail", f"{type(e).__name__}: {e}"


async def main() -> int:
    started_at = _now_iso()

    if not config.TG_API_ID or not config.TG_API_HASH:
        logger.error("TG_API_ID / TG_API_HASH not set — abort")
        return 1

    client = TelegramClient(
        config.TG_SESSION_NAME,
        config.TG_API_ID,
        config.TG_API_HASH,
    )
    await client.start(phone=config.TG_PHONE)
    me = await client.get_me()
    logger.info("Telethon connected as {} (id={})", config.TG_PHONE, me.id)

    dialogs = await client.get_dialogs()
    initial = [_serialize(d) for d in dialogs]
    SNAPSHOT_FILE.write_text(json.dumps({
        "captured_at": started_at,
        "phone": config.TG_PHONE,
        "session_name": config.TG_SESSION_NAME,
        "agent_name": config.AGENT_NAME,
        "me_id": me.id,
        "total": len(initial),
        "dialogs": initial,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Initial snapshot: {} dialogs -> {}", len(initial), SNAPSHOT_FILE)

    actions: list[dict] = []
    for dialog in dialogs:
        chat_type = _classify(dialog.entity)
        record = {
            "timestamp": _now_iso(),
            "chat_id": dialog.id,
            "title": dialog.name or "",
            "type": chat_type,
        }

        if chat_type == "dm":
            status, err = await _mark_dm_read(client, dialog)
            record["action"] = "mark_as_read"
        elif chat_type in ("basic_group", "supergroup", "channel", "channel_other"):
            status, err = await _leave(client, dialog, me.id)
            record["action"] = "leave"
        else:
            status, err = "skip", "unknown_type"
            record["action"] = "skip"

        record["status"] = status
        if err:
            record["error"] = err

        actions.append(record)
        logger.info(
            "{:>13} | {:>4} | {:>14} | {:>14} | {}",
            record["action"], status, chat_type, dialog.id, (dialog.name or "")[:60]
        )

        await asyncio.sleep(SLEEP_BETWEEN_ACTIONS_SEC)

    summary = {
        "ok": sum(1 for a in actions if a["status"] == "ok"),
        "skip": sum(1 for a in actions if a["status"] == "skip"),
        "fail": sum(1 for a in actions if a["status"] == "fail"),
    }

    EXIT_LOG_FILE.write_text(json.dumps({
        "started_at": started_at,
        "finished_at": _now_iso(),
        "phone": config.TG_PHONE,
        "agent_name": config.AGENT_NAME,
        "total_actions": len(actions),
        "summary": summary,
        "actions": actions,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Exit log -> {}", EXIT_LOG_FILE)

    final_dialogs = await client.get_dialogs()
    final = [_serialize(d) for d in final_dialogs]
    POST_EXIT_FILE.write_text(json.dumps({
        "captured_at": _now_iso(),
        "total": len(final),
        "dialogs": final,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Post-exit snapshot: {} dialogs -> {}", len(final), POST_EXIT_FILE)

    await client.disconnect()
    logger.info(".session preserved at {}.session (NOT deleted — needed for resume)",
                config.TG_SESSION_NAME)
    logger.info("DONE: ok={ok} skip={skip} fail={fail}".format(**summary))

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
