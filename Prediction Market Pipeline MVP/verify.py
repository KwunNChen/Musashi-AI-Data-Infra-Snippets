#!/usr/bin/env python
"""Verification suite for the prediction market pipeline.

    python verify.py              full check, exits non-zero on any failure
    python verify.py --self-test  proves the suite can fail, by injecting known faults
    python verify.py --offline    skip everything needing Supabase or the live APIs

Why this exists: the report quotes numbers that come from a database that keeps growing, and
prose that interprets those numbers but is not computed from them. Checking that by hand found
a new defect every time. This does it the same way every time, and says so out loud.

Two rules it follows, both learned from checks that lied:

  1. Nothing is suppressed. A check that crashes is a FAIL, never a silent pass. An earlier
     hand-check piped stderr to /dev/null and read a stale file, so a crashing stats.py looked
     like a passing determinism test.
  2. Unavailable is not the same as passing. Missing credentials produce SKIP lines and a
     separate skip count, so a green run with no database access cannot be mistaken for proof.

Section 5 regenerates analysis/output/stats.json on purpose: if the committed copy differs
from what the code produces today, that is a finding, not a nuisance.
"""
import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict

PROJ = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJ)
sys.path.insert(0, PROJ)

OUT = "analysis/output"
STATS = f"{OUT}/stats.json"
PDF = "Prediction_Market_Pipeline_Report.pdf"
CHARTS = ["repricing_speed.png", "volume.png"]  # divergence charts are discovered from stats

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Report:
    def __init__(self):
        self.rows = []
        self.section = ""

    def head(self, name):
        self.section = name
        print()
        print("=" * 78)
        print(name)
        print("=" * 78)

    def check(self, label, ok, detail=""):
        self.rows.append((self.section, label, PASS if ok else FAIL))
        print(f"  [{PASS if ok else FAIL}] {label}{('  ' + detail) if detail else ''}")
        return ok

    def skip(self, label, why):
        self.rows.append((self.section, label, SKIP))
        print(f"  [{SKIP}] {label}  ({why})")

    def counts(self):
        c = Counter(r[2] for r in self.rows)
        return c[PASS], c[FAIL], c[SKIP]

    def finish(self):
        p, f, s = self.counts()
        print()
        print("=" * 78)
        print(f"RESULT: {p} passed, {f} failed, {s} skipped")
        print("=" * 78)
        if f:
            print("\nFailures:")
            for sec, label, st in self.rows:
                if st == FAIL:
                    print(f"  {sec} -> {label}")
        if s:
            print("\nSkipped (not verified, do not read as passing):")
            for sec, label, st in self.rows:
                if st == SKIP:
                    print(f"  {sec} -> {label}")
        return 1 if f else 0


# --------------------------------------------------------------------------- helpers

def ts(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_stats(path=STATS):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def pair_by(stats, subject):
    hits = [p for p in stats["pairs"] if subject.lower() in p["kalshi_title"].lower()]
    return hits[0] if len(hits) == 1 else None


def is_btc(title):
    t = title.lower()
    return "btc" in t or "bitcoin" in t


def is_date_bucket(title):
    """Kalshi settle-on-one-date strike bucket, e.g. 'BTC price  on Jan 1, 2027? 65,000 to ...'"""
    t = title.lower()
    return "price" in t and " on jan" in t


def is_touch(title):
    """Polymarket touch-by-deadline contract, e.g. 'Will Bitcoin reach $90,000 by December 31'"""
    t = title.lower()
    return (" by december" in t or " by dec " in t) and ("reach" in t or "dip" in t)


def is_cabinet(title):
    return "cabinet" in title.lower()


def sh(cmd):
    """Run a command, never swallow its output."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def credentials():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PROJ, ".env"))
    except Exception:
        pass
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    return (url, key) if url and key else (None, None)


def fetch_all(url, key, table, order, select="*"):
    import requests
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    rows, offset = [], 0
    while True:
        params = {"select": select, "order": order, "limit": 1000, "offset": offset}
        r = requests.get(f"{url}/rest/v1/{table}", headers=headers, params=params, timeout=30)
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        offset += 1000


# --------------------------------------------------------------------------- claims

def claim_results(stats):
    """Each entry pairs a sentence from the PDF with a predicate over stats.json.

    These are the interpretations. Every number in the report is generated, but sentences like
    'Bitcoin sits at both ends of that ranking' are written by hand and stay in the document
    even when the data stops supporting them. Moving ANALYSIS_END is exactly when that happens.
    A failure here names the sentence to rewrite.
    """
    rep = stats["repricing"]
    vol = stats["volume"]
    fed = pair_by(stats, "Federal Reserve")
    rfk = pair_by(stats, "Kennedy")
    heg = pair_by(stats, "Hegseth")
    fast, slow = rep[:3], rep[-3:]
    top_vol = vol[0]
    rank = next((i for i, r in enumerate(rep, 1) if r["title"] == top_vol["title"]), None)

    out = []

    def c(sentence, ok):
        out.append((sentence, bool(ok)))

    bottom5 = rep[-5:]
    c("Most of the slow end is Kalshi settle-on-one-date strike buckets",
      sum(1 for r in bottom5 if r["platform"] == "kalshi" and is_date_bucket(r["title"])) >= 3)
    c("joined by the near-consensus Polymarket rate-cut market, the heaviest book tracked",
      any(r["title"] == top_vol["title"] for r in bottom5))
    c("Bitcoin sits at both ends of the ranking",
      any(is_btc(r["title"]) for r in fast) and any(is_btc(r["title"]) for r in slow))
    c("It splits along contract structure instead",
      any(is_touch(r["title"]) for r in fast)
      and sum(1 for r in bottom5 if is_date_bucket(r["title"])) >= 3)
    c("the heaviest book is among the slowest to move, though not the single slowest",
      rank is not None and rank > len(rep) * 2 / 3 and rank != len(rep))
    c("against $X and $Y on the thinnest Kalshi cabinet markets",
      all(v["platform"] == "kalshi" and is_cabinet(v["title"]) for v in vol[-2:]))
    c("all five Bitcoin strike buckets arrive as the same title",
      sum(1 for r in rep if r["platform"] == "kalshi" and is_btc(r["title"]) and is_date_bucket(r["title"])) == 5)
    c("one macro pair and two politics pairs",
      Counter(p["category"] for p in stats["pairs"]) == Counter({"macro": 1, "politics": 2}))
    c("the resolutions table holds 0 rows because nothing tracked has closed yet",
      stats["window"]["resolutions"] == 0)

    if fed:
        # The report prints the closing gap rather than asserting a size, so this only has to
        # hold the shape of the sentence: both series fell, and they end near each other
        # relative to how far apart they got mid-window.
        c("Both drifted down and finished close to level",
          fed["kalshi_last"] < fed["kalshi_first"] and fed["poly_last"] < fed["poly_first"]
          and abs(fed["kalshi_last"] - fed["poly_last"]) < 0.005)
        c("after Kalshi spiked mid-window and gave it back",
          fed["kalshi_max"] > fed["kalshi_first"] and fed["kalshi_last"] < fed["kalshi_max"])
        c("the gap opens wide and closes again inside a single window rather than holding",
          fed["ratio_max"] > 1.3 and abs(fed["kalshi_last"] / fed["poly_last"] - 1) < 0.1)
        c("Kalshi ends marginally below Polymarket",
          fed["kalshi_last"] < fed["poly_last"])
    else:
        c("Fed pair present in stats.json", False)

    if rfk and heg:
        c("RFK tight and consistent, Hegseth higher and noisier",
          rfk["ratio_std"] < heg["ratio_std"] and rfk["ratio_mean"] < heg["ratio_mean"])
        c("That upper bound is above 1.0 (Hegseth)", heg["ratio_max"] > 1.0)
        c("Kalshi prices this market consistently below Polymarket (RFK)", rfk["ratio_max"] < 1.0)
    else:
        c("RFK and Hegseth pairs present in stats.json", False)

    inc = stats["delivery"]["incomplete_batches"]
    c("Three fall in the bring-up period, the fourth is a local Polymarket-only run",
      len(inc) == 4 and sum(1 for b in inc if b["at"] < "2026-09-04") == 3)

    return out


def pdf_number_results(stats, flat):
    """Every figure the PDF quotes, matched back to stats.json."""
    W, D = stats["window"], stats["delivery"]
    fed = pair_by(stats, "Federal Reserve")
    rfk = pair_by(stats, "Kennedy")
    heg = pair_by(stats, "Hegseth")
    rep, vol = stats["repricing"], stats["volume"]
    top = vol[0]
    rank = next(i for i, r in enumerate(rep, 1) if r["title"] == top["title"])

    want = [
        ("window rows", f"{W['rows']} snapshot rows"),
        ("window markets", f"{W['markets']} markets"),
        ("window start", W["first_snapshot"]),
        ("window end", W["last_snapshot"]),
        ("observation days", f"{W['days']} days of observation"),
        ("resolutions", f"holds {W['resolutions']} rows"),
        ("watchlist split", f"{W['per_platform']['kalshi']} Kalshi tickers and {W['per_platform']['polymarket']}"),
        ("batches", f"{D['batches']} poll batches"),
        ("span hours", f"{D['span_hours']:.0f} hours"),
        ("median gap", f"{D['median_gap_hours']} hours"),
        ("max gap", f"{D['max_gap_hours']} hours"),
        ("batches per day", f"{D['batches_per_day']} batches a day"),
        ("delivery pct", f"{D['delivery_pct']}%"),
        ("complete batches", f"{D['complete_batches']} of {D['batches']}"),
        ("top volume", f"${top['volume'] / 1e6:.2f}M"),
        ("volume speed rank", f"{rank}th of {len(rep)}"),
    ]
    for i, r in enumerate(rep[:3]):
        want.append((f"fastest #{i + 1} speed", f"{r['speed']:.5f}"))
    for i, r in enumerate(rep[-3:]):
        want.append((f"slowest speed {i + 1}", f"{r['speed']:.5f}"))
    if fed:
        want += [
            ("fed n", f"{fed['n']} aligned snapshots"),
            ("fed mean", f"averaged {fed['ratio_mean']:.2f}"),
            ("fed median", f"median {fed['ratio_median']:.2f}"),
            ("fed std", f"deviation {fed['ratio_std']:.2f}"),
            ("fed range", f"{fed['ratio_min']:.2f} to {fed['ratio_max']:.2f}"),
            ("fed kalshi first", f"{fed['kalshi_first']:.3f}"),
            ("fed kalshi last", f"{fed['kalshi_last']:.3f}"),
            ("fed kalshi max", f"{fed['kalshi_max']:.3f}"),
            ("fed poly first", f"{fed['poly_first']:.3f}"),
            ("fed poly last", f"{fed['poly_last']:.3f}"),
        ]
    for name, p in (("rfk", rfk), ("hegseth", heg)):
        if p:
            want += [
                (f"{name} mean", f"{p['ratio_mean']:.2f}"),
                (f"{name} median", f"{p['ratio_median']:.2f}"),
                (f"{name} std", f"{p['ratio_std']:.2f}"),
                (f"{name} range", f"{p['ratio_min']:.2f} to {p['ratio_max']:.2f}"),
            ]
    for b in D["incomplete_batches"]:
        want.append((f"incomplete batch {b['at']}", b["at"]))
    return [(label, needle in flat, needle) for label, needle in want]


# --------------------------------------------------------------------------- sections

def section_environment(R):
    R.head("1. ENVIRONMENT")
    code, out = sh([sys.executable, "-m", "compileall", "-q", "ingest", "analysis"])
    R.check("all modules compile", code == 0, out.strip()[:200])
    mods = ["ingest.config", "ingest.db", "ingest.kalshi", "ingest.polymarket", "ingest.run_kalshi",
            "ingest.run_polymarket", "ingest.backfill_resolutions", "ingest.health_check",
            "ingest.logging_config", "ingest.refresh_market_metadata", "analysis.config",
            "analysis.load_data", "analysis.stats", "analysis.report"]
    for m in mods:
        code, out = sh([sys.executable, "-c", f"import {m}"])
        R.check(f"import {m}", code == 0, out.strip().splitlines()[-1][:160] if code else "")

    std = set(sys.stdlib_module_names)
    alias = {"dotenv": "python-dotenv"}
    req = {line.strip().lower() for line in open("requirements.txt") if line.strip()}
    found = set()
    for d in ("ingest", "analysis"):
        for f in os.listdir(d):
            if f.endswith(".py"):
                tree = ast.parse(open(os.path.join(d, f), encoding="utf-8").read())
                for n in ast.walk(tree):
                    if isinstance(n, ast.Import):
                        found |= {a.name.split(".")[0] for a in n.names}
                    elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                        found.add(n.module.split(".")[0])
    for m in sorted(found - std - {"ingest", "analysis"}):
        R.check(f"requirements.txt covers {m}", alias.get(m, m) in req)


def section_config(R):
    R.head("2. CONFIG SANITY")
    from analysis.config import ANALYSIS_START, ANALYSIS_END, BATCH_WINDOW_SECONDS, PAIR_TOLERANCE_SECONDS
    start, end = ts(ANALYSIS_START), ts(ANALYSIS_END)
    now = dt.datetime.now(dt.timezone.utc)
    R.check("ANALYSIS_START < ANALYSIS_END", start < end, f"{ANALYSIS_START} -> {ANALYSIS_END}")
    # A bound in the future is not a freeze: the next scheduled run lands inside the window.
    R.check("ANALYSIS_END is in the past", end < now, f"{ANALYSIS_END} vs now {now:%Y-%m-%dT%H:%M:%SZ}")
    R.check("batch window is positive", BATCH_WINDOW_SECONDS > 0)
    R.check("pair tolerance is positive", PAIR_TOLERANCE_SECONDS > 0)

    if os.path.exists(STATS):
        stats = load_stats()
        src = open("ingest/health_check.py", encoding="utf-8").read()
        m = re.search(r"STALE_AFTER_HOURS\s*=\s*(\d+(?:\.\d+)?)", src)
        if m:
            thresh = float(m.group(1))
            median = stats["delivery"]["median_gap_hours"]
            R.check("health-check threshold exceeds the measured median gap",
                    thresh > median, f"{thresh}h vs {median}h")
        R.check("stats.json records the configured window",
                stats["window"]["configured_end"] == ANALYSIS_END)


def section_data_integrity(R, url, key):
    R.head("3. DATA INTEGRITY (independent recomputation)")
    if not url:
        R.skip("recompute every figure from the database", "no Supabase credentials")
        return None
    import statistics
    from analysis.config import ANALYSIS_START, ANALYSIS_END, BATCH_WINDOW_SECONDS, PAIR_TOLERANCE_SECONDS
    start, end = ts(ANALYSIS_START), ts(ANALYSIS_END)
    stats = load_stats()

    raw = fetch_all(url, key, "market_snapshots", "ts.asc")
    snaps = []
    for r in raw:
        t = ts(r["ts"])
        if start <= t <= end:
            r["_t"] = t
            snaps.append(r)
    markets = {m["id"]: m for m in fetch_all(url, key, "markets", "id.asc")}
    plats = {p["id"]: p["name"] for p in fetch_all(url, key, "platforms", "id.asc")}
    links = fetch_all(url, key, "cross_platform_links", "id.asc")
    resos = fetch_all(url, key, "resolutions", "market_id.asc")

    W, D = stats["window"], stats["delivery"]
    beyond = sum(1 for r in raw if ts(r["ts"]) > end)
    print(f"  (table holds {len(raw)} rows; {beyond} sit past ANALYSIS_END and are excluded by the freeze)")
    R.check("window row count", W["rows"] == len(snaps), f"{W['rows']} vs {len(snaps)}")
    R.check("window excludes everything past END", not any(s["_t"] > end for s in snaps))
    R.check("market count", W["markets"] == len(markets))
    R.check("link count", W["links"] == len(links))
    R.check("resolution count", W["resolutions"] == len(resos))

    times = sorted(s["_t"] for s in snaps)
    span_h = (times[-1] - times[0]).total_seconds() / 3600
    R.check("first snapshot date", W["first_snapshot"] == times[0].strftime("%Y-%m-%d"))
    R.check("last snapshot date", W["last_snapshot"] == times[-1].strftime("%Y-%m-%d"))
    R.check("observation days", W["days"] == round(span_h / 24, 1))
    pc = Counter(plats[m["platform_id"]] for m in markets.values())
    R.check("kalshi market count", W["per_platform"]["kalshi"] == pc["kalshi"])
    R.check("polymarket market count", W["per_platform"]["polymarket"] == pc["polymarket"])

    batches = []
    for t in sorted(set(times)):
        if batches and (t - batches[-1][-1]).total_seconds() <= BATCH_WINDOW_SECONDS:
            batches[-1].append(t)
        else:
            batches.append([t])
    gaps = [(batches[i + 1][0] - batches[i][0]).total_seconds() / 3600 for i in range(len(batches) - 1)]
    R.check("batch count", D["batches"] == len(batches), f"{D['batches']} vs {len(batches)}")
    R.check("span hours", D["span_hours"] == round(span_h, 1))
    R.check("median gap", D["median_gap_hours"] == round(statistics.median(gaps), 1))
    R.check("max gap", D["max_gap_hours"] == round(max(gaps), 1))
    R.check("batches per day", D["batches_per_day"] == round(len(batches) / (span_h / 24), 1))
    R.check("delivery pct", D["delivery_pct"] == round(len(batches) / (span_h / 24) / 12 * 100))

    by_t = defaultdict(list)
    for s in snaps:
        by_t[s["_t"]].append(s)
    inc = []
    for b in batches:
        ids = {s["market_id"] for t in b for s in by_t[t]}
        if len(ids) != len(markets):
            inc.append({"at": b[0].strftime("%Y-%m-%d %H:%M UTC"), "markets": len(ids),
                        "platforms": sorted({plats[markets[i]["platform_id"]] for i in ids})})
    R.check("complete batch count", D["complete_batches"] == len(batches) - len(inc))
    R.check("incomplete batch list", D["incomplete_batches"] == inc)

    def series(mid):
        return sorted((s["_t"], s["yes_price"]) for s in snaps
                      if s["market_id"] == mid and s["yes_price"] is not None)

    def align(a, b):
        out = []
        for ta, va in a:
            best = min(b, key=lambda x: abs((x[0] - ta).total_seconds()), default=None)
            if best and abs((best[0] - ta).total_seconds()) <= PAIR_TOLERANCE_SECONDS:
                out.append((ta, va, best[1]))
        return out

    independent = {}
    for L in links:
        k, p = L["kalshi_market_id"], L["polymarket_market_id"]
        ks, ps = series(k), series(p)
        if L.get("note") and "invert" in L["note"].lower():
            ps = [(t, 1.0 - v) for t, v in ps]
        j = align(ks, ps)
        ratios = [kv / pv for _, kv, pv in j if pv]
        independent[k] = j
        sp = next((x for x in stats["pairs"] if x["kalshi_market_id"] == k), None)
        if not sp:
            R.check(f"pair {k} present in stats.json", False)
            continue
        nm = f"pair {k} ({sp['category']})"
        R.check(f"{nm} n", sp["n"] == len(ratios))
        R.check(f"{nm} mean", round(sp["ratio_mean"], 6) == round(statistics.mean(ratios), 6))
        R.check(f"{nm} median", round(sp["ratio_median"], 6) == round(statistics.median(ratios), 6))
        R.check(f"{nm} std", round(sp["ratio_std"], 6) == round(statistics.stdev(ratios), 6))
        R.check(f"{nm} min/max", round(sp["ratio_min"], 6) == round(min(ratios), 6)
                and round(sp["ratio_max"], 6) == round(max(ratios), 6))
        R.check(f"{nm} endpoints", round(sp["kalshi_first"], 6) == round(j[0][1], 6)
                and round(sp["kalshi_last"], 6) == round(j[-1][1], 6)
                and round(sp["poly_first"], 6) == round(j[0][2], 6)
                and round(sp["poly_last"], 6) == round(j[-1][2], 6))

    speeds = {}
    for mid, m in markets.items():
        pts = series(mid)
        vals = [abs(pts[i + 1][1] - pts[i][1]) / ((pts[i + 1][0] - pts[i][0]).total_seconds() / 3600)
                for i in range(len(pts) - 1) if (pts[i + 1][0] - pts[i][0]).total_seconds() > 0]
        if vals:
            speeds[m["title"]] = statistics.mean(vals)
    R.check("repricing entry count", len(stats["repricing"]) == len(speeds))
    R.check("every repricing speed matches",
            all(round(r["speed"], 9) == round(speeds.get(r["title"], -1), 9) for r in stats["repricing"]))
    R.check("repricing sorted fast to slow",
            [r["title"] for r in stats["repricing"]] == sorted(speeds, key=speeds.get, reverse=True))

    latest = {}
    for s in snaps:
        if s["market_id"] not in latest or s["_t"] > latest[s["market_id"]]["_t"]:
            latest[s["market_id"]] = s
    vols = {markets[mid]["title"]: r["volume"] for mid, r in latest.items() if r["volume"] is not None}
    R.check("volume entry count", len(stats["volume"]) == len(vols))
    R.check("every volume matches", all(v["volume"] == vols.get(v["title"]) for v in stats["volume"]))
    R.check("market titles are unique", len(markets) == len({m["title"] for m in markets.values()}))

    poly_ids = {mid for mid, m in markets.items() if plats[m["platform_id"]] == "polymarket"}
    R.check("Polymarket open_interest is NULL throughout",
            all(s["open_interest"] is None for s in snaps if s["market_id"] in poly_ids))
    return independent


def section_chart_text(R, independent):
    R.head("4. CHART PATH vs TEXT PATH")
    if independent is None:
        R.skip("polars join_asof against independent alignment", "no Supabase credentials")
        return
    import polars as pl
    from analysis.load_data import load_snapshots, load_links
    df, ldf = load_snapshots(), load_links()
    for link in ldf.iter_rows(named=True):
        k = df.filter(pl.col("market_id") == link["kalshi_market_id"]).sort("ts")
        p = (df.filter(pl.col("market_id") == link["polymarket_market_id"])
             .sort("ts").rename({"yes_price": "yes_price_poly"}))
        merged = k.join_asof(p, on="ts", strategy="nearest", tolerance="30m").drop_nulls("yes_price_poly")
        if link["note"] and "invert" in link["note"].lower():
            merged = merged.with_columns((1 - pl.col("yes_price_poly")).alias("yes_price_poly"))
        j = independent[link["kalshi_market_id"]]
        nm = f"pair {link['kalshi_market_id']}"
        R.check(f"{nm} aligned count agrees", len(j) == merged.height, f"{len(j)} vs {merged.height}")
        R.check(f"{nm} endpoints agree",
                round(j[0][1], 6) == round(merged["yes_price"][0], 6)
                and round(j[-1][1], 6) == round(merged["yes_price"][-1], 6)
                and round(j[0][2], 6) == round(merged["yes_price_poly"][0], 6)
                and round(j[-1][2], 6) == round(merged["yes_price_poly"][-1], 6))


def section_determinism(R, url):
    R.head("5. DETERMINISM")
    if not url:
        R.skip("stats.json and charts reproduce byte-for-byte", "no Supabase credentials")
        return
    before = md5(STATS) if os.path.exists(STATS) else None
    before_charts = sorted((f, md5(f"{OUT}/{f}")) for f in os.listdir(OUT) if f.endswith(".png"))
    # Regenerating rewrites these files. If the bytes come back identical the artifacts are
    # semantically untouched, so put the timestamps back: otherwise running this suite would
    # make charts look newer than the PDF and fail the freshness check on the next run.
    keep = {f"{OUT}/{f}": (os.path.getatime(f"{OUT}/{f}"), os.path.getmtime(f"{OUT}/{f}"))
            for f in os.listdir(OUT)}
    hashes, chart_hashes = [], []
    for i in (1, 2):
        code, out = sh([sys.executable, "-m", "analysis.report"])
        if not R.check(f"analysis.report run {i} exits clean", code == 0, out.strip()[-300:] if code else ""):
            return
        hashes.append(md5(STATS))
        chart_hashes.append(sorted((f, md5(f"{OUT}/{f}")) for f in os.listdir(OUT) if f.endswith(".png")))
    R.check("stats.json is byte-identical across runs", hashes[0] == hashes[1], f"{hashes[0][:12]} / {hashes[1][:12]}")
    R.check("charts are byte-identical across runs", chart_hashes[0] == chart_hashes[1])
    unchanged = before == hashes[0] and before_charts == chart_hashes[0]
    if before:
        R.check("committed stats.json was already current", before == hashes[0],
                "regenerating changed it, so the committed copy was stale" if before != hashes[0] else "")
    if unchanged:
        for path, (at, mt) in keep.items():
            if os.path.exists(path):
                os.utime(path, (at, mt))


def snapshot_mtimes():
    """Sampled before section 5 regenerates anything, so the freshness check reflects the state
    the run started in rather than the state the run created."""
    out = {}
    for f in os.listdir(OUT):
        out[f"{OUT}/{f}"] = os.path.getmtime(f"{OUT}/{f}")
    if os.path.exists(PDF):
        out[PDF] = os.path.getmtime(PDF)
    return out


def section_artifacts(R, mtimes):
    R.head("6. ARTIFACTS")
    stats = load_stats()
    wanted = CHARTS + [p["chart"] for p in stats["pairs"]]
    for f in wanted:
        path = f"{OUT}/{f}"
        R.check(f"{f} exists and is non-empty", os.path.exists(path) and os.path.getsize(path) > 0)
    R.check("stats.json non-empty", os.path.getsize(STATS) > 0)
    R.check("PDF exists and is non-empty", os.path.exists(PDF) and os.path.getsize(PDF) > 0)
    if PDF in mtimes:
        chart_times = [mtimes[f"{OUT}/{f}"] for f in wanted if f"{OUT}/{f}" in mtimes]
        R.check("PDF is at least as new as the charts it embeds",
                mtimes[PDF] >= max(chart_times) - 1)
        R.check("PDF is at least as new as stats.json",
                mtimes[PDF] >= mtimes.get(STATS, 0) - 1)


def pdf_text():
    from pypdf import PdfReader
    r = PdfReader(PDF)
    text = "".join(p.extract_text() for p in r.pages)
    return r, text, " ".join(text.split())


def section_pdf(R):
    R.head("7. PDF CONTENT AND HYGIENE")
    try:
        import pypdf  # noqa: F401
    except ImportError:
        R.skip("PDF content, numbers and hygiene", "pypdf not installed, see requirements-dev.txt")
        return
    stats = load_stats()
    reader, text, flat = pdf_text()
    R.check("page count is sane", 5 <= len(reader.pages) <= 20, f"{len(reader.pages)} pages")
    R.check("five charts embedded", sum(len(p.images) for p in reader.pages) == 5)

    for label, needle in [("no em dashes", "—"), ("no en dashes", "–"),
                          ("no replacement glyphs", "�"), ("no curly quotes", "“"),
                          ("no 'genuine'", "genuine")]:
        n = text.lower().count(needle) if needle.isalpha() else text.count(needle)
        R.check(label, n == 0, f"found {n}" if n else "")

    for h in ["1. Architecture and pipeline", "1.1 Schema", "1.2 Ingestion", "1.3 Scheduling",
              "2. Platform and API differences", "3. Research synthesis", "3.1 Resolution risk",
              "3.2 Trading methodology", "3.3 Theory", "4. Findings", "4.1 Repricing speed",
              "4.2 Volume distribution", "4.3 Cross-platform divergence", "4.3.1 Macro pair",
              "4.3.2 Politics pairs", "5. Limitations", "6. Next steps"]:
        R.check(f"heading present: {h}", h in flat)

    # Strings that were wrong in earlier drafts and must never come back.
    for gone in ["May 22, 2026", "640 snapshot rows", "Every batch that does land", "32 aligned",
                 "ended at 0.102", "8.19M", "4.9 batches", "not yet populated", "see Next Steps",
                 "two X accounts", "One wrinkle worth recording", "Two caveats keep that number honest",
                 "an earlier draft of this report", "behaviour"]:
        R.check(f"regression absent: {gone!r}", gone not in flat)

    for label, ok, needle in pdf_number_results(stats, flat):
        R.check(f"PDF quotes {label}", ok, "" if ok else f"missing {needle!r}")


def section_claims(R):
    R.head("8. CLAIMS (interpretations the data must still support)")
    stats = load_stats()
    for sentence, ok in claim_results(stats):
        R.check(f'"{sentence}"', ok, "" if ok else "<- rewrite this sentence in analysis/build_report.py")


def section_external(R):
    R.head("9. EXTERNAL API CLAIMS")
    try:
        import requests
        requests.get("https://gamma-api.polymarket.com/markets", params={"limit": 1}, timeout=15)
    except Exception as e:
        R.skip("Polymarket and Kalshi API claims", f"no network: {type(e).__name__}")
        return
    for ep in ("markets", "events"):
        r = requests.get(f"https://gamma-api.polymarket.com/{ep}", params={"limit": 1}, timeout=20)
        R.check(f"/{ep} still returns 200 while deprecated",
                r.status_code == 200 and r.headers.get("deprecation") == "true")
        R.check(f"/{ep} sunset header says 2026-05-01", "01 May 2026" in (r.headers.get("sunset") or ""))
    r = requests.get("https://gamma-api.polymarket.com/markets/keyset",
                     params={"closed": "false", "limit": 1}, timeout=20)
    m = r.json()["markets"][0]
    R.check("keyset returns price and metadata in one call", "outcomePrices" in m and "volume" in m)
    R.check("keyset exposes no per-market open interest",
            "openInterest" not in m and "open_interest" not in m)
    bid, ask = float(m["bestBid"]), float(m["bestAsk"])
    mid = float(json.loads(m["outcomePrices"])[0])
    R.check("outcomePrices is the bid/ask midpoint", abs(mid - (bid + ask) / 2) < 1e-6,
            f"{mid} vs ({bid}+{ask})/2")
    r = requests.get("https://api.elections.kalshi.com/trade-api/v2/markets/KXCABOUT-26MAY22-RFK", timeout=20)
    d = r.json()["market"]
    R.check("Kalshi reads with no auth header", r.status_code == 200)
    R.check("all five Kalshi price fields present",
            all(f in d for f in ("last_price_dollars", "no_bid_dollars", "no_ask_dollars",
                                 "volume_fp", "open_interest_fp")))
    R.check("cabinet ticker named 26MAY22 really closes 2029-01-20",
            d["close_time"].startswith("2029-01-20"), d["close_time"])
    R.check("yes_sub_title exists (used to disambiguate titles)", "yes_sub_title" in d)


def section_infrastructure(R):
    R.head("10. INFRASTRUCTURE CLAIMS")
    root = os.path.dirname(PROJ)
    wf = os.path.join(root, ".github", "workflows")
    ing = os.path.join(wf, "prediction-markets-w1.yml")
    hc = os.path.join(wf, "pipeline-health-check.yml")
    R.check("ingestion workflow at repo root", os.path.exists(ing))
    R.check("health-check workflow at repo root", os.path.exists(hc))
    if os.path.exists(ing):
        s = open(ing, encoding="utf-8").read()
        R.check("ingestion cron is every 2h offset off :00", 'cron: "17 */2 * * *"' in s)
        R.check("backfill runs after ingestion", "ingest.backfill_resolutions" in s)
        R.check("log uploaded as an artifact", "upload-artifact" in s)
        from ingest.logging_config import LOG_FILE
        R.check("artifact path matches logging_config.LOG_FILE",
                LOG_FILE.replace(os.sep, "/") in s.replace("\\", "/"), LOG_FILE)
    if os.path.exists(hc):
        s = open(hc, encoding="utf-8").read()
        R.check("health-check cron is every 6h", 'cron: "45 */6 * * *"' in s)
    src = open("ingest/health_check.py", encoding="utf-8").read()
    R.check("health-check threshold is the 10h the PDF states", "STALE_AFTER_HOURS = 10" in src)
    R.check("kalshi appends yes_sub_title", "yes_sub_title" in open("ingest/kalshi.py", encoding="utf-8").read())
    R.check("no unbounded row limit left in analysis",
            not re.search(r"limit\D{0,4}5000", open("analysis/load_data.py", encoding="utf-8").read()))


def section_security(R):
    R.head("11. SECURITY AND ENCODING")
    code, tracked = sh(["git", "ls-files"])
    if code != 0:
        R.skip("tracked-file checks", "git not available")
        return
    files = [f for f in tracked.splitlines() if f.strip()]
    root = os.path.dirname(PROJ)
    R.check(".env is gitignored", ".env" in open(".gitignore", encoding="utf-8").read())
    R.check(".env is not tracked", not any(f.endswith("/.env") or f == ".env" for f in files))

    secrets = re.compile(r"eyJhbGciOi|service_role\s*[:=]\s*['\"]ey")
    offenders = []
    for f in files:
        p = os.path.join(root, f)
        if not os.path.exists(p) or os.path.getsize(p) > 5_000_000:
            continue
        try:
            raw = open(p, "rb").read()
        except OSError:
            continue
        if raw[:4] == b"%PDF":
            continue
        text = raw.decode("utf-8", errors="replace")
        if secrets.search(text):
            offenders.append(f)
    R.check("no JWT material in tracked files", not offenders, ", ".join(offenders))

    url = os.environ.get("SUPABASE_URL") or ""
    host = url.split("//")[-1].split(".")[0] if url else None
    if host:
        leaked = []
        for f in files:
            p = os.path.join(root, f)
            if not os.path.exists(p) or os.path.getsize(p) > 5_000_000:
                continue
            if host in open(p, "rb").read().decode("utf-8", "replace"):
                leaked.append(f)
        R.check("project ref does not appear in tracked files", not leaked, ", ".join(leaked))
    else:
        R.skip("project ref not in tracked files", "SUPABASE_URL not loaded")
    R.check("stats.json carries no credentials",
            not secrets.search(open(STATS, encoding="utf-8").read()))

    text_ext = {".py", ".md", ".yml", ".yaml", ".txt", ".json", ".example", ".gitignore"}
    bad_enc = []
    for f in files:
        p = os.path.join(root, f)
        if not os.path.exists(p):
            continue
        if os.path.splitext(f)[1] in text_ext or f.endswith(".gitignore"):
            raw = open(p, "rb").read()
            if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                bad_enc.append(f)
    R.check("no UTF-16 text files (the bug that broke the README on GitHub)", not bad_enc, ", ".join(bad_enc))


def section_failure_modes(R):
    R.head("12. FAILURE MODES")
    tmp = tempfile.mkdtemp(prefix="verify_fm_")
    try:
        # Work on a copy so the real stats.json and PDF are never at risk.
        shutil.copytree("analysis", os.path.join(tmp, "analysis"))
        shutil.copytree("ingest", os.path.join(tmp, "ingest"))
        shutil.copy(".env", os.path.join(tmp, ".env")) if os.path.exists(".env") else None
        os.remove(os.path.join(tmp, "analysis", "output", "stats.json"))
        proc = subprocess.run([sys.executable, "-m", "analysis.build_report"], cwd=tmp,
                              capture_output=True, text=True)
        combined = (proc.stdout or "") + (proc.stderr or "")
        R.check("missing stats.json gives a readable message, not a traceback",
                proc.returncode != 0
                and "Run `python -m analysis.report` first" in combined
                and "Traceback" not in combined,
                combined.strip().splitlines()[-1][:140] if combined.strip() else "no output")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    src = open("analysis/build_report.py", encoding="utf-8").read()
    R.check("pairs looked up by subject, not by hardcoded database id",
            "PAIRS[8]" not in src and "def pair(" in src)


def section_readme(R):
    """The README quotes the same figures as the PDF and is the first thing a reviewer reads.
    Nothing checked it until a widened window silently made five of its numbers wrong."""
    R.head("13. README AGREES WITH THE DATA")
    stats = load_stats()
    W = stats["window"]
    fed, rfk, heg = (pair_by(stats, x) for x in ("Federal Reserve", "Kennedy", "Hegseth"))
    text = open("README.md", encoding="utf-8").read()
    flat = " ".join(text.split())
    want = [
        ("snapshot count", f"{W['rows']} snapshots"),
        ("market count", f"{W['markets']} markets tracked"),
        ("collection start", W["first_snapshot"]),
        ("fed aligned count", f"{fed['n']} aligned snapshots"),
        ("fed mean ratio", f"averaged {fed['ratio_mean']:.2f}"),
        ("fed ratio range", f"between {fed['ratio_min']:.2f} and {fed['ratio_max']:.2f}"),
        ("fed endpoints", f"({fed['kalshi_last']:.3f} against {fed['poly_last']:.3f})"),
        ("rfk mean", f"mean {rfk['ratio_mean']:.2f}"),
        ("rfk std", f"std {rfk['ratio_std']:.2f}"),
        ("rfk range", f"range {rfk['ratio_min']:.2f} to {rfk['ratio_max']:.2f}"),
        ("hegseth mean and std", f"({heg['ratio_mean']:.2f}, std {heg['ratio_std']:.2f})"),
        ("hegseth max", f"tops out at {heg['ratio_max']:.2f}"),
        ("median gap", f"{stats['delivery']['median_gap_hours']}h median gap"),
        ("worst gap", f"{stats['delivery']['max_gap_hours']}h worst case"),
        ("delivery pct", f"about {stats['delivery']['delivery_pct']}% of requested runs"),
    ]
    for label, needle in want:
        R.check(f"README quotes {label}", needle in flat, "" if needle in flat else f"missing {needle!r}")
    for bad in ["773 snapshots", "39 aligned", "averaged 1.40", "0.075 vs 0.074", "0.64 to 0.78"]:
        R.check(f"README regression absent: {bad!r}", bad not in flat)
    R.check("README has no em or en dashes", "—" not in text and "–" not in text)


# --------------------------------------------------------------------------- self-test

def section_self_test(R):
    """Prove the suite can fail. A check that has never failed is not evidence."""
    R.head("SELF-TEST (injecting known faults)")
    try:
        import pypdf  # noqa: F401
    except ImportError:
        R.skip("fault injection against PDF checks", "pypdf not installed")
        return
    base = load_stats()
    _, _, flat = pdf_text()

    def mutate(path, value):
        s = json.loads(json.dumps(base))
        node = s
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value
        return s

    fed_i = next(i for i, p in enumerate(base["pairs"]) if "Federal Reserve" in p["kalshi_title"])
    heg_i = next(i for i, p in enumerate(base["pairs"]) if "Hegseth" in p["kalshi_title"])

    faults = [
        ("row count bumped by one", mutate(["window", "rows"], base["window"]["rows"] + 1), "numbers"),
        ("resolutions claimed non-zero", mutate(["window", "resolutions"], 3), "claims"),
        ("batch count changed", mutate(["delivery", "batches"], base["delivery"]["batches"] + 5), "numbers"),
        ("Fed mean ratio shifted", mutate(["pairs", fed_i, "ratio_mean"], base["pairs"][fed_i]["ratio_mean"] + 0.5), "numbers"),
        ("Fed endpoints pulled apart", mutate(["pairs", fed_i, "kalshi_last"], base["pairs"][fed_i]["poly_last"] + 0.2), "claims"),
        ("Hegseth max dropped below 1.0", mutate(["pairs", heg_i, "ratio_max"], 0.9), "claims"),
        ("top volume changed", mutate(["volume", 0, "volume"], base["volume"][0]["volume"] * 2), "numbers"),
    ]
    rev = json.loads(json.dumps(base))
    rev["repricing"] = list(reversed(rev["repricing"]))
    faults.append(("repricing order reversed", rev, "claims"))

    caught = 0
    for name, bad, kind in faults:
        if kind == "numbers":
            detected = any(not ok for _, ok, _ in pdf_number_results(bad, flat))
        else:
            detected = any(not ok for _, ok in claim_results(bad))
        if R.check(f"fault caught: {name}", detected):
            caught += 1
    print(f"\n  {caught}/{len(faults)} injected faults detected")

    clean_numbers = all(ok for _, ok, _ in pdf_number_results(base, flat))
    clean_claims = all(ok for _, ok in claim_results(base))
    R.check("unmutated stats still passes (no false alarms)", clean_numbers and clean_claims)


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true", help="inject known faults and prove they are caught")
    ap.add_argument("--offline", action="store_true", help="skip Supabase and live API checks")
    args = ap.parse_args()

    R = Report()
    print(f"verifying {PROJ}")
    print(f"python {sys.version.split()[0]}  at {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} UTC")

    if args.self_test:
        section_self_test(R)
        return R.finish()

    url, key = (None, None) if args.offline else credentials()
    mtimes = snapshot_mtimes()
    section_environment(R)
    section_config(R)
    independent = section_data_integrity(R, url, key)
    section_chart_text(R, independent)
    section_determinism(R, url)
    section_artifacts(R, mtimes)
    section_pdf(R)
    section_claims(R)
    if args.offline:
        R.head("9. EXTERNAL API CLAIMS")
        R.skip("Polymarket and Kalshi API claims", "--offline")
    else:
        section_external(R)
    section_infrastructure(R)
    section_security(R)
    section_failure_modes(R)
    section_readme(R)
    return R.finish()


if __name__ == "__main__":
    sys.exit(main())
