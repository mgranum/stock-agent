from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from src.alerts import (
    ALERT_NEAR_TRAILING_STOP,
    ALERT_PENDING_ORDER,
    ALERT_TRAILING_STOP_TRIGGERED,
)
from src.company_names import get_company_name
from src.portfolio import valid_portfolio_rows
from src.sentiment import (
    SENTIMENT_DISPLAY_LABELS,
    SENTIMENT_NEGATIVE,
)
from src.watchlist_advisor import (
    ACTION_AVVENT_EARNINGS,
    ACTION_VURDER_KJOP,
)

BRIEFING_ITEM_LIMIT = 3
STRONG_CANDIDATE_SCORE = 80
EARNINGS_CRITICAL_DAYS = 3
STRONG_NEGATIVE_SENTIMENT_SCORE = -0.5

_CRITICAL_PORTFOLIO_ACTIONS = {
    "REDUSER / SELG",
    "VURDER REDUKSJON",
}

_TRAILING_STOP_ALERT_TYPES = {
    ALERT_NEAR_TRAILING_STOP,
    ALERT_TRAILING_STOP_TRIGGERED,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_int(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_ticker(ticker: str) -> str:
    normalized = str(ticker or "").strip().upper()
    if not normalized:
        return ""
    if normalized.endswith(".OL"):
        return normalized[:-3]
    return normalized


def _briefing_item(ticker, text, *, category=None, rule=None, **extra):
    item = {
        "ticker": _display_ticker(ticker),
        "text": text,
    }
    if category is not None:
        item["category"] = category
    if rule is not None:
        item["rule"] = rule
    item.update(extra)
    return item


def _item_key(item) -> tuple:
    return (
        item.get("category", ""),
        item.get("ticker", ""),
        item.get("text", ""),
    )


def _dedupe_items(items):
    seen = set()
    deduped = []
    for item in items:
        key = _item_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _earnings_briefing_text(item) -> str:
    days_until = _safe_int(item.get("days_until"))
    ticker = str(item.get("ticker") or "").strip().upper()
    name = get_company_name(ticker) or _display_ticker(ticker)

    if days_until == 0:
        timing = "i dag"
    elif days_until == 1:
        timing = "i morgen"
    else:
        timing = f"om {days_until} dager"

    return f"{name} rapporterer {timing}"


def _is_negative_analyst_change(change) -> bool:
    endring = str(change.get("Endring") or "").lower()
    if " ned" in endring or endring.startswith("kursmål ned"):
        return True

    til = str(change.get("Til") or "").lower()
    if change.get("change_type") == "recommendation_key" and (
        "selg" in til or "underperform" in til
    ):
        return True

    return False


def _is_major_analyst_change(change) -> bool:
    return bool(str(change.get("Endring") or "").strip())


def _is_strong_negative_sentiment(item) -> bool:
    if item.get("sentiment") != SENTIMENT_NEGATIVE:
        return False

    score = _safe_float(item.get("score"))
    return score is not None and score <= STRONG_NEGATIVE_SENTIMENT_SCORE


def _critical_from_alerts(alerts):
    items = []
    for alert in alerts or []:
        alert_type = alert.get("alert_type")
        ticker = alert.get("ticker", "")
        message = str(alert.get("message") or alert.get("title") or "").strip()

        if alert_type in _TRAILING_STOP_ALERT_TYPES:
            title = str(alert.get("title") or "Trailing stop").strip()
            text = f"{_display_ticker(ticker)}: {title}"
            if message and message not in text:
                text = f"{text} – {message}"
            items.append(
                _briefing_item(
                    ticker,
                    text,
                    category="trailing_stop",
                    rule="trailing_stop",
                )
            )
            continue

        if alert_type != ALERT_PENDING_ORDER:
            continue

        if "salgsordre" not in message.lower():
            continue

        items.append(
            _briefing_item(
                ticker,
                message,
                category="sell",
                rule="sell_order",
            )
        )

    return items


def _critical_from_portfolio(portfolio_report):
    items = []
    df = valid_portfolio_rows(portfolio_report)
    if df.empty:
        return items

    for _, row in df.iterrows():
        action = str(row.get("portefølje_råd") or "").strip()
        if action not in _CRITICAL_PORTFOLIO_ACTIONS:
            continue

        ticker = row.get("ticker", "")
        label = "Reduser / selg" if action == "REDUSER / SELG" else "Vurder reduksjon"
        items.append(
            _briefing_item(
                ticker,
                f"{_display_ticker(ticker)}: {label}",
                category="reduser",
                rule="portfolio_reduser",
            )
        )

    return items


def _critical_from_earnings(earnings_summary, limit_days=EARNINGS_CRITICAL_DAYS):
    items = []
    for item in (earnings_summary or {}).get("items") or []:
        days_until = _safe_int(item.get("days_until"))
        if days_until is None or days_until < 0 or days_until > limit_days:
            continue

        ticker = item.get("ticker", "")
        items.append(
            _briefing_item(
                ticker,
                _earnings_briefing_text(item),
                category="earnings",
                rule="earnings_critical",
                days_until=days_until,
                in_portfolio=bool(item.get("in_portfolio")),
            )
        )

    items.sort(
        key=lambda entry: (
            entry.get("days_until", 99),
            0 if entry.get("in_portfolio") else 1,
            entry.get("ticker", ""),
        ),
    )
    return items


def _critical_from_analyst(analyst_summary):
    items = []
    for change in (analyst_summary or {}).get("material_changes") or []:
        if not _is_negative_analyst_change(change):
            continue

        ticker = change.get("ticker", "")
        endring = str(change.get("Endring") or "").strip()
        if not ticker or not endring:
            continue

        items.append(
            _briefing_item(
                ticker,
                f"{_display_ticker(ticker)}: {endring}",
                category="analyst",
                rule="analyst_negative",
                change_type=change.get("change_type"),
            )
        )

    return items


def _important_from_watchlist(watchlist_advisor_output):
    items = []
    for item in (watchlist_advisor_output or {}).get("items") or []:
        action = item.get("watchlist_action")
        if action != ACTION_AVVENT_EARNINGS:
            continue

        ticker = item.get("ticker", "")
        headline = str(item.get("headline") or "").strip()
        if not ticker or not headline:
            continue

        items.append(
            _briefing_item(
                ticker,
                f"{_display_ticker(ticker)}: {headline[0].lower()}{headline[1:]}",
                category="watchlist",
                rule="avvent_earnings",
                watchlist_action=action,
            )
        )

    return items


def _important_from_sentiment(sentiment_summary):
    items = []
    candidates = [
        item
        for item in (sentiment_summary or {}).get("items") or []
        if _is_strong_negative_sentiment(item)
    ]
    candidates.sort(
        key=lambda item: (
            0 if item.get("in_portfolio") else 1,
            _safe_float(item.get("score")) or 0.0,
            item.get("ticker", ""),
        ),
    )

    for item in candidates:
        ticker = item.get("ticker", "")
        label = SENTIMENT_DISPLAY_LABELS.get(
            item.get("sentiment"),
            item.get("sentiment"),
        )
        score = _safe_float(item.get("score"))
        score_text = f" ({score:.2f})" if score is not None else ""
        items.append(
            _briefing_item(
                ticker,
                f"{_display_ticker(ticker)}: Sterk negativ nyhetstone{score_text} – {label}",
                category="sentiment",
                rule="strong_negative_sentiment",
                sentiment=item.get("sentiment"),
            )
        )

    return items


def _important_from_analyst(analyst_summary):
    items = []
    for change in (analyst_summary or {}).get("material_changes") or []:
        if not _is_major_analyst_change(change) or _is_negative_analyst_change(change):
            continue

        ticker = change.get("ticker", "")
        endring = str(change.get("Endring") or "").strip()
        if not ticker or not endring:
            continue

        items.append(
            _briefing_item(
                ticker,
                f"{_display_ticker(ticker)}: {endring}",
                category="analyst",
                rule="analyst_major",
                change_type=change.get("change_type"),
            )
        )

    return items


def _watchlist_briefing_items(watchlist_advisor_output, limit=BRIEFING_ITEM_LIMIT):
    items = list((watchlist_advisor_output or {}).get("items") or [])
    items.sort(
        key=lambda item: (
            item.get("priority", 99),
            item.get("ticker", ""),
        ),
    )

    briefing_items = []
    for item in items[:limit]:
        ticker = item.get("ticker", "")
        headline = str(item.get("headline") or "").strip()
        if not ticker or not headline:
            continue

        briefing_items.append(
            _briefing_item(
                ticker,
                f"{_display_ticker(ticker)}: {headline[0].lower()}{headline[1:]}",
                category="watchlist",
                watchlist_action=item.get("watchlist_action"),
                priority=item.get("priority"),
            )
        )

    return briefing_items


def _candidate_briefing_items(opportunity_advisor, limit=BRIEFING_ITEM_LIMIT):
    items = list((opportunity_advisor or {}).get("items") or [])
    items.sort(
        key=lambda item: (
            item.get("priority", 99),
            item.get("ticker", ""),
        ),
    )

    briefing_items = []
    for item in items[:limit]:
        ticker = item.get("ticker", "")
        headline = str(item.get("headline") or "").strip()
        if not ticker:
            continue

        if headline:
            text = f"{_display_ticker(ticker)}: {headline}"
        else:
            text = _display_ticker(ticker)

        briefing_items.append(
            _briefing_item(
                ticker,
                text,
                category="candidate",
                headline=headline,
                priority=item.get("priority"),
            )
        )

    return briefing_items


def _has_earnings_today(critical_items) -> bool:
    return any(item.get("days_until") == 0 for item in critical_items)


def _has_earnings_within_days(critical_items, days=EARNINGS_CRITICAL_DAYS) -> bool:
    return any(
        item.get("category") == "earnings"
        and _safe_int(item.get("days_until")) is not None
        and _safe_int(item.get("days_until")) <= days
        for item in critical_items
    )


def _has_strong_candidates(candidate_items) -> bool:
    if not candidate_items:
        return False

    for item in candidate_items:
        priority = _safe_int(item.get("priority"))
        if priority is not None and priority <= 2:
            return True

    return len(candidate_items) >= 2


def _build_headline(critical_items, important_items, candidate_items):
    has_critical = bool(critical_items)
    has_important = bool(important_items)
    earnings_today = _has_earnings_today(critical_items)
    earnings_soon = _has_earnings_within_days(critical_items)
    strong_candidates = _has_strong_candidates(candidate_items)

    if strong_candidates and earnings_soon and not earnings_today:
        return "Flere sterke kandidater, men rapporteringsrisiko nærmer seg."

    if earnings_today or (
        earnings_soon
        and not any(
            item.get("category") not in {"earnings"}
            for item in critical_items
        )
    ):
        return "Earnings-fokus i dag."

    if not has_critical and not has_important:
        return "Rolig dag – ingen kritiske hendelser."

    return "Handlingspunkter krever oppmerksomhet i dag."


def _summary_briefing_items(
    critical_items,
    important_items,
    candidate_items,
):
    summary_items = []

    if _has_earnings_today(critical_items):
        summary_items.append(
            {
                "text": "Kvartalsrapporter krever oppfølging i dag",
                "rule": "earnings_today",
            }
        )

    portfolio_critical = [
        item
        for item in critical_items
        if item.get("category") in {"reduser", "sell", "trailing_stop"}
    ]
    if portfolio_critical:
        summary_items.append(
            {
                "text": "Porteføljen har signaler som krever risikostyring",
                "rule": "portfolio_risk",
            }
        )

    if _has_strong_candidates(candidate_items):
        summary_items.append(
            {
                "text": "Markedet tilbyr flere interessante kandidater",
                "rule": "strong_candidates",
            }
        )

    if important_items and not summary_items:
        summary_items.append(
            {
                "text": "Det finnes støttende signaler å følge med på",
                "rule": "supporting_signals",
            }
        )

    return summary_items


def build_daily_briefing(context, today=None):
    context = context or {}
    today = today or date.today()

    portfolio_report = context.get("portfolio_report")
    alerts = context.get("alerts")
    earnings_summary = context.get("earnings_summary")
    analyst_summary = context.get("analyst_summary")
    sentiment_summary = context.get("sentiment_summary")
    watchlist_advisor_output = context.get("watchlist_advisor_output")
    opportunity_advisor = context.get("opportunity_advisor")

    critical_items = _dedupe_items(
        _critical_from_alerts(alerts)
        + _critical_from_portfolio(portfolio_report)
        + _critical_from_earnings(earnings_summary)
        + _critical_from_analyst(analyst_summary)
    )
    important_items = _dedupe_items(
        _important_from_watchlist(watchlist_advisor_output)
        + _important_from_sentiment(sentiment_summary)
        + _important_from_analyst(analyst_summary)
    )
    watchlist_items = _watchlist_briefing_items(watchlist_advisor_output)
    candidate_items = _candidate_briefing_items(opportunity_advisor)
    summary = _summary_briefing_items(
        critical_items,
        important_items,
        candidate_items,
    )
    headline = _build_headline(critical_items, important_items, candidate_items)

    return {
        "generated_at": _utc_now_iso(),
        "date": today.isoformat(),
        "headline": headline,
        "critical_items": critical_items,
        "important_items": important_items,
        "watchlist_items": watchlist_items,
        "candidate_items": candidate_items,
        "summary": summary,
    }


_SECTION_LABELS = {
    "critical_items": "Kritisk",
    "important_items": "Viktig",
    "watchlist_items": "Watchlist",
    "candidate_items": "Kandidater",
    "summary": "Oppsummering",
}


def resolve_daily_briefing(context):
    context = context or {}
    briefing = context.get("daily_briefing")
    if briefing:
        return briefing
    return build_daily_briefing(context)


def format_daily_briefing(briefing) -> str:
    briefing = briefing or {}
    lines = ["Dagens briefing", ""]

    headline = str(briefing.get("headline") or "").strip()
    if headline:
        lines.append(headline)
        lines.append("")

    has_sections = False
    for section_key, section_label in _SECTION_LABELS.items():
        items = briefing.get(section_key) or []
        if not items:
            continue

        has_sections = True
        lines.append(section_label)
        for item in items:
            text = item.get("text") if isinstance(item, dict) else str(item)
            if text:
                lines.append(f"• {text}")
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    if not headline and not has_sections:
        return "Dagens briefing"

    return "\n".join(lines)
