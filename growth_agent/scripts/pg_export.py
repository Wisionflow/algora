"""PostgreSQL export для resumable freeze (без pg_dump бинарника).

Подключается через psycopg2 к DSN из env (POSTGRES_DSN).
Для каждой таблицы из growth-agent (chats, messages, responses, metrics,
schedule, dm_interactions):
  - SELECT * → JSON Lines ({table}.jsonl, по строке на row, datetime ISO)
  - тот же набор → CSV ({table}.csv, для tabular tools)
  - INFORMATION_SCHEMA.columns → CREATE TABLE statement в schema_{table}.sql

manifest.json — общий summary: row counts, missing tables, timestamps,
DSN с redacted паролем.

Boundary:
  - Missing table → не падать, пометить в manifest как "missing", continue
  - Empty table (0 rows) → норма, отмечается count=0
  - Connection refused → surface, не пытаться обходить через docker

Usage:
    cd /home/mantas/cmo/local_freeze
    set -a; . ./.env; set +a
    python3 pg_export.py /home/mantas/cmo/freeze_2026-05-01/pg_export
"""

import csv
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
import psycopg2.extras

TABLES = ["chats", "messages", "responses", "metrics", "schedule", "dm_interactions"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_dsn(dsn: str) -> str:
    return re.sub(r"://([^:]+):[^@]+@", r"://\1:<redacted>@", dsn)


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (bytes, bytearray)):
        return o.hex()
    if isinstance(o, set):
        return list(o)
    raise TypeError(f"Cannot serialize {type(o).__name__}")


def _table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=%s",
        (table,),
    )
    return cur.fetchone() is not None


def _schema_sql(cur, table: str) -> str:
    cur.execute(
        """
        SELECT column_name, data_type, character_maximum_length,
               is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    cols = cur.fetchall()
    lines = [f"-- Schema for {table} (best-effort, captured {_now_iso()})"]
    lines.append(f"CREATE TABLE IF NOT EXISTS {table} (")
    parts = []
    for name, dtype, char_max, nullable, default in cols:
        if char_max and dtype in ("character varying", "character"):
            t = f"{dtype}({char_max})"
        else:
            t = dtype
        line = f"    {name} {t}"
        if default is not None:
            line += f" DEFAULT {default}"
        if nullable == "NO":
            line += " NOT NULL"
        parts.append(line)
    lines.append(",\n".join(parts))
    lines.append(");")
    return "\n".join(lines)


def _export_table(conn, table: str, out_dir: Path) -> dict:
    rec = {"table": table}
    with conn.cursor() as cur:
        if not _table_exists(cur, table):
            rec["status"] = "missing"
            rec["row_count"] = 0
            return rec
        rec["status"] = "ok"

        schema_sql = _schema_sql(cur, table)
        (out_dir / f"schema_{table}.sql").write_text(schema_sql, encoding="utf-8")

        cur2 = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur2.execute(f"SELECT * FROM {table}")
        rows = cur2.fetchall()
        cur2.close()

        jsonl_path = out_dir / f"{table}.jsonl"
        csv_path = out_dir / f"{table}.csv"

        if rows:
            cols = list(rows[0].keys())
        else:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s "
                "ORDER BY ordinal_position", (table,))
            cols = [r[0] for r in cur.fetchall()]

        with open(jsonl_path, "w", encoding="utf-8") as jf, \
             open(csv_path, "w", encoding="utf-8", newline="") as cf:
            cw = csv.DictWriter(cf, fieldnames=cols)
            cw.writeheader()
            for row in rows:
                jf.write(json.dumps(dict(row), default=_json_default,
                                    ensure_ascii=False) + "\n")
                cw.writerow({k: ("" if v is None else
                                 v.isoformat() if isinstance(v, (datetime, date))
                                 else v) for k, v in row.items()})
        n = len(rows)

        rec["row_count"] = n
    return rec


def main(out_dir_str: str) -> int:
    started_at = _now_iso()
    dsn = os.environ.get("POSTGRES_DSN", "")
    if not dsn:
        print("!! POSTGRES_DSN not set", file=sys.stderr)
        return 1

    out_dir = Path(out_dir_str)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[connect] {_redact_dsn(dsn)}")
    try:
        conn = psycopg2.connect(dsn, connect_timeout=10)
    except psycopg2.OperationalError as e:
        print(f"!! Connection failed: {e}", file=sys.stderr)
        manifest = {
            "started_at": started_at,
            "finished_at": _now_iso(),
            "dsn_redacted": _redact_dsn(dsn),
            "status": "connection_failed",
            "error": str(e),
            "tables": [],
        }
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return 2

    conn.autocommit = True
    print("[connect] OK")
    results = []
    for t in TABLES:
        try:
            rec = _export_table(conn, t, out_dir)
        except Exception as e:
            rec = {"table": t, "status": "fail", "error": f"{type(e).__name__}: {e}",
                   "row_count": -1}
        results.append(rec)
        print(f"  {t:>16} | {rec['status']:>8} | rows={rec.get('row_count', '?')}")
    conn.close()

    finished_at = _now_iso()
    manifest = {
        "started_at": started_at,
        "finished_at": finished_at,
        "dsn_redacted": _redact_dsn(dsn),
        "tables_requested": TABLES,
        "tables": results,
        "totals": {
            "ok": sum(1 for r in results if r["status"] == "ok"),
            "missing": sum(1 for r in results if r["status"] == "missing"),
            "fail": sum(1 for r in results if r["status"] == "fail"),
            "rows_total": sum(r.get("row_count", 0) for r in results
                              if r.get("status") == "ok"),
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[manifest] {manifest['totals']}")
    return 0


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "./pg_export"
    sys.exit(main(out))
