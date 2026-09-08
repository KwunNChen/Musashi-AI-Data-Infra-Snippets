import requests
import polars as pl
from ingest.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

HEADERS = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}

def load_snapshots() -> pl.DataFrame:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/market_snapshots",
        headers=HEADERS,
        params={"select": "*,markets(external_id,title,platform_id,category)", "order": "ts.asc", "limit": 5000},
        timeout=30,
    )
    resp.raise_for_status()
    df = pl.DataFrame(resp.json())
    df = df.unnest("markets")                              # flattens the embedded struct column
    df = df.with_columns(pl.col("ts").str.to_datetime(time_zone="UTC"))   # the fix above
    return df

def load_links() -> pl.DataFrame:
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/cross_platform_links", headers=HEADERS, params={"select": "*"}, timeout=10)
    resp.raise_for_status()
    return pl.DataFrame(resp.json())    