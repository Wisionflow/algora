"""
Algora Chat Discovery Module
Finds and ranks Telegram chats relevant to a target segment.

Usage:
    # Search mode (requires active Telethon session):
    python chat_discovery.py --segment T1 --search

    # From curated list (no Telethon needed):
    python chat_discovery.py --segment T1

    # Auto-join top N chats:
    python chat_discovery.py --segment T1 --search --join --top 10

    # Output as JSON:
    python chat_discovery.py --segment T1 --search --json
"""

import asyncio
import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("chat_discovery")

# ============================================================
# SEGMENT DEFINITIONS
# ============================================================
# Each segment defines: keywords for search, negative keywords to exclude,
# minimum members threshold, and curated "seed" chats known to be relevant.

SEGMENTS = {
    "T1": {
        "name": "Селлеры WB/Ozon ← Товары из Китая",
        "description": "Sellers on Russian marketplaces sourcing from China",
        "search_queries": [
            # Russian queries
            "селлеры WB",
            "селлеры Ozon",
            "WB партнёры",
            "маркетплейс чат",
            "товары из Китая",
            "закупки 1688",
            "закупки Китай",
            "карго Китай",
            "wildberries селлер",
            "ozon селлер",
            "маркетплейс бизнес",
            "импорт Китай",
            "поставщики Китай",
            "WB новички",
            "маржинальные товары",
        ],
        "positive_keywords": [
            "селлер", "wb", "wildberries", "ozon", "озон", "маркетплейс",
            "1688", "китай", "закупк", "поставщик", "карго", "фулфилмент",
            "маржа", "товар", "ниша", "аналитик", "mpstats", "юнит",
            "fob", "фоб", "опт", "импорт", "экспорт",
        ],
        "negative_keywords": [
            "крипто", "казино", "ставки", "форекс", "бинарные",
            "пирамида", "mlm", "сетевой", "заработок без вложений",
        ],
        "min_members": 200,
        "seed_chats": [
            # Verified chats from T1_CHAT_LIST.md research (2026-02-23)
            # Format: (username, name, estimated_members, notes)
            # Priority 1: Large seller chats
            ("ozon_fbs", "ЧАТ OZON | Клуб партнёров", 50000, "Крупнейший чат Ozon-селлеров"),
            ("sellersfriends", "WB Ozone | Свои Селлеры Чат", 31600, "Активный чат WB+Ozon"),
            ("sallerschat", "WB OZON | Мы селлеры!", 20000, "+50 новых/день, строгие правила"),
            ("ozon_partner", "Ozon ЧАТ поставщиков", 15000, "Фокус Ozon, поставщики"),
            ("wb_ozon_chat", "Селлеры WB OZON", 23000, "Мультиплатформенный чат"),
            # Priority 2: Niche chats (China sourcing — exact target audience)
            ("Modul_China", "Закупки в Китае (Модульбанк)", 5000, "Закупки на 1688 — прямая ЦА"),
            ("wb_ozon_marketplace", "WB & Ozon маркетплейс", 1300, "Логистика, цены, закупки"),
            ("marketplace_biz", "Маркетплейс Бизнес", 5000, "Лайфхаки WB/Ozon, аналитика"),
            # Priority 3: Large but noisy
            ("marketplace_pro", "PRO Маркетплейсы", 38000, "Много шума, но и вопросов"),
        ],
    },
    "H6": {
        "name": "Юристы ВЭД → Экспортёры/Импортёры",
        "description": "International trade lawyers and importers/exporters",
        "search_queries": [
            "ВЭД юрист",
            "таможенный брокер",
            "валютный контроль",
            "санкции бизнес",
            "импорт экспорт чат",
            "таможня РФ",
            "международная торговля",
        ],
        "positive_keywords": [
            "вэд", "таможн", "санкци", "валютн", "импорт", "экспорт",
            "брокер", "декларац", "сертифик", "лицензи",
        ],
        "negative_keywords": [
            "крипто", "казино", "ставки",
        ],
        "min_members": 100,
        "seed_chats": [],
    },
    "T2": {
        "name": "Автозапчасти Китай → СТО РФ",
        "description": "Chinese auto parts suppliers and Russian service centers",
        "search_queries": [
            "автозапчасти Китай",
            "запчасти оптом",
            "автосервис чат",
            "OEM запчасти",
            "аналоги запчастей",
        ],
        "positive_keywords": [
            "запчаст", "автосервис", "сто", "oem", "аналог", "vin",
            "каталог", "детал", "ремонт",
        ],
        "negative_keywords": [
            "крипто", "казино",
        ],
        "min_members": 100,
        "seed_chats": [],
    },
}


# ============================================================
# DATA MODEL
# ============================================================

@dataclass
class DiscoveredChat:
    """A Telegram chat discovered through search or curated list."""
    username: str                    # TG username or invite link
    title: str                       # Chat title
    members: int                     # Member count
    segment: str                     # Segment ID (T1, H6, etc.)
    source: str                      # "search", "seed", "tgstat"
    relevance_score: float = 0.0     # 0-10 composite score
    notes: str = ""                  # Human-readable notes
    joined: bool = False             # Whether we've joined
    discovered_at: str = ""          # ISO timestamp

    def __post_init__(self):
        if not self.discovered_at:
            self.discovered_at = datetime.now(timezone.utc).isoformat()


# ============================================================
# SCORING
# ============================================================

def score_chat(
    title: str,
    description: str,
    members: int,
    positive_keywords: list[str],
    negative_keywords: list[str],
    min_members: int,
) -> float:
    """
    Score a chat 0-10 based on relevance to segment.

    Components:
    - keyword_match (0-5): how many positive keywords appear in title+description
    - size_score (0-3): member count relative to min_members
    - penalty (-5): negative keywords present
    """
    text = f"{title} {description}".lower()

    # Keyword matching
    matches = sum(1 for kw in positive_keywords if kw.lower() in text)
    keyword_score = min(5.0, matches * 1.0)

    # Size scoring
    if members < min_members:
        size_score = 0.5  # Still discoverable, just small
    elif members < 1000:
        size_score = 1.0
    elif members < 5000:
        size_score = 2.0
    elif members < 15000:
        size_score = 2.5
    else:
        size_score = 3.0

    # Negative keyword penalty
    neg_matches = sum(1 for kw in negative_keywords if kw.lower() in text)
    penalty = min(5.0, neg_matches * 2.5)

    return max(0.0, min(10.0, keyword_score + size_score - penalty))


# ============================================================
# TELETHON SEARCH (requires active session)
# ============================================================

async def search_telegram(
    segment_id: str,
    session_path: str = "session/growth_agent",
    api_id: Optional[int] = None,
    api_hash: Optional[str] = None,
) -> list[DiscoveredChat]:
    """
    Search Telegram for chats matching segment keywords.
    Requires Telethon session to be authorized.
    """
    try:
        from telethon import TelegramClient
        from telethon.tl.functions.contacts import SearchRequest
    except ImportError:
        logger.error("Telethon not installed. Run: pip install telethon")
        return []

    segment = SEGMENTS.get(segment_id)
    if not segment:
        logger.error(f"Unknown segment: {segment_id}")
        return []

    api_id = api_id or int(os.getenv("TG_API_ID", "0"))
    api_hash = api_hash or os.getenv("TG_API_HASH", "")

    if not api_id or not api_hash:
        logger.error("TG_API_ID and TG_API_HASH required for search mode")
        return []

    discovered = []
    seen_ids = set()

    client = TelegramClient(session_path, api_id, api_hash)
    await client.start()

    try:
        for query in segment["search_queries"]:
            logger.info(f"Searching: '{query}'")
            try:
                result = await client(SearchRequest(q=query, limit=20))

                for chat in result.chats:
                    if chat.id in seen_ids:
                        continue
                    seen_ids.add(chat.id)

                    username = getattr(chat, "username", "") or ""
                    title = getattr(chat, "title", "") or ""
                    members = getattr(chat, "participants_count", 0) or 0

                    # Get description if available
                    description = ""
                    try:
                        full = await client.get_entity(chat)
                        if hasattr(full, "about"):
                            description = full.about or ""
                    except Exception:
                        pass

                    relevance = score_chat(
                        title=title,
                        description=description,
                        members=members,
                        positive_keywords=segment["positive_keywords"],
                        negative_keywords=segment["negative_keywords"],
                        min_members=segment["min_members"],
                    )

                    if relevance >= 2.0:
                        discovered.append(DiscoveredChat(
                            username=username or str(chat.id),
                            title=title,
                            members=members,
                            segment=segment_id,
                            source="search",
                            relevance_score=round(relevance, 1),
                            notes=f"Found via query: '{query}'",
                        ))

                # Rate limit: don't hammer TG API
                await asyncio.sleep(2)

            except Exception as e:
                logger.warning(f"Search failed for '{query}': {e}")
                await asyncio.sleep(5)

    finally:
        await client.disconnect()

    # Sort by relevance descending
    discovered.sort(key=lambda c: c.relevance_score, reverse=True)
    return discovered


# ============================================================
# SEED LIST (no Telethon needed)
# ============================================================

def get_seed_chats(segment_id: str) -> list[DiscoveredChat]:
    """Return curated seed chats for a segment."""
    segment = SEGMENTS.get(segment_id)
    if not segment:
        return []

    chats = []
    for username, title, members, notes in segment["seed_chats"]:
        relevance = score_chat(
            title=title,
            description=notes,
            members=members,
            positive_keywords=segment["positive_keywords"],
            negative_keywords=segment["negative_keywords"],
            min_members=segment["min_members"],
        )
        chats.append(DiscoveredChat(
            username=username,
            title=title,
            members=members,
            segment=segment_id,
            source="seed",
            relevance_score=round(relevance, 1),
            notes=notes,
        ))

    chats.sort(key=lambda c: c.relevance_score, reverse=True)
    return chats


# ============================================================
# AUTO-JOIN
# ============================================================

async def join_chats(
    chats: list[DiscoveredChat],
    session_path: str = "session/growth_agent",
    api_id: Optional[int] = None,
    api_hash: Optional[str] = None,
    top_n: int = 10,
) -> list[DiscoveredChat]:
    """Join top N chats from the list. Returns list of successfully joined."""
    try:
        from telethon import TelegramClient
    except ImportError:
        logger.error("Telethon not installed")
        return []

    api_id = api_id or int(os.getenv("TG_API_ID", "0"))
    api_hash = api_hash or os.getenv("TG_API_HASH", "")

    joined = []
    client = TelegramClient(session_path, api_id, api_hash)
    await client.start()

    try:
        for chat in chats[:top_n]:
            try:
                logger.info(f"Joining: @{chat.username} ({chat.title})")
                await client.get_dialogs()  # Refresh dialog list
                entity = await client.get_entity(chat.username)
                await client(
                    __import__("telethon.tl.functions.channels", fromlist=["JoinChannelRequest"])
                    .JoinChannelRequest(entity)
                )
                chat.joined = True
                joined.append(chat)
                logger.info(f"  ✅ Joined: {chat.title}")
                # Don't join too fast
                await asyncio.sleep(10 + (len(joined) * 5))
            except Exception as e:
                logger.warning(f"  ❌ Failed to join @{chat.username}: {e}")
                await asyncio.sleep(15)
    finally:
        await client.disconnect()

    return joined


# ============================================================
# DISPLAY
# ============================================================

def display_results(chats: list[DiscoveredChat], segment_id: str):
    """Print formatted results to console."""
    segment = SEGMENTS.get(segment_id, {})
    print(f"\n{'='*70}")
    print(f"  CHAT DISCOVERY: {segment.get('name', segment_id)}")
    print(f"  Found: {len(chats)} chats")
    print(f"{'='*70}\n")

    print(f"{'#':<4} {'Score':<7} {'Members':<9} {'Source':<8} {'Chat'}")
    print(f"{'-'*4} {'-'*6} {'-'*8} {'-'*7} {'-'*40}")

    for i, chat in enumerate(chats, 1):
        score_bar = "█" * int(chat.relevance_score) + "░" * (10 - int(chat.relevance_score))
        joined_mark = " ✅" if chat.joined else ""
        print(
            f"{i:<4} {chat.relevance_score:<7.1f} {chat.members:<9,} {chat.source:<8} "
            f"@{chat.username} — {chat.title}{joined_mark}"
        )
        if chat.notes:
            print(f"     {score_bar}  💬 {chat.notes}")
        print()


def export_json(chats: list[DiscoveredChat]) -> str:
    """Export results as JSON string."""
    return json.dumps(
        [asdict(c) for c in chats],
        ensure_ascii=False,
        indent=2,
    )


# ============================================================
# MAIN
# ============================================================

async def main():
    parser = argparse.ArgumentParser(description="Algora Chat Discovery")
    parser.add_argument("--segment", required=True, help="Segment ID (T1, H6, T2, etc.)")
    parser.add_argument("--search", action="store_true", help="Search Telegram (requires Telethon session)")
    parser.add_argument("--join", action="store_true", help="Auto-join top chats")
    parser.add_argument("--top", type=int, default=10, help="Number of top chats to join (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--session", default="session/growth_agent", help="Telethon session path")
    parser.add_argument("--output", default=None, help="Save results to file")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.segment not in SEGMENTS:
        print(f"❌ Unknown segment: {args.segment}")
        print(f"   Available: {', '.join(SEGMENTS.keys())}")
        sys.exit(1)

    # Collect chats from all sources
    all_chats: list[DiscoveredChat] = []

    # 1. Seed chats (always available)
    seeds = get_seed_chats(args.segment)
    all_chats.extend(seeds)
    logger.info(f"Loaded {len(seeds)} seed chats")

    # 2. Telegram search (optional)
    if args.search:
        searched = await search_telegram(args.segment, session_path=args.session)
        # Deduplicate by username
        existing = {c.username for c in all_chats}
        for chat in searched:
            if chat.username not in existing:
                all_chats.append(chat)
                existing.add(chat.username)
        logger.info(f"Found {len(searched)} chats via search ({len(all_chats)} total after dedup)")

    # Sort by score
    all_chats.sort(key=lambda c: c.relevance_score, reverse=True)

    # 3. Auto-join
    if args.join:
        joined = await join_chats(all_chats, session_path=args.session, top_n=args.top)
        logger.info(f"Joined {len(joined)} chats")

    # Output
    if args.json:
        result = export_json(all_chats)
        if args.output:
            with open(args.output, "w") as f:
                f.write(result)
            print(f"Saved to {args.output}")
        else:
            print(result)
    else:
        display_results(all_chats, args.segment)

    if args.output and not args.json:
        with open(args.output, "w") as f:
            f.write(export_json(all_chats))
        print(f"\nJSON saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
