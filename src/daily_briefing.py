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

CRITICAL_ITEM_LIMIT = 3
IMPORTANT_ITEM_LIMIT = 2
TOTAL_CONCRETE_ITEM_LIMIT = 5
WATCHLIST_ITEM_LIMIT = 2
CANDIDATE_ITEM_LIMIT = 2
CHANGE_ITEM_LIMIT = 3
EARNINGS_OWNED_CRITICAL_DAYS = 1
EARNINGS_AVVENT_DAYS = 3
STRONG_NEGATIVE_SENTIMENT_SCORE = -0.5
SUMMARY_ITEM_LIMIT = 2

_CRITICAL_PORTFOLIO_ACTIONS = {
    "REDUSER / SELG",
    "VURDER REDUKSJON",
}

_BRIEFING_WATCHLIST_ACTIONS = {
    ACTION_VURDER_KJOP,
    ACTION_AVVENT_EARNINGS,
}

_PRIORITY_SELL_ORDER = 1
_PRIORITY_TRAILING_STOP_TRIGGERED = 2
_PRIORITY_REDUSER = 3
_PRIORITY_VURDER_REDUKTION = 4
_PRIORITY_EARNINGS_OWNED = 5
_PRIORITY_ANALYST_NEGATIVE = 6
_PRIORITY_NEAR_TRAILING_STOP = 7
_PRIORITY_STRONG_NEGATIVE_SENTIMENT = 8
_PRIORITY_WATCHLIST_ACTION = 9
_PRIORITY_CANDIDATE = 10
_PRIORITY_ANALYST_MAJOR = 11

_CHANGE_PRIORITY_RECOMMENDATION = 1
_CHANGE_PRIORITY_SCORE = 2
_CHANGE_PRIORITY_NEW_BUY = 3

_BUY_RECOMMENDATION = "KJØP / ØK"
_SELL_RECOMMENDATION = "UNNGÅ / SELG"


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


def _owned_ticker_set(portfolio_report) -> set[str]:
    df = valid_portfolio_rows(portfolio_report)
    if df.empty:
        return set()
    return {_display_ticker(ticker) for ticker in df["ticker"]}


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


def _item_priority(item) -> int:
    rule = item.get("rule")
    if rule == "sell_order":
        return _PRIORITY_SELL_ORDER
    if rule == "trailing_stop_triggered":
        return _PRIORITY_TRAILING_STOP_TRIGGERED
    if rule == "portfolio_reduser":
        if item.get("portfolio_action") == "REDUSER / SELG":
            return _PRIORITY_REDUSER
        return _PRIORITY_VURDER_REDUKTION
    if rule == "earnings_critical":
        return _PRIORITY_EARNINGS_OWNED
    if rule == "analyst_negative":
        return _PRIORITY_ANALYST_NEGATIVE
    if rule == "trailing_stop_near":
        return _PRIORITY_NEAR_TRAILING_STOP
    if rule == "strong_negative_sentiment":
        return _PRIORITY_STRONG_NEGATIVE_SENTIMENT
    if rule in {"avvent_earnings", "vurder_kjop"}:
        return _PRIORITY_WATCHLIST_ACTION
    if rule == "candidate":
        return _PRIORITY_CANDIDATE
    if rule == "analyst_major":
        return _PRIORITY_ANALYST_MAJOR
    return 99


def _item_sort_key(item) -> tuple:
    days = _safe_int(item.get("days_until"))
    return (
        _item_priority(item),
        days if days is not None else 99,
        item.get("ticker", ""),
    )


def _sort_section_items(section_key, items):
    if section_key == "watchlist_items":
        return sorted(
            items,
            key=lambda item: (
                item.get("priority", 99),
                item.get("ticker", ""),
            ),
        )
    if section_key == "candidate_items":
        return sorted(
            items,
            key=lambda item: (
                item.get("priority", 99),
                item.get("ticker", ""),
            ),
        )
    return sorted(items, key=_item_sort_key)


def _dedupe_items_by_ticker(items):
    best_by_ticker: dict[str, dict] = {}
    for item in items:
        ticker = item.get("ticker", "")
        if not ticker:
            continue
        existing = best_by_ticker.get(ticker)
        if existing is None or _item_sort_key(item) < _item_sort_key(existing):
            best_by_ticker[ticker] = item
    return sorted(best_by_ticker.values(), key=_item_sort_key)


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


def _earnings_days_by_ticker(earnings_summary) -> dict[str, int]:
    days_by_ticker = {}
    for item in (earnings_summary or {}).get("items") or []:
        ticker = _display_ticker(item.get("ticker", ""))
        days_until = _safe_int(item.get("days_until"))
        if ticker and days_until is not None:
            days_by_ticker[ticker] = days_until
    return days_by_ticker


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

        if alert_type == ALERT_TRAILING_STOP_TRIGGERED:
            title = str(alert.get("title") or "Trailing stop trigget").strip()
            text = f"{_display_ticker(ticker)}: {title}"
            if message and message not in text:
                text = f"{text} – {message}"
            items.append(
                _briefing_item(
                    ticker,
                    text,
                    category="trailing_stop",
                    rule="trailing_stop_triggered",
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


def _important_from_alerts(alerts):
    items = []
    for alert in alerts or []:
        alert_type = alert.get("alert_type")
        if alert_type != ALERT_NEAR_TRAILING_STOP:
            continue

        ticker = alert.get("ticker", "")
        message = str(alert.get("message") or alert.get("title") or "").strip()
        title = str(alert.get("title") or "Nær trailing stop").strip()
        text = f"{_display_ticker(ticker)}: {title}"
        if message and message not in text:
            text = f"{text} – {message}"
        items.append(
            _briefing_item(
                ticker,
                text,
                category="trailing_stop",
                rule="trailing_stop_near",
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
                portfolio_action=action,
            )
        )

    return items


def _critical_from_earnings(earnings_summary, owned_tickers):
    items = []
    for item in (earnings_summary or {}).get("items") or []:
        days_until = _safe_int(item.get("days_until"))
        if days_until is None or days_until < 0 or days_until > EARNINGS_OWNED_CRITICAL_DAYS:
            continue
        if not item.get("in_portfolio"):
            continue

        ticker = item.get("ticker", "")
        if _display_ticker(ticker) not in owned_tickers:
            continue

        items.append(
            _briefing_item(
                ticker,
                _earnings_briefing_text(item),
                category="earnings",
                rule="earnings_critical",
                days_until=days_until,
                in_portfolio=True,
            )
        )

    items.sort(
        key=lambda entry: (
            entry.get("days_until", 99),
            entry.get("ticker", ""),
        ),
    )
    return items


def _critical_from_analyst(analyst_summary, owned_tickers):
    items = []
    for change in (analyst_summary or {}).get("material_changes") or []:
        if not _is_negative_analyst_change(change):
            continue

        ticker = change.get("ticker", "")
        endring = str(change.get("Endring") or "").strip()
        if not ticker or not endring:
            continue
        if _display_ticker(ticker) not in owned_tickers:
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


def _watchlist_headline_text(ticker, headline) -> str:
    headline = str(headline or "").strip()
    if not headline:
        return _display_ticker(ticker)
    return f"{_display_ticker(ticker)}: {headline[0].lower()}{headline[1:]}"


def _watchlist_briefing_items(
    watchlist_advisor_output,
    earnings_summary=None,
    *,
    only_avvent_within_days=False,
    limit=WATCHLIST_ITEM_LIMIT,
):
    earnings_days = _earnings_days_by_ticker(earnings_summary)
    items = list((watchlist_advisor_output or {}).get("items") or [])
    items.sort(
        key=lambda item: (
            item.get("priority", 99),
            item.get("ticker", ""),
        ),
    )

    briefing_items = []
    for item in items:
        action = item.get("watchlist_action")
        if action not in _BRIEFING_WATCHLIST_ACTIONS:
            continue

        ticker = item.get("ticker", "")
        headline = str(item.get("headline") or "").strip()
        if not ticker or not headline:
            continue

        display_ticker = _display_ticker(ticker)
        if only_avvent_within_days:
            if action != ACTION_AVVENT_EARNINGS:
                continue
            days_until = earnings_days.get(display_ticker)
            if days_until is None or days_until > EARNINGS_AVVENT_DAYS:
                continue

        rule = (
            "avvent_earnings"
            if action == ACTION_AVVENT_EARNINGS
            else "vurder_kjop"
        )
        briefing_items.append(
            _briefing_item(
                ticker,
                _watchlist_headline_text(ticker, headline),
                category="watchlist",
                rule=rule,
                watchlist_action=action,
                priority=item.get("priority"),
                days_until=earnings_days.get(display_ticker),
            )
        )

        if len(briefing_items) >= limit:
            break

    return briefing_items


def _candidate_briefing_items(opportunity_advisor, limit=CANDIDATE_ITEM_LIMIT):
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
                rule="candidate",
                headline=headline,
                priority=item.get("priority"),
            )
        )

    return briefing_items


def _partition_items(items):
    critical = []
    important = []
    watchlist = []
    candidates = []

    for item in items:
        rule = item.get("rule")
        if rule in {
            "sell_order",
            "trailing_stop_triggered",
            "portfolio_reduser",
            "earnings_critical",
            "analyst_negative",
        }:
            critical.append(item)
        elif rule in {
            "trailing_stop_near",
            "strong_negative_sentiment",
            "analyst_major",
        }:
            important.append(item)
        elif rule in {"avvent_earnings", "vurder_kjop"}:
            watchlist.append(item)
        elif rule == "candidate":
            candidates.append(item)

    return {
        "critical_items": critical,
        "important_items": important,
        "watchlist_items": watchlist,
        "candidate_items": candidates,
    }


def _apply_section_caps(sections):
    return {
        "critical_items": sections["critical_items"][:CRITICAL_ITEM_LIMIT],
        "important_items": sections["important_items"][:IMPORTANT_ITEM_LIMIT],
        "watchlist_items": sections["watchlist_items"][:WATCHLIST_ITEM_LIMIT],
        "candidate_items": sections["candidate_items"][:CANDIDATE_ITEM_LIMIT],
    }


def _apply_total_concrete_cap(sections, limit=TOTAL_CONCRETE_ITEM_LIMIT):
    combined = []
    for section_key in (
        "critical_items",
        "important_items",
        "watchlist_items",
        "candidate_items",
    ):
        for item in sections[section_key]:
            combined.append((item, section_key))

    combined.sort(key=lambda entry: _item_sort_key(entry[0]))
    kept = combined[:limit]
    kept_keys = {(section_key, item.get("ticker")) for item, section_key in kept}

    trimmed = {
        section_key: []
        for section_key in (
            "critical_items",
            "important_items",
            "watchlist_items",
            "candidate_items",
        )
    }
    for item, section_key in combined:
        if (section_key, item.get("ticker")) in kept_keys:
            trimmed[section_key].append(item)

    return trimmed


def _apply_watchlist_and_candidate_visibility(sections, has_critical):
    watchlist_items = list(sections["watchlist_items"])
    candidate_items = list(sections["candidate_items"])

    if has_critical:
        candidate_items = []
        watchlist_items = [
            item
            for item in watchlist_items
            if item.get("rule") == "avvent_earnings"
            and _safe_int(item.get("days_until")) is not None
            and _safe_int(item.get("days_until")) <= EARNINGS_AVVENT_DAYS
        ]

    return {
        **sections,
        "watchlist_items": watchlist_items,
        "candidate_items": candidate_items,
    }


def _has_earnings_today(items) -> bool:
    return any(
        item.get("rule") == "earnings_critical"
        and _safe_int(item.get("days_until")) == 0
        for item in items
    )


def _has_earnings_within_days(items, days=EARNINGS_AVVENT_DAYS) -> bool:
    return any(
        item.get("rule") == "earnings_critical"
        and _safe_int(item.get("days_until")) is not None
        and _safe_int(item.get("days_until")) <= days
        for item in items
    )


def _has_strong_candidates(candidate_items) -> bool:
    if not candidate_items:
        return False

    for item in candidate_items:
        priority = _safe_int(item.get("priority"))
        if priority is not None and priority <= 2:
            return True

    return len(candidate_items) >= 2


def _change_item_sort_key(item) -> tuple:
    return (
        item.get("change_priority", 99),
        item.get("ticker", ""),
    )


def _dedupe_change_items_by_ticker(items):
    best_by_ticker: dict[str, dict] = {}
    for item in items:
        ticker = item.get("ticker", "")
        if not ticker:
            continue
        existing = best_by_ticker.get(ticker)
        if existing is None or _change_item_sort_key(item) < _change_item_sort_key(existing):
            best_by_ticker[ticker] = item
    return sorted(best_by_ticker.values(), key=_change_item_sort_key)


def _format_recommendation_change_text(ticker, previous_recommendation, current_recommendation) -> str:
    display = _display_ticker(ticker)
    if current_recommendation == _BUY_RECOMMENDATION:
        return f"{display} oppgradert til KJØP / ØK"
    if current_recommendation == _SELL_RECOMMENDATION:
        return f"{display} nedgradert til UNNGÅ / SELG"
    if previous_recommendation == _BUY_RECOMMENDATION:
        return f"{display} nedgradert fra KJØP / ØK"
    if previous_recommendation == _SELL_RECOMMENDATION:
        return f"{display} oppgradert fra UNNGÅ / SELG"
    return f"{display} anbefaling endret til {current_recommendation}"


def _format_score_change_text(ticker, previous_score, current_score) -> str:
    display = _display_ticker(ticker)
    previous = _safe_int(previous_score)
    current = _safe_int(current_score)
    if previous is None or current is None:
        return f"{display} score endret siden sist"
    if current > previous:
        return f"{display} score økt fra {previous} til {current}"
    return f"{display} score sunket fra {previous} til {current}"


def _change_item_from_recommendation_row(row):
    ticker = row["ticker"]
    previous = row["previous_recommendation"]
    current = row["current_recommendation"]
    return _briefing_item(
        ticker,
        _format_recommendation_change_text(ticker, previous, current),
        category="change",
        rule="recommendation_change",
        change_priority=_CHANGE_PRIORITY_RECOMMENDATION,
        change_type="recommendation",
    )


def _change_item_from_score_row(row):
    ticker = row["ticker"]
    return _briefing_item(
        ticker,
        _format_score_change_text(
            ticker,
            row.get("previous_score"),
            row.get("current_score"),
        ),
        category="change",
        rule="score_change",
        change_priority=_CHANGE_PRIORITY_SCORE,
        change_type="score",
    )


def _change_item_from_new_buy(ticker):
    display = _display_ticker(ticker)
    return _briefing_item(
        ticker,
        f"{display} ny kjøpskandidat",
        category="change",
        rule="new_buy_candidate",
        change_priority=_CHANGE_PRIORITY_NEW_BUY,
        change_type="new_buy",
    )


def _collect_change_candidates(context):
    context = context or {}
    dashboard = context.get("dashboard") or {}
    daily_flow = context.get("daily_flow") or {}
    changes = dashboard.get("changes_since_last_snapshot")
    if changes is None:
        return []

    candidates = []
    covered_tickers: set[str] = set()

    recommendation_changed = changes.get("recommendation_changed")
    if recommendation_changed is not None and not recommendation_changed.empty:
        for _, row in recommendation_changed.iterrows():
            item = _change_item_from_recommendation_row(row)
            candidates.append(item)
            covered_tickers.add(item["ticker"])

    large_score_changes = changes.get("large_score_changes")
    if large_score_changes is not None and not large_score_changes.empty:
        for _, row in large_score_changes.iterrows():
            item = _change_item_from_score_row(row)
            candidates.append(item)
            covered_tickers.add(item["ticker"])

    key_opportunities = daily_flow.get("key_opportunities") or {}
    new_buy_candidates = key_opportunities.get("new_buy_candidates")
    if new_buy_candidates is not None and not new_buy_candidates.empty:
        for _, row in new_buy_candidates.iterrows():
            ticker = row.get("ticker", "")
            display = _display_ticker(ticker)
            if not display or display in covered_tickers:
                continue
            item = _change_item_from_new_buy(ticker)
            candidates.append(item)
            covered_tickers.add(display)

    return candidates


def _build_change_items(context):
    candidates = _collect_change_candidates(context)
    if not candidates:
        return []
    return _dedupe_change_items_by_ticker(candidates)[:CHANGE_ITEM_LIMIT]


def _remove_tickers_from_sections(sections, tickers):
    excluded = set(tickers)
    return {
        **sections,
        "watchlist_items": [
            item
            for item in sections["watchlist_items"]
            if item.get("ticker") not in excluded
        ],
        "candidate_items": [
            item
            for item in sections["candidate_items"]
            if item.get("ticker") not in excluded
        ],
    }


def _has_owned_earnings_within_days(earnings_summary, days=EARNINGS_AVVENT_DAYS) -> bool:
    for item in (earnings_summary or {}).get("items") or []:
        days_until = _safe_int(item.get("days_until"))
        if (
            item.get("in_portfolio")
            and days_until is not None
            and 0 <= days_until <= days
        ):
            return True
    return False


def _build_headline(
    critical_items,
    important_items,
    candidate_items,
    *,
    earnings_summary=None,
    has_changes=False,
):
    has_critical = bool(critical_items)
    has_important = bool(important_items)
    earnings_today = _has_earnings_today(critical_items)
    earnings_soon = _has_earnings_within_days(critical_items) or _has_owned_earnings_within_days(
        earnings_summary,
    )
    strong_candidates = _has_strong_candidates(candidate_items)

    if strong_candidates and earnings_soon and not earnings_today:
        return "Flere sterke kandidater, men rapporteringsrisiko nærmer seg."

    if earnings_today or (
        earnings_soon
        and not any(
            item.get("rule") != "earnings_critical"
            for item in critical_items
        )
    ):
        return "Earnings-fokus i dag."

    if not has_critical and not has_important:
        if has_changes:
            return "Flere nye signaler siden sist oppdatering."
        return "Rolig dag – ingen kritiske hendelser."

    return "Handlingspunkter krever oppmerksomhet i dag."


def _headline_implies_portfolio_risk(headline: str) -> bool:
    normalized = headline.lower()
    return (
        "handlingspunkter krever oppmerksomhet" in normalized
        or "risikostyring" in normalized
    )


def _summary_briefing_items(
    critical_items,
    important_items,
    candidate_items,
    *,
    headline="",
    has_changes=False,
):
    summary_items = []

    if has_changes:
        summary_items.append(
            {
                "text": "Flere nye signaler har oppstått siden forrige snapshot.",
                "rule": "snapshot_changes",
            }
        )

    if _has_earnings_today(critical_items):
        summary_items.append(
            {
                "text": "Sjekk posisjoner med rapport i dag",
                "rule": "earnings_today",
            }
        )

    portfolio_critical = [
        item
        for item in critical_items
        if item.get("category") in {"reduser", "sell", "trailing_stop"}
    ]
    if portfolio_critical and not _headline_implies_portfolio_risk(headline):
        summary_items.append(
            {
                "text": "Porteføljen har signaler som krever risikostyring",
                "rule": "portfolio_risk",
            }
        )

    if _has_strong_candidates(candidate_items) and not critical_items:
        summary_items.append(
            {
                "text": "Markedet tilbyr interessante kandidater",
                "rule": "strong_candidates",
            }
        )

    if important_items and not summary_items and not has_changes:
        summary_items.append(
            {
                "text": "Støttende signaler er verdt et raskt blikk",
                "rule": "supporting_signals",
            }
        )

    return summary_items[:SUMMARY_ITEM_LIMIT]


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
    owned_tickers = _owned_ticker_set(portfolio_report)

    raw_items = (
        _critical_from_alerts(alerts)
        + _important_from_alerts(alerts)
        + _critical_from_portfolio(portfolio_report)
        + _critical_from_earnings(earnings_summary, owned_tickers)
        + _critical_from_analyst(analyst_summary, owned_tickers)
        + _important_from_sentiment(sentiment_summary)
        + _important_from_analyst(analyst_summary)
        + _watchlist_briefing_items(
            watchlist_advisor_output,
            earnings_summary,
            limit=WATCHLIST_ITEM_LIMIT,
        )
        + _candidate_briefing_items(opportunity_advisor)
    )

    deduped_items = _dedupe_items_by_ticker(raw_items)
    sections = _partition_items(deduped_items)
    sections = _apply_section_caps(sections)
    sections = _apply_watchlist_and_candidate_visibility(
        sections,
        has_critical=bool(sections["critical_items"]),
    )
    sections = _apply_total_concrete_cap(sections)

    change_items = _build_change_items(context)
    change_tickers = {item.get("ticker") for item in change_items if item.get("ticker")}
    if change_tickers:
        sections = _remove_tickers_from_sections(sections, change_tickers)

    critical_items = _sort_section_items("critical_items", sections["critical_items"])
    important_items = _sort_section_items("important_items", sections["important_items"])
    watchlist_items = _sort_section_items("watchlist_items", sections["watchlist_items"])
    candidate_items = _sort_section_items("candidate_items", sections["candidate_items"])
    has_changes = bool(change_items)
    headline = _build_headline(
        critical_items,
        important_items,
        candidate_items,
        earnings_summary=earnings_summary,
        has_changes=has_changes,
    )
    summary = _summary_briefing_items(
        critical_items,
        important_items,
        candidate_items,
        headline=headline,
        has_changes=has_changes,
    )

    return {
        "generated_at": _utc_now_iso(),
        "date": today.isoformat(),
        "headline": headline,
        "critical_items": critical_items,
        "change_items": change_items,
        "important_items": important_items,
        "watchlist_items": watchlist_items,
        "candidate_items": candidate_items,
        "summary": summary,
    }


_SECTION_LABELS = [
    ("critical_items", "Kritisk"),
    ("change_items", "Endret siden sist"),
    ("important_items", "Viktig"),
    ("watchlist_items", "Watchlist"),
    ("candidate_items", "Kandidater"),
    ("summary", "Oppsummering"),
]


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
    for section_key, section_label in _SECTION_LABELS:
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
