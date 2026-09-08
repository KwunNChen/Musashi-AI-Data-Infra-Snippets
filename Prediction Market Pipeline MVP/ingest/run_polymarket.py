from .polymarket import fetch_watchlist
from .db import get_platform_id, upsert_market, insert_snapshot
from .logging_config import get_logger

logger = get_logger(__name__)

def main():
    platform_id = get_platform_id("polymarket")
    rows = fetch_watchlist()
    for row in rows:
        logger.info(f"{row['external_id']}: yes={row['yes_price']} vol={row['volume']}")
        try:
            market_id = upsert_market(platform_id, row)
            insert_snapshot(market_id, row)
        except Exception as e:
            logger.error(f"failed on {row['external_id']}: {e}")
            continue

if __name__ == "__main__":
    main()