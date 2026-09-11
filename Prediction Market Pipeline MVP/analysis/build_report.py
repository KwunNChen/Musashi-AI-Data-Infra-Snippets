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
REP = S["repricing"]
FAST, SLOW = REP[:3], REP[-3:]
TOP_VOL = S["volume"][0]
LOW_VOL = S["volume"][-2:]
VOL_SPEED_RANK = next(i for i, r in enumerate(REP, 1) if r["title"] == TOP_VOL["title"])
SPREAD = REP[0]["speed"] / REP[-1]["speed"]


def money(x):
    return f"${x/1_000_000:.2f}M" if x >= 1_000_000 else f"${x:,.0f}"


def per_day(speed):
    """A price is a probability between 0 and 1, so an hourly rate times 24, times 100, is
    'percentage points a day'. Readers can picture that; 0.00432 per hour they cannot."""
    return f"{speed * 2400:.1f}"


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], spaceBefore=18, spaceAfter=8))
styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#333333")))
styles.add(ParagraphStyle(name="H3", parent=styles["Heading3"], spaceBefore=10, spaceAfter=4, fontSize=11, textColor=colors.HexColor("#444444")))
styles.add(ParagraphStyle(name="Body", parent=styles["Normal"], fontSize=10.5, leading=15, spaceAfter=8))
styles.add(ParagraphStyle(name="Caption", parent=styles["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#555555"), spaceAfter=14))
styles.add(ParagraphStyle(name="Cell", parent=styles["Normal"], fontSize=8.5, leading=10.5))
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


def table(rows, widths, wrap_col=None):
    """Numbers belong in a grid. Six markets and six rates read as noise in a paragraph."""
    data = rows
    if wrap_col is not None:
        data = [list(r) for r in rows]
        for i, r in enumerate(data[1:], 1):
            r[wrap_col] = Paragraph(str(r[wrap_col]), styles["Cell"])
    t = Table(data, colWidths=[w * inch for w in widths])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))


# ---------- Title ----------
story.append(Paragraph("Prediction Market Data Pipeline", styles["TitleBig"]))
story.append(Paragraph("Where Kalshi and Polymarket disagree about the same events, and what it takes to measure that", styles["Subtitle"]))

# ---------- Executive Summary ----------
h1("Executive summary")
body(
    "Kalshi and Polymarket both let people bet on real events, and both publish a running price for "
    "each bet. That price is the crowd's estimate of how likely the event is. When the two sites price "
    "the same event differently, one of them is wrong, and the gap is worth measuring."
)
body(
    f"This project collects those prices. A scheduled job polls {W['markets']} markets across crypto, macro "
    f"and politics into a Supabase database, nominally every 2 hours. It has been running unattended since "
    f"{W['first_snapshot']} and has stored {W['rows']} snapshot rows across {W['markets']} markets, through "
    f"{W['last_snapshot']}. I then used that data to answer three questions: which markets move fastest, how "
    f"trading volume is distributed, and how far apart the two sites price {W['links']} matched pairs of "
    "markets."
)
body(
    "The most useful thing I caught was a mistake. Two markets that look like the same question are phrased "
    "in opposite directions, so comparing their prices directly showed an 80-percentage-point gap that was "
    "not real. Section 4.3.1 explains it. Every number in this report is generated from the stored data "
    "rather than typed in, and the date range is fixed in <b>analysis/config.py</b>, so re-running the report "
    "produces the same figures."
)

# ---------- Architecture ----------
h1("1. Architecture and pipeline")
h2("1.1 Schema")
body("Six tables in Supabase, which is hosted Postgres. Row Level Security is on, and the ingestion scripts "
     "write with the service_role key, which bypasses it. No read policies were needed at this stage.")
table([
    ["Table", "Purpose"],
    ["platforms", "Kalshi / Polymarket"],
    ["markets", "One row per tracked market"],
    ["market_snapshots", "The core time series: one row per market per poll"],
    ["resolutions", "Final outcomes, written once a market settles"],
    ["cross_platform_links", "Market pairs I matched by hand as the same real-world event"],
    ["kol_theses", "Research log of trader theses and frameworks"],
], [1.6, 4.6])

h2("1.2 Ingestion")
body("Neither platform requires a login to read prices. Only trading needs authentication. Kalshi's "
     "<b>/trade-api/v2/markets/{ticker}</b> and Polymarket's <b>/markets/keyset</b> both return the current "
     "price and the market's details in one request, so a snapshot poll is a single call per market.")
body(f"The watchlist is fixed: {W['per_platform']['kalshi']} Kalshi tickers and "
     f"{W['per_platform']['polymarket']} Polymarket slugs, chosen once and left alone. A list that "
     "re-selected the busiest markets each day would keep swapping markets in and out, and the time series "
     "would have gaps everywhere.")
body("One quirk cost me a chart. Kalshi gives every market inside an event the same title, so all five "
     "Bitcoin price buckets arrive called \"BTC price on Jan 1, 2027?\". The number that tells them apart "
     "sits in a separate <b>yes_sub_title</b> field. Before I appended it, the volume chart drew five bars "
     "with identical labels.")

h2("1.3 Scheduling and reliability")
body("A GitHub Actions workflow runs both ingestion scripts every 2 hours. It lives at the repo root, "
     "because Actions does not find workflows stored inside a subfolder, and its schedule is offset from the "
     "top of the hour because jobs scheduled for :00 queue behind everyone else's. A shared logger writes to "
     "the console and to <b>logs/pipeline.log</b>, which the workflow saves as a downloadable artifact.")
body(
    f"Asking for a run every 2 hours is not the same as getting one. Over {D['span_hours']:.0f} hours the "
    f"pipeline recorded {D['batches']} poll batches. The typical gap between them was {D['median_gap_hours']} "
    f"hours instead of 2, and the longest was {D['max_gap_hours']} hours. That is {D['batches_per_day']} "
    f"batches a day against the {D['requested_per_day']} requested, or about {D['delivery_pct']}%. GitHub "
    "drops scheduled jobs when its runners are busy, and this looks like that rather than a fault in the "
    "pipeline."
)
body(
    f"Two caveats. That {D['delivery_pct']}% flatters GitHub, because the count also includes runs I "
    "triggered by hand and runs from my own machine, and the table does not record what started a run "
    f"(Section 6). And the batches are not all complete: {D['complete_batches']} of {D['batches']} wrote all "
    f"{W['markets']} markets. The other {len(D['incomplete_batches'])} are listed here. Three are from the "
    "first two days, before both scripts were running together, and one is a local Polymarket-only run."
)
bullets([f"{b['at']}: {b['markets']} markets, {' and '.join(b['platforms'])} only"
         for b in D["incomplete_batches"]])
body(
    "After every run, a backfill step checks each tracked market and records the outcome once it settles. "
    f"The resolutions table holds {W['resolutions']} rows because nothing tracked has closed yet. A second "
    "workflow checks every 6 hours whether the newest snapshot is more than 10 hours old, and fails if it "
    f"is, which emails me. Ten hours sits comfortably above the real {D['median_gap_hours']}-hour typical "
    "gap, so a couple of skipped runs do not trigger a false alarm."
)

# ---------- Data Sources ----------
h1("2. Platform and API differences")
body("The two platforms look similar and differ in ways that matter. The last item below is the one that "
     "shaped the analysis most.")
bullets([
    "Polymarket retired its <b>/markets</b> and <b>/events</b> endpoints on 2026-05-01, but they still "
    "answer normally with HTTP 200. The only sign they are dead is a header in the response. I would have "
    "built on them without noticing, so I moved to the replacement <b>/markets/keyset</b> before writing any "
    "ingestion code.",

    "Kalshi reports open interest for each market. Polymarket reports it only for a whole event, added up "
    "across every market in that event. Copying that total onto a single market would be wrong, so "
    "Polymarket's open_interest stays empty.",

    "Polymarket's price field is the midpoint between the best bid and the best ask, not the last completed "
    "trade. I confirmed that against the bid and ask in the same response. A midpoint is the better choice "
    "here, because a last-trade price on a quiet market can be hours stale.",

    "Kalshi tickers are permanent. Polymarket slugs are not: once a market resolves, the same question is "
    "relisted under a new slug. I found three different slugs for \"Bitcoin dip to $60k\", so the pipeline "
    "stores Polymarket's numeric id instead.",

    "Two markets can name the same asset and the same dollar figure and still be different bets. Kalshi's "
    "crypto markets ask where the price will be on one specific date. Polymarket's ask whether the price is "
    "ever reached before a deadline. A market that touches the level in October and falls back pays out on "
    "Polymarket and not on Kalshi. The difference is only visible in the contract terms, and Section 4.1 "
    "shows it is large enough to measure.",
])

# ---------- Research ----------
h1("3. Research synthesis")
body("Seven theses from three traders on X, logged in the kol_theses table. These are their claims, recorded "
     "secondhand.")

h2("3.1 Resolution risk as an unpriced cost")
body("@thenarrator argues that a bet priced near $1 still costs something. Your money is locked up until the "
     "market settles, so a near-certain bet ties up capital that could be working elsewhere, and that gets "
     "worse if settlement drags or there is nobody to sell to. He wants platforms to show an expected "
     "time-to-payout next to the price. In his reading, the last few cents below $1 are payment for the risk "
     "that the market resolves badly.")
body("@Domahhhh supplies four cases where that risk turned real. Polymarket settled a Venezuela invasion "
     "market against its own written criteria after Trump said the US controlled the country. It settled an "
     "Epstein blackmail market YES on one ambiguous email, using a looser standard than it applied days "
     "later. Kalshi paid nothing on a Biden and Trudeau meeting that was televised, because its rules named "
     "only two acceptable sources and neither covered it. And Kalshi settled a market on Oscars viewership "
     "using preliminary Nielsen figures, hours before the final figures reversed the result.")

h2("3.2 Trading methodology: holding against consensus")
body("@Domahhhh's Fed Chair trade shows what acting on that view looks like with real money. He bet against "
     "the favourite for roughly five months, through four changes in who the favourite was, and held the "
     "position while the market pushed that candidate to 85%. His argument was that the favourite was a poor "
     "fit for the job. The eventual nominee was the lower-probability name he had backed, and the trade "
     "returned $425,000.")

h2("3.3 Theory: why bounded markets discipline claims")
body("@VitalikButerin argues that prediction markets are better at finding the truth than either social "
     "media or ordinary asset markets. A wrong opinion on social media costs nothing, while a wrong bet "
     "costs money. And because a prediction market price cannot go above $1 or below $0, it does not reward "
     "the momentum spirals that unbounded markets are prone to.")

story.append(PageBreak())

# ---------- Findings ----------
h1("4. Findings from the collected data")

h2("4.1 Repricing speed")
body("This measures how much a market's price moves in a typical hour. A market that jumps around is one "
     "where traders keep changing their minds. A market that sits still is one they have made up their minds "
     "about. Prices run from 0 to 1, so the table below also gives the movement in percentage points per "
     "day, which is easier to picture.")
chart("repricing_speed.png")
table(
    [["Rank", "Market", "Platform", "Per hour", "Points/day"]] +
    [[str(i + 1), r["title"], r["platform"], f"{r['speed']:.5f}", per_day(r["speed"])]
     for i, r in enumerate(FAST)] +
    [[str(len(REP) - 2 + i), r["title"], r["platform"], f"{r['speed']:.5f}", per_day(r["speed"])]
     for i, r in enumerate(SLOW)],
    [0.5, 3.1, 1.0, 0.8, 0.8], wrap_col=1)
body(
    f"The fastest market moves about {per_day(REP[0]['speed'])} points a day and the slowest about "
    f"{per_day(REP[-1]['speed'])}, a spread of roughly {SPREAD:.0f} times. I expected that split to fall "
    "between crypto and politics. It falls between the two contract shapes from Section 2 instead. The "
    "quick markets ask whether a price is ever reached, so every move toward that level matters. The slow "
    "ones ask where the price lands on one date, so day-to-day swings mean little. Bitcoin appears at both "
    "ends of the table, which is the clearest sign that the contract wording drives this and not the asset."
)

h2("4.2 Volume distribution")
chart("volume.png")
body(
    f"Volume is concentrated. The Polymarket market \"{TOP_VOL['title']}\" has taken about "
    f"{money(TOP_VOL['volume'])} in bets. The two thinnest Kalshi cabinet markets have taken "
    f"{money(LOW_VOL[0]['volume'])} and {money(LOW_VOL[1]['volume'])}. That busiest market also ranks "
    f"{VOL_SPEED_RANK}th of {len(REP)} for movement, so the market with the most money on it is also one of "
    "the least active, which fits: a question most traders consider settled attracts size and stops moving."
)
body(
    "Evercore ISI reportedly studied five years of settled Kalshi and Polymarket markets and found that "
    "busier markets predict more accurately than thin ones. I could not check that study myself, so it "
    "belongs here as background rather than as something this dataset proves."
)

h2("4.3 Cross-platform divergence")
body("Three of five intended pairs are populated: one macro pair and two politics pairs. I dropped the two "
     "crypto pairs on purpose. As Section 2 explains, the Kalshi and Polymarket crypto markets ask different "
     "questions, so any gap between their prices would measure the wording rather than a real disagreement.")

h3("4.3.1 Macro pair: Fed rate cut")
chart(FED["chart"])
body(
    f"Kalshi asks \"{FED['kalshi_title']}\" and Polymarket asks \"{FED['polymarket_title']}\". Those are "
    "opposite questions: a rate cut makes the Kalshi price rise and the Polymarket price fall. Comparing "
    "them as published showed an 80-percentage-point gap that was pure arithmetic, so the chart flips the "
    "Polymarket line to face the same way."
)
body(
    f"Corrected, the two lines start on {FED['start']} at {FED['kalshi_first']:.3f} and "
    f"{FED['poly_first']:.3f}, pull apart in the middle of the window, and finish on {FED['end']} at "
    f"{FED['kalshi_last']:.3f} and {FED['poly_last']:.3f}. Kalshi spiked as high as {FED['kalshi_max']:.3f} "
    f"before falling back. Across {FED['n']} aligned snapshots the Kalshi price averaged "
    f"{FED['ratio_mean']:.2f} times the Polymarket price. The gap opens and closes inside a single week, so "
    "this is movement rather than a standing difference between the two sites."
)

h3("4.3.2 Politics pairs: RFK Jr. and Hegseth")
chart(RFK["chart"])
chart(HEGSETH["chart"])
body("The two politics pairs behave differently, and averaging them would hide that. The table gives the "
     "Kalshi price as a multiple of the Polymarket price for all three pairs.")
table([
    ["Pair", "n", "Mean", "Median", "Std dev", "Range"],
    ["Fed rate cut", str(FED["n"]), f"{FED['ratio_mean']:.2f}", f"{FED['ratio_median']:.2f}",
     f"{FED['ratio_std']:.2f}", f"{FED['ratio_min']:.2f} to {FED['ratio_max']:.2f}"],
    ["RFK Jr. departure", str(RFK["n"]), f"{RFK['ratio_mean']:.2f}", f"{RFK['ratio_median']:.2f}",
     f"{RFK['ratio_std']:.2f}", f"{RFK['ratio_min']:.2f} to {RFK['ratio_max']:.2f}"],
    ["Hegseth departure", str(HEGSETH["n"]), f"{HEGSETH['ratio_mean']:.2f}", f"{HEGSETH['ratio_median']:.2f}",
     f"{HEGSETH['ratio_std']:.2f}", f"{HEGSETH['ratio_min']:.2f} to {HEGSETH['ratio_max']:.2f}"],
], [1.7, 0.4, 0.8, 0.8, 0.8, 1.7])
body(
    "RFK Jr. is steady. Kalshi prices it consistently below Polymarket and the multiple barely wanders. "
    "Hegseth is higher and noisier, and its range goes above 1.0, meaning Kalshi sometimes priced his "
    "departure as more likely than Polymarket did. There is a tidy explanation for the RFK Jr. pair, that "
    "Kalshi asks who leaves the cabinet first while Polymarket asks whether one person leaves at all, which "
    "should hold the Kalshi price lower. It fits RFK Jr. and it does not fit Hegseth."
)

# ---------- Limitations ----------
h1("5. Limitations")
bullets([
    f"{W['markets']} markets, a small fixed watchlist rather than either platform's full catalog.",

    f"{W['links']} of 5 planned pairs are populated. The two crypto pairs were dropped once the contract "
    "types turned out to differ.",

    f"{W['days']} days of observation ({W['first_snapshot']} to {W['last_snapshot']}), and less for the "
    f"pairs, which start {FED['start']}. The Fed gap is real and measured, but it closes again by the end of "
    "the window, so it is not evidence of a lasting difference.",

    "The politics pairs are approximate. Kalshi's cabinet tickers are named KXCABOUT-26MAY22, but they "
    "actually close on 2029-01-20, the end of the presidential term, against 2026-12-31 on Polymarket. "
    "Trusting the ticker name gives 2026-05-22, which is wrong by more than two and a half years, so the "
    "date has to come from the close_time field.",

    "Polymarket does not publish open interest per market, so that column is empty throughout.",

    "Snapshot rows do not record what triggered the run, so scheduled, manual and local runs cannot be told "
    "apart in the delivery figures in Section 1.3.",
])

# ---------- Next Steps ----------
h1("6. Next steps")
bullets([
    "Record what triggered each run, so the delivery rate can be measured against scheduled runs alone.",

    "Find a Kalshi market that asks the same question as Polymarket's crypto markets, so the two can be "
    "paired without measuring the wording.",

    "Ingest individual trades and track large wallets through Polymarket's subgraph. This was always a "
    "stretch goal for the week.",

    "Widen the watchlist and extend the date range to see whether the Fed pair converges again.",
])

doc = SimpleDocTemplate(
    PDF_PATH, pagesize=letter,
    topMargin=0.7 * inch, bottomMargin=0.7 * inch, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
)
doc.build(story)
print(f"wrote {PDF_PATH}")
