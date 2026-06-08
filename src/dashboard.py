import pandas as pd

from src.model_backtest import load_snapshots
from src.portfolio import summarize_portfolio
from src.orders import analyze_pending_orders


def build_dashboard(
    watchlist_report,
    portfolio_report,
    pending_orders,
):
    return {
        "portfolio_summary": summarize_portfolio(portfolio_report),
        "portfolio_risk": _portfolio_risk(portfolio_report),
        "weakening_positions": _weakening_positions(portfolio_report),
        "strong_winners": _strong_winners(portfolio_report),
        "top_buy_candidates": _top_buy_candidates(watchlist_report),
        "risk_alerts": _risk_alerts(watchlist_report, portfolio_report),
        "pending_orders": analyze_pending_orders(
            pending_orders,
            watchlist_report,
        ),
        "market_summary": _market_summary(watchlist_report),
        "changes_since_last_snapshot": _changes_since_last_snapshot(
            watchlist_report,
        ),
    }


def _top_buy_candidates(watchlist_report):
    if watchlist_report is None or watchlist_report.empty:
        return pd.DataFrame()

    df = watchlist_report[
        watchlist_report["anbefaling"] == "KJØP / ØK"
    ].copy()

    if df.empty:
        return pd.DataFrame()

    return df.sort_values(
        by=[
            "score",
            "relative_strength_20d",
            "fundamental_history_score",
        ],
        ascending=[False, False, False],
    )[
        [
            "ticker",
            "score",
            "trend_regime",
            "relative_strength_20d",
            "fundamental_score",
            "fundamental_history_score",
            "kurs",
            "stop_loss",
            "trailing_stop_loss",
        ]
    ].reset_index(drop=True)


def _risk_alerts(watchlist_report, portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return pd.DataFrame()

    rows = []

    for _, row in portfolio_report.iterrows():
        if row.get("trailing_stop_triggered") is True:
            rows.append({
                "ticker": row["ticker"],
                "alert": "Trailing stop trigget",
                "severity": "HIGH",
                "details": row.get("begrunnelse", ""),
            })

        if row.get("trend_regime") == "SVAK / NEGATIV TREND":
            rows.append({
                "ticker": row["ticker"],
                "alert": "Svak / negativ trend",
                "severity": "MEDIUM",
                "details": row.get("begrunnelse", ""),
            })

        if row.get("relative_strength_20d", 0) < -5:
            rows.append({
                "ticker": row["ticker"],
                "alert": "Svak relativ styrke",
                "severity": "MEDIUM",
                "details": f"RS 20d: {row['relative_strength_20d']}%",
            })

    return pd.DataFrame(rows)


def _market_summary(watchlist_report):
    if watchlist_report is None or watchlist_report.empty:
        return {
            "total_symbols": 0,
            "buy_count": 0,
            "hold_count": 0,
            "avoid_count": 0,
        }

    return {
        "total_symbols": len(watchlist_report),
        "buy_count": int(
            (watchlist_report["anbefaling"] == "KJØP / ØK").sum()
        ),
        "hold_count": int(
            (watchlist_report["anbefaling"] == "HOLD / OBSERVER").sum()
        ),
        "avoid_count": int(
            (watchlist_report["anbefaling"] == "UNNGÅ / SELG").sum()
        ),
    }


# Portfolio risk and concentration analysis
def _portfolio_risk(portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return {
            "positions": 0,
            "total_market_value": 0,
            "top_position_pct": 0,
            "top3_concentration_pct": 0,
            "top_positions": pd.DataFrame(),
            "allocations": pd.DataFrame(),
        }

    df = portfolio_report.copy()

    if "error" in df.columns:
        df = df[df["error"].isna()]

    if df.empty:
        return {
            "positions": 0,
            "total_market_value": 0,
            "top_position_pct": 0,
            "top3_concentration_pct": 0,
            "top_positions": pd.DataFrame(),
            "allocations": pd.DataFrame(),
        }

    total_market = df["market_value"].sum()
    alloc = df[["ticker", "market_value"]].copy()
    alloc = alloc.groupby("ticker", as_index=False).sum()
    alloc["allocation_pct"] = alloc["market_value"] / total_market * 100
    alloc = alloc.sort_values(by="allocation_pct", ascending=False).reset_index(drop=True)

    top_positions = alloc.head(5).copy()

    top_position_pct = round(float(top_positions.iloc[0]["allocation_pct"]) if not top_positions.empty else 0, 2)
    top3_conc = round(float(top_positions.head(3)["allocation_pct"].sum()) if not top_positions.empty else 0, 2)

    # Return both metrics and DataFrames
    return {
        "positions": len(alloc),
        "total_market_value": round(total_market, 2),
        "top_position_pct": top_position_pct,
        "top3_concentration_pct": top3_conc,
        "top_positions": top_positions,
        "allocations": alloc,
    }


def _weakening_positions(portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return pd.DataFrame()

    df = portfolio_report.copy()
    if "error" in df.columns:
        df = df[df["error"].isna()]

    if df.empty:
        return pd.DataFrame()

    filt = (
        (df.get("trend_regime") == "SVAK / NEGATIV TREND")
        | (df.get("relative_strength_20d", 0) < 0)
    )

    res = df[filt].copy()
    if res.empty:
        return pd.DataFrame()

    cols = ["ticker", "market_value", "unrealized_gain_pct", "trend_regime", "relative_strength_20d"]
    present_cols = [c for c in cols if c in res.columns]
    res = res[present_cols].sort_values(by=["relative_strength_20d", "unrealized_gain_pct"], ascending=[True, True]).reset_index(drop=True)

    return res


def _strong_winners(portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return pd.DataFrame()

    df = portfolio_report.copy()
    if "error" in df.columns:
        df = df[df["error"].isna()]

    if df.empty:
        return pd.DataFrame()

    filt = (df.get("unrealized_gain_pct", -999) > 15) & (df.get("trend_regime") != "SVAK / NEGATIV TREND")

    res = df[filt].copy()
    if res.empty:
        return pd.DataFrame()

    cols = ["ticker", "market_value", "unrealized_gain_pct", "trend_regime"]
    present_cols = [c for c in cols if c in res.columns]
    res = res[present_cols].sort_values(by=["unrealized_gain_pct"], ascending=[False]).reset_index(drop=True)

    return res


_SNAPSHOT_CHANGE_COLUMNS = [
    "ticker",
    "previous_score",
    "current_score",
    "score_change",
    "previous_recommendation",
    "current_recommendation",
]


def _sort_snapshot_changes(df):
    if df.empty:
        return df

    return df.sort_values(
        by="score_change",
        key=lambda s: s.abs(),
        ascending=False,
    )[_SNAPSHOT_CHANGE_COLUMNS].reset_index(drop=True)


def _changes_since_last_snapshot(watchlist_report):
    snapshots = load_snapshots()

    if snapshots.empty:
        return None

    latest_date = sorted(snapshots["date"].unique())[-1]
    previous = snapshots[snapshots["date"] == latest_date][
        ["ticker", "score", "anbefaling"]
    ].rename(
        columns={
            "score": "previous_score",
            "anbefaling": "previous_recommendation",
        }
    )

    empty_sections = {
        "recommendation_changed": pd.DataFrame(),
        "large_score_changes": pd.DataFrame(),
    }

    if watchlist_report is None or watchlist_report.empty:
        return empty_sections

    current = watchlist_report[["ticker", "score", "anbefaling"]].rename(
        columns={
            "score": "current_score",
            "anbefaling": "current_recommendation",
        }
    )

    merged = current.merge(previous, on="ticker", how="inner")
    if merged.empty:
        return empty_sections

    merged["score_change"] = (
        merged["current_score"] - merged["previous_score"]
    )

    recommendation_changed = merged[
        merged["previous_recommendation"]
        != merged["current_recommendation"]
    ]

    large_score_changes = merged[
        (merged["previous_recommendation"] == merged["current_recommendation"])
        & (merged["score_change"].abs() >= 10)
    ]

    return {
        "recommendation_changed": _sort_snapshot_changes(
            recommendation_changed,
        ),
        "large_score_changes": _sort_snapshot_changes(
            large_score_changes,
        ),
    }
