import pandas as pd

from src.alerts import (
    ACTION_REVIEW_SELL,
    ALERT_PENDING_ORDER,
    ALERT_PROFIT_PROTECTION,
    _pending_order_message,
)
from src.orders import analyze_pending_orders
from src.portfolio import valid_portfolio_rows
from src.strategy_classification import add_strategy_types


NEAR_TRAILING_STOP_PCT = 3.0
LARGE_DRAWDOWN_PCT = -15.0
CONCENTRATION_TOP_POSITION_PCT = 25.0
CONCENTRATION_TOP3_PCT = 60.0
DAILY_AGENDA_DISPLAY_LIMIT = 3
WHATS_NEW_SUMMARY_LIMIT = 5

_AGENDA_PRIORITY_LABELS = {
    1: "Høy",
    2: "Medium",
    3: "Lav",
}

_RECOMMENDATION_SHORT_LABELS = {
    "HOLD / OBSERVER": "HOLD",
    "UNNGÅ / SELG": "UNNGÅ/SELG",
    "KJØP / ØK": "KJØP/ØK",
}

_OPPORTUNITY_COLUMNS = [
    "ticker",
    "strategy_type",
    "score",
    "relative_strength_20d",
    "fundamental_score",
    "fundamental_history_score",
    "anbefaling",
    "trend_regime",
]


def build_daily_flow(
    watchlist_report,
    portfolio_report,
    dashboard,
    pending_orders=None,
    alerts=None,
    portfolio=None,
):
    market_regime = _build_market_regime(watchlist_report, dashboard)
    key_opportunities = _build_key_opportunities(
        watchlist_report,
        dashboard,
        portfolio_report,
        portfolio,
    )
    risk_alerts = _build_risk_alerts(portfolio_report, dashboard)
    pending_summary = _build_pending_order_summary(
        pending_orders,
        watchlist_report,
        dashboard,
    )
    order_actions = build_order_actions(pending_orders)
    portfolio_actions = build_portfolio_actions(portfolio_report)
    daily_actions = build_daily_actions(
        alerts,
        pending_orders,
        portfolio_report,
    )
    whats_new_today = _build_whats_new_today(dashboard)
    summary_bullets = _build_summary_bullets(
        market_regime,
        key_opportunities,
        risk_alerts,
        pending_summary,
        dashboard,
    )

    return {
        "market_regime": market_regime,
        "key_opportunities": key_opportunities,
        "risk_alerts": risk_alerts,
        "pending_orders": pending_summary,
        "order_actions": order_actions,
        "portfolio_actions": portfolio_actions,
        "daily_actions": daily_actions,
        "whats_new_today": whats_new_today,
        "summary_bullets": summary_bullets,
    }


_ORDER_ACTION_LABEL = "Gjennomgå ordre"
_ORDER_SELL_PRIORITY = 1
_ORDER_BUY_PRIORITY = 2

_ACTIONABLE_PORTFOLIO_RÅD = {
    "REDUSER / SELG",
    "VURDER REDUKSJON",
    "VURDER GEVINSTSIKRING",
    "FØLG MED / IKKE ØK",
}

_PORTFOLIO_ACTION_LABELS = {
    "REDUSER / SELG": "Vurder salg",
    "VURDER REDUKSJON": "Vurder reduksjon",
    "VURDER GEVINSTSIKRING": "Sikre gevinst",
    "FØLG MED / IKKE ØK": "Følg med",
}

_PORTFOLIO_ACTION_PRIORITY = {
    "REDUSER / SELG": 1,
    "VURDER REDUKSJON": 1,
    "VURDER GEVINSTSIKRING": 2,
    "FØLG MED / IKKE ØK": 3,
}

_PORTFOLIO_ACTION_SORT = {
    "REDUSER / SELG": 0,
    "VURDER REDUKSJON": 1,
    "VURDER GEVINSTSIKRING": 2,
    "FØLG MED / IKKE ØK": 3,
}


def daily_actions_from_alerts(alerts):
    if not alerts:
        return []

    actions = []
    for alert in alerts:
        actions.append({
            "priority": alert.get("priority", 3),
            "category": alert.get("source", ""),
            "ticker": alert.get("ticker", ""),
            "action_label": alert.get("action_label", ""),
            "message": alert.get("message", ""),
        })

    return sorted(
        actions,
        key=lambda item: (item["priority"], item.get("ticker", "")),
    )


def build_order_actions(pending_orders):
    return [
        _public_order_action(item)
        for item in _build_order_action_items(pending_orders)
    ]


def build_portfolio_actions(portfolio_report):
    return [
        _public_portfolio_action(item)
        for item in _build_portfolio_action_items(portfolio_report)
    ]


def build_daily_actions(alerts, pending_orders=None, portfolio_report=None):
    alert_actions = daily_actions_from_alerts(alerts)
    covered_order_keys = {
        alert.get("dedupe_key")
        for alert in (alerts or [])
        if alert.get("alert_type") == ALERT_PENDING_ORDER
    }
    review_sell_tickers = {
        alert.get("ticker")
        for alert in (alerts or [])
        if alert.get("action") == ACTION_REVIEW_SELL
    }
    profit_protection_tickers = {
        alert.get("ticker")
        for alert in (alerts or [])
        if alert.get("alert_type") == ALERT_PROFIT_PROTECTION
    }

    extra_actions = []
    for item in _build_order_action_items(pending_orders):
        if item["_dedupe_key"] in covered_order_keys:
            continue
        extra_actions.append(_public_order_action(item))

    for item in _build_portfolio_action_items(portfolio_report):
        ticker = item["ticker"]
        portefølje_råd = item["_portefølje_råd"]
        if (
            portefølje_råd == "REDUSER / SELG"
            and ticker in review_sell_tickers
        ):
            continue
        if (
            portefølje_råd == "VURDER GEVINSTSIKRING"
            and ticker in profit_protection_tickers
        ):
            continue
        if (
            portefølje_råd == "VURDER REDUKSJON"
            and ticker in review_sell_tickers
        ):
            continue
        extra_actions.append(_public_portfolio_action(item))

    return sorted(
        alert_actions + extra_actions,
        key=lambda item: (item["priority"], item.get("ticker", "")),
    )


def _public_order_action(item):
    return {
        "priority": item["priority"],
        "ticker": item["ticker"],
        "action_label": item["action_label"],
        "message": item["message"],
    }


def _public_portfolio_action(item):
    return {
        "priority": item["priority"],
        "ticker": item["ticker"],
        "action_label": item["action_label"],
        "message": item["message"],
        "source": item["source"],
        "dedupe_key": item["dedupe_key"],
    }


def _build_portfolio_action_items(portfolio_report):
    df = valid_portfolio_rows(portfolio_report)
    if df.empty:
        return []

    actionable = df[
        df["portefølje_råd"].isin(_ACTIONABLE_PORTFOLIO_RÅD)
    ].copy()
    if actionable.empty:
        return []

    actionable["_sort"] = actionable["portefølje_råd"].map(
        lambda action: _PORTFOLIO_ACTION_SORT.get(action, 99)
    )
    actionable = actionable.sort_values(
        by=["_sort", "ticker"],
    ).drop(columns="_sort")

    items = []
    for _, row in actionable.iterrows():
        portefølje_råd = row["portefølje_råd"]
        ticker = row["ticker"]
        items.append({
            "priority": _PORTFOLIO_ACTION_PRIORITY[portefølje_råd],
            "ticker": ticker,
            "action_label": _PORTFOLIO_ACTION_LABELS[portefølje_råd],
            "message": _portfolio_action_message(row),
            "source": "PORTFOLIO",
            "dedupe_key": _portfolio_action_dedupe_key(ticker, portefølje_råd),
            "_portefølje_råd": portefølje_råd,
        })

    return items


def _portfolio_action_dedupe_key(ticker, portefølje_råd):
    return f"PORTFOLIO_ACTION:{ticker}:{portefølje_råd}"


def _portfolio_action_message(row):
    parts = []

    begrunnelse = row.get("begrunnelse")
    if begrunnelse is not None and pd.notna(begrunnelse) and str(begrunnelse).strip():
        parts.append(str(begrunnelse).strip())

    gain = row.get("unrealized_gain_pct")
    if gain is not None and not pd.isna(gain):
        rounded = round(float(gain), 1)
        sign = "+" if rounded > 0 else ""
        parts.append(f"gevinst/tap {sign}{rounded} %")

    score = row.get("score")
    if score is not None and not pd.isna(score):
        parts.append(f"score {int(score)}")

    anbefaling = row.get("anbefaling")
    if anbefaling is not None and not pd.isna(anbefaling):
        parts.append(str(anbefaling).strip())

    if parts:
        return " · ".join(parts)

    return str(row.get("portefølje_råd", ""))


def _build_order_action_items(pending_orders):
    sells = []
    buys = []
    other = []

    for order in pending_orders or []:
        item = _order_to_action_item(order)
        action = str(order.get("action", "")).upper()
        if action == "SELL":
            sells.append(item)
        elif action == "BUY":
            buys.append(item)
        else:
            other.append(item)

    sort_key = lambda item: item.get("ticker", "")
    return (
        sorted(sells, key=sort_key)
        + sorted(buys, key=sort_key)
        + sorted(other, key=sort_key)
    )


def _order_to_action_item(order):
    action = str(order.get("action", "")).upper()
    return {
        "priority": (
            _ORDER_SELL_PRIORITY
            if action == "SELL"
            else _ORDER_BUY_PRIORITY
        ),
        "ticker": order.get("ticker", ""),
        "action_label": _ORDER_ACTION_LABEL,
        "message": _pending_order_message(order),
        "_dedupe_key": _order_action_dedupe_key(order),
    }


def _order_action_dedupe_key(order):
    action = str(order.get("action", "")).upper()
    shares = order.get("shares")
    limit_price = order.get("limit_price")
    order_key = order.get("id") or f"{action}:{shares}:{limit_price or ''}"
    ticker = order.get("ticker", "")
    return f"{ALERT_PENDING_ORDER}:{ticker}:{order_key}"


def daily_agenda_items(daily_flow, limit=DAILY_AGENDA_DISPLAY_LIMIT):
    actions = daily_flow.get("daily_actions") or []
    return actions[:limit]


def daily_agenda_from_alerts(alerts, limit=DAILY_AGENDA_DISPLAY_LIMIT):
    return daily_actions_from_alerts(alerts)[:limit]


def format_daily_agenda_item(action):
    priority = _AGENDA_PRIORITY_LABELS.get(action.get("priority"), "Lav")
    ticker = action.get("ticker") or "—"
    action_label = action.get("action_label") or ""
    message = action.get("message") or ""
    return f"{priority} · {ticker} · {action_label} — {message}"


def build_daily_agenda_table(actions):
    columns = ["Prioritet", "Ticker", "Handling"]
    if not actions:
        return pd.DataFrame(columns=columns)

    rows = []
    for action in actions:
        rows.append({
            "Prioritet": _AGENDA_PRIORITY_LABELS.get(
                action.get("priority"),
                "Lav",
            ),
            "Ticker": action.get("ticker", ""),
            "Handling": action.get("action_label", ""),
        })

    return pd.DataFrame(rows, columns=columns)


def explain_snapshot_change_begrunnelse(row):
    score_change = row.get("score_change")
    if score_change is not None and not pd.isna(score_change):
        score_change = int(score_change)
        if score_change != 0:
            sign = "+" if score_change > 0 else ""
            return f"Score {sign}{score_change} poeng siden sist snapshot"

    previous = row.get("previous_recommendation")
    current = row.get("current_recommendation")
    if (
        previous is not None
        and current is not None
        and not pd.isna(previous)
        and not pd.isna(current)
        and previous != current
    ):
        return _recommendation_change_begrunnelse(previous, current)

    return "Endring siden sist snapshot"


def _recommendation_change_begrunnelse(previous_recommendation, current_recommendation):
    ranks = {
        "KJØP / ØK": 3,
        "HOLD / OBSERVER": 2,
        "UNNGÅ / SELG": 1,
    }
    previous_rank = ranks.get(previous_recommendation, 0)
    current_rank = ranks.get(current_recommendation, 0)

    if current_rank < previous_rank:
        return "Anbefaling nedgradert etter svakere total score"
    if current_rank > previous_rank:
        return "Anbefaling oppgradert etter sterkere total score"
    return "Anbefaling endret siden sist snapshot"


def _short_recommendation_label(recommendation):
    return _RECOMMENDATION_SHORT_LABELS.get(
        recommendation,
        recommendation,
    )


def whats_new_display_items(
    daily_flow,
    limit=WHATS_NEW_SUMMARY_LIMIT,
):
    whats_new = daily_flow.get("whats_new_today") or {}
    items = whats_new.get("summary_items") or []
    return items[:limit]


def format_whats_new_item(item):
    ticker = item.get("ticker") or "—"
    message = item.get("message") or ""
    return f"{ticker} · {message}"


def build_whats_new_table(daily_flow, limit=WHATS_NEW_SUMMARY_LIMIT):
    columns = ["Ticker", "Fra", "Til", "Begrunnelse"]
    items = whats_new_display_items(daily_flow, limit=limit)
    if not items:
        return pd.DataFrame(columns=columns)

    rows = []
    for item in items:
        rows.append({
            "Ticker": item.get("ticker", ""),
            "Fra": item.get("fra", ""),
            "Til": item.get("til", ""),
            "Begrunnelse": item.get("begrunnelse", ""),
        })

    return pd.DataFrame(rows, columns=columns)


def _build_whats_new_today(dashboard):
    empty = {
        "available": False,
        "has_changes": False,
        "recommendation_changed": pd.DataFrame(),
        "large_score_changes": pd.DataFrame(),
        "summary_items": [],
    }

    changes = dashboard.get("changes_since_last_snapshot")
    if changes is None:
        return empty

    recommendation_changed = changes.get("recommendation_changed")
    if recommendation_changed is None:
        recommendation_changed = pd.DataFrame()

    large_score_changes = changes.get("large_score_changes")
    if large_score_changes is None:
        large_score_changes = pd.DataFrame()

    summary_items = _whats_new_summary_items(
        recommendation_changed,
        large_score_changes,
    )

    return {
        "available": True,
        "has_changes": (
            not recommendation_changed.empty
            or not large_score_changes.empty
        ),
        "recommendation_changed": recommendation_changed,
        "large_score_changes": large_score_changes,
        "summary_items": summary_items,
    }


def _whats_new_summary_items(
    recommendation_changed,
    large_score_changes,
    limit=WHATS_NEW_SUMMARY_LIMIT,
):
    items = []

    if recommendation_changed is not None and not recommendation_changed.empty:
        for _, row in recommendation_changed.iterrows():
            previous = row["previous_recommendation"]
            current = row["current_recommendation"]
            items.append({
                "ticker": row["ticker"],
                "change_type": "recommendation",
                "fra": _short_recommendation_label(previous),
                "til": _short_recommendation_label(current),
                "begrunnelse": explain_snapshot_change_begrunnelse(row),
            })
            if len(items) >= limit:
                return items

    if large_score_changes is not None and not large_score_changes.empty:
        for _, row in large_score_changes.iterrows():
            previous = row["previous_recommendation"]
            current = row["current_recommendation"]
            items.append({
                "ticker": row["ticker"],
                "change_type": "score",
                "fra": _short_recommendation_label(previous),
                "til": _short_recommendation_label(current),
                "begrunnelse": explain_snapshot_change_begrunnelse(row),
            })
            if len(items) >= limit:
                return items

    return items


def _build_market_regime(watchlist_report, dashboard):
    market_summary = dashboard.get("market_summary") or {}
    strategy_counts = dashboard.get("strategy_type_counts") or {}

    total = market_summary.get("total_symbols", 0)
    buy_count = market_summary.get("buy_count", 0)
    avoid_count = market_summary.get("avoid_count", 0)
    weak_avoid_count = strategy_counts.get("WEAK/AVOID", 0)

    avg_rs = 0.0
    avg_score = 0.0
    if watchlist_report is not None and not watchlist_report.empty:
        avg_rs = float(watchlist_report["relative_strength_20d"].mean())
        avg_score = float(watchlist_report["score"].mean())

    buy_ratio = buy_count / total if total else 0
    weak_ratio = weak_avoid_count / total if total else 0
    avoid_ratio = avoid_count / total if total else 0

    risk_on_points = 0
    defensive_points = 0

    if buy_ratio >= 0.25:
        risk_on_points += 1
    elif buy_ratio <= 0.10:
        defensive_points += 1

    if weak_ratio <= 0.15:
        risk_on_points += 1
    elif weak_ratio >= 0.30:
        defensive_points += 1

    if avg_rs >= 2:
        risk_on_points += 1
    elif avg_rs <= -2:
        defensive_points += 1

    if avg_score >= 60:
        risk_on_points += 1
    elif avg_score <= 45:
        defensive_points += 1

    if risk_on_points >= 3:
        label = "Risk-on"
    elif defensive_points >= 3:
        label = "Defensive"
    else:
        label = "Mixed"

    return {
        "label": label,
        "signals": {
            "buy_count": buy_count,
            "avoid_count": avoid_count,
            "weak_avoid_count": weak_avoid_count,
            "avg_relative_strength": round(avg_rs, 2),
            "avg_score": round(avg_score, 1),
            "buy_ratio_pct": round(buy_ratio * 100, 1),
            "weak_avoid_ratio_pct": round(weak_ratio * 100, 1),
            "avoid_ratio_pct": round(avoid_ratio * 100, 1),
        },
    }


def _build_key_opportunities(
    watchlist_report,
    dashboard,
    portfolio_report=None,
    portfolio=None,
):
    empty = {
        "new_buy_candidates": pd.DataFrame(),
        "existing_positions_to_increase": pd.DataFrame(),
        "strongest_momentum": pd.DataFrame(),
        "strongest_quality_compounders": pd.DataFrame(),
    }

    if watchlist_report is None or watchlist_report.empty:
        return empty

    classified = add_strategy_types(watchlist_report)

    buy_candidates = _new_buy_candidates(classified, dashboard)
    owned = _owned_tickers(portfolio_report, portfolio)
    if buy_candidates.empty:
        new_buys = buy_candidates
        increase_buys = pd.DataFrame()
    else:
        tickers_upper = (
            buy_candidates["ticker"].astype(str).str.strip().str.upper()
        )
        owned_mask = tickers_upper.isin(owned)
        new_buys = buy_candidates[~owned_mask]
        increase_buys = buy_candidates[owned_mask]

    momentum = _top_by_strategy(
        classified,
        "MOMENTUM",
        sort_by=["relative_strength_20d", "score"],
    )
    quality = _top_by_strategy(
        classified,
        "QUALITY_COMPOUNDER",
        sort_by=[
            "fundamental_history_score",
            "fundamental_score",
            "score",
        ],
    )

    return {
        "new_buy_candidates": _select_opportunity_columns(new_buys, limit=5),
        "existing_positions_to_increase": _select_opportunity_columns(
            increase_buys,
            limit=5,
        ),
        "strongest_momentum": _select_opportunity_columns(momentum, limit=5),
        "strongest_quality_compounders": _select_opportunity_columns(
            quality,
            limit=5,
        ),
    }


def _owned_tickers(portfolio_report, portfolio=None):
    owned = set()

    for position in portfolio or []:
        ticker = position.get("ticker")
        if ticker:
            owned.add(str(ticker).strip().upper())

    if portfolio_report is None or portfolio_report.empty:
        return owned

    df = valid_portfolio_rows(portfolio_report)
    for ticker in df["ticker"]:
        owned.add(str(ticker).strip().upper())

    return owned


def _new_buy_candidates(classified, dashboard):
    top_buys = dashboard.get("top_buy_candidates")
    if top_buys is not None and not top_buys.empty:
        return top_buys.copy()

    buys = classified[classified["anbefaling"] == "KJØP / ØK"].copy()
    if buys.empty:
        return pd.DataFrame()

    snapshot_changes = dashboard.get("changes_since_last_snapshot")
    if snapshot_changes is not None:
        changed = snapshot_changes.get("recommendation_changed")
        if changed is not None and not changed.empty:
            new_tickers = changed[
                changed["current_recommendation"] == "KJØP / ØK"
            ]["ticker"]
            newly_upgraded = buys[buys["ticker"].isin(new_tickers)]
            if not newly_upgraded.empty:
                return newly_upgraded.sort_values(
                    by=["score", "relative_strength_20d"],
                    ascending=[False, False],
                )

    return buys.sort_values(
        by=["score", "relative_strength_20d"],
        ascending=[False, False],
    )


def _top_by_strategy(classified, strategy_type, sort_by):
    subset = classified[
        classified["strategy_type"] == strategy_type
    ].copy()

    if subset.empty:
        return pd.DataFrame()

    return subset.sort_values(
        by=sort_by,
        ascending=[False] * len(sort_by),
    )


def _select_opportunity_columns(df, limit=5):
    if df is None or df.empty:
        return pd.DataFrame()

    if "strategy_type" not in df.columns:
        df = add_strategy_types(df)

    cols = [c for c in _OPPORTUNITY_COLUMNS if c in df.columns]
    return df[cols].head(limit).reset_index(drop=True)


def _build_risk_alerts(portfolio_report, dashboard):
    near_stop = _positions_near_trailing_stop(portfolio_report)
    weakening = dashboard.get("weakening_positions", pd.DataFrame())
    drawdowns = _large_drawdown_positions(portfolio_report)
    concentration = _concentration_risk(dashboard)
    other = dashboard.get("risk_alerts", pd.DataFrame())

    return {
        "near_trailing_stop": near_stop,
        "weakening_positions": _format_weakening_positions(weakening),
        "large_drawdowns": drawdowns,
        "concentration_risk": concentration,
        "other_alerts": other,
        "has_alerts": _has_any_alerts(
            near_stop,
            weakening,
            drawdowns,
            concentration,
            other,
        ),
    }


def _positions_near_trailing_stop(portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return pd.DataFrame()

    df = valid_portfolio_rows(portfolio_report)

    rows = []
    for _, row in df.iterrows():
        price = row.get("current_price")
        trailing = row.get("trailing_stop_loss")

        if price is None or trailing is None or pd.isna(price) or pd.isna(trailing):
            continue

        if price <= trailing:
            continue

        distance_pct = (price - trailing) / price * 100
        if distance_pct <= NEAR_TRAILING_STOP_PCT:
            rows.append({
                "ticker": row["ticker"],
                "alert": "Nær trailing stop",
                "severity": "HIGH",
                "details": (
                    f"Kurs {round(price, 2)} – "
                    f"stop {round(trailing, 2)} "
                    f"({round(distance_pct, 1)}% unna)"
                ),
            })

    return pd.DataFrame(rows)


def _large_drawdown_positions(portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return pd.DataFrame()

    df = valid_portfolio_rows(portfolio_report)

    if df.empty:
        return pd.DataFrame()

    losers = df[df["unrealized_gain_pct"] <= LARGE_DRAWDOWN_PCT].copy()
    if losers.empty:
        return pd.DataFrame()

    rows = []
    for _, row in losers.iterrows():
        rows.append({
            "ticker": row["ticker"],
            "alert": "Stort urealisert tap",
            "severity": "HIGH",
            "details": f"{row['unrealized_gain_pct']}%",
        })

    return pd.DataFrame(rows)


def _format_weakening_positions(weakening):
    if weakening is None or weakening.empty:
        return pd.DataFrame()

    rows = []
    for _, row in weakening.iterrows():
        details_parts = []
        if "trend_regime" in row and pd.notna(row["trend_regime"]):
            details_parts.append(str(row["trend_regime"]))
        if "relative_strength_20d" in row and pd.notna(row["relative_strength_20d"]):
            details_parts.append(f"RS {row['relative_strength_20d']}%")

        rows.append({
            "ticker": row["ticker"],
            "alert": "Svekkende posisjon",
            "severity": "MEDIUM",
            "details": " · ".join(details_parts),
        })

    return pd.DataFrame(rows)


def _concentration_risk(dashboard):
    pr = dashboard.get("portfolio_risk") or {}
    top_pct = pr.get("top_position_pct", 0)
    top3_pct = pr.get("top3_concentration_pct", 0)

    alerts = []
    if top_pct >= CONCENTRATION_TOP_POSITION_PCT:
        alerts.append({
            "alert": "Høy enkeltposisjon",
            "severity": "MEDIUM",
            "details": f"Topp posisjon {top_pct}%",
        })

    if top3_pct >= CONCENTRATION_TOP3_PCT:
        alerts.append({
            "alert": "Høy konsentrasjon (topp 3)",
            "severity": "MEDIUM",
            "details": f"Topp 3 utgjør {top3_pct}%",
        })

    return {
        "top_position_pct": top_pct,
        "top3_concentration_pct": top3_pct,
        "alerts": alerts,
        "has_risk": len(alerts) > 0,
    }


def _has_any_alerts(near_stop, weakening, drawdowns, concentration, other):
    if not near_stop.empty or not drawdowns.empty:
        return True

    if weakening is not None and not weakening.empty:
        return True

    if other is not None and not other.empty:
        return True

    return concentration.get("has_risk", False)


def _build_pending_order_summary(pending_orders, watchlist_report, dashboard):
    orders_df = dashboard.get("pending_orders")

    if orders_df is None or orders_df.empty:
        if pending_orders:
            orders_df = analyze_pending_orders(
                pending_orders,
                watchlist_report,
            )
        else:
            orders_df = pd.DataFrame()

    if orders_df is None or orders_df.empty:
        return {
            "total": 0,
            "buy_count": 0,
            "sell_count": 0,
            "orders": pd.DataFrame(),
            "summary": "Ingen ventende ordre.",
        }

    buy_count = int((orders_df["action"] == "BUY").sum())
    sell_count = int((orders_df["action"] == "SELL").sum())
    total = len(orders_df)

    parts = [f"{total} ventende ordre"]
    if buy_count:
        parts.append(f"{buy_count} kjøp")
    if sell_count:
        parts.append(f"{sell_count} salg")

    return {
        "total": total,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "orders": orders_df,
        "summary": " · ".join(parts),
    }


def _build_summary_bullets(
    market_regime,
    key_opportunities,
    risk_alerts,
    pending_summary,
    dashboard,
):
    bullets = []
    signals = market_regime["signals"]

    bullets.append(
        f"Marked: {market_regime['label']} – "
        f"{signals['buy_count']} kjøp, "
        f"{signals['weak_avoid_count']} svake/unngå, "
        f"snitt RS {signals['avg_relative_strength']}%."
    )

    new_buys = key_opportunities["new_buy_candidates"]
    if not new_buys.empty:
        tickers = ", ".join(new_buys["ticker"].head(3).tolist())
        bullets.append(f"Topp kjøpskandidater: {tickers}.")

    momentum = key_opportunities["strongest_momentum"]
    if not momentum.empty:
        leader = momentum.iloc[0]["ticker"]
        rs = momentum.iloc[0]["relative_strength_20d"]
        bullets.append(f"Sterkest momentum: {leader} (RS {rs}%).")

    if risk_alerts.get("has_alerts"):
        alert_count = _count_risk_items(risk_alerts)
        bullets.append(f"{alert_count} risikovarsler krever oppmerksomhet.")
    else:
        bullets.append("Ingen kritiske risikovarsler i porteføljen.")

    if pending_summary["total"] > 0:
        bullets.append(pending_summary["summary"] + ".")

    research_summary = dashboard.get("research_ideas") or {}
    bullets.extend(_research_idea_bullets(research_summary))

    portfolio_summary = dashboard.get("portfolio_summary") or {}
    gain_pct = portfolio_summary.get("total_unrealized_gain_pct")
    if gain_pct is not None and portfolio_summary.get("positions", 0) > 0:
        bullets.append(
            f"Portefølje: {portfolio_summary['positions']} posisjoner, "
            f"urealisert {gain_pct}%."
        )

    return bullets[:8]


def _research_idea_bullets(research_summary):
    if not research_summary or research_summary.get("total", 0) == 0:
        return []

    bullets = []

    watchlist_count = research_summary.get("watchlist_count", 0)
    if watchlist_count > 0:
        tickers = ", ".join(
            idea.get("ticker", "")
            for idea in research_summary.get("watchlist_ideas", [])[:3]
            if idea.get("ticker")
        )
        if tickers:
            bullets.append(
                f"{watchlist_count} research-idé(er) bør legges til watchlist: "
                f"{tickers}."
            )
        else:
            bullets.append(
                f"{watchlist_count} research-idé(er) bør legges til watchlist."
            )

    stale_count = research_summary.get("stale_count", 0)
    if stale_count > 0:
        bullets.append(
            f"{stale_count} research-idé(er) er utdaterte (>7 dager). "
            "Oppdater i Screening."
        )

    archive_count = research_summary.get("archive_count", 0)
    if archive_count > 0:
        bullets.append(
            f"{archive_count} research-idé(er) bør arkiveres/fjernes."
        )

    return bullets


def _count_risk_items(risk_alerts):
    count = 0

    for key in ("near_trailing_stop", "weakening_positions", "large_drawdowns"):
        df = risk_alerts.get(key)
        if df is not None and not df.empty:
            count += len(df)

    other = risk_alerts.get("other_alerts")
    if other is not None and not other.empty:
        count += len(other)

    concentration = risk_alerts.get("concentration_risk") or {}
    count += len(concentration.get("alerts", []))

    return count
