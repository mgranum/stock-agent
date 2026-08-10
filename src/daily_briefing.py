from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from src.recommendation_engine import (
    BRIEFING_SECTION_CANDIDATE,
    BRIEFING_SECTION_CRITICAL,
    BRIEFING_SECTION_IMPORTANT,
    BRIEFING_SECTION_WATCHLIST,
    build_recommendations,
)

CRITICAL_ITEM_LIMIT = 3
IMPORTANT_ITEM_LIMIT = 2
TOTAL_CONCRETE_ITEM_LIMIT = 5
WATCHLIST_ITEM_LIMIT = 2
CANDIDATE_ITEM_LIMIT = 2
CHANGE_ITEM_LIMIT = 3
EARNINGS_AVVENT_DAYS = 3
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



def _recommendation_to_briefing_item(recommendation):
    item = {
        "ticker": recommendation.get("ticker", ""),
        "text": recommendation.get("briefing_text") or recommendation.get("action", ""),
        "rule": recommendation.get("rule"),
        "category": recommendation.get("briefing_category"),
    }
    for key in (
        "days_until",
        "portfolio_action",
        "watchlist_action",
        "headline",
        "change_type",
        "sentiment",
        "in_portfolio",
    ):
        if key in recommendation:
            item[key] = recommendation[key]

    if recommendation.get("priority_source") is not None:
        item["priority"] = recommendation["priority_source"]

    return item


def _recommendation_sort_key(recommendation) -> tuple:
    return _item_sort_key(_recommendation_to_briefing_item(recommendation))


def _dedupe_recommendations_by_ticker(recommendations):
    best_by_ticker: dict[str, dict] = {}
    for recommendation in recommendations:
        ticker = recommendation.get("ticker", "")
        if not ticker:
            continue
        existing = best_by_ticker.get(ticker)
        if (
            existing is None
            or _recommendation_sort_key(recommendation) < _recommendation_sort_key(existing)
        ):
            best_by_ticker[ticker] = recommendation
    return sorted(best_by_ticker.values(), key=_recommendation_sort_key)


def _sections_from_recommendations(recommendations):
    sections = {
        "critical_items": [],
        "important_items": [],
        "watchlist_items": [],
        "candidate_items": [],
    }
    section_keys = {
        BRIEFING_SECTION_CRITICAL: "critical_items",
        BRIEFING_SECTION_IMPORTANT: "important_items",
        BRIEFING_SECTION_WATCHLIST: "watchlist_items",
        BRIEFING_SECTION_CANDIDATE: "candidate_items",
    }

    for recommendation in recommendations:
        section_name = section_keys.get(recommendation.get("briefing_section"))
        if section_name is None:
            continue

        rule = recommendation.get("rule")
        if section_name == "watchlist_items" and rule not in {
            "vurder_kjop",
            "avvent_earnings",
        }:
            continue

        sections[section_name].append(_recommendation_to_briefing_item(recommendation))

    return sections


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

    # On non-critical days, reserve one slot for discovery. Without this,
    # watchlist items always outrank candidates and can fill the entire briefing.
    reserved_candidate = None
    if not sections["critical_items"] and sections["candidate_items"] and limit > 0:
        reserved_candidate = sections["candidate_items"][0]
        combined = [
            entry
            for entry in combined
            if not (
                entry[1] == "candidate_items"
                and entry[0].get("ticker") == reserved_candidate.get("ticker")
            )
        ]

    kept = combined[: limit - 1] if reserved_candidate is not None else combined[:limit]
    if reserved_candidate is not None:
        kept.append((reserved_candidate, "candidate_items"))
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
    for item, section_key in kept:
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
        return f"{display} nedgradert til {current_recommendation}"
    if previous_recommendation == _SELL_RECOMMENDATION:
        return f"{display} oppgradert til {current_recommendation}"
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


def _collect_change_candidates(context):
    context = context or {}
    dashboard = context.get("dashboard") or {}
    changes = dashboard.get("changes_since_last_snapshot")
    if changes is None:
        return []

    candidates = []

    recommendation_changed = changes.get("recommendation_changed")
    if recommendation_changed is not None and not recommendation_changed.empty:
        for _, row in recommendation_changed.iterrows():
            item = _change_item_from_recommendation_row(row)
            candidates.append(item)

    large_score_changes = changes.get("large_score_changes")
    if large_score_changes is not None and not large_score_changes.empty:
        for _, row in large_score_changes.iterrows():
            item = _change_item_from_score_row(row)
            candidates.append(item)

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


def build_daily_briefing(context, today=None, recommendations=None):
    context = context or {}
    today = today or date.today()
    earnings_summary = context.get("earnings_summary")

    if recommendations is None:
        recommendations = context.get("recommendations")
    if recommendations is None:
        recommendations = build_recommendations(context)

    deduped_items = _dedupe_recommendations_by_ticker(
        recommendations.get("actions") or [],
    )
    sections = _sections_from_recommendations(deduped_items)
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
    return {
        "generated_at": _utc_now_iso(),
        "date": today.isoformat(),
        "headline": headline,
        "critical_items": critical_items,
        "change_items": change_items,
        "important_items": important_items,
        "watchlist_items": watchlist_items,
        "candidate_items": candidate_items,
        "summary": [],
        "recommendations": recommendations,
    }


_SECTION_LABELS = [
    ("critical_items", "Kritisk"),
    ("change_items", "Endret siden sist"),
    ("important_items", "Viktig"),
    ("watchlist_items", "Watchlist"),
    ("candidate_items", "Nye kandidater"),
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
