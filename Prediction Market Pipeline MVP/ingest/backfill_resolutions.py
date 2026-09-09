import json
from .db import get_platforms, get_all_markets, upsert_resolution
from .kalshi import fetch_market as fetch_kalshi_market
from .polymarket import fetch_market_by_id as fetch_poly_market
from .logging_config import get_logger

logger = get_logger(__name__)

# Safe to rerun on a schedule — most markets are still open, so most runs find nothing new.
# Checked against real Kalshi settled-market JSON before writing this (not guessed):
# status flips to "finalized" and a "result" field ("yes"/"no") appears.
# Polymarket's outcome is read off outcomePrices once closed=True (see analysis notes on Day 3/5).


def check_kalshi(market):
    data = fetch_kalshi_market(market["external_id"])
    if data.get("status") != "finalized":
        return None
    return data.get("result"), data.get("settlement_ts")


def check_polymarket(market):
    data = fetch_poly_market(market["external_id"])
    if not data.get("closed"):
        return None
    outcomes = json.loads(data["outcomes"])
    prices = [float(p) for p in json.loads(data["outcomePrices"])]
    winner = outcomes[prices.index(max(prices))]
    return winner.lower(), data.get("closedTime")


def main():
    platforms = get_platforms()
    markets = get_all_markets()
    newly_resolved = 0

    for m in markets:
        platform_name = platforms.get(m["platform_id"])
        try:
            if platform_name == "kalshi":
                result = check_kalshi(m)
            elif platform_name == "polymarket":
                result = check_polymarket(m)
            else:
                logger.warning(f"unknown platform_id {m['platform_id']} for {m['external_id']}")
                continue
        except Exception as e:
            logger.warning(f"couldn't check {m['external_id']}: {e}")
            continue

        if result is None:
            continue
        outcome, resolved_at = result
        upsert_resolution(m["id"], outcome, resolved_at)
        logger.info(f"resolved: {m['title']} -> {outcome}")
        newly_resolved += 1

    logger.info(f"backfill complete, {newly_resolved} resolution(s) recorded/updated")


if __name__ == "__main__":
    main()
