# analysis/build_report.py
# Generates the Day 6 PDF deliverable from analysis/output/*.png + the write-up below.
# Rerun after regenerating charts (`python -m analysis.report`) to refresh the PDF.

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle, ListFlowable, ListItem
)

OUT = "analysis/output"
PDF_PATH = "Prediction_Market_Pipeline_Report.pdf"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], spaceBefore=18, spaceAfter=8))
styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#333333")))
styles.add(ParagraphStyle(name="Body", parent=styles["Normal"], fontSize=10.5, leading=15, spaceAfter=8))
styles.add(ParagraphStyle(name="Caption", parent=styles["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#555555"), spaceAfter=14))
styles.add(ParagraphStyle(name="TitleBig", parent=styles["Title"], fontSize=22, spaceAfter=4))
styles.add(ParagraphStyle(name="Subtitle", parent=styles["Normal"], fontSize=11, textColor=colors.HexColor("#555555"), spaceAfter=24))

story = []

def h1(text): story.append(Paragraph(text, styles["H1"]))
def h2(text): story.append(Paragraph(text, styles["H2"]))
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
    "resolution risk, and cross-platform edges. Roughly 19 markets across crypto, macro, and politics get polled "
    "every 2 hours through an unattended GitHub Actions cron job. On the analysis side, I used the collected "
    "data to build a repricing-speed metric, compare volume across markets, and measure price divergence across "
    "three linked market pairs. Along the way I caught a question-polarity mismatch that would have produced a "
    "false ~80-percentage-point \"divergence\" on the clearest pair in the dataset, and fixed it before it made "
    "it into a finding."
)

# ---------- Architecture ----------
h1("1. Architecture and pipeline")
h2("Schema")
body("Six tables live in Supabase (Postgres), with Row Level Security enabled. Writes go through the "
     "service_role key, which bypasses RLS, so no read policies were needed for this stage of the project.")
schema_rows = [
    ["Table", "Purpose"],
    ["platforms", "Kalshi / Polymarket"],
    ["markets", "One row per tracked market, upserted on (platform_id, external_id)"],
    ["market_snapshots", "The core time-series table: one row per market per poll"],
    ["resolutions", "Final outcomes (not yet populated, see Next Steps)"],
    ["cross_platform_links", "Manually matched market pairs tracking the same real-world event"],
    ["kol_theses", "Research log of prediction-market researcher theses and frameworks"],
]
t = Table(schema_rows, colWidths=[1.6*inch, 4.6*inch])
t.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2b2b2b")),
    ("TEXTCOLOR", (0,0), (-1,0), colors.white),
    ("FONTSIZE", (0,0), (-1,-1), 9.5),
    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
    ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cccccc")),
    ("VALIGN", (0,0), (-1,-1), "TOP"),
    ("TOPPADDING", (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
]))
story.append(t)
story.append(Spacer(1, 10))

h2("Ingestion")
body("Both platforms expose market and price data with no authentication required for reads. Only trading "
     "requires auth, and this pipeline never needed it. Kalshi's <b>/trade-api/v2/markets/{ticker}</b> and "
     "Polymarket's <b>/markets/keyset</b> both return the current price alongside metadata in a single call, so "
     "a periodic snapshot poll doesn't need a separate historical-candlestick or order-book call.")
body("The watchlist (12 Kalshi tickers and 7 Polymarket slugs, across crypto, macro, and politics) is a fixed "
     "list rather than a dynamically re-selected top-N by volume. A market that drops in and out of tracking "
     "from day to day would break the time-series continuity the whole analysis depends on.")

h2("Automation and operations")
body("A GitHub Actions workflow (<b>.github/workflows/prediction-markets-w1.yml</b>, at the repo root, since "
     "GitHub Actions doesn't discover workflows nested in a project subfolder) runs both ingestion scripts every "
     "2 hours. It's offset from the top of the hour to avoid the queueing delays GitHub applies when many "
     "workflows are scheduled for :00 at once. A shared logger (<b>ingest/logging_config.py</b>) writes "
     "timestamped output to both the console, visible in the Actions logs, and a local <b>logs/pipeline.log</b> "
     "file. That replaced four separate, duplicated logging configurations that used to be scattered across the "
     "ingestion scripts.")

# ---------- Data Sources ----------
h1("2. Data sources: platform differences")
bullets([
    "<b>Endpoint migration:</b> Polymarket's original <b>/markets</b> and <b>/events</b> endpoints are "
    "deprecated and were sunset on 2026-05-01. They still return HTTP 200, so it would have been easy to build "
    "the pipeline on a dying endpoint without noticing. I migrated to the replacement, cursor-paginated "
    "<b>/markets/keyset</b>, before writing any ingestion code.",
    "<b>Open interest isn't symmetric between platforms.</b> Kalshi exposes open_interest per market directly. "
    "Polymarket only exposes it at the event level, which aggregates across every sibling market in a "
    "multi-market event (all eight Bitcoin price-threshold markets share one event, for example). Attributing "
    "that combined number to a single market would misrepresent it, so Polymarket's open_interest is left NULL "
    "in this schema instead of populated with a misleading figure.",
    "<b>Price field choice:</b> Polymarket's outcomePrices field is the bid/ask midpoint, not the last executed "
    "trade price. I confirmed this directly against raw bid/ask data. The midpoint doesn't go stale on a quiet "
    "market the way \"last trade\" can, which makes it the better choice for a periodic snapshot.",
    "<b>Slugs aren't stable long-term identifiers</b> on Polymarket the way Kalshi tickers are. The same price "
    "threshold gets re-listed under a new slug once the prior instance resolves; I found three different "
    "\"Bitcoin dip to $60k\" slugs for the same nominal question. Watchlist slugs need periodic re-verification "
    "because of this.",
])

# ---------- Research ----------
h1("3. Research synthesis")
body("I logged seven theses from two X accounts, spanning theory, trading methodology, and platform risk.")

h2("Framework, then evidence it's real")
body("<b>@thenarrator</b> argues that a YES price near $1 still carries a hidden cost: capital stays locked "
     "until settlement, so a near-certain bet can be capital-inefficient if resolution drags or the exit is "
     "thin. He thinks markets need a visible \"carry\" metric, something like expected time-to-redemption shown "
     "next to price, similar to a funding rate on perpetual futures. The last few cents near $1, in his view, "
     "often just compensate for resolution or dispute risk the trader hasn't priced in.")
body("<b>@Domahhhh</b> supplies four separate, documented cases where that abstract resolution risk actually "
     "played out. Polymarket resolved a Venezuela \"invasion\" market against its own stated criteria after "
     "Trump publicly claimed the US controlled the country. Polymarket resolved an Epstein \"blackmail\" market "
     "YES off one ambiguous email, using a markedly looser standard than it applied days later. Kalshi paid out "
     "a \"will Biden meet Trudeau\" market at $0 even though the meeting was televised, because its rules only "
     "recognized two sources and neither reported it. And Kalshi settled an Oscars-viewership market on "
     "preliminary Nielsen numbers hours before the final numbers came out and flipped the outcome. Put together, "
     "these four cases turn narrator's abstract framing into something concrete and citable.")

h2("Trading methodology")
body("<b>@Domahhhh's</b> Fed Chair nomination trade is a good example of this. He held a large net-short "
     "position against the market-implied favorite, who reached 85% consensus, for roughly five months and "
     "through four different frontrunner swaps, based on his own analysis that the favorite was a poor fit for "
     "monetary policy. The eventual pick matched his own, lower-probability estimate instead, netting him "
     "$425,000. It's a real example of conviction against consensus pricing paying off, but only because the "
     "conviction was backed by genuine independent analysis rather than stubbornness.")

h2("Theory")
body("<b>@VitalikButerin</b> argues prediction markets are epistemically healthier than social media or "
     "unbounded asset markets. A bad take on social media earns unaccountable clout; a bad bet on a prediction "
     "market loses real money. And bounded [0,1] pricing resists the reflexivity and pump-and-dump dynamics "
     "that unbounded markets are prone to.")

story.append(PageBreak())

# ---------- Findings ----------
h1("4. Findings from my own data")

h2("4.1 Repricing speed (\"prediction-market VIX\")")
body("This operationalizes narrator's framing: mean absolute price change per hour, per market, over the "
     "observation window.")
chart("repricing_speed.png")
caption("Crypto threshold markets and politics markets with active reshuffling, like \"Will Markwayne Mullin be "
        "the next to leave the Cabinet?\", move fastest. The near-consensus \"no Fed rate cuts\" market, which "
        "is also the highest-volume market tracked, moves slowest. That fits the volume-reliability finding "
        "below: high conviction and high volume line up with low repricing.")

h2("4.2 Volume distribution")
chart("volume.png")
caption("The Polymarket \"Will no Fed rate cuts happen in 2026?\" market carries about $8.16M in volume, "
        "against near-zero volume on niche Kalshi cabinet markets like Susie Wiles and Markwayne Mullin. That's "
        "a direct, self-collected instance of the Evercore ISI finding that high-volume markets price more "
        "reliably than thin ones.")

h2("4.3 Cross-platform divergence")
body("Of five intended cross-platform pairs, only three are populated in cross_platform_links: one macro pair "
     "and two politics pairs. I didn't add the two crypto pairs, since Kalshi's and Polymarket's Bitcoin "
     "threshold markets track different strike prices and resolution dates. A like-for-like match there would "
     "have been impractical, not just noisy.")

h2("Macro pair: Fed rate cut")
chart("divergence_8_29.png")
caption("This compares Kalshi's \"will the Fed cut rates before 2027\" against Polymarket's \"will no Fed rate "
        "cuts happen in 2026,\" with Polymarket's series inverted for comparison. That inversion mattered: the "
        "two questions are logically opposite (on Kalshi, Yes means a cut happens; on Polymarket, Yes means it "
        "doesn't), so a naive raw comparison showed a false ~80-percentage-point \"divergence\" that was really "
        "just two inverted questions lined up against each other. Once I corrected for polarity, the two series "
        "started in close agreement, around 0.10 to 0.11 in early September, then diverged over the week: "
        "Kalshi's implied cut probability rose to 0.142 while Polymarket's fell to 0.073. Across 27 aligned "
        "snapshots, the Kalshi:Polymarket ratio averaged 1.41 (median 1.42, range 0.81 to 1.93). By the end of "
        "the window the platforms were roughly twice as far apart in ratio terms, despite a fairly modest "
        "absolute gap. I can't tell from one week of data whether that's a real information or liquidity "
        "asymmetry between the platforms, or just noise from a short observation window.")

h2("Politics pairs")
chart("divergence_9_32.png")
chart("divergence_10_31.png")
body("The two politics pairs don't show one uniform pattern, and treating them as if they did would overstate "
     "the finding. The RFK Jr. pair (Kalshi:Polymarket ratio) is tight and consistent: mean 0.72, median 0.70, "
     "standard deviation 0.06 across 27 points. Kalshi is consistently pricing this market about 30% below "
     "Polymarket. The Pete Hegseth pair is both higher and noisier: mean 0.80, median 0.80, standard deviation "
     "0.11, ranging from 0.59 to 0.95, with no comparably tight relationship. These are two distinct patterns, "
     "not one \"~65-70%, consistent\" finding across politics.")

# ---------- Limitations ----------
story.append(PageBreak())
h1("5. Limitations")
bullets([
    "About 19 markets tracked, a deliberately small and fixed watchlist, not the full catalog of either "
    "platform.",
    "Only 3 of 5 planned cross-platform links are populated. The 2 crypto pairs were never added, because of "
    "strike and date mismatches between platforms.",
    "About 1 week of observation history. The Fed-pair divergence trend is a real, measured result, but it's "
    "too short a window to call it a durable pattern rather than a one-week move.",
    "The politics pairs are approximate matches. Kalshi's cabinet-departure tickers resolve by May 22, 2026, "
    "while the matched Polymarket markets resolve by December 31, 2026: the same underlying question, but "
    "different windows.",
    "Polymarket's open_interest isn't available at market granularity (see Section 2), so it's NULL throughout.",
])

# ---------- Next Steps ----------
h1("6. Next steps")
bullets([
    "Populate the two crypto cross_platform_links now that there's a live watchlist history to match against.",
    "Backfill the resolutions table as tracked markets close, to evaluate realized accuracy instead of just "
    "live pricing.",
    "Persist GitHub Actions log history through actions/upload-artifact. Right now logs/pipeline.log resets "
    "every run, since Actions runners are ephemeral.",
    "Trade-level ingestion and wallet-level \"smart money\" tracking through Polymarket's subgraph. This was "
    "scoped out of this week's MVP and flagged as a stretch goal from the start.",
    "Widen the watchlist once the pipeline has run unattended for longer, to strengthen the volume-reliability "
    "and repricing-speed findings with a bigger sample.",
])

doc = SimpleDocTemplate(
    PDF_PATH, pagesize=letter,
    topMargin=0.7*inch, bottomMargin=0.7*inch, leftMargin=0.8*inch, rightMargin=0.8*inch,
)
doc.build(story)
print(f"wrote {PDF_PATH}")
