from datetime import datetime
from uuid import uuid4

from src.storage import (
    save_portfolio,
    save_pending_orders,
    save_order_history,
    load_order_history,
)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def create_buy_order(
    orders,
    ticker,
    shares,
    limit_price=None,
    note="",
):
    order = {
        "order_id": str(uuid4()),
        "created_at": now_iso(),
        "ticker": ticker.upper(),
        "action": "BUY",
        "shares": float(shares),
        "limit_price": limit_price,
        "note": note,
    }

    updated = orders + [order]
    save_pending_orders(updated)

    return updated


def create_sell_order(
    orders,
    portfolio,
    position_id,
    shares,
    limit_price=None,
    note="",
):
    position = _find_position(portfolio, position_id)

    if position is None:
        raise ValueError("Fant ikke posisjon.")

    if shares > position["shares"]:
        raise ValueError("Kan ikke selge flere aksjer enn du eier i posisjonen.")

    order = {
        "order_id": str(uuid4()),
        "created_at": now_iso(),
        "ticker": position["ticker"],
        "action": "SELL",
        "position_id": position_id,
        "shares": float(shares),
        "limit_price": limit_price,
        "note": note,
    }

    updated = orders + [order]
    save_pending_orders(updated)

    return updated


def execute_order(
    orders,
    portfolio,
    order_id,
    executed_price,
    executed_at=None,
):
    executed_at = executed_at or now_iso()

    order = _find_order(orders, order_id)

    if order is None:
        raise ValueError("Fant ikke ordre.")

    remaining_orders = [
        item for item in orders
        if item["order_id"] != order_id
    ]

    history = load_order_history([])

    if order["action"] == "BUY":
        new_position = {
            "position_id": str(uuid4()),
            "ticker": order["ticker"],
            "shares": float(order["shares"]),
            "buy_price": float(executed_price),
            "buy_datetime": executed_at,
            "source_order_id": order_id,
            "note": order.get("note", ""),
        }

        updated_portfolio = portfolio + [new_position]

        history.append({
            **order,
            "status": "EXECUTED",
            "executed_at": executed_at,
            "executed_price": float(executed_price),
            "created_position_id": new_position["position_id"],
        })

    elif order["action"] == "SELL":
        updated_portfolio, realized = _execute_sell(
            portfolio=portfolio,
            order=order,
            executed_price=float(executed_price),
            executed_at=executed_at,
        )

        history.append({
            **order,
            "status": "EXECUTED",
            "executed_at": executed_at,
            "executed_price": float(executed_price),
            **realized,
        })

    else:
        raise ValueError(f"Ukjent ordretype: {order['action']}")

    save_portfolio(updated_portfolio)
    save_pending_orders(remaining_orders)
    save_order_history(history)

    return remaining_orders, updated_portfolio


def cancel_order(
    orders,
    order_id,
    cancelled_at=None,
    reason="Ikke effektuert",
):
    cancelled_at = cancelled_at or now_iso()

    order = _find_order(orders, order_id)

    if order is None:
        raise ValueError("Fant ikke ordre.")

    remaining_orders = [
        item for item in orders
        if item["order_id"] != order_id
    ]

    history = load_order_history([])

    history.append({
        **order,
        "status": "CANCELLED",
        "cancelled_at": cancelled_at,
        "cancel_reason": reason,
    })

    save_pending_orders(remaining_orders)
    save_order_history(history)

    return remaining_orders


def _execute_sell(
    portfolio,
    order,
    executed_price,
    executed_at,
):
    position_id = order["position_id"]
    shares_to_sell = float(order["shares"])

    updated = []
    realized = None

    for position in portfolio:
        if position["position_id"] != position_id:
            updated.append(position)
            continue

        owned_shares = float(position["shares"])

        if shares_to_sell > owned_shares:
            raise ValueError("Kan ikke selge flere aksjer enn du eier.")

        remaining_shares = owned_shares - shares_to_sell

        buy_price = float(position["buy_price"])
        realized_pl = (executed_price - buy_price) * shares_to_sell
        realized_pct = ((executed_price - buy_price) / buy_price) * 100

        realized = {
            "sold_position_id": position_id,
            "buy_price": buy_price,
            "buy_datetime": position.get("buy_datetime"),
            "sold_shares": shares_to_sell,
            "realized_profit_loss": round(realized_pl, 2),
            "realized_gain_pct": round(realized_pct, 2),
        }

        if remaining_shares > 0:
            updated.append({
                **position,
                "shares": remaining_shares,
            })

    if realized is None:
        raise ValueError("Fant ikke posisjon å selge fra.")

    return updated, realized


def _find_order(orders, order_id):
    for order in orders:
        if order["order_id"] == order_id:
            return order

    return None


def _find_position(portfolio, position_id):
    for position in portfolio:
        if position["position_id"] == position_id:
            return position

    return None