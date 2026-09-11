import json
import requests
from .config import POLYMARKET_WATCHLIST
from .logging_config import get_logger

POLY_BASE = "https://gamma-api.polymarket.com"

logger = get_logger(__name__)

def _fetch_by(param, value):
    """`closed` is a hard filter on this endpoint, not a hint. Omitting it defaults to
    closed=false, so a market that has actually closed comes back as an empty list unless
    you explicitly ask for closed=true (confirmed directly against the live API, not assumed).
    Since we're looking up one specific known market, try open first, then closed."""
    for closed in (False, True):
        resp = requests.get(f"{POLY_BASE}/markets/keyset", params={param: value, "closed": closed}, timeout=10)
        resp.raise_for_status()
        markets = resp.json()["markets"]
        if markets:
            return markets[0]
    raise ValueError(f"no market for {param}={value} (checked both open and closed)")


def fetch_market(slug):
    return _fetch_by("slug", slug)


def fetch_market_by_id(market_id):
    """Same as fetch_market but keyed by Polymarket's numeric id, which is what's stored as
    external_id in our `markets` table, not the slug, so lookups by external_id go through here."""
    return _fetch_by("id", market_id)


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