import time
from datetime import datetime, timezone

from src.analysis import analyze_stock
from src.company_names import get_company_name
from src.storage import load_json, save_json
from src.strategy_classification import classify_stock

FILENAME = "research_ideas.json"
BUY_RECOMMENDATION = "KJØP / ØK"
AVOID_RECOMMENDATION = "UNNGÅ / SELG"


def load_research_ideas():
    return load_json(FILENAME, [])


def save_research_ideas(ideas):
    return save_json(FILENAME, ideas)


def _normalize_ticker(ticker):
    return str(ticker).strip().upper()


def _coerce_score(score):
    if score is None:
        return 0

    try:
        return float(score)
    except (TypeError, ValueError):
        return 0


def research_idea_status(idea):
    recommendation = idea.get("recommendation") or ""
    score = _coerce_score(idea.get("score"))

    if recommendation == AVOID_RECOMMENDATION or score < 40:
        return "ARKIVER"

    if score >= 70 and recommendation == BUY_RECOMMENDATION:
        return "LEGG TIL WATCHLIST"

    if score >= 55:
        return "FØLG MED"

    return "VENT"


def _build_idea(candidate, source_universe, saved_at=None):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    idea = {
        "ticker": _normalize_ticker(candidate["ticker"]),
        "company_name": candidate.get("company_name") or "",
        "source_universe": source_universe,
        "score": candidate.get("score"),
        "recommendation": candidate.get("recommendation") or "",
        "strategy_type": candidate.get("strategy_type") or "",
        "trend_regime": candidate.get("trend_regime") or "",
        "relative_strength_20d": candidate.get("relative_strength_20d"),
        "fundamental_score": candidate.get("fundamental_score"),
        "fundamental_history_score": candidate.get(
            "fundamental_history_score"
        ),
        "saved_at": saved_at or now,
        "last_updated_at": candidate.get("last_updated_at") or now,
    }
    idea["status"] = research_idea_status(idea)
    return idea


def _refresh_research_idea(idea):
    ticker = _normalize_ticker(idea["ticker"])
    analysis, _ = analyze_stock(ticker)

    refreshed = {
        "ticker": ticker,
        "company_name": get_company_name(ticker) or idea.get("company_name") or "",
        "source_universe": idea.get("source_universe") or "",
        "score": analysis["score"],
        "recommendation": analysis["anbefaling"],
        "strategy_type": classify_stock({
            "ticker": ticker,
            "score": analysis["score"],
            "anbefaling": analysis["anbefaling"],
            "trend_regime": analysis["trend_regime"],
            "relative_strength_20d": analysis["relative_strength_20d"],
            "fundamental_score": analysis["fundamental_score"],
            "fundamental_history_score": analysis[
                "fundamental_history_score"
            ],
        }),
        "trend_regime": analysis["trend_regime"],
        "relative_strength_20d": analysis["relative_strength_20d"],
        "fundamental_score": analysis["fundamental_score"],
        "fundamental_history_score": analysis["fundamental_history_score"],
        "saved_at": idea.get("saved_at"),
        "last_updated_at": datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds"),
    }
    refreshed["status"] = research_idea_status(refreshed)
    return refreshed


def add_research_idea(candidate, source_universe):
    ticker = _normalize_ticker(candidate["ticker"])
    if not ticker:
        raise ValueError("Ticker kan ikke være tom.")

    ideas = load_research_ideas()
    existing = next(
        (
            idea
            for idea in ideas
            if _normalize_ticker(idea.get("ticker")) == ticker
        ),
        None,
    )
    idea = _build_idea(
        candidate,
        source_universe,
        saved_at=existing.get("saved_at") if existing else None,
    )

    for index, current in enumerate(ideas):
        if _normalize_ticker(current.get("ticker")) == ticker:
            ideas[index] = idea
            save_research_ideas(ideas)
            return ideas

    ideas.append(idea)
    save_research_ideas(ideas)
    return ideas


def update_research_ideas(pause_seconds=1):
    ideas = load_research_ideas()
    updated = []
    failed = []

    for index, idea in enumerate(ideas):
        ticker = idea.get("ticker")
        try:
            updated.append(_refresh_research_idea(idea))
        except Exception as exc:
            failed.append({"ticker": ticker, "error": str(exc)})
            stale = dict(idea)
            stale["status"] = research_idea_status(stale)
            updated.append(stale)

        if pause_seconds and index < len(ideas) - 1:
            time.sleep(pause_seconds)

    save_research_ideas(updated)
    return {
        "ideas": updated,
        "failed": failed,
    }


def remove_research_idea(ticker):
    ticker = _normalize_ticker(ticker)
    ideas = load_research_ideas()
    filtered = [
        idea
        for idea in ideas
        if _normalize_ticker(idea.get("ticker")) != ticker
    ]

    if len(filtered) == len(ideas):
        raise ValueError(f"Research-idé for {ticker} finnes ikke.")

    save_research_ideas(filtered)
    return filtered
