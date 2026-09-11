"""Re-fetch market metadata (title, close_time, status) and upsert it, without writing any
snapshot rows.

Titles and close times change upstream, and a snapshot-writing run is the wrong tool when you
only want the metadata corrected: it moves the end of the analysis window. Run this after
changing how a title is built, or when a tracked market gets relisted.
"""
from .kalshi import fetch_watchlist as fetch_kalshi
from .polymarket import fetch_watchlist as fetch_polymarket
from .db import get_platform_id, upsert_market
from .logging_config import get_logger

logger = get_logger(__name__)


def main():
    for name, fetch in (("kalshi", fetch_kalshi), ("polymarket", fetch_polymarket)):
        platform_id = get_platform_id(name)
        for row in fetch():
            try:
                upsert_market(platform_id, row)
                logger.info(f"{name} {row['external_id']}: {row['title']}")
            except Exception as e:
                logger.error(f"failed on {row['external_id']}: {e}")


if __name__ == "__main__":
    main()
