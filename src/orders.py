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

        stock_data = {}

        if not match.empty:
            stock = match.iloc[0]
            stock_data = {
                "current_price": stock["kurs"],
                "score": stock["score"],
                "recommendation": stock["anbefaling"],
                "trend_regime": stock["trend_regime"],
                "relative_strength_20d": stock["relative_strength_20d"],
                "stop_loss": stock["stop_loss"],
                "trailing_stop_loss": stock["trailing_stop_loss"],
            }

        rows.append({
            "order_id": order.get("order_id"),
            "created_at": order.get("created_at"),
            "ticker": ticker,
            "action": order["action"],
            "shares": order.get("shares"),
            "limit_price": order.get("limit_price"),
            "position_id": order.get("position_id"),
            "note": order.get("note", ""),
            **stock_data,
        })

    return pd.DataFrame(rows)


def analyze_order_history(order_history):
    if not order_history:
        return pd.DataFrame()

    rows = []

    for order in order_history:
        row = {
            "order_id": order.get("order_id"),
            "status": order.get("status"),
            "ticker": order.get("ticker"),
            "action": order.get("action"),
            "shares": order.get("shares"),
            "limit_price": order.get("limit_price"),
            "executed_price": order.get("executed_price"),
            "executed_at": order.get("executed_at"),
            "cancelled_at": order.get("cancelled_at"),
            "realized_profit_loss": order.get("realized_profit_loss"),
            "realized_gain_pct": order.get("realized_gain_pct"),
            "note": order.get("note", ""),
            "cancel_reason": order.get("cancel_reason", ""),
        }

        rows.append(row)

    return pd.DataFrame(rows)