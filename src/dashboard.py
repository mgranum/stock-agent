import pandas as pd

from src.portfolio import summarize_portfolio
from src.orders import analyze_pending_orders


def build_dashboard(
    watchlist_report,
    portfolio_report,
    pending_orders,
):
    return {
        "portfolio_summary": summarize_portfolio(portfolio_report),
        "top_buy_candidates": _top_buy_candidates(watchlist_report),
        "risk_alerts": _risk_alerts(watchlist_report, portfolio_report),
        "pending_orders": analyze_pending_orders(
            pending_orders,
            watchlist_report,
        ),
        "market_summary": _market_summary(watchlist_report),
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