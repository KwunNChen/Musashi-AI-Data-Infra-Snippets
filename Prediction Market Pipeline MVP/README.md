# Prediction Market Pipeline MVP

Kalshi and Polymarket both price the same real-world events. They don't always agree. This pulls both into Supabase on a schedule and measures the gap.

**[Full write-up (PDF)](./Prediction_Market_Pipeline_Report.pdf)** · 19 markets tracked · 640+ snapshots · running unattended since 2026-09-02

![Fed rate cut divergence](./analysis/output/divergence_8_29.png)

Both lines above are the same question: will the Fed cut rates before 2027? Kalshi ended the week near where it started, around 0.10. Polymarket drifted down to 0.07. Getting this chart to mean anything required catching that the two platforms phrase the question in opposite directions, comparing them raw showed a fake 80-point gap that was really just inverted polarity.

## What it found

- **Platforms diverge on the same event.** Across 32 aligned snapshots the Kalshi:Polymarket ratio averaged 1.44 on the Fed pair, and the gap widened over the week.
- **The divergence isn't uniform.** RFK Jr. tracks tightly (ratio 0.71, std 0.06); Pete Hegseth is much noisier (0.81, std 0.11) despite being the same category of market. Averaging them together would have hidden that.
- **Matching strikes don't mean matching contracts.** Kalshi's crypto markets ask what BTC will be worth on one date; Polymarket's ask whether it ever touches a price first. Same asset, same dollar amount, different question, so they're deliberately not linked.

## How it works

```
ingest/     Kalshi + Polymarket pulls, shared logging, resolutions backfill, health check
analysis/   reads the data back out, builds charts, assembles the PDF
```

Six tables in Supabase: `platforms`, `markets`, `market_snapshots` (the core time series), `resolutions`, `cross_platform_links`, `kol_theses`. RLS is on; ingestion writes with the service_role key, which bypasses it.

Two workflows live in the repo root `.github/workflows/` (Actions won't find them in a subfolder): ingestion, and an independent health check every 6 hours that fails loudly if snapshots go stale.

The ingestion cron asks for every 2 hours. GitHub delivers about 41% of that — measured median gap between actual batches is 4.6h, worst case 34.6h. Runs that fire always complete all 19 markets, so this is GitHub dropping scheduled events, not the pipeline breaking. If you need a guaranteed interval, this is the wrong scheduler.

## Running it

```bash
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # then fill in your Supabase URL + service_role key
```

```bash
python -m ingest.run_kalshi        # one snapshot per watchlist market
python -m ingest.run_polymarket
python -m analysis.report          # regenerate charts
python -m analysis.build_report    # rebuild the PDF from them
```

Charts first, then the PDF. Doing it the other way embeds stale images.

## Gotchas worth knowing

- **Polymarket's `closed` param is a filter, not a hint.** Omit it and you silently only get open markets, so a resolved market comes back as an empty list. This quietly broke resolution detection until it was caught.
- **Polymarket slugs aren't stable.** The same price threshold gets re-listed under a new slug once the old one resolves. Re-verify watchlist slugs periodically.
- **Polymarket doesn't expose open interest per market**, only per event, which aggregates across sibling markets. Left NULL rather than filled with a misleading number.
