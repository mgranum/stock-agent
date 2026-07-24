from datetime import date
from pathlib import Path

import pandas as pd

from src.analysis import analyze_stock
from src.model_version import LEGACY_MODEL_VERSION, MODEL_VERSION


def backtest_current_model(symbols):
    rows = []

    for symbol in symbols:
        result, _ = analyze_stock(symbol)

        rows.append({
            "date": date.today().isoformat(),
            "model_version": MODEL_VERSION,
            "ticker": symbol,
            "score": result["score"],
            "anbefaling": result["anbefaling"],
            "trend_regime": result["trend_regime"],
            "technical_score": result["technical_score"],
            "fundamental_score": result["fundamental_score"],
            "fundamental_history_score": result["fundamental_history_score"],
            "relative_strength_20d": result["relative_strength_20d"],
            "kurs": result["kurs"],
            "stop_loss": result["stop_loss"],
            "trailing_stop_loss": result["trailing_stop_loss"],
        })

    return pd.DataFrame(rows).sort_values(
        by="score",
        ascending=False,
    ).reset_index(drop=True)


def save_model_snapshot(symbols, filename=None):
    df = backtest_current_model(symbols)

    output_dir = Path("snapshots")
    output_dir.mkdir(exist_ok=True)

    if filename is None:
        filename = f"model_snapshot_{date.today().isoformat()}.csv"

    path = output_dir / filename
    df.to_csv(path, index=False)

    return df, path

def load_snapshots():
    snapshot_dir = Path("snapshots")

    if not snapshot_dir.exists():
        return pd.DataFrame()

    files = sorted(snapshot_dir.glob("model_snapshot_*.csv"))

    if not files:
        return pd.DataFrame()

    frames = []

    for file in files:
        df = pd.read_csv(file)
        if "model_version" not in df.columns:
            df["model_version"] = LEGACY_MODEL_VERSION
        df["snapshot_file"] = file.name
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


def compare_snapshots():
    df = load_snapshots()

    if df.empty:
        return df

    return df.sort_values(
        by=["ticker", "date"]
    ).reset_index(drop=True)

def latest_snapshot_changes():
    df = load_snapshots()

    if df.empty:
        return pd.DataFrame()

    snapshot_dates = sorted(df["date"].unique())

    if len(snapshot_dates) < 2:
        return pd.DataFrame()

    previous_date = snapshot_dates[-2]
    latest_date = snapshot_dates[-1]

    previous = df[df["date"] == previous_date].copy()
    latest = df[df["date"] == latest_date].copy()

    merged = latest.merge(
        previous,
        on="ticker",
        suffixes=("_new", "_old"),
    )

    merged["score_change"] = (
        merged["score_new"] - merged["score_old"]
    )

    merged["rs_change"] = (
        merged["relative_strength_20d_new"]
        - merged["relative_strength_20d_old"]
    )

    merged["recommendation_change"] = (
        merged["anbefaling_old"]
        + " → "
        + merged["anbefaling_new"]
    )

    columns = [
        "ticker",
        "score_old",
        "score_new",
        "score_change",
        "relative_strength_20d_old",
        "relative_strength_20d_new",
        "rs_change",
        "recommendation_change",
    ]

    return merged[columns].sort_values(
        by="score_change",
        ascending=False,
    ).reset_index(drop=True)
