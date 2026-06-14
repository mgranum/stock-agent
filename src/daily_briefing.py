from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from src.company_names import get_company_name
from src.sentiment import (
    SENTIMENT_DISPLAY_LABELS,
    SENTIMENT_NEGATIVE,
    SENTIMENT_POSITIVE,
)

BRIEFING_ITEM_LIMIT = 3
STRONG_CANDIDATE_SCORE = 80


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


def _portfolio_briefing_items(advisor_output, limit=BRIEFING_ITEM_LIMIT):
    items = list((advisor_output or {}).get("items") or [])
    items.sort(
        key=lambda item: (
            item.get("priority", 99),
            item.get("ticker", ""),
        ),
    )

    briefing_items = []
    for item in items[:limit]:
        ticker = _display_ticker(item.get("ticker"))
        headline = str(item.get("headline") or "").strip()
        if not ticker or not headline:
            continue

        briefing_items.append(
            {
                "ticker": ticker,
                "text": f"{ticker}: {headline[0].lower()}{headline[1:]}",
                "priority": item.get("priority"),
                "conflict_id": item.get("conflict_id"),
            }
        )

    return briefing_items


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


def _earnings_briefing_items(earnings_summary, limit=BRIEFING_ITEM_LIMIT):
    candidates = []
    for item in (earnings_summary or {}).get("items") or []:
        days_until = _safe_int(item.get("days_until"))
        if days_until is None or days_until < 0 or days_until > 7:
            continue

        candidates.append(
            {
                "item": item,
                "days_until": days_until,
                "in_portfolio": bool(item.get("in_portfolio")),
            }
        )

    candidates.sort(
        key=lambda entry: (
            entry["days_until"],
            0 if entry["in_portfolio"] else 1,
            str(entry["item"].get("ticker") or ""),
        ),
    )

    briefing_items = []
    for entry in candidates[:limit]:
        item = entry["item"]
        ticker = _display_ticker(item.get("ticker"))
        briefing_items.append(
            {
                "ticker": ticker,
                "text": _earnings_briefing_text(item),
                "days_until": entry["days_until"],
                "in_portfolio": entry["in_portfolio"],
            }
        )

    return briefing_items


def _analyst_briefing_items(analyst_summary, limit=BRIEFING_ITEM_LIMIT):
    briefing_items = []
    for change in (analyst_summary or {}).get("material_changes") or []:
        ticker = _display_ticker(change.get("ticker"))
        endring = str(change.get("Endring") or "").strip()
        if not ticker or not endring:
            continue

        briefing_items.append(
            {
                "ticker": ticker,
                "text": f"{ticker}: {endring}",
                "change_type": change.get("change_type"),
            }
        )

        if len(briefing_items) >= limit:
            break

    return briefing_items


def _screener_rows(screener_results, limit=BRIEFING_ITEM_LIMIT):
    if screener_results is None:
        return []

    if isinstance(screener_results, pd.DataFrame):
        if screener_results.empty:
            return []
        return screener_results.head(limit).to_dict("records")

    rows = list(screener_results)[:limit]
    return [dict(row) for row in rows]


def _opportunity_by_ticker(opportunity_advisor):
    return {
        str(item.get("ticker") or "").strip().upper(): item
        for item in (opportunity_advisor or {}).get("items") or []
        if item.get("ticker")
    }


def _candidate_briefing_items(
    screener_results,
    opportunity_advisor=None,
    limit=BRIEFING_ITEM_LIMIT,
):
    rows = _screener_rows(screener_results, limit=limit)
    if not rows:
        return []

    advisor_map = _opportunity_by_ticker(opportunity_advisor)
    briefing_items = []

    for row in rows:
        ticker = _display_ticker(row.get("ticker"))
        if not ticker:
            continue

        normalized = str(row.get("ticker") or "").strip().upper()
        advisor_item = advisor_map.get(normalized)
        score = _safe_float(row.get("score"))

        if advisor_item and advisor_item.get("headline"):
            text = f"{ticker}: {advisor_item['headline']}"
        elif score is not None:
            text = f"{ticker} score {int(score) if score == int(score) else round(score, 1)}"
        else:
            text = ticker

        briefing_items.append(
            {
                "ticker": ticker,
                "text": text,
                "score": score,
                "headline": (advisor_item or {}).get("headline"),
            }
        )

        if len(briefing_items) >= limit:
            break

    return briefing_items


def _news_briefing_items(sentiment_summary, limit=BRIEFING_ITEM_LIMIT):
    items = [
        item
        for item in (sentiment_summary or {}).get("items") or []
        if item.get("sentiment") in (SENTIMENT_POSITIVE, SENTIMENT_NEGATIVE)
    ]

    items.sort(
        key=lambda item: (
            0 if item.get("in_portfolio") else 1,
            -abs(_safe_float(item.get("score")) or 0.0),
            item.get("ticker", ""),
        ),
    )

    briefing_items = []
    for item in items[:limit]:
        ticker = _display_ticker(item.get("ticker"))
        sentiment = item.get("sentiment")
        label = SENTIMENT_DISPLAY_LABELS.get(sentiment, sentiment)
        if not ticker or not label:
            continue

        briefing_items.append(
            {
                "ticker": ticker,
                "text": f"{ticker}: {label} nyhetstone",
                "sentiment": sentiment,
            }
        )

    return briefing_items


def _has_earnings_today(earnings_items) -> bool:
    return any(item.get("days_until") == 0 for item in earnings_items)


def _has_advisor_conflicts(advisor_output) -> bool:
    return bool((advisor_output or {}).get("items"))


def _has_strong_candidates(candidate_items) -> bool:
    if not candidate_items:
        return False

    for item in candidate_items:
        score = _safe_float(item.get("score"))
        if score is not None and score >= STRONG_CANDIDATE_SCORE:
            return True

    return len(candidate_items) >= 2


def _summary_briefing_items(
    earnings_items,
    advisor_output,
    candidate_items,
):
    summary_items = []

    if _has_earnings_today(earnings_items):
        summary_items.append(
            {
                "text": "Kvartalsrapporter krever oppfølging i dag",
                "rule": "earnings_today",
            }
        )

    if _has_advisor_conflicts(advisor_output):
        summary_items.append(
            {
                "text": "Flere porteføljeaksjer har motstridende signaler",
                "rule": "advisor_conflicts",
            }
        )

    if _has_strong_candidates(candidate_items):
        summary_items.append(
            {
                "text": "Markedet tilbyr flere interessante kandidater",
                "rule": "strong_candidates",
            }
        )

    return summary_items


def build_daily_briefing(context, today=None):
    context = context or {}
    today = today or date.today()

    advisor_output = context.get("advisor_output")
    earnings_summary = context.get("earnings_summary")
    analyst_summary = context.get("analyst_summary")
    sentiment_summary = context.get("sentiment_summary")
    screener_results = context.get("screener_results")
    opportunity_advisor = context.get("opportunity_advisor")

    portfolio_items = _portfolio_briefing_items(advisor_output)
    earnings_items = _earnings_briefing_items(earnings_summary)
    analyst_items = _analyst_briefing_items(analyst_summary)
    candidate_items = _candidate_briefing_items(
        screener_results,
        opportunity_advisor=opportunity_advisor,
    )
    news_items = _news_briefing_items(sentiment_summary)
    summary_items = _summary_briefing_items(
        earnings_items,
        advisor_output,
        candidate_items,
    )

    return {
        "generated_at": _utc_now_iso(),
        "date": today.isoformat(),
        "portfolio_items": portfolio_items,
        "earnings_items": earnings_items,
        "analyst_items": analyst_items,
        "candidate_items": candidate_items,
        "news_items": news_items,
        "summary_items": summary_items,
    }


_SECTION_LABELS = {
    "portfolio_items": "Portefølje",
    "earnings_items": "Earnings",
    "analyst_items": "Analytiker",
    "candidate_items": "Kandidater",
    "news_items": "Nyheter",
    "summary_items": "Oppsummering",
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

    for section_key, section_label in _SECTION_LABELS.items():
        items = briefing.get(section_key) or []
        if not items:
            continue

        lines.append(section_label)
        for item in items:
            text = item.get("text") if isinstance(item, dict) else str(item)
            if text:
                lines.append(f"• {text}")
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)
