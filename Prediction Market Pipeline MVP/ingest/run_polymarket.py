import logging
from .polymarket import fetch_watchlist
from .db import get_platform_id, upsert_market, insert_snapshot

logging.basicConfig(level=logging.INFO, format="%(message)s") 

def main():
    platform_id = get_platform_id("polymarket")
    rows = fetch_watchlist()    
    for row in rows:
        logging.info(f"{row['external_id']}: yes={row['yes_price']} vol={row['volume']}")
        try:
            market_id = upsert_market(platform_id, row)
            insert_snapshot(market_id, row)
        except Exception as e:
            logging.error(f"failed on {row['external_id']}: {e}")
            continue

if __name__ == "__main__":
    main()