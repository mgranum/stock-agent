from datetime import datetime, timezone

import pandas as pd

from src.portfolio import valid_portfolio_rows
from src.research_ideas import (
    STATUS_ARCHIVE,
    STATUS_WATCHLIST,
    research_idea_status,
)

NEAR_TRAILING_STOP_PCT = 3.0

ALERT_PORTFOLIO_SELL = "PORTFOLIO_SELL"
ALERT_PROFIT_PROTECTION = "PROFIT_PROTECTION"
ALERT_NEAR_TRAILING_STOP = "NEAR_TRAILING_STOP"
ALERT_TRAILING_STOP_TRIGGERED = "TRAILING_STOP_TRIGGERED"
ALERT_PENDING_ORDER = "PENDING_ORDER"
ALERT_RESEARCH_ADD = "RESEARCH_ADD"
ALERT_RESEARCH_ARCHIVE = "RESEARCH_ARCHIVE"
ALERT_EARNINGS_TODAY = "EARNINGS_TODAY"
ALERT_EARNINGS_TOMORROW = "EARNINGS_TOMORROW"
ALERT_EARNINGS_WITHIN_7_DAYS = "EARNINGS_WITHIN_7_DAYS"
ALERT_EARNINGS_WITHIN_14_DAYS = "EARNINGS_WITHIN_14_DAYS"

ACTION_REVIEW_SELL = "REVIEW_SELL"
ACTION_PROTECT_PROFIT = "PROTECT_PROFIT"
ACTION_PREPARE_SELL_ORDER = "PREPARE_SELL_ORDER"
ACTION_REVIEW_ORDER = "REVIEW_ORDER"
ACTION_ADD_TO_WATCHLIST = "ADD_TO_WATCHLIST"
ACTION_ARCHIVE_RESEARCH = "ARCHIVE_RESEARCH"
ACTION_PREPARE_EARNINGS = "PREPARE_EARNINGS"

SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

_SEVERITY_ORDER = {
    SEVERITY_HIGH: 0,
    SEVERITY_MEDIUM: 1,
    SEVERITY_LOW: 2,
}

_PRIORITY_BY_SEVERITY = {
    SEVERITY_HIGH: 1,
    SEVERITY_MEDIUM: 2,
    SEVERITY_LOW: 3,
}

_REVIEW_SELL_ALERT_PRIORITY = {
    ALERT_PORTFOLIO_SELL: 0,
    ALERT_TRAILING_STOP_TRIGGERED: 1,
}

_ACTION_LABELS = {
    ACTION_REVIEW_SELL: "Vurder salg",
    ACTION_PROTECT_PROFIT: "Sikre gevinst",
    ACTION_PREPARE_SELL_ORDER: "Følg stop-nivå",
    ACTION_REVIEW_ORDER: "Gjennomgå ordre",
    ACTION_ADD_TO_WATCHLIST: "Legg til watchlist",
    ACTION_ARCHIVE_RESEARCH: "Arkiver idé",
    ACTION_PREPARE_EARNINGS: "Forbered kvartalsrapport",
}

_ALERT_ACTIONS = {
    ALERT_PORTFOLIO_SELL: ACTION_REVIEW_SELL,
    ALERT_PROFIT_PROTECTION: ACTION_PROTECT_PROFIT,
    ALERT_NEAR_TRAILING_STOP: ACTION_PREPARE_SELL_ORDER,
    ALERT_TRAILING_STOP_TRIGGERED: ACTION_REVIEW_SELL,
    ALERT_PENDING_ORDER: ACTION_REVIEW_ORDER,
    ALERT_RESEARCH_ADD: ACTION_ADD_TO_WATCHLIST,
    ALERT_RESEARCH_ARCHIVE: ACTION_ARCHIVE_RESEARCH,
    ALERT_EARNINGS_TODAY: ACTION_PREPARE_EARNINGS,
    ALERT_EARNINGS_TOMORROW: ACTION_PREPARE_EARNINGS,
    ALERT_EARNINGS_WITHIN_7_DAYS: ACTION_PREPARE_EARNINGS,
    ALERT_EARNINGS_WITHIN_14_DAYS: ACTION_PREPARE_EARNINGS,
}

_EARNINGS_ALERT_PRIORITY = {
    ALERT_EARNINGS_TODAY: 1,
    ALERT_EARNINGS_TOMORROW: 1,
    ALERT_EARNINGS_WITHIN_7_DAYS: 2,
    ALERT_EARNINGS_WITHIN_14_DAYS: 3,
}

_EARNINGS_ALERT_TITLES = {
    ALERT_EARNINGS_TODAY: "Kvartalsrapport i dag",
    ALERT_EARNINGS_TOMORROW: "Kvartalsrapport i morgen",
    ALERT_EARNINGS_WITHIN_7_DAYS: "Kvartalsrapport innen 7 dager",
    ALERT_EARNINGS_WITHIN_14_DAYS: "Kvartalsrapport innen 14 dager",
}


def build_alerts(
    portfolio_report,
    pending_orders,
    research_ideas,
    earnings_summary=None,
):
    alerts = []
    now = _utc_now()

    alerts.extend(_portfolio_alerts(portfolio_report, now))
    alerts.extend(_near_trailing_stop_alerts(portfolio_report, now))
    alerts.extend(_trailing_stop_triggered_alerts(portfolio_report, now))
    alerts.extend(_pending_order_alerts(pending_orders, now))
    alerts.extend(_research_alerts(research_ideas, now))
    alerts.extend(_earnings_alerts(earnings_summary, now))

    alerts = _dedupe_alerts(alerts)
    alerts = _apply_alert_conflicts(alerts, pending_orders)

    return sorted(
        alerts,
        key=lambda alert: (
            alert["priority"],
            _SEVERITY_ORDER.get(alert["severity"], 99),
        ),
    )


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _make_alert(
    alert_type,
    severity,
    ticker,
    title,
    message,
    source,
    created_at,
    action=None,
    action_label=None,
    priority=None,
    dedupe_key=None,
):
    action = action or _ALERT_ACTIONS[alert_type]
    return {
        "alert_type": alert_type,
        "severity": severity,
        "ticker": ticker,
        "title": title,
        "message": message,
        "source": source,
        "created_at": created_at,
        "action": action,
        "action_label": action_label or _ACTION_LABELS[action],
        "priority": priority if priority is not None else _PRIORITY_BY_SEVERITY[severity],
        "dedupe_key": dedupe_key or f"{alert_type}:{ticker}",
    }


def _dedupe_alerts(alerts):
    best_by_key = {}

    for alert in alerts:
        key = alert["dedupe_key"]
        existing = best_by_key.get(key)

        if existing is None or alert["priority"] < existing["priority"]:
            best_by_key[key] = alert

    return list(best_by_key.values())


def _pending_sell_tickers(pending_orders):
    tickers = set()

    for order in pending_orders or []:
        if str(order.get("action", "")).upper() != "SELL":
            continue

        ticker = str(order.get("ticker", "")).strip().upper()
        if ticker:
            tickers.add(ticker)

    return tickers


def _apply_alert_conflicts(alerts, pending_orders):
    pending_sells = _pending_sell_tickers(pending_orders)
    profit_protection_tickers = {
        alert["ticker"]
        for alert in alerts
        if alert["alert_type"] == ALERT_PROFIT_PROTECTION
    }

    filtered = []
    for alert in alerts:
        ticker = alert.get("ticker", "")
        alert_type = alert["alert_type"]

        if (
            alert_type == ALERT_TRAILING_STOP_TRIGGERED
            and ticker in profit_protection_tickers
        ):
            continue

        if (
            alert_type == ALERT_NEAR_TRAILING_STOP
            and str(ticker).strip().upper() in pending_sells
        ):
            continue

        filtered.append(alert)

    return _merge_review_sell_alerts(filtered)


def _merge_review_sell_alerts(alerts):
    merged_sell = {}
    other = []

    for alert in alerts:
        if alert.get("action") != ACTION_REVIEW_SELL:
            other.append(alert)
            continue

        ticker = alert["ticker"]
        existing = merged_sell.get(ticker)
        if existing is None:
            merged_sell[ticker] = alert
            continue

        existing_rank = _REVIEW_SELL_ALERT_PRIORITY.get(
            existing["alert_type"],
            99,
        )
        new_rank = _REVIEW_SELL_ALERT_PRIORITY.get(alert["alert_type"], 99)
        if new_rank < existing_rank:
            merged_sell[ticker] = alert

    return other + list(merged_sell.values())


def _valid_portfolio_rows(portfolio_report):
    df = valid_portfolio_rows(portfolio_report)
    return [row for _, row in df.iterrows()]


def _format_signed_pct(value):
    if value is None or pd.isna(value):
        return None

    rounded = round(float(value), 1)
    sign = "+" if rounded > 0 else ""
    return f"{sign}{rounded} %"


def _reason_fragment(row):
    begrunnelse = row.get("begrunnelse")
    if begrunnelse is not None and pd.notna(begrunnelse) and str(begrunnelse).strip():
        return str(begrunnelse).strip()

    trend_regime = row.get("trend_regime")
    if trend_regime is not None and pd.notna(trend_regime):
        return str(trend_regime).strip()

    return None


def _portfolio_sell_message(row):
    parts = []

    reason = _reason_fragment(row)
    if reason:
        parts.append(reason)

    gain = _format_signed_pct(row.get("unrealized_gain_pct"))
    if gain:
        parts.append(f"gevinst/tap {gain}")

    score = row.get("score")
    if score is not None and not pd.isna(score):
        parts.append(f"score {int(score)}")

    recommendation = row.get("anbefaling")
    if recommendation is not None and pd.notna(recommendation):
        parts.append(str(recommendation).strip())

    body = " · ".join(parts) if parts else str(row.get("portefølje_råd", "REDUSER / SELG"))
    return f"{body}. Vurder reduksjon eller exit."


def _profit_protection_message(row):
    parts = []

    reason = _reason_fragment(row)
    if reason:
        parts.append(reason)

    gain = _format_signed_pct(row.get("unrealized_gain_pct"))
    if gain:
        parts.append(f"gevinst {gain}")

    recommendation = row.get("anbefaling")
    if recommendation is not None and pd.notna(recommendation):
        parts.append(str(recommendation).strip())

    body = " · ".join(parts) if parts else "Trailing stop trigget, trend OK"
    return f"{body}. Vurder delvis salg eller strammere stop."


def _near_trailing_stop_message(row, distance_pct):
    price = row.get("current_price")
    trailing = row.get("trailing_stop_loss")
    return (
        f"Dagens kurs er {float(price):.2f}. "
        f"Stop loss er {float(trailing):.2f}, "
        f"{round(distance_pct, 1)} % under dagens kurs. "
        "Behold posisjonen, men vær klar til å handle hvis stop brytes."
    )


def _trailing_stop_triggered_message(row):
    price = row.get("current_price")
    trailing = row.get("trailing_stop_loss")

    if (
        price is not None
        and not pd.isna(price)
        and trailing is not None
        and not pd.isna(trailing)
    ):
        message = (
            f"Stop {float(trailing):.2f} brutt "
            f"(kurs {float(price):.2f})."
        )
    else:
        message = "Trailing stop er brutt."

    gain = _format_signed_pct(row.get("unrealized_gain_pct"))
    if gain:
        message += f" Posisjon {gain}."

    return f"{message} Vurder salg eller reduksjon."


def _pending_order_message(order):
    action = str(order.get("action", "")).upper()
    shares = order.get("shares")
    limit_price = order.get("limit_price")

    detail_parts = [f"{shares} aksjer"]
    if limit_price:
        detail_parts.append(f"@ {limit_price}")
    detail = " ".join(str(part) for part in detail_parts if part)

    if action == "SELL":
        return (
            f"Salgsordre venter: {detail}. "
            "Utfør, juster limit, eller kanseller."
        )

    if action == "BUY":
        return (
            f"Kjøpsordre venter: {detail}. "
            "Utfør, juster limit, eller kanseller."
        )

    return detail


def _portfolio_alerts(portfolio_report, created_at):
    alerts = []

    for row in _valid_portfolio_rows(portfolio_report):
        ticker = row.get("ticker", "")
        action = row.get("portefølje_råd", "")

        if action == "REDUSER / SELG":
            alerts.append(
                _make_alert(
                    ALERT_PORTFOLIO_SELL,
                    SEVERITY_HIGH,
                    ticker,
                    "Reduser / selg",
                    _portfolio_sell_message(row),
                    "PORTFOLIO",
                    created_at,
                )
            )
        elif action == "VURDER GEVINSTSIKRING":
            alerts.append(
                _make_alert(
                    ALERT_PROFIT_PROTECTION,
                    SEVERITY_MEDIUM,
                    ticker,
                    "Vurder gevinstsikring",
                    _profit_protection_message(row),
                    "PORTFOLIO",
                    created_at,
                )
            )

    return alerts


def _near_trailing_stop_alerts(portfolio_report, created_at):
    alerts = []

    for row in _valid_portfolio_rows(portfolio_report):
        price = row.get("current_price")
        trailing = row.get("trailing_stop_loss")

        if price is None or trailing is None or pd.isna(price) or pd.isna(trailing):
            continue

        if price <= trailing:
            continue

        distance_pct = (price - trailing) / price * 100
        if distance_pct > NEAR_TRAILING_STOP_PCT:
            continue

        ticker = row.get("ticker", "")
        alerts.append(
            _make_alert(
                ALERT_NEAR_TRAILING_STOP,
                SEVERITY_HIGH,
                ticker,
                "Nær trailing stop",
                _near_trailing_stop_message(row, distance_pct),
                "PORTFOLIO",
                created_at,
            )
        )

    return alerts


def _trailing_stop_triggered_alerts(portfolio_report, created_at):
    alerts = []

    for row in _valid_portfolio_rows(portfolio_report):
        if row.get("trailing_stop_triggered") is not True:
            continue

        ticker = row.get("ticker", "")
        alerts.append(
            _make_alert(
                ALERT_TRAILING_STOP_TRIGGERED,
                SEVERITY_HIGH,
                ticker,
                "Trailing stop trigget",
                _trailing_stop_triggered_message(row),
                "PORTFOLIO",
                created_at,
            )
        )

    return alerts


def _pending_order_alerts(pending_orders, created_at):
    alerts = []

    for order in pending_orders or []:
        ticker = order.get("ticker", "")
        action = str(order.get("action", "")).upper()
        shares = order.get("shares")
        limit_price = order.get("limit_price")

        severity = SEVERITY_HIGH if action == "SELL" else SEVERITY_MEDIUM
        order_key = order.get("id") or f"{action}:{shares}:{limit_price or ''}"
        alerts.append(
            _make_alert(
                ALERT_PENDING_ORDER,
                severity,
                ticker,
                "Ventende ordre",
                _pending_order_message(order),
                "ORDERS",
                order.get("created_at") or created_at,
                dedupe_key=f"{ALERT_PENDING_ORDER}:{ticker}:{order_key}",
            )
        )

    return alerts


def _research_alerts(research_ideas, created_at):
    alerts = []

    for idea in research_ideas or []:
        ticker = idea.get("ticker", "")
        status = idea.get("status") or research_idea_status(idea)
        score = idea.get("score")
        recommendation = idea.get("recommendation") or ""

        if status == STATUS_WATCHLIST:
            score_text = f" (score {int(score)})" if score is not None else ""
            alerts.append(
                _make_alert(
                    ALERT_RESEARCH_ADD,
                    SEVERITY_LOW,
                    ticker,
                    "Legg til watchlist",
                    f"Research-idé bør vurderes for watchlist{score_text}",
                    "RESEARCH",
                    idea.get("last_updated_at")
                    or idea.get("saved_at")
                    or created_at,
                )
            )
        elif status == STATUS_ARCHIVE:
            score_text = f" (score {int(score)})" if score is not None else ""
            message = f"Research-idé bør arkiveres{score_text}"
            if recommendation:
                message += f" ({recommendation})"
            alerts.append(
                _make_alert(
                    ALERT_RESEARCH_ARCHIVE,
                    SEVERITY_LOW,
                    ticker,
                    "Arkiver research-idé",
                    message,
                    "RESEARCH",
                    idea.get("last_updated_at")
                    or idea.get("saved_at")
                    or created_at,
                )
            )

    return alerts


def _earnings_alert_type(days_until):
    if days_until == 0:
        return ALERT_EARNINGS_TODAY
    if days_until == 1:
        return ALERT_EARNINGS_TOMORROW
    if 2 <= days_until <= 7:
        return ALERT_EARNINGS_WITHIN_7_DAYS
    if 8 <= days_until <= 14:
        return ALERT_EARNINGS_WITHIN_14_DAYS
    return None


def _earnings_severity(alert_type, in_portfolio):
    if alert_type in (ALERT_EARNINGS_TODAY, ALERT_EARNINGS_TOMORROW):
        return SEVERITY_HIGH if in_portfolio else SEVERITY_MEDIUM

    if alert_type == ALERT_EARNINGS_WITHIN_7_DAYS:
        return SEVERITY_MEDIUM if in_portfolio else SEVERITY_LOW

    return SEVERITY_LOW


def _earnings_message(days_until):
    if days_until == 0:
        return "Kvartalsrapport i dag."
    if days_until == 1:
        return "Kvartalsrapport i morgen."
    return f"Kvartalsrapport om {days_until} dager."


def _earnings_alerts(earnings_summary, created_at):
    alerts = []

    for item in (earnings_summary or {}).get("upcoming_14_days") or []:
        days_until = item.get("days_until")
        if days_until is None:
            continue

        alert_type = _earnings_alert_type(days_until)
        if alert_type is None:
            continue

        ticker = item.get("ticker", "")
        in_portfolio = bool(item.get("in_portfolio"))
        alerts.append(
            _make_alert(
                alert_type,
                _earnings_severity(alert_type, in_portfolio),
                ticker,
                _EARNINGS_ALERT_TITLES[alert_type],
                _earnings_message(days_until),
                "EARNINGS",
                created_at,
                action=ACTION_PREPARE_EARNINGS,
                action_label=_ACTION_LABELS[ACTION_PREPARE_EARNINGS],
                priority=_EARNINGS_ALERT_PRIORITY[alert_type],
                dedupe_key=f"EARNINGS:{ticker}",
            )
        )

    return alerts
