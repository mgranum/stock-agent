from datetime import datetime, timezone

import pandas as pd

from src.analyst import format_recommendation_label
from src.portfolio import valid_portfolio_rows
from src.sentiment import SENTIMENT_NEGATIVE
from src.strategy_classification import POSITIVE_TRENDS

METHOD_RULE_V1 = "rule_v1"
EARNINGS_NEAR_DAYS = 7
SCORE_FALL_THRESHOLD = 10
FJERN_SCORE_THRESHOLD = 40
STRONG_SCORE_THRESHOLD = 70
LOW_SCORE_THRESHOLD = 45

DISCLAIMER = (
    "Tolkningslag for watchlist. Endrer ikke score eller handlinger."
)

ACTION_FJERN_FRA_WATCHLIST = "FJERN_FRA_WATCHLIST"
ACTION_AVVENT_EARNINGS = "AVVENT_EARNINGS"
ACTION_VURDER_KJOP = "VURDER_KJØP"
ACTION_FLYTT_TIL_RESEARCH = "FLYTT_TIL_RESEARCH"
ACTION_FOLG_MED = "FØLG_MED"
ACTION_VENT = "VENT"

_BUY_RECOMMENDATION = "KJØP / ØK"
_HOLD_RECOMMENDATION = "HOLD / OBSERVER"
_AVOID_RECOMMENDATION = "UNNGÅ / SELG"
_STRONG_UPTREND = "STERK OPPTREND"
_WEAK_TREND = "SVAK / NEGATIV TREND"

_BEARISH_ANALYST_KEYS = {"sell", "strong_sell"}
_POSITIVE_ANALYST_KEYS = {"strong_buy", "buy"}
_NEUTRAL_ANALYST_KEYS = {"hold"}
_NEGATIVE_ANALYST_MEAN_THRESHOLD = 4.0

_RECOMMENDATION_RANK = {
    _BUY_RECOMMENDATION: 3,
    _HOLD_RECOMMENDATION: 2,
    _AVOID_RECOMMENDATION: 1,
}

_ACTION_PRIORITY = {
    ACTION_FJERN_FRA_WATCHLIST: 1,
    ACTION_AVVENT_EARNINGS: 1,
    ACTION_VURDER_KJOP: 1,
    ACTION_FLYTT_TIL_RESEARCH: 2,
    ACTION_FOLG_MED: 2,
    ACTION_VENT: 3,
}

_ACTION_TIE_ORDER = {
    ACTION_FJERN_FRA_WATCHLIST: 0,
    ACTION_AVVENT_EARNINGS: 1,
    ACTION_VURDER_KJOP: 2,
    ACTION_FLYTT_TIL_RESEARCH: 0,
    ACTION_FOLG_MED: 1,
    ACTION_VENT: 0,
}

_ACTION_DEFINITIONS = {
    ACTION_FJERN_FRA_WATCHLIST: {
        "headline": "Fjern fra watchlist",
        "takeaway": (
            "Modellen og trendbildet er svakt. "
            "Det er lite grunn til å bruke plass på listen."
        ),
    },
    ACTION_AVVENT_EARNINGS: {
        "headline": "Avvent kvartalsrapport",
        "takeaway": (
            "Kjøpssignal finnes, men rapport er nær. "
            "Vurder om du vil vente til etter earnings."
        ),
    },
    ACTION_VURDER_KJOP: {
        "headline": "Vurder kjøp",
        "takeaway": (
            "Sterk kandidat med god trend og relativ styrke. "
            "Verdt nærmere vurdering for inngang."
        ),
    },
    ACTION_FLYTT_TIL_RESEARCH: {
        "headline": "Flytt til research",
        "takeaway": (
            "Aksjen er fortsatt interessant å følge, "
            "men trenger mer arbeid før den fortjener aktiv watchlist-plass."
        ),
    },
    ACTION_FOLG_MED: {
        "headline": "Følg med",
        "takeaway": (
            "Fortsatt verdt å følge, men ikke klart kjøpskandidat ennå."
        ),
    },
    ACTION_VENT: {
        "headline": "Vent",
        "takeaway": (
            "Ikke prioritet nå. Vent på bedre signaler før du bruker mer tid."
        ),
    },
}


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _index_by_ticker(items):
    indexed = {}
    for item in items or []:
        ticker = str(item.get("ticker") or "").strip().upper()
        if ticker:
            indexed[ticker] = item
    return indexed


def _owned_tickers(portfolio_report, portfolio=None):
    owned = set()

    for position in portfolio or []:
        ticker = position.get("ticker")
        if ticker:
            owned.add(str(ticker).strip().upper())

    if portfolio_report is not None and not portfolio_report.empty:
        df = valid_portfolio_rows(portfolio_report)
        if df.empty and "ticker" in portfolio_report.columns:
            for ticker in portfolio_report["ticker"]:
                owned.add(str(ticker).strip().upper())
        else:
            for ticker in df["ticker"]:
                owned.add(str(ticker).strip().upper())

    return owned


def _watchlist_rows(watchlist_report, owned):
    if watchlist_report is None or watchlist_report.empty:
        return []

    df = watchlist_report.copy()
    if "error" in df.columns:
        df = df[df["error"].isna()]

    if df.empty:
        return []

    tickers_upper = df["ticker"].astype(str).str.strip().str.upper()
    df = df[~tickers_upper.isin(owned)]
    return [row for _, row in df.iterrows()]


def _earnings_within_days(earnings_item, max_days=EARNINGS_NEAR_DAYS):
    if not earnings_item:
        return False

    days_until = earnings_item.get("days_until")
    if days_until is None or (isinstance(days_until, float) and pd.isna(days_until)):
        return False

    try:
        days_until = int(days_until)
    except (TypeError, ValueError):
        return False

    return 0 <= days_until <= max_days


def _is_recommendation_downgraded(previous, current):
    previous_rank = _RECOMMENDATION_RANK.get(previous, 0)
    current_rank = _RECOMMENDATION_RANK.get(current, 0)
    return current_rank < previous_rank


def _index_snapshot_changes(snapshot_changes):
    by_ticker = {}

    if not snapshot_changes:
        return by_ticker

    recommendation_changed = snapshot_changes.get("recommendation_changed")
    if recommendation_changed is not None and not recommendation_changed.empty:
        for _, row in recommendation_changed.iterrows():
            ticker = str(row.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            info = by_ticker.setdefault(ticker, {})
            info["recommendation_downgraded"] = _is_recommendation_downgraded(
                row.get("previous_recommendation"),
                row.get("current_recommendation"),
            )
            score_change = _safe_float(row.get("score_change"))
            if score_change is not None and score_change <= -SCORE_FALL_THRESHOLD:
                info["score_fall"] = True

    large_score_changes = snapshot_changes.get("large_score_changes")
    if large_score_changes is not None and not large_score_changes.empty:
        for _, row in large_score_changes.iterrows():
            ticker = str(row.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            info = by_ticker.setdefault(ticker, {})
            score_change = _safe_float(row.get("score_change"))
            if score_change is not None and score_change <= -SCORE_FALL_THRESHOLD:
                info["score_fall"] = True

    return by_ticker


def _has_analyst_data(analyst_item):
    if not analyst_item:
        return False

    return any(
        analyst_item.get(field) is not None
        for field in (
            "analyst_count",
            "target_mean",
            "recommendation_key",
            "recommendation_mean",
        )
    )


def _is_analyst_weak_or_negative(analyst_item):
    if not _has_analyst_data(analyst_item):
        return False

    recommendation_key = str(
        analyst_item.get("recommendation_key") or ""
    ).lower().strip()

    if recommendation_key in _BEARISH_ANALYST_KEYS:
        return True

    if (
        recommendation_key in _POSITIVE_ANALYST_KEYS
        or recommendation_key in _NEUTRAL_ANALYST_KEYS
    ):
        return False

    recommendation_mean = _safe_float(analyst_item.get("recommendation_mean"))
    return (
        recommendation_mean is not None
        and recommendation_mean >= _NEGATIVE_ANALYST_MEAN_THRESHOLD
    )


def _weak_signal_flags(row):
    score = _safe_float(row.get("score"))
    trend_regime = row.get("trend_regime")
    relative_strength = _safe_float(row.get("relative_strength_20d"))

    return {
        "low_score": score is not None and score < FJERN_SCORE_THRESHOLD,
        "weak_trend": trend_regime == _WEAK_TREND,
        "negative_rs": (
            relative_strength is not None and relative_strength < 0
        ),
    }


def _weak_signal_count(row):
    return sum(_weak_signal_flags(row).values())


def _matches_fjern(row):
    if row.get("anbefaling") != _AVOID_RECOMMENDATION:
        return False

    return _weak_signal_count(row) == 3


def _matches_avoid_partial_flytt(row):
    if row.get("anbefaling") != _AVOID_RECOMMENDATION:
        return False

    weak_count = _weak_signal_count(row)
    return weak_count in (0, 2)


def _matches_avoid_partial_vent(row):
    if row.get("anbefaling") != _AVOID_RECOMMENDATION:
        return False

    return _weak_signal_count(row) == 1


def _matches_avvent(row, earnings_item):
    return (
        row.get("anbefaling") == _BUY_RECOMMENDATION
        and _earnings_within_days(earnings_item)
    )


def _matches_vurder_kjop(row, earnings_item):
    if row.get("anbefaling") != _BUY_RECOMMENDATION:
        return False

    if _earnings_within_days(earnings_item):
        return False

    trend_regime = row.get("trend_regime")
    relative_strength = _safe_float(row.get("relative_strength_20d"))
    return (
        trend_regime == _STRONG_UPTREND
        or (relative_strength is not None and relative_strength > 0)
    )


def _matches_flytt_til_research(row, snapshot_info):
    if snapshot_info.get("recommendation_downgraded"):
        return True

    if snapshot_info.get("score_fall"):
        return True

    return _matches_avoid_partial_flytt(row)


def _matches_folg_med(row):
    if row.get("anbefaling") != _HOLD_RECOMMENDATION:
        return False

    trend_regime = row.get("trend_regime")
    score = _safe_float(row.get("score"))
    return (
        trend_regime in POSITIVE_TRENDS
        or (score is not None and score >= STRONG_SCORE_THRESHOLD)
    )


def _matches_vent(row):
    if _matches_avoid_partial_vent(row):
        return True

    if row.get("anbefaling") == _HOLD_RECOMMENDATION:
        if row.get("trend_regime") == _WEAK_TREND:
            return True

    score = _safe_float(row.get("score"))
    return score is not None and score < LOW_SCORE_THRESHOLD


def _matching_actions(row, snapshot_info, earnings_item):
    actions = []

    if _matches_fjern(row):
        actions.append(ACTION_FJERN_FRA_WATCHLIST)

    if _matches_avvent(row, earnings_item):
        actions.append(ACTION_AVVENT_EARNINGS)

    if _matches_vurder_kjop(row, earnings_item):
        actions.append(ACTION_VURDER_KJOP)

    if _matches_flytt_til_research(row, snapshot_info):
        actions.append(ACTION_FLYTT_TIL_RESEARCH)

    if _matches_folg_med(row):
        actions.append(ACTION_FOLG_MED)

    if _matches_vent(row):
        actions.append(ACTION_VENT)

    return actions


def _select_action(actions):
    if not actions:
        return None

    return min(
        actions,
        key=lambda action: (
            _ACTION_PRIORITY[action],
            _ACTION_TIE_ORDER[action],
        ),
    )


def _relative_strength_why_line(relative_strength):
    if relative_strength is None:
        return None

    if relative_strength > 0:
        return f"Positiv relativ styrke ({round(relative_strength, 1)}%)"

    if relative_strength < 0:
        return f"Negativ relativ styrke ({round(relative_strength, 1)}%)"

    return None


def _build_why(row, action, snapshot_info):
    why = []
    anbefaling = row.get("anbefaling")
    trend_regime = row.get("trend_regime")
    score = _safe_float(row.get("score"))
    relative_strength = _safe_float(row.get("relative_strength_20d"))

    if anbefaling:
        why.append(f"Modellanbefaling: {anbefaling}")

    if trend_regime:
        why.append(trend_regime)

    if score is not None:
        why.append(f"Score {int(score)}")

    rs_line = _relative_strength_why_line(relative_strength)
    if rs_line:
        why.append(rs_line)

    if snapshot_info.get("recommendation_downgraded"):
        why.append("Anbefaling nedgradert siden snapshot")

    if snapshot_info.get("score_fall"):
        why.append(f"Score-fall >= {SCORE_FALL_THRESHOLD} poeng siden snapshot")

    if action == ACTION_VURDER_KJOP and trend_regime == _STRONG_UPTREND:
        if "Sterk opptrend" not in why:
            why.append("Sterk opptrend")

    seen = set()
    deduped = []
    for item in why:
        if item not in seen:
            seen.add(item)
            deduped.append(item)

    return deduped


def _build_watch_out_for(
    analyst_item,
    sentiment_item,
    earnings_item,
    snapshot_info,
):
    watch_out = []

    if _earnings_within_days(earnings_item):
        days_until = earnings_item.get("days_until")
        watch_out.append(f"Kvartalsrapport om {days_until} dager")

    if (sentiment_item or {}).get("sentiment") == SENTIMENT_NEGATIVE:
        watch_out.append("Negativ nyhetstone")

    if analyst_item is None or not _has_analyst_data(analyst_item):
        watch_out.append("Manglende analytikerdata")
    elif _is_analyst_weak_or_negative(analyst_item):
        label = format_recommendation_label(
            analyst_item.get("recommendation_key")
        )
        if label != "—":
            watch_out.append(
                f"Svak eller negativ analytikerkonsensus ({label})"
            )
        else:
            watch_out.append("Svak eller negativ analytikerkonsensus")

    if snapshot_info.get("recommendation_downgraded"):
        watch_out.append("Nylig nedgradering siden snapshot")

    if snapshot_info.get("score_fall"):
        watch_out.append(
            f"Nylig score-fall (>= {SCORE_FALL_THRESHOLD} poeng) siden snapshot"
        )

    return watch_out


def _refine_takeaway(action, row, analyst_item, sentiment_item, watch_out_for):
    definition = _ACTION_DEFINITIONS[action]
    takeaway = definition["takeaway"]

    score = _safe_float(row.get("score"))
    has_conflict = (
        score is not None
        and score >= STRONG_SCORE_THRESHOLD
        and (
            _is_analyst_weak_or_negative(analyst_item)
            or (sentiment_item or {}).get("sentiment") == SENTIMENT_NEGATIVE
        )
    )

    if action == ACTION_FOLG_MED and has_conflict:
        return (
            "Modellen er sterk, men analytikere eller nyhetstone er negative. "
            "Følg med og dobbeltsjekk før du vurderer kjøp."
        )

    if action == ACTION_VURDER_KJOP and watch_out_for:
        return (
            "Sterk kandidat, men med tydelige forbehold. "
            "Vurder nærmere før inngang."
        )

    if action == ACTION_FLYTT_TIL_RESEARCH and watch_out_for:
        first = watch_out_for[0]
        return (
            f"Kandidaten trenger mer arbeid. "
            f"Vurder å flytte til research: {first}."
        )

    return takeaway


def _build_watchlist_advisor_item(
    row,
    analyst_item=None,
    sentiment_item=None,
    earnings_item=None,
    snapshot_info=None,
):
    snapshot_info = snapshot_info or {}
    matching = _matching_actions(
        row,
        snapshot_info,
        earnings_item,
    )
    action = _select_action(matching)
    if action is None:
        return None

    ticker = str(row.get("ticker") or "").strip().upper()
    definition = _ACTION_DEFINITIONS[action]
    watch_out_for = _build_watch_out_for(
        analyst_item,
        sentiment_item,
        earnings_item,
        snapshot_info,
    )

    return {
        "ticker": ticker,
        "watchlist_action": action,
        "headline": definition["headline"],
        "why": _build_why(row, action, snapshot_info),
        "watch_out_for": watch_out_for,
        "takeaway": _refine_takeaway(
            action,
            row,
            analyst_item,
            sentiment_item,
            watch_out_for,
        ),
        "priority": _ACTION_PRIORITY[action],
    }


def build_watchlist_advisor(
    watchlist_report,
    portfolio_report=None,
    portfolio=None,
    analyst_summary=None,
    sentiment_summary=None,
    earnings_summary=None,
    snapshot_changes=None,
):
    owned = _owned_tickers(portfolio_report, portfolio)
    rows = _watchlist_rows(watchlist_report, owned)
    if not rows:
        return _empty_watchlist_advisor_output()

    analyst_by_ticker = _index_by_ticker((analyst_summary or {}).get("items"))
    sentiment_by_ticker = _index_by_ticker((sentiment_summary or {}).get("items"))
    earnings_by_ticker = _index_by_ticker((earnings_summary or {}).get("items"))
    snapshot_by_ticker = _index_snapshot_changes(snapshot_changes)

    items = []
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue

        item = _build_watchlist_advisor_item(
            row,
            analyst_item=analyst_by_ticker.get(ticker),
            sentiment_item=sentiment_by_ticker.get(ticker),
            earnings_item=earnings_by_ticker.get(ticker),
            snapshot_info=snapshot_by_ticker.get(ticker, {}),
        )
        if item:
            items.append(item)

    items.sort(
        key=lambda item: (
            item.get("priority", 99),
            item.get("ticker", ""),
        ),
    )

    return {
        "items": items,
        "method": METHOD_RULE_V1,
        "disclaimer": DISCLAIMER,
        "last_updated": _utc_now_iso(),
    }


def _empty_watchlist_advisor_output():
    return {
        "items": [],
        "method": METHOD_RULE_V1,
        "disclaimer": DISCLAIMER,
        "last_updated": _utc_now_iso(),
    }


WATCHLIST_ACTION_LABELS = {
    ACTION_VURDER_KJOP: "Vurder kjøp",
    ACTION_AVVENT_EARNINGS: "Avvent earnings",
    ACTION_FJERN_FRA_WATCHLIST: "Fjern fra watchlist",
    ACTION_FLYTT_TIL_RESEARCH: "Flytt til research",
    ACTION_FOLG_MED: "Følg med",
    ACTION_VENT: "Vent",
}

WATCHLIST_PRIORITY_LABELS = {
    1: "Høy",
    2: "Medium",
    3: "Lav",
}

_WATCHLIST_ADVISOR_TABLE_COLUMNS = [
    "Ticker",
    "Handling",
    "Headline",
    "Tolkning",
    "Prioritet",
]


def format_watchlist_action_label(action):
    return WATCHLIST_ACTION_LABELS.get(action, action or "")


def format_watchlist_priority_label(priority):
    return WATCHLIST_PRIORITY_LABELS.get(priority, "Lav")


def build_watchlist_advisor_table(watchlist_advisor_output):
    items = (watchlist_advisor_output or {}).get("items") or []
    if not items:
        return pd.DataFrame(columns=_WATCHLIST_ADVISOR_TABLE_COLUMNS)

    rows = []
    for item in items:
        rows.append({
            "Ticker": item.get("ticker", ""),
            "Handling": format_watchlist_action_label(
                item.get("watchlist_action"),
            ),
            "Headline": item.get("headline", ""),
            "Tolkning": item.get("takeaway", ""),
            "Prioritet": format_watchlist_priority_label(
                item.get("priority"),
            ),
        })

    return pd.DataFrame(rows, columns=_WATCHLIST_ADVISOR_TABLE_COLUMNS)


def format_watchlist_advisor_detail(item):
    if not item:
        return None

    return {
        "why": list(item.get("why") or []),
        "watch_out_for": list(item.get("watch_out_for") or []),
        "takeaway": item.get("takeaway") or "",
    }
