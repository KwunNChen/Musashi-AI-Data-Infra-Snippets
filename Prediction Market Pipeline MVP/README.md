# Prediction Market Pipeline MVP

A pipeline that pulls Kalshi and Polymarket prediction-market data into Supabase on a schedule, plus the analysis and research that came out of it. Built for a one-week internship deliverable.

Full write-up: [`Prediction_Market_Pipeline_Report.pdf`](./Prediction_Market_Pipeline_Report.pdf).

## What's here

- `ingest/` — Kalshi and Polymarket ingestion scripts, shared logging, and the resolutions backfill.
- `analysis/` — pulls the collected data back out, builds the repricing-speed/volume/divergence charts, and assembles the PDF report.
- `.github/workflows/` (repo root, not here): runs the ingestion scripts every 2 hours and checks the pipeline is still alive every 6.

## Running it locally

1. `python -m venv venv`, activate it, then `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and fill in your own Supabase project URL and service_role key.
3. `python -m ingest.run_kalshi` and `python -m ingest.run_polymarket` each pull one snapshot.
4. `python -m analysis.report` regenerates the charts in `analysis/output/`, then `python -m analysis.build_report` rebuilds the PDF from them.

## Schema

Six tables in Supabase: `platforms`, `markets`, `market_snapshots` (the core time-series table), `resolutions`, `cross_platform_links`, and `kol_theses`. Row Level Security is on; the ingestion scripts write through the service_role key, which bypasses it.

## Notes for next time

- Kalshi's and Polymarket's crypto markets in this watchlist turned out to ask different kinds of questions (price on a specific date vs. touched-by-a-deadline), so they're not linked for cross-platform comparison. The report has the full explanation.
- Polymarket slugs aren't stable long-term identifiers. The same price threshold gets re-listed under a new slug once the old one resolves, so watchlist slugs need periodic re-checking.
