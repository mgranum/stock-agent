from collections import Counter

import pandas as pd

from src.data import get_daily_prices
from src.indicators import add_indicators
from src.model_backtest import load_snapshots
from src.orders import analyze_pending_orders
from src.portfolio import summarize_portfolio
from src.regime import analyze_market_regime
from src.strategy_classification import add_strategy_types, strategy_type_counts
from src.strategy_profiles import (
    add_strategy_profile_columns,
    strategy_profiles_overview,
)
from src.research_ideas import summarize_research_ideas
from src.technicals import get_benchmark_for_symbol


def build_dashboard(
    watchlist_report,
    portfolio_report,
    pending_orders,
    watchlist_symbols=None,
    research_ideas=None,
):
    return {
        "portfolio_summary": summarize_portfolio(portfolio_report),
        "portfolio_risk": _portfolio_risk(portfolio_report),
        "weakening_positions": _weakening_positions(
            portfolio_report,
            watchlist_report,
        ),
        "strong_winners": _strong_winners(portfolio_report),
        "top_buy_candidates": _top_buy_candidates(watchlist_report),
        "risk_alerts": _risk_alerts(watchlist_report, portfolio_report),
        "pending_orders": analyze_pending_orders(
            pending_orders,
            watchlist_report,
        ),
        "market_summary": _market_summary(watchlist_report),
        "market_regime": build_market_regime_summary(
            watchlist_symbols or [],
            watchlist_report,
        ),
        "changes_since_last_snapshot": _changes_since_last_snapshot(
            watchlist_report,
        ),
        "strategy_type_counts": strategy_type_counts(watchlist_report),
        "strategy_profiles": strategy_profiles_overview(),
        "research_ideas": summarize_research_ideas(research_ideas),
    }


def build_market_regime_summary(watchlist_symbols, watchlist_report=None):
    unavailable = {
        "available": False,
        "regime_label": "UNKNOWN",
        "benchmark_symbol": None,
        "benchmark_price": None,
        "sma20": None,
        "sma50": None,
        "sma100": None,
        "reasons": [],
        "interpretation": "Markedsregime utilgjengelig.",
        "watchlist_kpis": _watchlist_regime_kpis(watchlist_report),
        "message": "Markedsregime utilgjengelig.",
    }

    if not watchlist_symbols:
        return unavailable

    benchmark_symbol = _benchmark_for_watchlist(watchlist_symbols)

    try:
        benchmark_df = get_daily_prices(benchmark_symbol)
        benchmark_df = add_indicators(benchmark_df)
    except (ValueError, KeyError):
        return {
            **unavailable,
            "benchmark_symbol": benchmark_symbol,
            "message": (
                f"Kunne ikke hente benchmark-data for {benchmark_symbol}."
            ),
        }

    if len(benchmark_df) < 100:
        latest = benchmark_df.iloc[-1]
        return {
            **unavailable,
            "benchmark_symbol": benchmark_symbol,
            "benchmark_price": _round_metric(latest.get("close")),
            "sma20": _round_metric(latest.get("sma20")),
            "sma50": _round_metric(latest.get("sma50")),
            "sma100": _round_metric(latest.get("sma100")),
            "message": "For lite historikk til å beregne markedsregime.",
        }

    regime_result = analyze_market_regime(benchmark_df)
    latest = benchmark_df.iloc[-1]
    regime_label = _regime_display_label(regime_result)

    return {
        "available": True,
        "regime_label": regime_label,
        "benchmark_symbol": benchmark_symbol,
        "benchmark_price": _round_metric(latest["close"]),
        "sma20": _round_metric(latest["sma20"]),
        "sma50": _round_metric(latest["sma50"]),
        "sma100": _round_metric(latest["sma100"]),
        "reasons": regime_result["market_regime_reasons"],
        "interpretation": _regime_interpretation(regime_label),
        "watchlist_kpis": _watchlist_regime_kpis(watchlist_report),
        "message": None,
    }


def _benchmark_for_watchlist(symbols):
    benchmarks = [get_benchmark_for_symbol(symbol) for symbol in symbols]
    return Counter(benchmarks).most_common(1)[0][0]


def _regime_display_label(regime_result):
    score = regime_result["market_regime_score"]

    if regime_result["market_regime"] == "RISK_ON":
        return "RISK_ON"

    if score == 1:
        return "NEUTRAL"

    return "RISK_OFF"


def _regime_interpretation(regime_label):
    interpretations = {
        "RISK_ON": "Markedet støtter trendfølgende strategier",
        "RISK_OFF": "Defensiv posisjonering anbefales",
        "NEUTRAL": "Nøytralt marked – vær selektiv med nye posisjoner",
        "UNKNOWN": "Markedsregime utilgjengelig",
    }
    return interpretations.get(
        regime_label,
        "Markedsregime utilgjengelig",
    )


def _watchlist_regime_kpis(watchlist_report):
    if watchlist_report is None or watchlist_report.empty:
        return {
            "strong_uptrend_pct": 0,
            "weak_trend_pct": 0,
            "avg_relative_strength": 0,
        }

    total = len(watchlist_report)
    strong = int(
        (watchlist_report["trend_regime"] == "STERK OPPTREND").sum()
    )
    weak = int(
        (watchlist_report["trend_regime"] == "SVAK / NEGATIV TREND").sum()
    )
    avg_rs = float(watchlist_report["relative_strength_20d"].mean())

    return {
        "strong_uptrend_pct": round(strong / total * 100, 1),
        "weak_trend_pct": round(weak / total * 100, 1),
        "avg_relative_strength": round(avg_rs, 2),
    }


def _round_metric(value):
    if value is None or pd.isna(value):
        return None

    return round(float(value), 2)


def _top_buy_candidates(watchlist_report):
    if watchlist_report is None or watchlist_report.empty:
        return pd.DataFrame()

    df = watchlist_report[
        watchlist_report["anbefaling"] == "KJØP / ØK"
    ].copy()

    if df.empty:
        return pd.DataFrame()

    df = add_strategy_profile_columns(df)

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
            "strategy_type",
            "style",
            "preferred_hold_days",
            "preferred_stop_loss_pct",
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

    strategy_by_ticker = {}
    if watchlist_report is not None and not watchlist_report.empty:
        classified = add_strategy_types(watchlist_report)
        strategy_by_ticker = dict(
            zip(classified["ticker"], classified["strategy_type"])
        )

    rows = []

    for _, row in portfolio_report.iterrows():
        strategy_type = strategy_by_ticker.get(
            row["ticker"],
            "UNKNOWN",
        )

        if row.get("trailing_stop_triggered") is True:
            rows.append({
                "ticker": row["ticker"],
                "strategy_type": strategy_type,
                "alert": "Trailing stop trigget",
                "severity": "HIGH",
                "details": row.get("begrunnelse", ""),
            })

        if row.get("trend_regime") == "SVAK / NEGATIV TREND":
            rows.append({
                "ticker": row["ticker"],
                "strategy_type": strategy_type,
                "alert": "Svak / negativ trend",
                "severity": "MEDIUM",
                "details": row.get("begrunnelse", ""),
            })

        if row.get("relative_strength_20d", 0) < -5:
            rows.append({
                "ticker": row["ticker"],
                "strategy_type": strategy_type,
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


def _weakening_positions(portfolio_report, watchlist_report=None):
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

    strategy_by_ticker = {}
    if watchlist_report is not None and not watchlist_report.empty:
        classified = add_strategy_types(watchlist_report)
        strategy_by_ticker = dict(
            zip(classified["ticker"], classified["strategy_type"])
        )

    res["strategy_type"] = res["ticker"].map(
        lambda ticker: strategy_by_ticker.get(ticker, "UNKNOWN")
    )
    res = add_strategy_profile_columns(res)

    cols = [
        "ticker",
        "strategy_type",
        "style",
        "preferred_hold_days",
        "preferred_stop_loss_pct",
        "market_value",
        "unrealized_gain_pct",
        "trend_regime",
        "relative_strength_20d",
    ]
    present_cols = [c for c in cols if c in res.columns]
    res = res[present_cols].sort_values(
        by=["relative_strength_20d", "unrealized_gain_pct"],
        ascending=[True, True],
    ).reset_index(drop=True)

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
