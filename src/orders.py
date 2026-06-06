import pandas as pd


def analyze_pending_orders(
    pending_orders,
    watchlist_report,
):
    if not pending_orders:
        return pd.DataFrame()

    rows = []

    for order in pending_orders:
        ticker = order["ticker"]

        match = watchlist_report[
            watchlist_report["ticker"] == ticker
        ]

        if match.empty:
            rows.append({
                "ticker": ticker,
                "status": "IKKE FUNNET I WATCHLIST",
                "action": order["action"],
                "shares": order.get("shares"),
                "limit_price": order.get("limit_price"),
            })
            continue

        stock = match.iloc[0]

        rows.append({
            "ticker": ticker,
            "status": "VENTER PÅ FYLLING",
            "action": order["action"],
            "shares": order.get("shares"),
            "limit_price": order.get("limit_price"),
            "current_price": stock["kurs"],
            "score": stock["score"],
            "recommendation": stock["anbefaling"],
            "trend_regime": stock["trend_regime"],
            "relative_strength_20d": stock["relative_strength_20d"],
            "stop_loss": stock["stop_loss"],
            "trailing_stop_loss": stock["trailing_stop_loss"],
            "note": order.get("note", ""),
        })

    return pd.DataFrame(rows)