"""Frozen analysis window.

The pipeline keeps collecting, so an unfiltered analysis silently changes every time it runs
and the figures quoted in the PDF drift away from the charts beside them. Everything in
analysis/ reads these bounds, so re-running on a later day reproduces the same report.

Move ANALYSIS_END forward when you want the report to cover newer data, then rerun
`python -m analysis.report` and `python -m analysis.build_report` together.

Keep ANALYSIS_END in the past. A bound set into the future still lets the next scheduled run
land inside the window, which is the drift this module exists to prevent.
"""

ANALYSIS_START = "2026-09-02T00:00:00Z"
ANALYSIS_END = "2026-09-11T21:30:00Z"

# join_asof tolerance when lining up a Kalshi snapshot against a Polymarket one.
PAIR_TOLERANCE = "30m"
PAIR_TOLERANCE_SECONDS = 30 * 60

# Snapshots written within this many seconds of each other count as one poll batch.
BATCH_WINDOW_SECONDS = 600
