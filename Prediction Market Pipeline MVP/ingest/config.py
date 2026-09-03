import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

KALSHI_WATCHLIST = [
    ("KXBTCY-27JAN0100-B67500", "crypto"),
    ("KXBTCY-27JAN0100-B72500", "crypto"),
    ("KXBTCY-27JAN0100-B77500", "crypto"),
    ("KXBTCY-27JAN0100-T20000.00", "crypto"),
    ("KXBTCY-27JAN0100-T149999.99", "crypto"),
    ("KXETHY-27JAN0100-B2125", "crypto"),
    ("KXETHY-27JAN0100-B2375", "crypto"),
    ("KXRATECUT-26DEC31", "macro"),
    ("KXCABOUT-26MAY22-PHEG", "politics"),
    ("KXCABOUT-26MAY22-RFK", "politics"),
    ("KXCABOUT-26MAY22-MMUL", "politics"),
    ("KXCABOUT-26MAY22-SWIL", "politics"),
]

POLYMARKET_WATCHLIST = [
    ("will-bitcoin-reach-95000-by-december-31-2026-from-june-8", "crypto"),      # 43.5% yes
    ("will-bitcoin-reach-90000-by-december-31-2026-113-862-581-343", "crypto"),  # 59.5% yes
    ("will-bitcoin-dip-to-70000-by-december-31-2026-from-august-24", "crypto"),  # 49% yes — basically a coinflip
    ("will-no-fed-rate-cuts-happen-in-2026", "macro"),
    ("will-1-fed-rate-cut-happen-in-2026", "macro"),
    ("rfk-jr-out-by-december-31-524", "politics"),
    ("pete-hegseth-out-as-secretary-of-defense-by-december-31", "politics"),
]

'''Note for Eric:This is where I pull API keys from the .env file. Also change WATCHLIST whenever wanna change'''