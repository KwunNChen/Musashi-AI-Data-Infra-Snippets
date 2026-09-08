import os
import polars as pl
import matplotlib.pyplot as plt
from .load_data import load_snapshots, load_links
from ingest.logging_config import get_logger

OUTPUT_DIR = "analysis/output"
logger = get_logger(__name__)


def compute_repricing_speed(snapshots: pl.DataFrame) -> pl.DataFrame:
    df = snapshots.sort(["market_id", "ts"])
    df = df.with_columns([
        pl.col("ts").diff().over("market_id").alias("dt"),
        pl.col("yes_price").diff().over("market_id").abs().alias("d_price"),
    ])
    return df.with_columns(
        (pl.col("d_price") / (pl.col("dt") / pl.duration(hours=1))).alias("repricing_speed")
    )


def plot_repricing_speed(df: pl.DataFrame):
    per_market = (
        df.group_by(["external_id", "title"])
        .agg(pl.col("repricing_speed").mean().alias("avg_repricing_speed"))
        .drop_nulls("avg_repricing_speed")
        .with_columns((pl.col("title") + " — " + pl.col("external_id")).alias("label"))
        .sort("avg_repricing_speed", descending=True)
    )
    plt.figure(figsize=(10, 6))
    plt.barh(per_market["title"].to_list(), per_market["avg_repricing_speed"].to_numpy())
    plt.xlabel("avg repricing speed (price change / hour)")
    plt.title("Which markets move fastest")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/repricing_speed.png")
    plt.close()


def plot_divergence(snapshots: pl.DataFrame, links: pl.DataFrame):
    for link in links.iter_rows(named=True):
        k = snapshots.filter(pl.col("market_id") == link["kalshi_market_id"]).sort("ts")
        p = (snapshots.filter(pl.col("market_id") == link["polymarket_market_id"])
             .sort("ts").rename({"yes_price": "yes_price_poly"}))
        if k.is_empty() or p.is_empty():
            continue
        merged = k.join_asof(p, on="ts", strategy="nearest", tolerance="30m").drop_nulls("yes_price_poly")
        if merged.is_empty():
            logger.warning(f"no overlapping snapshots for link {link['kalshi_market_id']}/{link['polymarket_market_id']} within tolerance")
            continue

        if link["note"] and "invert" in link["note"].lower():
            merged = merged.with_columns((1 - pl.col("yes_price_poly")).alias("yes_price_poly"))

        plt.figure(figsize=(10, 5))
        plt.plot(merged["ts"].to_numpy(), merged["yes_price"].to_numpy(), label="Kalshi")
        plt.plot(merged["ts"].to_numpy(), merged["yes_price_poly"].to_numpy(), label="Polymarket")
        plt.legend()
        plt.title(k["title"][0])
        plt.tight_layout()
        plt.savefig(f"{OUTPUT_DIR}/divergence_{link['kalshi_market_id']}_{link['polymarket_market_id']}.png")
        plt.close()


def plot_volume(snapshots: pl.DataFrame):
    volume_latest = (
        snapshots.sort("ts")
        .group_by(["external_id", "category", "title"])
        .agg(pl.col("volume").last())
        .sort("volume", descending=True)
    )
    plt.figure(figsize=(10, 6))
    plt.barh(volume_latest["title"].to_list(), volume_latest["volume"].to_numpy())
    plt.xlabel("volume")
    plt.title("Volume across tracked markets")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/volume.png")
    plt.close()


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)   # savefig errors if this doesn't exist yet
    snapshots = load_snapshots()
    links = load_links()

    snapshots = compute_repricing_speed(snapshots)
    plot_repricing_speed(snapshots)
    plot_divergence(snapshots, links)
    plot_volume(snapshots)


if __name__ == "__main__":
    main()