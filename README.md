# Musashi AI Data Infra Snippets

Weekly data infrastructure projects. One folder per week, each self-contained.

| Week | Project | What it does |
|---|---|---|
| 1 | [Prediction Market Pipeline MVP](<./Prediction Market Pipeline MVP/>) | Pulls Kalshi + Polymarket odds into Supabase on a 2-hour cron (GitHub delivers about 40% of those), then measures where the two platforms disagree. [Report (PDF)](<./Prediction Market Pipeline MVP/Prediction_Market_Pipeline_Report.pdf>) |

## How this repo is organized

Each project folder owns its own `requirements.txt`, virtual environment, and README, so nothing bleeds between weeks.

Scheduled jobs are the one exception: they live in the root `.github/workflows/` because GitHub Actions doesn't discover workflows nested inside a subfolder. Each workflow is scoped to its own project with `working-directory`.
