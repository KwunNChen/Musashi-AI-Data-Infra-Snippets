import sys
from datetime import datetime, timezone

import requests

from .config import SUPABASE_URL, SUPABASE_SERVICE_KEY
from .logging_config import get_logger

logger = get_logger(__name__)

# Cron runs every 2h. 4h allows one missed run before this flags anything, so a single
# hiccup doesn't page anyone, but two in a row does.
STALE_AFTER_HOURS = 4


def main():
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/market_snapshots",
        headers=headers,
        params={"select": "ts", "order": "ts.desc", "limit": 1},
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json()

    if not rows:
        logger.error("market_snapshots is empty, nothing has ever landed")
        sys.exit(1)

    last_ts = datetime.fromisoformat(rows[0]["ts"].replace("Z", "+00:00"))
    age_hours = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
    logger.info(f"most recent snapshot: {last_ts.isoformat()} ({age_hours:.1f}h ago)")

    if age_hours > STALE_AFTER_HOURS:
        logger.error(
            f"pipeline looks stale: last snapshot was {age_hours:.1f}h ago, expected under {STALE_AFTER_HOURS}h"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
