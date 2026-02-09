"""Quick test script to verify Apify 1688 integration.

Runs one search query and prints the raw JSON output
to help map fields to RawProduct.

Usage:
    python -X utf8 scripts/test_apify.py
    python -X utf8 scripts/test_apify.py --keyword "电子产品 爆款" --limit 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout and sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()


def main(keyword: str = "电子产品 爆款", limit: int = 3):
    token = os.getenv("APIFY_API_TOKEN", "")
    actor_id = os.getenv("APIFY_1688_ACTOR_ID", "devcake/1688-com-products-scraper")

    if not token:
        print("ERROR: APIFY_API_TOKEN not set in .env")
        print("Get your free token at https://apify.com")
        return

    from apify_client import ApifyClient

    print(f"Testing Apify actor: {actor_id}")
    print(f"Keyword: {keyword}")
    print(f"Limit: {limit}")
    print("=" * 60)

    client = ApifyClient(token)

    print("Running actor (this may take 30-90 seconds)...")
    try:
        run = client.actor(actor_id).call(
            run_input={"queries": [keyword], "maxItems": limit},
            timeout_secs=180,
        )
    except Exception as e:
        print(f"ERROR: Actor failed: {e}")
        return

    items = client.dataset(run["defaultDatasetId"]).list_items().items
    print(f"\nGot {len(items)} items\n")

    for i, item in enumerate(items, 1):
        print(f"--- Item {i} ---")
        print(json.dumps(item, ensure_ascii=False, indent=2))
        print()

    if items:
        print("=" * 60)
        print("Available field names:")
        all_keys = set()
        for item in items:
            all_keys.update(item.keys())
        for key in sorted(all_keys):
            sample = items[0].get(key, "N/A")
            if isinstance(sample, str) and len(sample) > 80:
                sample = sample[:80] + "..."
            print(f"  {key}: {sample}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Apify 1688 scraper")
    parser.add_argument("--keyword", default="电子产品 爆款", help="Search keyword")
    parser.add_argument("--limit", type=int, default=3, help="Number of items")
    args = parser.parse_args()
    main(keyword=args.keyword, limit=args.limit)
