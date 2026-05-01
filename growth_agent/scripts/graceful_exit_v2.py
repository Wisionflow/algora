"""Graceful exit v2 — запускается ВНЕ docker контейнера через скопированную session.

Расширяет graceful_exit.py тремя блоками:
  a) inventory_before — все active authorizations (GetAuthorizationsRequest)
  b) [как раньше] LeaveChannelRequest для каналов/групп + send_read_acknowledge для DM
  c) revoke только zombie/old docker authorizations (filtered by app_name AND inactivity)
  d) inventory_after — для сравнения

Запуск:
    cd /home/mantas/cmo/local_freeze
    set -a; . ./.env; set +a
    python3 graceful_exit_v2.py

Требования:
  - cwd содержит growth_agent.session (копию live)
  - env: TG_API_ID, TG_API_HASH, TG_PHONE
  - telethon installed

Boundary (прошитые в коде):
  - НЕ revoke current authorization (auth.current=True) — иначе мы сами отрубимся
  - НЕ revoke authorizations не-нашего app (Telegram Android/Desktop = personal devices)
  - Revoke ТОЛЬКО authorizations с app_name начинающимся на 'algora' AND not current
    AND last active > 7 дней назад (zombie heuristic)
  - НЕ DeleteHistoryRequest — только read_acknowledge (resumable)
  - При FloodWait — sleep + retry-as-fail
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserNotParticipantError
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.messages import DeleteChatUserRequest
from telethon.tl.types import Channel, Chat, User

OUT_DIR = Path(".")  # cwd
SLEEP_BETWEEN_ACTIONS_SEC = 2.0
ZOMBIE_INACTIVITY_DAYS = 7


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


def _serialize_dialog(d) -> dict:
    return {
        "id": d.id,
        "name": d.name or "",
        "type": _classify(d.entity),
        "is_user": d.is_user,
        "is_group": d.is_group,
        "is_channel": d.is_channel,
        "unread_count": d.unread_count,
    }


def _serialize_auth(a) -> dict:
    return {
        "hash": str(a.hash),
        "current": a.current,
        "device_model": a.device_model,
        "app_name": a.app_name,
        "app_version": a.app_version,
        "platform": a.platform,
        "system_version": a.system_version,
        "ip": a.ip,
        "country": a.country,
        "region": a.region,
        "date_created": a.date_created.isoformat() if a.date_created else None,
        "date_active": a.date_active.isoformat() if a.date_active else None,
    }


async def _leave(client, dialog, me_id) -> tuple[str, str | None]:
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
        await asyncio.sleep(e.seconds + 1)
        return "fail", f"flood_wait_{e.seconds}s"
    except UserNotParticipantError:
        return "skip", "not_participant"
    except Exception as e:
        return "fail", f"{type(e).__name__}: {e}"


async def _mark_dm_read(client, dialog) -> tuple[str, str | None]:
    try:
        await client.send_read_acknowledge(dialog.entity)
        return "ok", None
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds + 1)
        return "fail", f"flood_wait_{e.seconds}s"
    except Exception as e:
        return "fail", f"{type(e).__name__}: {e}"


def _is_revokable_zombie(a, now: datetime) -> tuple[bool, str]:
    """Boundary: revoke only old algora* authorizations that are clearly zombies."""
    if a.current:
        return False, "current_session"
    app = (a.app_name or "").lower()
    if not app.startswith("algora"):
        return False, f"not_algora_app ({a.app_name!r})"
    if not a.date_active:
        return False, "no_date_active"
    age = now - a.date_active
    if age < timedelta(days=ZOMBIE_INACTIVITY_DAYS):
        return False, f"recently_active ({age.days}d ago)"
    return True, f"zombie ({age.days}d inactive)"


async def main() -> int:
    started_at = _now_iso()

    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    phone = os.environ.get("TG_PHONE", "?")

    client = TelegramClient("growth_agent", api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print("!! NOT AUTHORIZED — session revoked. Aborting.")
        return 2

    me = await client.get_me()
    print(f"[connect] me={me.id} {me.first_name!r} phone={me.phone}")

    # ---- (a) inventory before
    auths_before = await client(GetAuthorizationsRequest())
    inventory_before = [_serialize_auth(a) for a in auths_before.authorizations]
    (OUT_DIR / "auth_inventory_before.json").write_text(
        json.dumps({"captured_at": started_at, "count": len(inventory_before),
                    "authorizations": inventory_before}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"[inventory_before] {len(inventory_before)} authorizations captured")

    # ---- (b) leave + read_ack
    dialogs = await client.get_dialogs()
    initial = [_serialize_dialog(d) for d in dialogs]
    (OUT_DIR / "dialogs_snapshot.json").write_text(
        json.dumps({"captured_at": started_at, "phone": phone, "me_id": me.id,
                    "total": len(initial), "dialogs": initial}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"[snapshot] {len(initial)} dialogs")

    leave_actions: list[dict] = []
    dm_actions: list[dict] = []
    for d in dialogs:
        chat_type = _classify(d.entity)
        rec = {"timestamp": _now_iso(), "chat_id": d.id, "title": d.name or "", "type": chat_type}
        if chat_type == "dm":
            status, err = await _mark_dm_read(client, d)
            rec["action"] = "mark_as_read"; rec["status"] = status
            if err: rec["error"] = err
            dm_actions.append(rec)
        elif chat_type in ("basic_group", "supergroup", "channel", "channel_other"):
            status, err = await _leave(client, d, me.id)
            rec["action"] = "leave"; rec["status"] = status
            if err: rec["error"] = err
            leave_actions.append(rec)
        else:
            rec["action"] = "skip"; rec["status"] = "skip"; rec["error"] = "unknown_type"
            leave_actions.append(rec)
        print(f"  {rec['action']:>13} | {rec['status']:>4} | {chat_type:>14} | {(d.name or '')[:60]}")
        await asyncio.sleep(SLEEP_BETWEEN_ACTIONS_SEC)

    leave_summary = {"ok": sum(1 for a in leave_actions if a["status"] == "ok"),
                     "skip": sum(1 for a in leave_actions if a["status"] == "skip"),
                     "fail": sum(1 for a in leave_actions if a["status"] == "fail")}
    dm_summary = {"ok": sum(1 for a in dm_actions if a["status"] == "ok"),
                  "skip": sum(1 for a in dm_actions if a["status"] == "skip"),
                  "fail": sum(1 for a in dm_actions if a["status"] == "fail")}

    (OUT_DIR / "leave_log.json").write_text(
        json.dumps({"started_at": started_at, "summary": leave_summary, "actions": leave_actions},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "dm_read_log.json").write_text(
        json.dumps({"started_at": started_at, "summary": dm_summary, "actions": dm_actions},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[leave] {leave_summary}")
    print(f"[dm_read] {dm_summary}")

    # ---- (c) revoke zombies
    now = datetime.now(timezone.utc)
    revoke_log: list[dict] = []
    for a in auths_before.authorizations:
        ok, reason = _is_revokable_zombie(a, now)
        rec = {"hash": str(a.hash), "device": a.device_model, "app": a.app_name,
               "version": a.app_version, "current": a.current,
               "date_active": a.date_active.isoformat() if a.date_active else None,
               "decision": "revoke" if ok else "keep", "reason": reason}
        if ok:
            try:
                await client(ResetAuthorizationRequest(hash=a.hash))
                rec["status"] = "ok"
                print(f"  REVOKE ok   | {a.app_name!r} v{a.app_version} | {reason}")
            except FloodWaitError as e:
                rec["status"] = "fail"; rec["error"] = f"flood_wait_{e.seconds}s"
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                rec["status"] = "fail"; rec["error"] = f"{type(e).__name__}: {e}"
                print(f"  REVOKE fail | {a.app_name!r} v{a.app_version} | {e}")
        else:
            rec["status"] = "kept"
            print(f"  KEEP        | {a.app_name!r} v{a.app_version} | {reason}")
        revoke_log.append(rec)
        await asyncio.sleep(1.0)

    (OUT_DIR / "sessions_revoked.json").write_text(
        json.dumps({"started_at": started_at, "actions": revoke_log}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # ---- (d) inventory after
    auths_after = await client(GetAuthorizationsRequest())
    inventory_after = [_serialize_auth(a) for a in auths_after.authorizations]
    (OUT_DIR / "auth_inventory_after.json").write_text(
        json.dumps({"captured_at": _now_iso(), "count": len(inventory_after),
                    "authorizations": inventory_after}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"[inventory_after] {len(inventory_after)} authorizations remain")

    # ---- final post-run snapshot
    final_dialogs = await client.get_dialogs()
    final = [_serialize_dialog(d) for d in final_dialogs]
    (OUT_DIR / "dialogs_post_exit.json").write_text(
        json.dumps({"captured_at": _now_iso(), "total": len(final), "dialogs": final},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[post_exit] {len(final)} dialogs remain (expected: Saved Messages + service ~1-3)")

    await client.disconnect()
    print("[disconnected] .session preserved at growth_agent.session")
    print(f"DONE: leave={leave_summary} dm_read={dm_summary} revoked={sum(1 for r in revoke_log if r['status']=='ok')}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
