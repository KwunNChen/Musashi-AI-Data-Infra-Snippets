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

'''Note for Eric:This is where I pull API keys from the .env file. Also change WATCHLIST whenever wanna change'''