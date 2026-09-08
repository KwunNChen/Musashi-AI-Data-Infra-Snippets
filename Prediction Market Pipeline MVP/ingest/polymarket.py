import json
import requests
from .config import POLYMARKET_WATCHLIST
from .logging_config import get_logger

POLY_BASE = "https://gamma-api.polymarket.com"

logger = get_logger(__name__)

def fetch_market(slug):
    resp = requests.get(f"{POLY_BASE}/markets/keyset", params={"slug": slug}, timeout=10)
    resp.raise_for_status()
    markets = resp.json()["markets"]
    if not markets:
        raise ValueError(f"no market for slug {slug}")
    return markets[0]


def fetch_watchlist():
    rows = []
    for slug, category in POLYMARKET_WATCHLIST:
        try:
            market = fetch_market(slug)
        except (requests.RequestException, ValueError) as e:
            logger.error(f"skip {slug}: {e}")
            continue

        outcomes = json.loads(market["outcomes"])
        prices = json.loads(market["outcomePrices"])
        yes_idx = outcomes.index("Yes")
        no_idx = 1 - yes_idx

        rows.append({
            "external_id": market["id"],
            "title": market["question"],
            "category": category,
            "event_slug": market["events"][0]["slug"] if market.get("events") else market["slug"],
            "close_time": market["endDate"],
            "status": "open" if market.get("active") and not market.get("closed") else "closed",
            "yes_price": float(prices[yes_idx]),
            "no_price": float(prices[no_idx]),
            "volume": float(market["volume"]),
            "open_interest": None,   # see note below
        })
    return rows