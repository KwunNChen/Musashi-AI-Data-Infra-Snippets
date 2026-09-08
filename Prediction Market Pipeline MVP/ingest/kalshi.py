import requests
from .config import KALSHI_WATCHLIST
from .logging_config import get_logger

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"

logger = get_logger(__name__)

def fetch_market(ticker):
    resp = requests.get(f"{KALSHI_BASE}/markets/{ticker}", timeout=10)
    resp.raise_for_status()
    return resp.json()["market"]


def fetch_watchlist():
    rows = []
    for ticker, category in KALSHI_WATCHLIST:
        try:
            market = fetch_market(ticker)
        except requests.RequestException as e:
            logger.error(f"skip {ticker}: {e}")
            continue

        yes_price = float(market["last_price_dollars"])
        rows.append({
            "external_id": market["ticker"],
            "title": market["title"],
            "category": category,
            "event_slug": market["event_ticker"],
            "close_time": market["close_time"],
            "status": market["status"],
            "yes_price": yes_price,
            "no_price": (float(market['no_bid_dollars']) + float(market['no_ask_dollars'])) / 2,  # midpoint of the no-side quote
            "volume": float(market["volume_fp"]),
            "open_interest": float(market["open_interest_fp"]),
        })
    return rows