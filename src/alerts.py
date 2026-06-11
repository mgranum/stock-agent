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
ALERT_PENDING_ORDER = "PENDING_ORDER"
ALERT_RESEARCH_ADD = "RESEARCH_ADD"
ALERT_RESEARCH_ARCHIVE = "RESEARCH_ARCHIVE"

SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

_SEVERITY_ORDER = {
    SEVERITY_HIGH: 0,
    SEVERITY_MEDIUM: 1,
    SEVERITY_LOW: 2,
}


def build_alerts(portfolio_report, pending_orders, research_ideas):
    alerts = []
    now = _utc_now()

    alerts.extend(_portfolio_alerts(portfolio_report, now))
    alerts.extend(_near_trailing_stop_alerts(portfolio_report, now))
    alerts.extend(_pending_order_alerts(pending_orders, now))
    alerts.extend(_research_alerts(research_ideas, now))

    return sorted(
        alerts,
        key=lambda alert: _SEVERITY_ORDER.get(alert["severity"], 99),
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
):
    return {
        "alert_type": alert_type,
        "severity": severity,
        "ticker": ticker,
        "title": title,
        "message": message,
        "source": source,
        "created_at": created_at,
    }


def _valid_portfolio_rows(portfolio_report):
    df = valid_portfolio_rows(portfolio_report)
    return [row for _, row in df.iterrows()]


def _portfolio_alerts(portfolio_report, created_at):
    alerts = []

    for row in _valid_portfolio_rows(portfolio_report):
        ticker = row.get("ticker", "")
        action = row.get("portefølje_råd", "")
        recommendation = row.get("anbefaling", "")

        if action == "REDUSER / SELG":
            alerts.append(
                _make_alert(
                    ALERT_PORTFOLIO_SELL,
                    SEVERITY_HIGH,
                    ticker,
                    "Reduser / selg",
                    f"Porteføljeråd: {action} ({recommendation})",
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
                    f"Porteføljeråd: {action} ({recommendation})",
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
                (
                    f"Kurs {round(float(price), 2)} – "
                    f"stop {round(float(trailing), 2)} "
                    f"({round(distance_pct, 1)}% unna)"
                ),
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

        parts = [f"{action} {shares} aksjer"]
        if limit_price:
            parts.append(f"limit {limit_price}")

        note = order.get("note", "")
        if note:
            parts.append(note)

        severity = SEVERITY_HIGH if action == "SELL" else SEVERITY_MEDIUM
        alerts.append(
            _make_alert(
                ALERT_PENDING_ORDER,
                severity,
                ticker,
                "Ventende ordre",
                " · ".join(str(part) for part in parts if part),
                "ORDERS",
                order.get("created_at") or created_at,
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
