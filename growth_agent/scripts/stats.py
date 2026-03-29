"""Agent performance analytics.

Usage:
    python -m scripts.stats                  # Full report (30 days)
    python -m scripts.stats --days 7         # Last 7 days
    python -m scripts.stats --daily          # Daily breakdown
    python -m scripts.stats --dms            # DM interactions detail
"""

import asyncio
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src import config, db


def _bar(value: int, max_val: int, width: int = 30) -> str:
    if max_val == 0:
        return ""
    filled = int(value / max_val * width)
    return "█" * filled + "░" * (width - filled)


async def run_stats(days: int, show_daily: bool, show_dms: bool) -> None:
    await db.init_pool(config.POSTGRES_DSN)

    try:
        stats = await db.get_agent_stats(days)

        print(f"\n{'='*60}")
        print(f"  ALGORA GROWTH AGENT — ОТЧЁТ ЗА {days} ДНЕЙ")
        print(f"{'='*60}\n")

        # Conversion funnel
        seen = stats["messages_seen"]
        relevant = stats["messages_relevant"]
        responded = stats["responses_sent"]
        links = stats["responses_with_link"]

        print("📊 ВОРОНКА КОНВЕРСИИ:")
        print(f"  Сообщений увидено:     {seen:>6}")
        print(f"  Релевантных:           {relevant:>6}  ({relevant/seen*100:.1f}%)" if seen else "  Релевантных:           0")
        print(f"  Ответов отправлено:    {responded:>6}  ({responded/relevant*100:.1f}% от релевантных)" if relevant else f"  Ответов отправлено:    {responded:>6}")
        print(f"  С ссылкой на канал:    {links:>6}  ({links/responded*100:.1f}% ответов)" if responded else f"  С ссылкой на канал:    {links:>6}")
        print()

        # DMs
        print("💬 ЛИЧНЫЕ СООБЩЕНИЯ (DM):")
        print(f"  Всего получено:        {stats['dms_total']:>6}")
        print(f"  Ответили:              {stats['dms_responded']:>6}")
        if stats['dms_total'] > 0:
            rate = stats['dms_responded'] / stats['dms_total'] * 100
            print(f"  Response rate:         {rate:>5.1f}%")
        print()

        # Chats
        print(f"📡 ЧАТЫ: {stats['active_chats']} активных, {stats['banned_chats']} забанено")
        print()

        if stats["by_chat"]:
            print("🏆 АКТИВНОСТЬ ПО ЧАТАМ:")
            max_resp = max(r["responses"] for r in stats["by_chat"]) if stats["by_chat"] else 1
            for r in stats["by_chat"]:
                bar = _bar(r["responses"], max_resp, 20)
                print(f"  {bar} {r['responses']:>3} отв. | {r['title'][:40]} ({r['member_count']})")
            print()

        # Subscriber history
        if stats["subscriber_history"]:
            print("📈 ПОДПИСЧИКИ КАНАЛА:")
            for h in stats["subscriber_history"][:10]:
                new = f"+{h['new']}" if h['new'] > 0 else "0"
                print(f"  {h['date']}  {h['subscribers']:>5} подписчиков ({new} новых)")
            print()

        # Daily breakdown
        if show_daily and stats["daily"]:
            print("📅 ПО ДНЯМ (последние 7):")
            print(f"  {'Дата':<12} {'Увидено':>8} {'Релев.':>7} {'Ответы':>7} {'DM':>5}")
            print(f"  {'-'*12} {'-'*8} {'-'*7} {'-'*7} {'-'*5}")
            for d in stats["daily"]:
                print(f"  {d['day']:<12} {d['messages_seen']:>8} {d['relevant']:>7} {d['responses']:>7} {d['dms']:>5}")
            print()

        # DM details
        if show_dms:
            dm_stats = await db.get_dm_stats()
            print("📨 DM ПО ТИПАМ:")
            for dm_type, cnt in dm_stats["by_type"].items():
                print(f"  {dm_type:<20} {cnt:>5}")
            print()

        # Conversion estimate
        print("🎯 ОЦЕНКА ЭФФЕКТИВНОСТИ:")
        if responded == 0:
            print("  ⚠️  Агент не отправил ни одного ответа за период!")
        elif links == 0:
            print("  ⚠️  Ни одной ссылки на канал не было отправлено!")
        else:
            print(f"  Ссылок на канал показано: {links}")
            print(f"  Охват (участники чатов):  ~{sum(r['member_count'] for r in stats['by_chat'])}")
            est_ctr = links * 0.03  # ~3% CTR estimate
            print(f"  Оценка переходов (3% CTR): ~{est_ctr:.0f}")
            print(f"  Оценка подписок (30% конв.): ~{est_ctr * 0.3:.0f}")
        print()

        print(f"{'='*60}\n")

    finally:
        await db.close_pool()


def main():
    parser = argparse.ArgumentParser(description="Agent Performance Stats")
    parser.add_argument("--days", type=int, default=30, help="Period in days (default: 30)")
    parser.add_argument("--daily", action="store_true", help="Show daily breakdown")
    parser.add_argument("--dms", action="store_true", help="Show DM type breakdown")
    args = parser.parse_args()

    asyncio.run(run_stats(args.days, args.daily, args.dms))


if __name__ == "__main__":
    main()
