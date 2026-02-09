"""Set up Telegram channel: avatar, description, and pinned lead-magnet post.

Usage:
    python -X utf8 scripts/setup_channel.py
    python -X utf8 scripts/setup_channel.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
AVATAR_PATH = Path(__file__).parent.parent / "assets" / "avatar_640.png"

CHANNEL_DESCRIPTION = (
    "Товарные находки из Китая с расчётом маржи. "
    "ИИ-система мониторит фабрики 24/7 и отбирает лучшее для селлеров WB/Ozon. "
    "Цена, поставщик, конкуренция — всё посчитано. "
    "Корпорация Алгора."
)

LEAD_MAGNET_POST = """<b>ALGORA | Как это работает</b>

Каждый день ИИ-система Algora анализирует тысячи товаров на китайских площадках и выдаёт концентрат: только те находки, которые имеют реальный потенциал для продажи на российском рынке.

<b>Что вы получаете в каждом посте:</b>
— Название и категория товара
— Цена FOB от фабрики (в юанях и рублях)
— Полная себестоимость с доставкой в РФ
— Средняя цена и количество конкурентов на WB
— Расчётная маржа в процентах
— Проверка поставщика (стаж, рейтинг)
— ИИ-инсайт с оценкой рисков и рекомендацией

<b>Почему это работает:</b>
Система обрабатывает объём данных, который один человек не может охватить физически. Пока вы ищете один товар вручную — Algora уже проанализировала сотни и отобрала лучшие.

<b>Кому подходит:</b>
— Селлерам WB и Ozon, которые ищут новые ниши
— Предпринимателям, которые хотят начать торговлю с Китаем
— Действующим импортёрам для расширения ассортимента

Подписывайтесь. Находки публикуются ежедневно.

<i>Корпорация Алгора</i>"""


API = f"https://api.telegram.org/bot{TOKEN}"


async def set_avatar(client: httpx.AsyncClient, dry_run: bool) -> bool:
    """Set the channel photo."""
    if not AVATAR_PATH.exists():
        print(f"[ERROR] Avatar not found: {AVATAR_PATH}")
        return False

    if dry_run:
        print(f"[DRY RUN] Would set channel photo from {AVATAR_PATH}")
        return True

    with open(AVATAR_PATH, "rb") as f:
        resp = await client.post(
            f"{API}/setChatPhoto",
            data={"chat_id": CHANNEL},
            files={"photo": ("avatar.png", f, "image/png")},
        )
    data = resp.json()
    if data.get("ok"):
        print("[OK] Channel avatar set")
        return True
    else:
        print(f"[ERROR] setChatPhoto: {data.get('description')}")
        return False


async def set_description(client: httpx.AsyncClient, dry_run: bool) -> bool:
    """Set the channel description (About)."""
    if dry_run:
        print(f"[DRY RUN] Would set description ({len(CHANNEL_DESCRIPTION)} chars):")
        print(f"  {CHANNEL_DESCRIPTION}")
        return True

    resp = await client.post(
        f"{API}/setChatDescription",
        json={"chat_id": CHANNEL, "description": CHANNEL_DESCRIPTION},
    )
    data = resp.json()
    if data.get("ok"):
        print(f"[OK] Channel description set ({len(CHANNEL_DESCRIPTION)} chars)")
        return True
    else:
        print(f"[ERROR] setChatDescription: {data.get('description')}")
        return False


async def publish_lead_magnet(client: httpx.AsyncClient, dry_run: bool) -> int | None:
    """Send the lead magnet post and pin it."""
    if dry_run:
        print(f"[DRY RUN] Would send & pin lead magnet ({len(LEAD_MAGNET_POST)} chars):")
        # Show preview without HTML tags
        import re
        preview = re.sub(r"<[^>]+>", "", LEAD_MAGNET_POST)
        for line in preview.split("\n")[:5]:
            print(f"  {line}")
        print("  ...")
        return None

    # Send the post
    resp = await client.post(
        f"{API}/sendMessage",
        json={
            "chat_id": CHANNEL,
            "text": LEAD_MAGNET_POST,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )
    data = resp.json()
    if not data.get("ok"):
        print(f"[ERROR] sendMessage: {data.get('description')}")
        return None

    message_id = data["result"]["message_id"]
    print(f"[OK] Lead magnet posted (message_id={message_id})")

    # Pin the message
    resp = await client.post(
        f"{API}/pinChatMessage",
        json={
            "chat_id": CHANNEL,
            "message_id": message_id,
            "disable_notification": True,
        },
    )
    data = resp.json()
    if data.get("ok"):
        print(f"[OK] Message pinned")
    else:
        print(f"[WARNING] pinChatMessage: {data.get('description')}")

    return message_id


async def main(dry_run: bool = False):
    print("=" * 50)
    print("ALGORA — Channel Setup")
    print(f"Channel: {CHANNEL}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("=" * 50)

    if not TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN not set")
        return
    if not CHANNEL:
        print("[ERROR] TELEGRAM_CHANNEL_ID not set")
        return

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Verify bot access
        resp = await client.get(f"{API}/getMe")
        bot_data = resp.json()
        if not bot_data.get("ok"):
            print(f"[ERROR] Bot auth failed: {bot_data.get('description')}")
            return
        print(f"Bot: @{bot_data['result']['username']}")

        # 2. Set avatar
        print("\n--- Setting avatar ---")
        await set_avatar(client, dry_run)

        # 3. Set description
        print("\n--- Setting description ---")
        await set_description(client, dry_run)

        # 4. Publish and pin lead magnet
        print("\n--- Publishing lead magnet ---")
        await publish_lead_magnet(client, dry_run)

    print("\n" + "=" * 50)
    print("Channel setup complete!")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up Algora Telegram channel")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
