import datetime as dt

import requests
import polars as pl

from ingest.config import SUPABASE_URL, SUPABASE_SERVICE_KEY
from .config import ANALYSIS_START, ANALYSIS_END

HEADERS = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}

PAGE = 1000


def parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


WINDOW_START = parse_ts(ANALYSIS_START)
WINDOW_END = parse_ts(ANALYSIS_END)


def fetch_all(table, **params):
    """Pages through PostgREST instead of taking the first N rows. A fixed limit quietly
    truncates the analysis once the table outgrows it, which is the kind of bug that shows up
    as numbers that are merely a bit wrong."""
    rows, offset = [], 0
    while True:
        page = dict(params, limit=PAGE, offset=offset)
        resp = requests.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, params=page, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        offset += PAGE


def load_snapshot_records():
    """Raw dicts with a parsed `ts`, clipped to the frozen analysis window. Kept out of polars
    so the stats module can run where tzdata isn't installed."""
    rows = fetch_all(
        "market_snapshots",
        select="*,markets(external_id,title,platform_id,category)",
        order="ts.asc",
    )
    out = []
    for r in rows:
        t = parse_ts(r["ts"])
        if WINDOW_START <= t <= WINDOW_END:
            r["ts_parsed"] = t
            out.append(r)
    return out


def load_snapshots() -> pl.DataFrame:
    records = load_snapshot_records()
    for r in records:
        r.pop("ts_parsed", None)
    df = pl.DataFrame(records)
    df = df.unnest("markets")
    df = df.with_columns(pl.col("ts").str.to_datetime(time_zone="UTC"))
    return df


def load_links() -> pl.DataFrame:
    return pl.DataFrame(fetch_all("cross_platform_links", select="*"))


def load_markets():
    return fetch_all("markets", select="*")


def load_platforms():
    return {p["id"]: p["name"] for p in fetch_all("platforms", select="*")}
