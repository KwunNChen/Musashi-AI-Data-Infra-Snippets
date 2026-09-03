import requests
from .config import SUPABASE_URL, SUPABASE_SERVICE_KEY

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

def get_platform_id(name):
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/platforms",
        headers=HEADERS,
        params={"name": f"eq.{name}", "select": "id"},
        timeout=10,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        raise ValueError(f"platform '{name}' not found in Supabase")
    return rows[0]["id"]


def upsert_market(platform_id, row):
    payload = {
        "platform_id": platform_id,
        "external_id": row["external_id"],
        "title": row["title"],
        "category": row["category"],
        "event_slug": row["event_slug"],
        "close_time": row["close_time"],
        "status": row["status"],
    }
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/markets",
        headers={**HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"},
        params={"on_conflict": "platform_id,external_id"},
        json=[payload],
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()[0]["id"]


def insert_snapshot(market_id, row):
    payload = {
        "market_id": market_id,
        "yes_price": row["yes_price"],
        "no_price": row["no_price"],
        "volume": row["volume"],
        "open_interest": row["open_interest"],
    }
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/market_snapshots",
        headers=HEADERS,
        json=[payload],
        timeout=10,
    )
    resp.raise_for_status()

    '''Note for Eric: 
    SUPABASE is different from duckdb because you send a request to the API instead of writing own SQL. Like we send GET or POST instead. And each table we create has its own URL 
    HEADERS is needed because you enabled RLS for Supabase, and that requires the service key to be passed to the Supabase API gateway'''