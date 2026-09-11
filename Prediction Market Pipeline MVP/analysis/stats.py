"""Every number the PDF quotes, computed once and written to analysis/output/stats.json.

build_report.py reads that file instead of holding hardcoded figures, so the prose cannot
drift away from the charts. Repricing speed uses the same mean-of-per-interval formula as
plot_repricing_speed, so the text and the bar chart always agree.
"""
import json
import os
import statistics

from .config import (
    ANALYSIS_START, ANALYSIS_END, BATCH_WINDOW_SECONDS, PAIR_TOLERANCE_SECONDS,
)
from .load_data import (
    load_snapshot_records, load_markets, load_platforms, fetch_all,
)

OUTPUT_DIR = "analysis/output"
STATS_PATH = f"{OUTPUT_DIR}/stats.json"


def _batches(times):
    out = []
    for t in sorted(times):
        if out and (t - out[-1][-1]).total_seconds() <= BATCH_WINDOW_SECONDS:
            out[-1].append(t)
        else:
            out.append([t])
    return out


def _series(records, market_id):
    return sorted(
        (r["ts_parsed"], r["yes_price"])
        for r in records
        if r["market_id"] == market_id and r["yes_price"] is not None
    )


def _align(a, b):
    """Nearest match within tolerance, mirroring polars join_asof(strategy='nearest')."""
    out = []
    for ta, va in a:
        best = min(b, key=lambda x: abs((x[0] - ta).total_seconds()), default=None)
        if best and abs((best[0] - ta).total_seconds()) <= PAIR_TOLERANCE_SECONDS:
            out.append((ta, va, best[1]))
    return out


def _repricing_speed(series):
    """Mean of the per-interval |dprice|/dt, matching plot_repricing_speed."""
    speeds = []
    for i in range(len(series) - 1):
        hours = (series[i + 1][0] - series[i][0]).total_seconds() / 3600
        if hours > 0:
            speeds.append(abs(series[i + 1][1] - series[i][1]) / hours)
    return statistics.mean(speeds) if speeds else None


def compute_all():
    records = load_snapshot_records()
    markets = {m["id"]: m for m in load_markets()}
    platforms = load_platforms()
    links = fetch_all("cross_platform_links", select="*", order="id.asc")
    resolutions = fetch_all("resolutions", select="*", order="market_id.asc")

    times = sorted({r["ts_parsed"] for r in records})
    batches = _batches(times)
    starts = [b[0] for b in batches]
    gaps = [(starts[i + 1] - starts[i]).total_seconds() / 3600 for i in range(len(starts) - 1)]
    span_hours = (times[-1] - times[0]).total_seconds() / 3600

    rows_by_time = {}
    for r in records:
        rows_by_time.setdefault(r["ts_parsed"], []).append(r)

    incomplete = []
    for b in batches:
        ids = {r["market_id"] for t in b for r in rows_by_time[t]}
        if len(ids) != len(markets):
            names = {platforms[markets[i]["platform_id"]] for i in ids}
            incomplete.append({
                "at": b[0].strftime("%Y-%m-%d %H:%M UTC"),
                "markets": len(ids),
                "platforms": sorted(names),
            })

    per_platform = {}
    for m in markets.values():
        name = platforms[m["platform_id"]]
        per_platform[name] = per_platform.get(name, 0) + 1

    speeds = []
    for mid, m in markets.items():
        s = _repricing_speed(_series(records, mid))
        if s is not None:
            speeds.append({"title": m["title"], "platform": platforms[m["platform_id"]], "speed": s})
    speeds.sort(key=lambda x: x["speed"], reverse=True)

    latest = {}
    for r in records:
        mid = r["market_id"]
        if mid not in latest or r["ts_parsed"] > latest[mid]["ts_parsed"]:
            latest[mid] = r
    volumes = [
        {"title": markets[mid]["title"], "platform": platforms[markets[mid]["platform_id"]],
         "volume": r["volume"]}
        for mid, r in latest.items() if r["volume"] is not None
    ]
    volumes.sort(key=lambda x: x["volume"], reverse=True)

    pairs = []
    for link in links:
        k_id, p_id = link["kalshi_market_id"], link["polymarket_market_id"]
        invert = bool(link.get("note")) and "invert" in link["note"].lower()
        ks = _series(records, k_id)
        ps = _series(records, p_id)
        if invert:
            ps = [(t, 1.0 - v) for t, v in ps]
        joined = _align(ks, ps)
        if not joined:
            continue
        ratios = [kv / pv for _, kv, pv in joined if pv]
        kvals = [x[1] for x in joined]
        pvals = [x[2] for x in joined]
        pairs.append({
            "kalshi_market_id": k_id,
            "polymarket_market_id": p_id,
            "kalshi_title": markets[k_id]["title"],
            "polymarket_title": markets[p_id]["title"],
            "category": markets[k_id].get("category"),
            "inverted": invert,
            "chart": f"divergence_{k_id}_{p_id}.png",
            "n": len(ratios),
            "start": joined[0][0].strftime("%Y-%m-%d"),
            "end": joined[-1][0].strftime("%Y-%m-%d"),
            "ratio_mean": statistics.mean(ratios),
            "ratio_median": statistics.median(ratios),
            "ratio_std": statistics.stdev(ratios) if len(ratios) > 1 else 0.0,
            "ratio_min": min(ratios),
            "ratio_max": max(ratios),
            "kalshi_first": kvals[0], "kalshi_last": kvals[-1],
            "kalshi_min": min(kvals), "kalshi_max": max(kvals),
            "poly_first": pvals[0], "poly_last": pvals[-1],
            "poly_min": min(pvals), "poly_max": max(pvals),
        })

    return {
        "window": {
            "configured_start": ANALYSIS_START,
            "configured_end": ANALYSIS_END,
            "first_snapshot": times[0].strftime("%Y-%m-%d"),
            "last_snapshot": times[-1].strftime("%Y-%m-%d"),
            "days": round(span_hours / 24, 1),
            "rows": len(records),
            "markets": len(markets),
            "per_platform": per_platform,
            "links": len(links),
            "resolutions": len(resolutions),
        },
        "delivery": {
            "batches": len(batches),
            "span_hours": round(span_hours, 1),
            "median_gap_hours": round(statistics.median(gaps), 1) if gaps else None,
            "max_gap_hours": round(max(gaps), 1) if gaps else None,
            "batches_per_day": round(len(batches) / (span_hours / 24), 1),
            "requested_per_day": 12,
            "delivery_pct": round(len(batches) / (span_hours / 24) / 12 * 100),
            "complete_batches": len(batches) - len(incomplete),
            "incomplete_batches": incomplete,
        },
        "repricing": speeds,
        "volume": volumes,
        "pairs": pairs,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stats = compute_all()
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, sort_keys=True)
    print(f"wrote {STATS_PATH}")
    return stats


if __name__ == "__main__":
    main()
