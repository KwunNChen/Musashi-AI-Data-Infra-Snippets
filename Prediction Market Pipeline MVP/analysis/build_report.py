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

try:
    with open(f"{OUT}/stats.json", encoding="utf-8") as f:
        S = json.load(f)
except FileNotFoundError:
    raise SystemExit(
        f"{OUT}/stats.json not found. Run `python -m analysis.report` first: it regenerates the "
        "charts and the figures this report quotes, over the same window."
    )

W, D = S["window"], S["delivery"]


def pair(match):
    """Look pairs up by what they are about. Market ids are database identities, so keying off
    them silently breaks the report if the links table is ever rebuilt."""
    hits = [p for p in S["pairs"] if match.lower() in p["kalshi_title"].lower()]
    if len(hits) != 1:
        raise SystemExit(
            f"expected exactly one cross-platform pair matching {match!r}, found {len(hits)}. "
            "Section 4.3 is written around the macro pair plus the two cabinet pairs."
        )
    return hits[0]


FED, HEGSETH, RFK = pair("Federal Reserve"), pair("Hegseth"), pair("Kennedy")
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
    "A pipeline polls Kalshi and Polymarket into Supabase on a schedule, paired with research into how "
    f"professional traders think about pricing and resolution risk. {W['markets']} markets across crypto, macro "
    "and politics run on an unattended GitHub Actions cron, nominally every 2 hours. From the collected data I "
    f"built a repricing-speed metric, compared volume, and measured divergence across {W['links']} linked pairs. "
    "One early catch: a question-polarity mismatch that would have reported a false 80-percentage-point "
    "divergence on the clearest pair in the set."
)
body(
    f"The figures below cover {W['first_snapshot']} to {W['last_snapshot']}, {W['rows']} snapshot rows across "
    f"{W['markets']} markets. Cross-platform comparisons start {FED['start']}, since Polymarket ingestion came "
    "online after Kalshi's. The window is pinned in <b>analysis/config.py</b> and every number here is generated "
    "from it, so re-running reproduces the same report until the window is deliberately moved."
)

# ---------- Architecture ----------
h1("1. Architecture and pipeline")
h2("1.1 Schema")
body("Six tables in Supabase (Postgres), with Row Level Security on. Writes use the service_role key, which "
     "bypasses RLS, so no read policies were needed at this stage.")
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
body("Both platforms serve prices without authentication; only trading needs auth. Kalshi's "
     "<b>/trade-api/v2/markets/{ticker}</b> and Polymarket's <b>/markets/keyset</b> each return price plus "
     "metadata in one call, so snapshot polling needs no separate candlestick or order-book request.")
body(f"The watchlist ({W['per_platform']['kalshi']} Kalshi tickers and {W['per_platform']['polymarket']} "
     "Polymarket slugs) is fixed rather than a rolling top-N by volume, since markets dropping in and out would "
     "break the time series. One quirk: Kalshi gives every market in an event the same title, so all five "
     "Bitcoin strike buckets arrive as \"BTC price on Jan 1, 2027?\". The strike lives in <b>yes_sub_title</b>, "
     "and without appending it the volume chart drew five identically labeled bars.")

h2("1.3 Scheduling and reliability")
body("A workflow at the repo root (<b>.github/workflows/prediction-markets-w1.yml</b>, since Actions ignores "
     "workflows nested in subfolders) asks for both ingestion scripts every 2 hours, offset off the hour to "
     "dodge :00 queueing. A shared logger writes to the console and to <b>logs/pipeline.log</b>, which the "
     "workflow uploads as an artifact so it outlives the runner.")
body(
    f"Requested and delivered are not the same thing. Across {D['batches']} poll batches over "
    f"{D['span_hours']:.0f} hours the median gap is {D['median_gap_hours']} hours rather than 2, the worst was "
    f"{D['max_gap_hours']} hours, and the rate works out to {D['batches_per_day']} batches a day against the "
    f"{D['requested_per_day']} requested, about {D['delivery_pct']}%. That looks like GitHub dropping scheduled "
    "events under load rather than anything specific to this repository."
)
body(
    f"Two things qualify that number. {D['delivery_pct']}% overstates GitHub's share, because the batch count "
    "also includes manual <b>workflow_dispatch</b> runs and local runs, and rows don't record their trigger "
    f"(Section 6). The batches are uneven too, with {D['complete_batches']} of {D['batches']} writing all "
    f"{W['markets']} markets and the other {len(D['incomplete_batches'])} listed below: three from the bring-up "
    "period before both scripts ran together, and one local Polymarket-only run."
)
bullets([f"{b['at']}: {b['markets']} markets, {' and '.join(b['platforms'])} only"
         for b in D["incomplete_batches"]])
body(
    "A backfill step after each run checks every tracked market and records outcomes once they settle. The "
    f"resolutions table holds {W['resolutions']} rows because nothing tracked has closed yet. A separate "
    "workflow checks every 6 hours whether the newest snapshot is over 10 hours old and fails if it is. The "
    f"10-hour threshold clears the real {D['median_gap_hours']}-hour median, so a couple of skipped runs don't "
    "trip it while a true outage still does."
)

# ---------- Data Sources ----------
h1("2. Platform and API differences")
bullets([
    "Polymarket's <b>/markets</b> and <b>/events</b> were sunset on 2026-05-01 but still return HTTP 200, with "
    "the deprecation only in the response headers. Easy to build on a dead endpoint without noticing. I moved "
    "to the cursor-paginated <b>/markets/keyset</b> before writing any ingestion code.",

    "Open interest isn't symmetric. Kalshi reports it per market; Polymarket only per event, summed across "
    "sibling markets. Assigning that total to one market would misrepresent it, so Polymarket's open_interest "
    "stays NULL.",

    "Polymarket's outcomePrices is the bid/ask midpoint, not the last trade. I checked it against bestBid and "
    "bestAsk on the same response. A midpoint doesn't go stale on a quiet market the way a last-trade price "
    "does.",

    "Polymarket slugs aren't stable the way Kalshi tickers are: a resolved threshold gets relisted under a new "
    "slug. I found three different \"Bitcoin dip to $60k\" slugs for the same question, so external_id stores "
    "Polymarket's numeric id instead.",

    "Matching strikes don't mean matching contracts. Kalshi's crypto markets ask what BTC or ETH will be worth "
    "on one date; Polymarket's ask whether it ever touches a price first. Same asset, similar dollar figure, "
    "different question, and only visible in the contract terms. Section 4.1 shows the difference is measurable.",
])

# ---------- Research ----------
h1("3. Research synthesis")
body("Seven theses logged from three X accounts, recorded secondhand in the kol_theses table.")

h2("3.1 Resolution risk as an unpriced cost")
body("@thenarrator argues a YES price near $1 still carries a hidden cost: capital is locked until settlement, "
     "so a near-certain bet is capital-inefficient if resolution drags or the exit is thin. He wants a visible "
     "carry metric, expected time-to-redemption shown beside price, like a funding rate on perpetual futures. "
     "The last few cents, in his view, pay for resolution risk the trader hasn't priced.")
body("@Domahhhh supplies four cases where that risk landed. Polymarket resolved a Venezuela invasion market "
     "against its own stated criteria after Trump claimed the US controlled the country, and an Epstein "
     "blackmail market YES off one ambiguous email, on a looser standard than it applied days later. Kalshi paid "
     "$0 on a televised Biden and Trudeau meeting because its rules recognized only two sources, neither of "
     "which reported it, and settled an Oscars-viewership market on preliminary Nielsen numbers hours before "
     "the finals flipped the outcome.")

h2("3.2 Trading methodology: holding against consensus")
body("@Domahhhh's Fed Chair trade shows the same read at size. He held a large net-short against the "
     "market-implied favorite, who peaked at 85% consensus, for roughly five months and four frontrunner swaps, "
     "on his own view that the favorite was a poor fit for monetary policy. The eventual pick matched his "
     "lower-probability estimate, netting $425,000.")

h2("3.3 Theory: why bounded markets discipline claims")
body("@VitalikButerin argues prediction markets are epistemically healthier than social media or unbounded "
     "asset markets. A bad take on social media earns unaccountable clout; a bad bet loses real money. Bounded "
     "[0,1] pricing also resists the reflexivity and pump-and-dump dynamics unbounded markets are prone to.")

story.append(PageBreak())

# ---------- Findings ----------
h1("4. Findings from the collected data")

h2("4.1 Repricing speed")
body("Narrator's \"prediction-market VIX\" made measurable: mean absolute price change per hour, per market, "
     "across the window.")
chart("repricing_speed.png")
caption(
    "I expected the split to fall along crypto against politics. It falls along contract structure. Fastest: "
    f"\"{FAST[0]['title']}\" at {FAST[0]['speed']:.5f} per hour, \"{FAST[1]['title']}\" at "
    f"{FAST[1]['speed']:.5f}, \"{FAST[2]['title']}\" at {FAST[2]['speed']:.5f}. Slowest: \"{SLOW[2]['title']}\" "
    f"at {SLOW[2]['speed']:.5f}, \"{SLOW[1]['title']}\" at {SLOW[1]['speed']:.5f}, \"{SLOW[0]['title']}\" at "
    f"{SLOW[0]['speed']:.5f}. Most of the slow end is Kalshi settle-on-one-date buckets, plus the "
    "near-consensus Polymarket rate-cut market, the heaviest book tracked. Bitcoin sits at both ends. A "
    "touch-by-deadline contract reprices on every move toward the barrier; a settle-on-one-date bucket only "
    "cares where price finishes."
)

h2("4.2 Volume distribution")
chart("volume.png")
caption(
    f"The Polymarket \"{TOP_VOL['title']}\" market carries about {money(TOP_VOL['volume'])} against "
    f"{money(LOW_VOL[0]['volume'])} and {money(LOW_VOL[1]['volume'])} on the thinnest Kalshi cabinet markets. "
    f"It also sits {VOL_SPEED_RANK}th of {len(S['repricing'])} on repricing speed, so the heaviest book is "
    "among the slowest movers without being the slowest. Evercore ISI reportedly found, across five years of "
    "settled Kalshi and Polymarket markets, that high-volume markets price more reliably than thin ones. I "
    "could not verify that study, so treat it as context rather than evidence from this dataset."
)

h2("4.3 Cross-platform divergence")
body(f"Three of five intended pairs are populated: one macro, two politics. The crypto pairs were never added. "
     "The tracked Kalshi crypto markets ask what BTC or ETH will be worth on a specific date while the "
     "Polymarket ones ask whether that price is touched before a deadline, so linking them would produce a "
     "divergence number that measures nothing.")

h3("4.3.1 Macro pair: Fed rate cut")
chart(FED["chart"])
caption(
    f"Kalshi's \"{FED['kalshi_title']}\" against Polymarket's \"{FED['polymarket_title']}\", with Polymarket "
    "inverted. The inversion matters: the two questions are logically opposite, so a raw comparison showed a "
    f"false 80-percentage-point divergence. Corrected, the series open on {FED['start']} at "
    f"{FED['kalshi_first']:.3f} and {FED['poly_first']:.3f}, separate mid-window, then close on {FED['end']} at "
    f"{FED['kalshi_last']:.3f} and {FED['poly_last']:.3f}, a gap of "
    f"{abs(FED['kalshi_last'] - FED['poly_last']):.4f}. Both drifted down, Kalshi ending marginally below after "
    f"spiking to {FED['kalshi_max']:.3f} and giving it back. Across {FED['n']} aligned snapshots the ratio "
    f"averaged {FED['ratio_mean']:.2f} (median {FED['ratio_median']:.2f}, standard deviation "
    f"{FED['ratio_std']:.2f}, range {FED['ratio_min']:.2f} to {FED['ratio_max']:.2f}). The gap opens wide and "
    "closes inside one window rather than holding, which argues for reading it as movement rather than a "
    "standing platform difference."
)

h3("4.3.2 Politics pairs: RFK Jr. and Hegseth")
chart(RFK["chart"])
chart(HEGSETH["chart"])
body(
    f"The two politics pairs don't share one pattern. RFK Jr. is tight: mean {RFK['ratio_mean']:.2f}, median "
    f"{RFK['ratio_median']:.2f}, standard deviation {RFK['ratio_std']:.2f} across {RFK['n']} points, ranging "
    f"{RFK['ratio_min']:.2f} to {RFK['ratio_max']:.2f}, with Kalshi consistently below Polymarket. Hegseth is "
    f"higher and noisier: mean {HEGSETH['ratio_mean']:.2f}, median {HEGSETH['ratio_median']:.2f}, standard "
    f"deviation {HEGSETH['ratio_std']:.2f}, ranging {HEGSETH['ratio_min']:.2f} to {HEGSETH['ratio_max']:.2f}. "
    "That upper bound clears 1.0, so Kalshi at times priced Hegseth's departure above Polymarket. One "
    "structural story about Kalshi's \"next to leave\" framing sitting below Polymarket's independent yes/no "
    "fits RFK Jr. and not Hegseth."
)

# ---------- Limitations ----------
h1("5. Limitations")
bullets([
    f"{W['markets']} markets, a deliberately small fixed watchlist rather than either full catalog.",

    f"{W['links']} of 5 planned links populated. The 2 crypto pairs were dropped once the contract types turned "
    "out to differ (price-on-a-date versus touch-by-deadline).",

    f"{W['days']} days of observation ({W['first_snapshot']} to {W['last_snapshot']}), less for the pairs, "
    f"which start {FED['start']}. The Fed divergence is measured and real, but it closes again by the end, so "
    "the mid-window gap isn't a durable platform difference.",

    "The politics pairs are approximate. Kalshi's cabinet tickers are named KXCABOUT-26MAY22 but close "
    "2029-01-20, the end of the presidential term, against 2026-12-31 on Polymarket. Reading the date out of "
    "the ticker gives 2026-05-22, wrong by more than two and a half years, so take it from close_time.",

    "Polymarket open_interest is unavailable per market (Section 2), so it's NULL throughout.",

    "Snapshot rows don't record their trigger, so scheduled, manual and local runs are indistinguishable in the "
    "delivery figures in Section 1.3.",
])

# ---------- Next Steps ----------
h1("6. Next steps")
bullets([
    "Record a trigger source on every snapshot row so the delivery rate measures scheduled runs alone.",

    "Track a crypto pair defined the same way on both platforms, which means finding a Kalshi "
    "touch-by-deadline market. Section 4.1 suggests the two contract types behave differently enough that "
    "pairing them would measure the contract rather than the platform.",

    "Trade-level ingestion and wallet-level \"smart money\" tracking via Polymarket's subgraph, scoped out of "
    "this week as a stretch goal.",

    "Widen the watchlist and extend the window to test whether the Fed convergence holds.",
])

doc = SimpleDocTemplate(
    PDF_PATH, pagesize=letter,
    topMargin=0.7 * inch, bottomMargin=0.7 * inch, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
)
doc.build(story)
print(f"wrote {PDF_PATH}")
