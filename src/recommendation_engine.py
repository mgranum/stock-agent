from __future__ import annotations

from src.advisor import (
    CONFLICT_GAIN_VS_STOP,
    CONFLICT_SELL_VS_ANALYST,
)
from src.alerts import (
    ALERT_NEAR_TRAILING_STOP,
    ALERT_PENDING_ORDER,
    ALERT_TRAILING_STOP_TRIGGERED,
)
from src.company_names import get_company_name
from src.daily_flow import build_daily_actions
from src.model_version import MODEL_VERSION
from src.portfolio import valid_portfolio_rows
from src.sentiment import (
    SENTIMENT_DISPLAY_LABELS,
    SENTIMENT_NEGATIVE,
)
from src.watchlist_advisor import (
    ACTION_AVVENT_EARNINGS,
    ACTION_FJERN_FRA_WATCHLIST,
    ACTION_FLYTT_TIL_RESEARCH,
    ACTION_FOLG_MED,
    ACTION_VENT,
    ACTION_VURDER_KJOP,
    format_watchlist_action_label,
)

MAX_RECOMMENDATIONS = 5
EARNINGS_OWNED_CRITICAL_DAYS = 1
STRONG_NEGATIVE_SENTIMENT_SCORE = -0.5

CATEGORY_PORTFOLIO = "Portefølje"
CATEGORY_BUYING = "Kjøpsmuligheter"
CATEGORY_WATCHLIST = "Watchlist"
CATEGORY_RISK = "Risiko"
CATEGORY_ORDERS = "Ordre"
CATEGORY_GENERAL = "Generelt"

BRIEFING_SECTION_CRITICAL = "critical"
BRIEFING_SECTION_IMPORTANT = "important"
BRIEFING_SECTION_WATCHLIST = "watchlist"
BRIEFING_SECTION_CANDIDATE = "candidate"

_CONFIDENCE_BY_PRIORITY = {
    1: "høy",
    2: "høy",
    3: "medium",
    4: "lav",
}

_DAILY_FLOW_ACTION_CONFIG = {
    "Vurder salg": {
        "action": "Gjennomgå {ticker}",
        "category": CATEGORY_PORTFOLIO,
        "priority": 1,
        "merge_group": "portfolio_sell",
        "rule": "portfolio_reduser",
        "briefing_section": BRIEFING_SECTION_CRITICAL,
        "briefing_category": "reduser",
    },
    "Vurder reduksjon": {
        "action": "Gjennomgå {ticker}",
        "category": CATEGORY_PORTFOLIO,
        "priority": 2,
        "merge_group": "portfolio_sell",
        "rule": "portfolio_reduser",
        "briefing_section": BRIEFING_SECTION_CRITICAL,
        "briefing_category": "reduser",
    },
    "Sikre gevinst": {
        "action": "Sikre gevinst på {ticker}",
        "category": CATEGORY_PORTFOLIO,
        "priority": 1,
        "merge_group": "portfolio_profit",
        "rule": "portfolio_reduser",
        "briefing_section": BRIEFING_SECTION_CRITICAL,
        "briefing_category": "trailing_stop",
    },
    "Følg stop-nivå": {
        "action": "Flytt trailing stop på {ticker}",
        "category": CATEGORY_PORTFOLIO,
        "priority": 1,
        "merge_group": "portfolio_stop",
        "rule": "trailing_stop_near",
        "briefing_section": BRIEFING_SECTION_IMPORTANT,
        "briefing_category": "trailing_stop",
    },
    "Følg med": {
        "action": "Følg med på {ticker}",
        "category": CATEGORY_PORTFOLIO,
        "priority": 3,
        "merge_group": "portfolio_monitor",
        "rule": "portfolio_monitor",
        "briefing_section": BRIEFING_SECTION_IMPORTANT,
        "briefing_category": "portfolio",
    },
    "Gjennomgå ordre": {
        "action": "Gjennomgå ordre for {ticker}",
        "category": CATEGORY_ORDERS,
        "priority": 2,
        "merge_group": "order_review",
        "rule": "order_review",
        "briefing_section": BRIEFING_SECTION_CRITICAL,
        "briefing_category": "orders",
    },
    "Forbered kvartalsrapport": {
        "action": "Forbered kvartalsrapport for {ticker}",
        "category": CATEGORY_RISK,
        "priority": 2,
        "merge_group": "earnings_prepare",
        "rule": "earnings_prepare",
        "briefing_section": BRIEFING_SECTION_CRITICAL,
        "briefing_category": "earnings",
    },
}

_WATCHLIST_ACTION_CONFIG = {
    ACTION_VURDER_KJOP: {
        "action": "Vurder kjøp av {ticker}",
        "category": CATEGORY_WATCHLIST,
        "priority": 2,
        "merge_group": "watchlist_buy",
        "rule": "vurder_kjop",
        "briefing_section": BRIEFING_SECTION_WATCHLIST,
        "briefing_category": "watchlist",
    },
    ACTION_AVVENT_EARNINGS: {
        "action": "Avvent {ticker} til etter kvartalsrapport",
        "category": CATEGORY_WATCHLIST,
        "priority": 2,
        "merge_group": "watchlist_earnings",
        "rule": "avvent_earnings",
        "briefing_section": BRIEFING_SECTION_WATCHLIST,
        "briefing_category": "watchlist",
    },
    ACTION_FJERN_FRA_WATCHLIST: {
        "action": "Fjern {ticker} fra watchlist",
        "category": CATEGORY_WATCHLIST,
        "priority": 3,
        "merge_group": "watchlist_remove",
        "rule": "watchlist_remove",
        "briefing_section": BRIEFING_SECTION_WATCHLIST,
        "briefing_category": "watchlist",
    },
    ACTION_FLYTT_TIL_RESEARCH: {
        "action": "Flytt {ticker} til research",
        "category": CATEGORY_WATCHLIST,
        "priority": 3,
        "merge_group": "watchlist_research",
        "rule": "watchlist_research",
        "briefing_section": BRIEFING_SECTION_WATCHLIST,
        "briefing_category": "watchlist",
    },
}

_OPPORTUNITY_PROFILES = [
    ("new_buy_candidates", "Høyest rangerte kjøpskandidat"),
    ("strongest_momentum", "Sterkest momentum-kandidat"),
    ("strongest_quality_compounders", "Sterkest kvalitetskandidat"),
    ("existing_positions_to_increase", "Sterkest posisjon å øke"),
]


def _display_ticker(ticker: str) -> str:
    normalized = str(ticker or "").strip().upper()
    if not normalized:
        return ""
    if normalized.endswith(".OL"):
        return normalized[:-3]
    return normalized


def _safe_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _owned_ticker_set(portfolio_report) -> set[str]:
    df = valid_portfolio_rows(portfolio_report)
    if df.empty:
        return set()
    return {_display_ticker(ticker) for ticker in df["ticker"]}


def _confidence(priority: int) -> str:
    return _CONFIDENCE_BY_PRIORITY.get(priority, "medium")


def _watchlist_headline_text(ticker, headline) -> str:
    headline = str(headline or "").strip()
    if not headline:
        return _display_ticker(ticker)
    return f"{_display_ticker(ticker)}: {headline[0].lower()}{headline[1:]}"


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


def _recommendation(
    *,
    ticker,
    action,
    reason,
    category,
    priority,
    source,
    merge_group=None,
    dedupe_key=None,
    rule=None,
    briefing_section=None,
    briefing_text=None,
    briefing_category=None,
    **extra,
):
    normalized_ticker = _display_ticker(ticker)
    item = {
        "priority": priority,
        "category": category,
        "action": action,
        "reason": reason,
        "confidence": _confidence(priority),
        "ticker": normalized_ticker,
        "source": source,
        "merge_group": merge_group,
        "dedupe_key": dedupe_key or f"{category}:{normalized_ticker}:{merge_group or action}",
        "rule": rule,
        "briefing_section": briefing_section,
        "briefing_text": briefing_text or action,
        "briefing_category": briefing_category,
    }
    item.update(extra)
    return item


def _apply_daily_action_config(item, config, *, ticker, message, dedupe_key=None):
    display = _display_ticker(ticker)
    action_label = str(item.get("action_label") or "").strip()
    merged_config = dict(config)

    if action_label == "Gjennomgå ordre" and "salgsordre" in message.lower():
        merged_config = {
            **merged_config,
            "category": CATEGORY_ORDERS,
            "priority": 1,
            "merge_group": "order_sell",
            "rule": "sell_order",
            "briefing_section": BRIEFING_SECTION_CRITICAL,
            "briefing_category": "sell",
            "action": "Gjennomgå salgsordre for {ticker}",
        }

    action_text = merged_config["action"].format(ticker=display)
    if merged_config.get("rule") == "portfolio_reduser":
        if action_label == "Vurder salg":
            briefing_text = f"{display}: Reduser / selg"
        else:
            briefing_text = f"{display}: Vurder reduksjon"
    elif merged_config.get("rule") == "sell_order":
        briefing_text = message
    else:
        briefing_text = f"{display}: {message}" if message else action_text

    return _recommendation(
        ticker=ticker,
        action=action_text,
        reason=message,
        category=merged_config["category"],
        priority=merged_config["priority"],
        merge_group=f"{merged_config['merge_group']}:{display}",
        source="daily_flow",
        dedupe_key=dedupe_key,
        rule=merged_config.get("rule"),
        briefing_section=merged_config.get("briefing_section"),
        briefing_text=briefing_text,
        briefing_category=merged_config.get("briefing_category"),
    )


def _collect_from_daily_actions(context) -> list[dict]:
    daily_flow = context.get("daily_flow") or {}
    actions = daily_flow.get("daily_actions")
    if actions is None:
        actions = build_daily_actions(
            context.get("alerts"),
            pending_orders=context.get("pending_orders"),
            portfolio_report=context.get("portfolio_report"),
        )

    recommendations = []
    for item in actions or []:
        action_label = str(item.get("action_label") or "").strip()
        config = _DAILY_FLOW_ACTION_CONFIG.get(action_label)
        if config is None:
            continue

        message = str(item.get("message") or action_label).strip()
        recommendations.append(
            _apply_daily_action_config(
                item,
                config,
                ticker=item.get("ticker", ""),
                message=message,
                dedupe_key=item.get("dedupe_key"),
            )
        )

    return recommendations


def _collect_from_alerts(context) -> list[dict]:
    recommendations = []
    for alert in context.get("alerts") or []:
        alert_type = alert.get("alert_type")
        ticker = alert.get("ticker", "")
        message = str(alert.get("message") or alert.get("title") or "").strip()
        display = _display_ticker(ticker)

        if alert_type == ALERT_TRAILING_STOP_TRIGGERED:
            title = str(alert.get("title") or "Trailing stop trigget").strip()
            text = f"{display}: {title}"
            if message and message not in text:
                text = f"{text} – {message}"
            recommendations.append(
                _recommendation(
                    ticker=ticker,
                    action=f"Gjennomgå {display}",
                    reason=message or title,
                    category=CATEGORY_PORTFOLIO,
                    priority=1,
                    merge_group=f"portfolio_sell:{display}",
                    source="alerts",
                    dedupe_key=alert.get("dedupe_key"),
                    rule="trailing_stop_triggered",
                    briefing_section=BRIEFING_SECTION_CRITICAL,
                    briefing_text=text,
                    briefing_category="trailing_stop",
                )
            )
            continue

        if alert_type == ALERT_NEAR_TRAILING_STOP:
            title = str(alert.get("title") or "Nær trailing stop").strip()
            text = f"{display}: {title}"
            if message and message not in text:
                text = f"{text} – {message}"
            recommendations.append(
                _recommendation(
                    ticker=ticker,
                    action=f"Flytt trailing stop på {display}",
                    reason=message or title,
                    category=CATEGORY_PORTFOLIO,
                    priority=2,
                    merge_group=f"portfolio_stop:{display}",
                    source="alerts",
                    dedupe_key=alert.get("dedupe_key"),
                    rule="trailing_stop_near",
                    briefing_section=BRIEFING_SECTION_IMPORTANT,
                    briefing_text=text,
                    briefing_category="trailing_stop",
                )
            )
            continue

        if alert_type != ALERT_PENDING_ORDER or "salgsordre" not in message.lower():
            continue

        recommendations.append(
            _recommendation(
                ticker=ticker,
                action=f"Gjennomgå salgsordre for {display}",
                reason=message,
                category=CATEGORY_ORDERS,
                priority=1,
                merge_group=f"order_sell:{display}",
                source="alerts",
                dedupe_key=alert.get("dedupe_key"),
                rule="sell_order",
                briefing_section=BRIEFING_SECTION_CRITICAL,
                briefing_text=message,
                briefing_category="sell",
            )
        )

    return recommendations


def _collect_from_earnings(context) -> list[dict]:
    owned_tickers = _owned_ticker_set(context.get("portfolio_report"))
    recommendations = []

    for item in (context.get("earnings_summary") or {}).get("items") or []:
        days_until = _safe_int(item.get("days_until"))
        if (
            days_until is None
            or days_until < 0
            or days_until > EARNINGS_OWNED_CRITICAL_DAYS
            or not item.get("in_portfolio")
        ):
            continue

        ticker = item.get("ticker", "")
        display = _display_ticker(ticker)
        if display not in owned_tickers:
            continue

        text = _earnings_briefing_text(item)
        recommendations.append(
            _recommendation(
                ticker=ticker,
                action=f"Forbered kvartalsrapport for {display}",
                reason=text,
                category=CATEGORY_RISK,
                priority=1,
                merge_group=f"earnings_prepare:{display}",
                source="earnings",
                rule="earnings_critical",
                briefing_section=BRIEFING_SECTION_CRITICAL,
                briefing_text=text,
                briefing_category="earnings",
                days_until=days_until,
                in_portfolio=True,
            )
        )

    recommendations.sort(
        key=lambda entry: (
            entry.get("days_until", 99),
            entry.get("ticker", ""),
        ),
    )
    return recommendations


def _collect_from_analyst(context) -> list[dict]:
    owned_tickers = _owned_ticker_set(context.get("portfolio_report"))
    recommendations = []

    for change in (context.get("analyst_summary") or {}).get("material_changes") or []:
        ticker = change.get("ticker", "")
        endring = str(change.get("Endring") or "").strip()
        if not ticker or not endring:
            continue

        display = _display_ticker(ticker)
        text = f"{display}: {endring}"

        if _is_negative_analyst_change(change):
            if display not in owned_tickers:
                continue
            recommendations.append(
                _recommendation(
                    ticker=ticker,
                    action=f"Gjennomgå {display}",
                    reason=endring,
                    category=CATEGORY_RISK,
                    priority=2,
                    merge_group=f"analyst_downgrade:{display}",
                    source="analyst",
                    rule="analyst_negative",
                    briefing_section=BRIEFING_SECTION_CRITICAL,
                    briefing_text=text,
                    briefing_category="analyst",
                    change_type=change.get("change_type"),
                )
            )
            continue

        if not _is_major_analyst_change(change):
            continue

        recommendations.append(
            _recommendation(
                ticker=ticker,
                action=f"Gjennomgå {display}",
                reason=endring,
                category=CATEGORY_RISK,
                priority=4,
                merge_group=f"analyst_change:{display}",
                source="analyst",
                rule="analyst_major",
                briefing_section=BRIEFING_SECTION_IMPORTANT,
                briefing_text=text,
                briefing_category="analyst",
                change_type=change.get("change_type"),
            )
        )

    return recommendations


def _collect_from_sentiment(context) -> list[dict]:
    recommendations = []
    candidates = [
        item
        for item in (context.get("sentiment_summary") or {}).get("items") or []
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
        display = _display_ticker(ticker)
        label = SENTIMENT_DISPLAY_LABELS.get(
            item.get("sentiment"),
            item.get("sentiment"),
        )
        score = _safe_float(item.get("score"))
        score_text = f" ({score:.2f})" if score is not None else ""
        text = f"{display}: Sterk negativ nyhetstone{score_text} – {label}"
        recommendations.append(
            _recommendation(
                ticker=ticker,
                action=f"Gjennomgå {display}",
                reason=text,
                category=CATEGORY_RISK,
                priority=2,
                merge_group=f"sentiment_risk:{display}",
                source="sentiment",
                rule="strong_negative_sentiment",
                briefing_section=BRIEFING_SECTION_IMPORTANT,
                briefing_text=text,
                briefing_category="sentiment",
                sentiment=item.get("sentiment"),
            )
        )

    return recommendations


def _collect_from_watchlist_advisor(context) -> list[dict]:
    earnings_days = _earnings_days_by_ticker(context.get("earnings_summary"))
    items = list((context.get("watchlist_advisor_output") or {}).get("items") or [])
    items.sort(
        key=lambda item: (
            item.get("priority", 99),
            item.get("ticker", ""),
        ),
    )

    recommendations = []
    for item in items:
        watchlist_action = item.get("watchlist_action")
        if watchlist_action in {ACTION_FOLG_MED, ACTION_VENT}:
            continue

        config = _WATCHLIST_ACTION_CONFIG.get(watchlist_action)
        if config is None:
            continue

        ticker = item.get("ticker", "")
        headline = str(item.get("headline") or "").strip()
        takeaway = str(item.get("takeaway") or headline or "").strip()
        if not ticker:
            continue

        display = _display_ticker(ticker)
        if not takeaway:
            takeaway = format_watchlist_action_label(watchlist_action)

        recommendations.append(
            _recommendation(
                ticker=ticker,
                action=config["action"].format(ticker=display),
                reason=takeaway,
                category=config["category"],
                priority=config["priority"],
                merge_group=f"{config['merge_group']}:{display}",
                source="watchlist_advisor",
                rule=config["rule"],
                briefing_section=config["briefing_section"],
                briefing_text=_watchlist_headline_text(ticker, headline),
                briefing_category=config["briefing_category"],
                watchlist_action=watchlist_action,
                priority_source=item.get("priority"),
                days_until=earnings_days.get(display),
            )
        )

    return recommendations


def _opportunity_advisor_sort_key(item) -> tuple:
    priority = _safe_int(item.get("priority"))
    rank = _safe_int(item.get("rank"))
    profile_rank = _safe_int(item.get("profile_rank"))
    return (
        priority if priority is not None else 99,
        rank if rank is not None else 99,
        profile_rank if profile_rank is not None else 99,
        item.get("ticker", ""),
    )


def _collect_from_opportunity_advisor(context) -> list[dict]:
    items = list((context.get("opportunity_advisor") or {}).get("items") or [])
    items.sort(key=_opportunity_advisor_sort_key)

    recommendations = []
    for item in items[:2]:
        ticker = item.get("ticker", "")
        headline = str(item.get("headline") or "").strip()
        takeaway = str(item.get("takeaway") or headline or "").strip()
        if not ticker:
            continue

        display = _display_ticker(ticker)
        if headline:
            text = f"{display}: {headline}"
            reason = takeaway or headline
        else:
            text = display
            reason = takeaway or "Sterk screener-kandidat."

        recommendations.append(
            _recommendation(
                ticker=ticker,
                action=f"Vurder kjøp av {display}",
                reason=reason,
                category=CATEGORY_BUYING,
                priority=min(item.get("priority", 3), 2),
                merge_group=f"opportunity_buy:{display}",
                source="opportunity_advisor",
                rule="candidate",
                briefing_section=BRIEFING_SECTION_CANDIDATE,
                briefing_text=text,
                briefing_category="candidate",
                headline=headline,
                priority_source=item.get("priority"),
            )
        )

    return recommendations


def _collect_from_key_opportunities(context) -> list[dict]:
    if (context.get("opportunity_advisor") or {}).get("items"):
        return []

    daily_flow = context.get("daily_flow") or {}
    key_opportunities = daily_flow.get("key_opportunities") or {}
    recommendations = []

    for key, reason_prefix in _OPPORTUNITY_PROFILES:
        frame = key_opportunities.get(key)
        if frame is None or getattr(frame, "empty", True):
            continue

        row = frame.iloc[0]
        ticker = row.get("ticker", "")
        if not ticker:
            continue

        display = _display_ticker(ticker)
        recommendations.append(
            _recommendation(
                ticker=ticker,
                action=f"Vurder kjøp av {display}",
                reason=f"{reason_prefix}.",
                category=CATEGORY_BUYING,
                priority=2,
                merge_group=f"opportunity_buy:{display}",
                source="daily_flow",
                rule="candidate",
                briefing_section=BRIEFING_SECTION_CANDIDATE,
                briefing_text=f"{display}: {reason_prefix.lower()}",
                briefing_category="candidate",
            )
        )
        break

    return recommendations


def _collect_from_portfolio_advisor(context) -> list[dict]:
    items = (context.get("advisor_output") or {}).get("items") or []
    recommendations = []

    for item in items:
        ticker = item.get("ticker", "")
        conflict_id = item.get("conflict_id")
        headline = str(item.get("headline") or "").strip()
        takeaway = str(item.get("takeaway") or headline or "").strip()
        if not ticker or not takeaway:
            continue

        display = _display_ticker(ticker)
        priority = item.get("priority", 2)
        merge_group = f"portfolio_review:{display}"
        briefing_section = BRIEFING_SECTION_IMPORTANT
        if conflict_id in {CONFLICT_SELL_VS_ANALYST, CONFLICT_GAIN_VS_STOP}:
            priority = 1
            merge_group = f"portfolio_sell:{display}"
            briefing_section = BRIEFING_SECTION_CRITICAL

        recommendations.append(
            _recommendation(
                ticker=ticker,
                action=f"Gjennomgå {display}",
                reason=takeaway,
                category=CATEGORY_PORTFOLIO,
                priority=priority,
                merge_group=merge_group,
                source="portfolio_advisor",
                rule="portfolio_advisor",
                briefing_section=briefing_section,
                briefing_text=f"{display}: {headline}" if headline else takeaway,
                briefing_category="portfolio",
                conflict_id=conflict_id,
            )
        )

    return recommendations


def _sort_key(recommendation) -> tuple:
    return (
        recommendation.get("priority", 99),
        recommendation.get("ticker", ""),
        recommendation.get("category", ""),
    )


def _dedupe_recommendations(recommendations) -> list[dict]:
    best_by_key: dict[str, dict] = {}

    for recommendation in recommendations:
        merge_group = recommendation.get("merge_group")
        if merge_group:
            key = merge_group
        else:
            key = recommendation.get("dedupe_key") or (
                f"{recommendation.get('category')}:{recommendation.get('ticker')}"
            )

        existing = best_by_key.get(key)
        if existing is None or _sort_key(recommendation) < _sort_key(existing):
            best_by_key[key] = recommendation

    return sorted(best_by_key.values(), key=_sort_key)


def _build_summary(actions) -> str:
    if not actions:
        return "Ingen viktige handlinger anbefales i dag."

    categories = {action.get("category") for action in actions}
    if CATEGORY_PORTFOLIO in categories or CATEGORY_RISK in categories:
        return "Portefølje- og risikotiltak krever oppmerksomhet i dag."
    if CATEGORY_BUYING in categories:
        return "Det finnes kjøpsmuligheter i markedet i dag."
    if CATEGORY_ORDERS in categories:
        return "Ventende ordre bør gjennomgås i dag."
    if CATEGORY_WATCHLIST in categories:
        return "Watchlist har kandidater verdt et nærmere blikk i dag."
    return "Noen punkter er verdt oppmerksomhet i dag."


def build_recommendations(context) -> dict:
    context = context or {}
    raw_recommendations = (
        _collect_from_daily_actions(context)
        + _collect_from_alerts(context)
        + _collect_from_earnings(context)
        + _collect_from_analyst(context)
        + _collect_from_sentiment(context)
        + _collect_from_watchlist_advisor(context)
        + _collect_from_opportunity_advisor(context)
        + _collect_from_key_opportunities(context)
        + _collect_from_portfolio_advisor(context)
    )
    actions = _dedupe_recommendations(raw_recommendations)
    return {
        "model_version": MODEL_VERSION,
        "summary": _build_summary(actions),
        "actions": actions,
    }


def limit_recommendations(recommendations, limit=MAX_RECOMMENDATIONS) -> dict:
    recommendations = recommendations or {}
    actions = list(recommendations.get("actions") or [])[:limit]
    return {
        "model_version": recommendations.get("model_version") or MODEL_VERSION,
        "summary": recommendations.get("summary") or _build_summary(actions),
        "actions": actions,
    }


def is_recommendation_question(question: str) -> bool:
    question = str(question or "").lower().strip()
    if not question:
        return False

    overview_phrases = [
        "morning briefing",
        "morgenbrief",
        "morgen briefing",
        "daily flow",
        "dagens situasjon",
        "dagens oversikt",
    ]
    if any(phrase in question for phrase in overview_phrases):
        return False

    explicit_phrases = [
        "what should i do today",
        "what should i do",
        "today's recommendations",
        "todays recommendations",
        "what are today's recommendations",
        "what are todays recommendations",
        "what should i focus on",
        "anything important today",
        "most important actions",
        "what are the most important actions",
        "hva bør jeg gjøre i dag",
        "hva skal jeg gjøre i dag",
        "hva bør jeg gjøre",
        "dagens anbefalinger",
        "dagens råd",
        "hva bør jeg fokusere på",
        "hva bør jeg fokusere på i dag",
        "viktigste handlinger",
        "viktigste tiltak",
        "hva er viktig i dag",
        "what are today's recommendations?",
        "what should i do today?",
    ]
    if any(phrase in question for phrase in explicit_phrases):
        return True

    if ("important" in question or "viktig" in question) and (
        "today" in question or "i dag" in question
    ):
        action_words = [
            "do",
            "gjøre",
            "action",
            "handling",
            "tiltak",
            "focus",
            "fokus",
            "anbefaling",
            "recommend",
        ]
        if any(word in question for word in action_words):
            return True

    return False


def format_recommendations(recommendations) -> str:
    recommendations = limit_recommendations(recommendations)
    actions = recommendations.get("actions") or []

    if not actions:
        return (
            "Dagens anbefalinger\n\n"
            "Ingen viktige handlinger anbefales i dag."
        )

    lines = ["Dagens anbefalinger", ""]

    for index, action in enumerate(actions, start=1):
        confidence = str(action.get("confidence") or "medium").capitalize()
        lines.extend([
            f"{index}.",
            action.get("action", ""),
            "Begrunnelse",
            action.get("reason", ""),
            "Konfidans",
            confidence,
            "",
        ])

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)
