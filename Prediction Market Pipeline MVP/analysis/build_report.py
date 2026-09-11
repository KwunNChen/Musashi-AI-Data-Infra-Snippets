# analysis/build_report.py
# Generates the PDF deliverable from analysis/output/*.png plus analysis/output/stats.json.
# Every figure quoted below is read from stats.json, which analysis/report.py writes over the
# same frozen window it plots, so the prose cannot drift away from the charts.
# Run `python -m analysis.report` first.

import json

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle, ListFlowable, ListItem
)

OUT = "analysis/output"
PDF_PATH = "Prediction_Market_Pipeline_Report.pdf"

with open(f"{OUT}/stats.json", encoding="utf-8") as f:
    S = json.load(f)

W, D = S["window"], S["delivery"]
PAIRS = {p["kalshi_market_id"]: p for p in S["pairs"]}
FED, HEGSETH, RFK = PAIRS[8], PAIRS[9], PAIRS[10]
FAST, SLOW = S["repricing"][:3], S["repricing"][-3:]
TOP_VOL = S["volume"][0]
LOW_VOL = S["volume"][-2:]
VOL_SPEED_RANK = next(i for i, r in enumerate(S["repricing"], 1) if r["title"] == TOP_VOL["title"])


def money(x):
    return f"${x/1_000_000:.2f}M" if x >= 1_000_000 else f"${x:,.0f}"


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], spaceBefore=18, spaceAfter=8))
styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#333333")))
styles.add(ParagraphStyle(name="H3", parent=styles["Heading3"], spaceBefore=10, spaceAfter=4, fontSize=11, textColor=colors.HexColor("#444444")))
styles.add(ParagraphStyle(name="Body", parent=styles["Normal"], fontSize=10.5, leading=15, spaceAfter=8))
styles.add(ParagraphStyle(name="Caption", parent=styles["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#555555"), spaceAfter=14))
styles.add(ParagraphStyle(name="TitleBig", parent=styles["Title"], fontSize=22, spaceAfter=4))
styles.add(ParagraphStyle(name="Subtitle", parent=styles["Normal"], fontSize=11, textColor=colors.HexColor("#555555"), spaceAfter=24))

story = []


def h1(text): story.append(Paragraph(text, styles["H1"]))
def h2(text): story.append(Paragraph(text, styles["H2"]))
def h3(text): story.append(Paragraph(text, styles["H3"]))
def body(text): story.append(Paragraph(text, styles["Body"]))
def caption(text): story.append(Paragraph(text, styles["Caption"]))


def bullets(items):
    story.append(ListFlowable(
        [ListItem(Paragraph(i, styles["Body"]), leftIndent=12) for i in items],
        bulletType="bullet", start="•",
    ))


def chart(filename, width=6.2):
    story.append(Image(f"{OUT}/{filename}", width=width * inch, height=width * inch * 0.5))
    story.append(Spacer(1, 4))


# ---------- Title ----------
story.append(Paragraph("Prediction Market Data Pipeline", styles["TitleBig"]))
story.append(Paragraph("Kalshi and Polymarket ingestion, cross-platform analysis, and research synthesis for a weekly internship deliverable", styles["Subtitle"]))

# ---------- Executive Summary ----------
h1("Executive summary")
body(
    "I built a live data pipeline that pulls Kalshi and Polymarket prediction-market data into Supabase on a "
    "schedule, and paired it with research into how professional prediction-market traders think about pricing, "
    f"resolution risk, and cross-platform edges. {W['markets']} markets across crypto, macro, and politics get "
    "polled on an unattended GitHub Actions cron job, nominally every 2 hours. On the analysis side, I used the "
    "collected data to build a repricing-speed metric, compare volume across markets, and measure price "
    f"divergence across {W['links']} linked market pairs. Along the way I caught a question-polarity mismatch "
    "that would have produced a false 80-percentage-point \"divergence\" on the clearest pair in the dataset, "
    "and fixed it before it made it into a finding."
)
body(
    f"Everything below is a point-in-time analysis of data collected between {W['first_snapshot']} and "
    f"{W['last_snapshot']} ({W['rows']} snapshot rows across {W['markets']} markets). The cross-platform "
    f"comparisons in Section 4.3 start from {FED['start']}, since Polymarket ingestion came online after "
    "Kalshi's. The pipeline keeps running, so the analysis window is pinned in <b>analysis/config.py</b> and "
    "every figure quoted here is generated from that window rather than typed in by hand. Re-running the report "
    "on a later date reproduces these same numbers until the window is deliberately moved."
)

# ---------- Architecture ----------
h1("1. Architecture and pipeline")
h2("1.1 Schema")
body("Six tables live in Supabase (Postgres), with Row Level Security enabled. Writes go through the "
     "service_role key, which bypasses RLS, so no read policies were needed for this stage of the project.")
schema_rows = [
    ["Table", "Purpose"],
    ["platforms", "Kalshi / Polymarket"],
    ["markets", "One row per tracked market, upserted on (platform_id, external_id)"],
    ["market_snapshots", "The core time-series table: one row per market per poll"],
    ["resolutions", "Final outcomes, written by the backfill step once a market settles"],
    ["cross_platform_links", "Manually matched market pairs tracking the same real-world event"],
    ["kol_theses", "Research log of prediction-market researcher theses and frameworks"],
]
t = Table(schema_rows, colWidths=[1.6 * inch, 4.6 * inch])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
story.append(t)
story.append(Spacer(1, 10))

h2("1.2 Ingestion")
body("Both platforms expose market and price data with no authentication required for reads. Only trading "
     "requires auth, and this pipeline never needed it. Kalshi's <b>/trade-api/v2/markets/{ticker}</b> and "
     "Polymarket's <b>/markets/keyset</b> both return the current price alongside metadata in a single call, so "
     "a periodic snapshot poll doesn't need a separate historical-candlestick or order-book call.")
body(f"The watchlist ({W['per_platform']['kalshi']} Kalshi tickers and {W['per_platform']['polymarket']} "
     "Polymarket slugs, across crypto, macro, and politics) is a fixed list rather than a dynamically "
     "re-selected top-N by volume. A market that drops in and out of tracking from day to day would break the "
     "time-series continuity the whole analysis depends on.")
body("One wrinkle worth recording: Kalshi gives every market inside an event the same title, so all five "
     "Bitcoin strike buckets arrive as \"BTC price on Jan 1, 2027?\". The strike sits in a separate "
     "<b>yes_sub_title</b> field. Until I appended it, five different markets shared one label and the volume "
     "chart drew five bars with identical names.")

h2("1.3 Scheduling and reliability")
body("A GitHub Actions workflow (<b>.github/workflows/prediction-markets-w1.yml</b>, at the repo root, since "
     "GitHub Actions doesn't discover workflows nested in a project subfolder) asks for both ingestion scripts "
     "every 2 hours. How often that actually happens is its own problem, covered in the next paragraph. The "
     "cron is offset from the top of the hour to avoid the queueing delays GitHub applies when many workflows "
     "are scheduled for :00 at once. A shared logger (<b>ingest/logging_config.py</b>) writes timestamped "
     "output to both the console, visible in the Actions logs, and a local <b>logs/pipeline.log</b> file, which "
     "the workflow also uploads as a build artifact so it survives past the runner. That replaced the four "
     "duplicated logging setups the ingestion scripts each carried before.")
body(
    f"The requested schedule and the delivered one are not the same thing. Across {D['batches']} poll batches "
    f"over {D['span_hours']:.0f} hours, the median gap between batches is {D['median_gap_hours']} hours rather "
    f"than 2, and the worst gap was {D['max_gap_hours']} hours. That works out to {D['batches_per_day']} "
    f"batches a day against the {D['requested_per_day']} requested, or about {D['delivery_pct']}%. The likeliest "
    "cause is GitHub dropping or delaying scheduled events under load, which is documented behaviour for cron "
    "on hosted runners rather than anything specific to this repository."
)
body(
    f"Two caveats keep that number honest. First, {D['delivery_pct']}% is an upper bound on what GitHub "
    "delivered, because the batch count includes manual <b>workflow_dispatch</b> runs and local runs I made "
    "while developing, and snapshot rows don't record which trigger produced them. Separating them needs a "
    "run-origin column, which is a fix rather than a caveat, and it opens Section 6. Second, "
    f"{D['complete_batches']} of the {D['batches']} batches wrote all {W['markets']} markets, not all of them. "
    f"The {len(D['incomplete_batches'])} exceptions are below. Three fall in the bring-up period before both "
    "ingestion scripts ran together, and the fourth is a local Polymarket-only run. None is an unattended "
    "failure, but an earlier draft of this report claimed every batch was complete, and that was wrong."
)
bullets([f"{b['at']}: {b['markets']} markets, {' and '.join(b['platforms'])} only"
         for b in D["incomplete_batches"]])
body(
    "After each ingestion run, a resolutions backfill step checks every tracked market against its platform and "
    f"records the outcome once a market settles. The resolutions table holds {W['resolutions']} rows because "
    "nothing tracked has closed yet, but the mechanism is in place and running. A second, independent workflow "
    "checks every 6 hours whether the newest snapshot is more than 10 hours old, and fails if it is, which "
    "sends GitHub's usual failed-workflow email. The 10-hour threshold sits above the real "
    f"{D['median_gap_hours']}-hour median gap, so a couple of skipped runs don't trip it while a true outage "
    "still does."
)

# ---------- Data Sources ----------
h1("2. Platform and API differences")
bullets([
    "Polymarket's original <b>/markets</b> and <b>/events</b> endpoints were deprecated and sunset on "
    "2026-05-01, but they still return HTTP 200, with the deprecation visible only in the response headers, so "
    "it would have been easy to build on a dead endpoint without noticing. I moved to the replacement, "
    "cursor-paginated <b>/markets/keyset</b>, before writing any ingestion code.",

    "Open interest isn't symmetric between the platforms. Kalshi reports it per market. Polymarket only reports "
    "it per event, which sums across every sibling market in a multi-market event. Assigning that combined "
    "number to a single market would misrepresent it, so Polymarket's open_interest stays NULL here rather "
    "than holding a misleading figure.",

    "Polymarket's outcomePrices field is the bid/ask midpoint, not the last executed trade price. I checked it "
    "against the raw bestBid and bestAsk on the same response. The midpoint doesn't go stale on a quiet market "
    "the way a last-trade price can, so it's the better choice for a periodic snapshot.",

    "Polymarket slugs aren't stable identifiers the way Kalshi tickers are. Once a market resolves, the same "
    "price threshold gets re-listed under a new slug. I found three different \"Bitcoin dip to $60k\" slugs for "
    "the same nominal question, so the pipeline stores Polymarket's numeric id as external_id, and the "
    "watchlist slugs still need re-checking every so often.",

    "Matching strikes don't mean matching contracts. When I tried to link the crypto markets across platforms, "
    "the Kalshi ones asked what price BTC or ETH would be on one specific date, while the Polymarket ones asked "
    "whether that price was ever touched before a deadline. That's the same asset at a similar dollar figure "
    "but a different question, and I only caught it by reading the contract terms instead of trusting the "
    "strike price. Section 4.1 shows the difference is measurable, not just semantic.",
])

# ---------- Research ----------
h1("3. Research synthesis")
body("I logged seven theses from three X accounts, covering theory, trading methodology, and platform "
     "resolution risk. These are secondhand accounts recorded in the kol_theses table, not claims I verified "
     "independently.")

h2("3.1 Resolution risk as an unpriced cost")
body("@thenarrator argues that a YES price near $1 still carries a hidden cost: capital stays locked until "
     "settlement, so a near-certain bet can be capital-inefficient if resolution drags or the exit is thin. He "
     "thinks markets need a visible \"carry\" metric, something like expected time-to-redemption shown next to "
     "price, similar to a funding rate on perpetual futures. The last few cents near $1, in his view, often "
     "just compensate for resolution or dispute risk the trader hasn't priced in.")
body("@Domahhhh gives four documented cases where that abstract resolution risk played out. Polymarket "
     "resolved a Venezuela \"invasion\" market against its own stated criteria after Trump publicly claimed the "
     "US controlled the country. Polymarket resolved an Epstein \"blackmail\" market YES off one ambiguous "
     "email, using a much looser standard than it applied days later. Kalshi paid out a \"will Biden meet "
     "Trudeau\" market at $0 even though the meeting was televised, because its rules only recognized two "
     "sources and neither reported it. And Kalshi settled an Oscars-viewership market on preliminary Nielsen "
     "numbers hours before the final numbers came out and flipped the outcome. Together they make narrator's "
     "point less hypothetical.")

h2("3.2 Trading methodology: holding against consensus")
body("@Domahhhh's Fed Chair nomination trade shows what acting on that kind of read looks like in size. He "
     "held a large net-short position against the market-implied favorite, who reached 85% consensus, for "
     "roughly five months and through four different frontrunner swaps, based on his own analysis that the "
     "favorite was a poor fit for monetary policy. The eventual pick matched his own, lower-probability "
     "estimate instead, netting him $425,000. It's a contrarian position that paid off because the analysis "
     "behind it held up, not just because he refused to fold.")

h2("3.3 Theory: why bounded markets discipline claims")
body("@VitalikButerin argues prediction markets are epistemically healthier than social media or unbounded "
     "asset markets. A bad take on social media earns unaccountable clout; a bad bet on a prediction market "
     "loses real money. And bounded [0,1] pricing resists the reflexivity and pump-and-dump dynamics that "
     "unbounded markets are prone to.")

story.append(PageBreak())

# ---------- Findings ----------
h1("4. Findings from the collected data")

h2("4.1 Repricing speed")
body("Narrator's \"prediction-market VIX\" framing, made measurable: the mean absolute price change per hour "
     "for each market across the window. It's a rough proxy for how much a market is still arguing with "
     "itself.")
chart("repricing_speed.png")
caption(
    "The split is not crypto against politics, which is what I expected going in. It is contract structure. "
    f"The three fastest markets are \"{FAST[0]['title']}\" at {FAST[0]['speed']:.5f} per hour, "
    f"\"{FAST[1]['title']}\" at {FAST[1]['speed']:.5f}, and \"{FAST[2]['title']}\" at {FAST[2]['speed']:.5f}. "
    f"The three slowest are all Kalshi price-on-a-date buckets: \"{SLOW[2]['title']}\" at "
    f"{SLOW[2]['speed']:.5f}, \"{SLOW[1]['title']}\" at {SLOW[1]['speed']:.5f}, and \"{SLOW[0]['title']}\" at "
    f"{SLOW[0]['speed']:.5f}. Bitcoin sits at both ends of that ranking. A touch-by-deadline contract reprices "
    "on every move toward the barrier, while a settle-on-one-date bucket only cares where price finishes, so it "
    "ignores the same volatility. That is the Section 2 contract-type distinction showing up as a number."
)

h2("4.2 Volume distribution")
chart("volume.png")
caption(
    f"The Polymarket \"{TOP_VOL['title']}\" market carries about {money(TOP_VOL['volume'])} in volume, against "
    f"{money(LOW_VOL[0]['volume'])} and {money(LOW_VOL[1]['volume'])} on the thinnest Kalshi cabinet markets. "
    f"That market also sits {VOL_SPEED_RANK}th of {len(S['repricing'])} on repricing speed, so the heaviest "
    "book in the set is among the slowest to move, though it is not the single slowest. Evercore ISI's analysis "
    "of five years of completed Kalshi and Polymarket markets reportedly found that high-volume markets price "
    "more reliably than thin ones. I could not verify that study directly, so treat it as context from the "
    "research log rather than as evidence this dataset establishes."
)

h2("4.3 Cross-platform divergence")
body("Of five intended cross-platform pairs, only three are populated in cross_platform_links: one macro pair "
     "and two politics pairs. I didn't add crypto pairs. Checking the actual contract terms, not just the "
     "dollar strikes, showed that the tracked Kalshi crypto markets ask what price BTC or ETH will be on a "
     "specific future date, while the tracked Polymarket markets ask whether that price is ever touched before "
     "a deadline. Those are different questions even at matching strikes, so linking them would have produced a "
     "divergence number that looks real but doesn't measure anything.")

h3("4.3.1 Macro pair: Fed rate cut")
chart(FED["chart"])
caption(
    f"This compares Kalshi's \"{FED['kalshi_title']}\" against Polymarket's \"{FED['polymarket_title']}\", with "
    "Polymarket's series inverted for comparison. That inversion mattered: the two questions are logically "
    "opposite (on Kalshi, Yes means a cut happens; on Polymarket, Yes means it doesn't), so a naive raw "
    "comparison showed a false 80-percentage-point \"divergence\" that was really just two inverted questions "
    f"lined up against each other. Once corrected for polarity, the series open on {FED['start']} at "
    f"{FED['kalshi_first']:.3f} on Kalshi and {FED['poly_first']:.3f} on Polymarket, separate through the "
    f"middle of the window, then close on {FED['end']} at {FED['kalshi_last']:.3f} and "
    f"{FED['poly_last']:.3f}. Both drifted down and finished within a thousandth of each other, after Kalshi "
    f"spiked to {FED['kalshi_max']:.3f} mid-window and gave it back. Across {FED['n']} aligned snapshots the "
    f"Kalshi:Polymarket ratio averaged {FED['ratio_mean']:.2f} (median {FED['ratio_median']:.2f}, standard "
    f"deviation {FED['ratio_std']:.2f}, range {FED['ratio_min']:.2f} to {FED['ratio_max']:.2f}). The divergence "
    "is real inside the window but does not survive to the end of it, which is the strongest argument in this "
    "report against reading a durable pattern into one week of data."
)

h3("4.3.2 Politics pairs: RFK Jr. and Hegseth")
chart(RFK["chart"])
chart(HEGSETH["chart"])
body(
    "The two politics pairs don't show one uniform pattern, and treating them as if they did would overstate "
    f"the finding. The RFK Jr. pair (Kalshi:Polymarket ratio) is tight and consistent: mean "
    f"{RFK['ratio_mean']:.2f}, median {RFK['ratio_median']:.2f}, standard deviation {RFK['ratio_std']:.2f} "
    f"across {RFK['n']} points, ranging only from {RFK['ratio_min']:.2f} to {RFK['ratio_max']:.2f}. Kalshi "
    f"prices this market consistently below Polymarket. The Pete Hegseth pair is higher and noisier: mean "
    f"{HEGSETH['ratio_mean']:.2f}, median {HEGSETH['ratio_median']:.2f}, standard deviation "
    f"{HEGSETH['ratio_std']:.2f}, ranging from {HEGSETH['ratio_min']:.2f} to {HEGSETH['ratio_max']:.2f}. That "
    "upper bound is above 1.0, meaning Kalshi at times priced Hegseth's departure higher than Polymarket did. A "
    "single structural story about Kalshi's comparative \"next to leave\" framing sitting below Polymarket's "
    "independent yes/no framing fits RFK Jr. well and fits Hegseth badly."
)

# ---------- Limitations ----------
story.append(PageBreak())
h1("5. Limitations")
bullets([
    f"{W['markets']} markets tracked, a deliberately small and fixed watchlist, not the full catalog of either "
    "platform.",

    f"Only {W['links']} of 5 planned cross-platform links are populated. The 2 crypto pairs were never added: "
    "the tracked Kalshi and Polymarket crypto markets turned out to be different contract types "
    "(price-on-a-date versus touch-by-deadline), not just different strikes.",

    f"{W['days']} days of observation ({W['first_snapshot']} to {W['last_snapshot']}), and less than that for "
    f"the cross-platform pairs, which start {FED['start']}. The Fed-pair divergence is a real, measured result, "
    "but the series converge again by the end of the window, so treating the mid-window gap as a durable "
    "platform difference would be reading too much into one week.",

    "The politics pairs are approximate matches, and the mismatch is wider than the tickers suggest. Kalshi's "
    "cabinet-departure tickers are named KXCABOUT-26MAY22, but their actual close_time is 2029-01-20, the end "
    "of the presidential term, while the matched Polymarket markets close 2026-12-31. Same underlying question, "
    "very different windows. Reading the date out of the ticker string instead of the close_time field is what "
    "put a wrong figure in an earlier draft of this report.",

    "Polymarket's open_interest isn't available at market granularity (see Section 2), so it's NULL throughout.",

    "Snapshot rows don't record what triggered the run, so scheduled, manual and local runs are "
    "indistinguishable in the delivery statistics in Section 1.3.",
])

# ---------- Next Steps ----------
h1("6. Next steps")
bullets([
    "Record a trigger source on every snapshot row (scheduled, manual, or local) so the GitHub delivery rate in "
    "Section 1.3 can be measured against scheduled runs alone instead of against every write to the table.",

    "Track a crypto pair the two platforms define the same way. That means finding a Kalshi market phrased as "
    "touch-by-deadline, since the ones tracked now ask a different question than the Polymarket side. Section "
    "4.1 suggests the two contract types behave differently enough that pairing them would measure the "
    "contract, not the platform.",

    "Trade-level ingestion and wallet-level \"smart money\" tracking through Polymarket's subgraph. This was "
    "scoped out of this week's MVP and flagged as a stretch goal from the start.",

    "Widen the watchlist and extend the window once the pipeline has run unattended for longer, to test whether "
    "the Fed-pair convergence holds or was a one-week artifact.",
])

doc = SimpleDocTemplate(
    PDF_PATH, pagesize=letter,
    topMargin=0.7 * inch, bottomMargin=0.7 * inch, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
)
doc.build(story)
print(f"wrote {PDF_PATH}")
