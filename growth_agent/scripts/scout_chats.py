"""Scout — find live Telegram chats with real people.

Searches public groups by keywords, reads last messages WITHOUT joining,
scores each chat for "liveness" (real humans vs AI-generated / dead / read-only).

Usage (inside Docker — stop agent first to free session):
    python -m scripts.scout_chats

Usage (local with .env):
    python -X utf8 -m scripts.scout_chats
"""

import asyncio
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import Channel, User

load_dotenv()

TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_PHONE = os.getenv("TG_PHONE", "")
TG_SESSION_NAME = os.getenv("TG_SESSION_NAME", "growth_agent")

# Keywords to search for groups
SEARCH_QUERIES = [
    "wildberries чат селлеров",
    "ozon чат продавцов",
    "маркетплейс чат",
    "wb ozon чат",
    "селлеры wildberries",
    "импорт китай товары",
    "поставщики маркетплейс",
    "фулфилмент wb ozon",
    "карточки товаров wildberries",
    "закупка китай 1688",
]

# Skip chats we already monitor (by telegram_id or username)
SKIP_IDS: set[int] = set()

# Minimum members to consider
MIN_MEMBERS = 500
MAX_MEMBERS = 200_000

# How many messages to analyze per chat
MESSAGES_TO_ANALYZE = 50


@dataclass
class ChatScore:
    telegram_id: int
    username: str
    title: str
    members: int
    # Liveness signals
    unique_senders: int = 0
    avg_msg_length: float = 0
    question_ratio: float = 0     # % of messages with "?"
    reply_ratio: float = 0        # % of messages that are replies
    bot_ratio: float = 0          # % of messages from bots
    is_broadcast: bool = False     # read-only channel
    msgs_last_24h: int = 0
    timing_regularity: float = 0  # 0=irregular(good), 1=clockwork(bad)
    # Final score
    score: float = 0
    reasons: list[str] = field(default_factory=list)


def compute_timing_regularity(timestamps: list[datetime]) -> float:
    """How regular are message intervals? 0=human(chaotic), 1=bot(clockwork)."""
    if len(timestamps) < 5:
        return 0.5
    intervals = []
    for i in range(1, len(timestamps)):
        diff = abs((timestamps[i] - timestamps[i - 1]).total_seconds())
        if diff > 0:
            intervals.append(diff)
    if not intervals:
        return 0.5
    mean = sum(intervals) / len(intervals)
    if mean == 0:
        return 1.0
    variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
    std = variance ** 0.5
    cv = std / mean  # coefficient of variation
    # Low CV = regular (bot-like), High CV = irregular (human-like)
    # cv < 0.3 is very regular, cv > 1.5 is very irregular
    regularity = max(0, 1 - cv / 1.5)
    return round(regularity, 2)


def score_chat(cs: ChatScore) -> float:
    """Compute final liveness score 0-100."""
    s = 0
    reasons = []

    if cs.is_broadcast:
        cs.reasons = ["read-only channel"]
        return 0

    # Unique senders (max 30 pts)
    sender_score = min(30, cs.unique_senders * 2)
    s += sender_score
    if cs.unique_senders >= 10:
        reasons.append(f"{cs.unique_senders} авторов")
    elif cs.unique_senders < 5:
        reasons.append(f"мало авторов ({cs.unique_senders})")

    # Questions (max 15 pts) — real chats have questions
    q_score = min(15, cs.question_ratio * 50)
    s += q_score
    if cs.question_ratio > 0.15:
        reasons.append(f"вопросы {cs.question_ratio:.0%}")

    # Reply ratio (max 15 pts) — real chats have replies
    r_score = min(15, cs.reply_ratio * 30)
    s += r_score
    if cs.reply_ratio > 0.2:
        reasons.append(f"реплаи {cs.reply_ratio:.0%}")

    # Message length (max 15 pts) — too long = AI, too short = spam
    if 30 <= cs.avg_msg_length <= 150:
        s += 15
        reasons.append("норм длина сообщ.")
    elif cs.avg_msg_length > 300:
        s -= 10
        reasons.append(f"длинные сообщ. ({cs.avg_msg_length:.0f} симв.)")
    elif cs.avg_msg_length < 15:
        reasons.append("очень короткие сообщ.")

    # Activity — messages in last 24h (max 10 pts)
    act_score = min(10, cs.msgs_last_24h)
    s += act_score
    if cs.msgs_last_24h > 5:
        reasons.append(f"{cs.msgs_last_24h} сообщ/24ч")
    elif cs.msgs_last_24h == 0:
        reasons.append("нет активности 24ч")
        s -= 15

    # Bot ratio penalty
    if cs.bot_ratio > 0.3:
        s -= 20
        reasons.append(f"много ботов ({cs.bot_ratio:.0%})")

    # Timing regularity penalty
    if cs.timing_regularity > 0.7:
        s -= 10
        reasons.append("подозрительно регулярный")

    # Member count bonus
    if 1000 <= cs.members <= 30000:
        s += 10
        reasons.append(f"{cs.members // 1000}K участников")
    elif cs.members > 30000:
        s += 5

    cs.reasons = reasons
    return max(0, min(100, s))


async def analyze_chat(client: TelegramClient, entity: Channel) -> ChatScore | None:
    """Read last messages from a public chat and score it."""
    cs = ChatScore(
        telegram_id=entity.id,
        username=entity.username or "",
        title=entity.title or "",
        members=entity.participants_count or 0,
        is_broadcast=bool(entity.broadcast),
    )

    if cs.is_broadcast:
        cs.score = score_chat(cs)
        return cs

    try:
        messages = await client.get_messages(entity, limit=MESSAGES_TO_ANALYZE)
    except Exception as e:
        print(f"  skip {cs.title}: {e}")
        return None

    if not messages:
        return None

    senders = Counter()
    lengths = []
    questions = 0
    replies = 0
    bots = 0
    timestamps = []
    now = datetime.now(timezone.utc)
    msgs_24h = 0

    for msg in messages:
        if not msg.message:
            continue

        text = msg.message
        lengths.append(len(text))

        if "?" in text:
            questions += 1

        if msg.reply_to:
            replies += 1

        if msg.date:
            timestamps.append(msg.date)
            if (now - msg.date) < timedelta(hours=24):
                msgs_24h += 1

        sender = msg.sender
        if sender:
            if isinstance(sender, User):
                if sender.bot:
                    bots += 1
                senders[sender.id] += 1
            else:
                senders[getattr(sender, "id", 0)] += 1

    total = len(lengths)
    if total < 5:
        return None

    cs.unique_senders = len(senders)
    cs.avg_msg_length = sum(lengths) / total
    cs.question_ratio = questions / total
    cs.reply_ratio = replies / total
    cs.bot_ratio = bots / total if total > 0 else 0
    cs.msgs_last_24h = msgs_24h
    cs.timing_regularity = compute_timing_regularity(sorted(timestamps))
    cs.score = score_chat(cs)

    return cs


async def main():
    if not TG_API_ID or not TG_API_HASH:
        print("ERROR: TG_API_ID / TG_API_HASH not set")
        sys.exit(1)

    client = TelegramClient(TG_SESSION_NAME, TG_API_ID, TG_API_HASH)
    await client.start(phone=TG_PHONE)

    # Load already-joined chats to skip
    try:
        import asyncpg
        dsn = os.getenv("POSTGRES_DSN", "")
        if dsn:
            conn = await asyncpg.connect(dsn)
            rows = await conn.fetch("SELECT telegram_id FROM chats")
            for r in rows:
                SKIP_IDS.add(abs(r["telegram_id"]))
            await conn.close()
            print(f"Skipping {len(SKIP_IDS)} already-joined chats\n")
    except Exception:
        pass

    seen_ids: set[int] = set()
    results: list[ChatScore] = []

    for query in SEARCH_QUERIES:
        print(f"Searching: {query}...")
        try:
            result = await client(SearchRequest(q=query, limit=20))
        except Exception as e:
            print(f"  search error: {e}")
            continue

        for chat in result.chats:
            if not isinstance(chat, Channel):
                continue
            if chat.id in seen_ids or chat.id in SKIP_IDS:
                continue
            seen_ids.add(chat.id)

            members = chat.participants_count or 0
            if members < MIN_MEMBERS or members > MAX_MEMBERS:
                continue

            print(f"  Analyzing: {chat.title} ({members} members)...")
            cs = await analyze_chat(client, chat)
            if cs:
                results.append(cs)

            # Rate limit — be gentle
            await asyncio.sleep(1)

        await asyncio.sleep(2)

    await client.disconnect()

    # Sort by score
    results.sort(key=lambda x: x.score, reverse=True)

    # Print report
    print("\n" + "=" * 70)
    print("SCOUT REPORT — Живые чаты для Growth Agent")
    print("=" * 70)

    for i, cs in enumerate(results, 1):
        status = ""
        if cs.score >= 60:
            status = "LIVE"
        elif cs.score >= 35:
            status = "maybe"
        else:
            status = "skip"

        link = f"@{cs.username}" if cs.username else f"id:{cs.telegram_id}"
        print(f"\n{i:2}. [{status:5}] {cs.score:5.1f} pts | {link}")
        print(f"    {cs.title} ({cs.members} members)")
        print(f"    {', '.join(cs.reasons)}")

    # Summary
    live = [c for c in results if c.score >= 60]
    maybe = [c for c in results if 35 <= c.score < 60]
    print(f"\n{'=' * 70}")
    print(f"Total found: {len(results)} | LIVE: {len(live)} | maybe: {len(maybe)}")
    print(f"Join these (copy links):")
    for cs in live:
        link = f"https://t.me/{cs.username}" if cs.username else f"(id: {cs.telegram_id})"
        print(f"  {link}  — {cs.title} ({cs.members})")


if __name__ == "__main__":
    asyncio.run(main())
