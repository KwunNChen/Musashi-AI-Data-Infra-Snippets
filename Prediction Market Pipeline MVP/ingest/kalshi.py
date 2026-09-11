import requests
from .config import KALSHI_WATCHLIST
from .logging_config import get_logger

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"

logger = get_logger(__name__)

def fetch_market(ticker):
    resp = requests.get(f"{KALSHI_BASE}/markets/{ticker}", timeout=10)
    resp.raise_for_status()
    return resp.json()["market"]


def build_title(market):
    """Every market in a Kalshi event shares one `title`, so all five BTC strike buckets
    arrive as "BTC price  on Jan 1, 2027?". The strike is in `yes_sub_title`; append it when
    it has a digit so chart labels stay distinct. Digit-free subtitles ("Cuts") are skipped."""
    title = market["title"].strip()
    sub = (market.get("yes_sub_title") or "").strip()
    if sub and any(c.isdigit() for c in sub) and sub not in title:
        return f"{title} {sub}"
    return title


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
            "title": build_title(market),
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