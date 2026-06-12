import pandas as pd

from src.analyst import format_recommendation_label, get_analyst
from src.company_names import get_company_name
from src.earnings import get_earnings
from src.news import (
    filter_recent_news,
    filter_relevant_news,
    get_news,
    limit_news_per_ticker,
    sort_news_items,
)
from src.sentiment import SENTIMENT_NEGATIVE, build_sentiment_summary
from src.strategy_classification import POSITIVE_TRENDS

METHOD_RULE_V1 = "rule_v1"
SUPPORT_ENRICH_LIMIT = 5
EARNINGS_NEAR_DAYS = 7
STRONG_SCORE_THRESHOLD = 80
QUALITY_FUNDAMENTAL_THRESHOLD = 75
MOMENTUM_RS_THRESHOLD = 10

DISCLAIMER = (
    "Tolkningslag basert på screener-resultat og støttedata. "
    "Endrer ikke score, anbefaling eller porteføljehandlinger."
)

_STRONG_UPTREND = "STERK OPPTREND"
_BEARISH_ANALYST_KEYS = {"sell", "strong_sell"}
_POSITIVE_ANALYST_KEYS = {"strong_buy", "buy"}
_NEUTRAL_ANALYST_KEYS = {"hold"}
_NEGATIVE_ANALYST_MEAN_THRESHOLD = 4.0


def _screener_top_tickers(screener_results, limit=SUPPORT_ENRICH_LIMIT):
    if screener_results is None:
        return []

    if isinstance(screener_results, pd.DataFrame):
        if screener_results.empty:
            return []
        rows = screener_results.head(limit)
        tickers = rows["ticker"].tolist()
    else:
        tickers = [
            row.get("ticker")
            for row in list(screener_results)[:limit]
        ]

    normalized = []
    for ticker in tickers:
        value = str(ticker or "").strip().upper()
        if value and value not in normalized:
            normalized.append(value)

    return normalized


def _summary_item_tickers(summary):
    return {
        str(item.get("ticker") or "").strip().upper()
        for item in (summary or {}).get("items") or []
        if item.get("ticker")
    }


def _merge_summary_items(base_summary, extra_items, tickers_to_add):
    merged = dict(base_summary or {})
    items = [dict(item) for item in merged.get("items") or []]
    existing = _summary_item_tickers(merged)

    for item in extra_items or []:
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker or ticker in existing:
            continue
        if tickers_to_add and ticker not in tickers_to_add:
            continue
        items.append(dict(item))
        existing.add(ticker)

    merged["items"] = items
    return merged


def _build_support_for_tickers(tickers, use_cache=True, today=None):
    from datetime import date

    today = today or date.today()
    analyst_items = []
    earnings_items = []
    news_items = []
    company_names = {
        ticker: get_company_name(ticker) for ticker in tickers
    }

    for ticker in tickers:
        analyst_item = dict(get_analyst(ticker, use_cache=use_cache, today=today))
        analyst_items.append(analyst_item)

        earnings_item = dict(get_earnings(ticker, use_cache=use_cache, today=today))
        earnings_items.append(earnings_item)

        for item in get_news(ticker, use_cache=use_cache, today=today):
            enriched = dict(item)
            enriched["in_portfolio"] = False
            news_items.append(enriched)

    news_items = filter_relevant_news(
        news_items,
        company_names=company_names,
        universe_tickers=tickers,
        limit_per_ticker=False,
    )
    news_items = filter_recent_news(news_items, today=today)
    news_items = limit_news_per_ticker(news_items)
    news_items = sort_news_items(news_items)

    news_summary = {"items": news_items}
    sentiment_summary = build_sentiment_summary(news_summary)

    return {
        "analyst_summary": {"items": analyst_items},
        "earnings_summary": {"items": earnings_items},
        "news_summary": news_summary,
        "sentiment_summary": sentiment_summary,
    }


def enrich_support_summaries_for_screener(
    screener_results,
    analyst_summary=None,
    sentiment_summary=None,
    earnings_summary=None,
    news_summary=None,
    limit=SUPPORT_ENRICH_LIMIT,
    use_cache=True,
    today=None,
):
    tickers = _screener_top_tickers(screener_results, limit=limit)
    if not tickers:
        return analyst_summary, sentiment_summary, earnings_summary, news_summary

    missing_analyst = [
        ticker
        for ticker in tickers
        if ticker not in _summary_item_tickers(analyst_summary)
    ]
    missing_earnings = [
        ticker
        for ticker in tickers
        if ticker not in _summary_item_tickers(earnings_summary)
    ]
    missing_sentiment = [
        ticker
        for ticker in tickers
        if ticker not in _summary_item_tickers(sentiment_summary)
    ]
    missing_news = [
        ticker
        for ticker in tickers
        if ticker not in _summary_item_tickers(news_summary)
    ]

    tickers_to_fetch = sorted(
        set(missing_analyst + missing_earnings + missing_sentiment + missing_news)
    )
    if not tickers_to_fetch:
        return analyst_summary, sentiment_summary, earnings_summary, news_summary

    fetched = _build_support_for_tickers(
        tickers_to_fetch,
        use_cache=use_cache,
        today=today,
    )

    analyst_summary = _merge_summary_items(
        analyst_summary,
        fetched["analyst_summary"]["items"],
        set(missing_analyst),
    )
    earnings_summary = _merge_summary_items(
        earnings_summary,
        fetched["earnings_summary"]["items"],
        set(missing_earnings),
    )
    news_summary = _merge_summary_items(
        news_summary,
        fetched["news_summary"]["items"],
        set(missing_news),
    )
    sentiment_summary = _merge_summary_items(
        sentiment_summary,
        fetched["sentiment_summary"]["items"],
        set(missing_sentiment),
    )

    return analyst_summary, sentiment_summary, earnings_summary, news_summary


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


def _is_positive_trend(trend_regime):
    return trend_regime in POSITIVE_TRENDS


def _is_strong_candidate(row):
    score = _safe_float(row.get("score"))
    relative_strength = _safe_float(row.get("relative_strength_20d"))
    trend_regime = row.get("trend_regime")

    if score is None or score < STRONG_SCORE_THRESHOLD:
        return False

    return trend_regime == _STRONG_UPTREND or (
        relative_strength is not None and relative_strength > 0
    )


def _is_quality_candidate(row):
    fundamental_score = _safe_float(row.get("fundamental_score"))
    fundamental_history_score = _safe_float(
        row.get("fundamental_history_score")
    )

    if fundamental_score is None or fundamental_history_score is None:
        return False

    return (
        fundamental_score >= QUALITY_FUNDAMENTAL_THRESHOLD
        and fundamental_history_score >= QUALITY_FUNDAMENTAL_THRESHOLD
    )


def _is_momentum_candidate(row):
    relative_strength = _safe_float(row.get("relative_strength_20d"))
    trend_regime = row.get("trend_regime")

    if relative_strength is None or relative_strength <= MOMENTUM_RS_THRESHOLD:
        return False

    return _is_positive_trend(trend_regime)


def _is_analyst_positive(analyst_item):
    if not _has_analyst_data(analyst_item):
        return False

    recommendation_key = str(
        analyst_item.get("recommendation_key") or ""
    ).lower().strip()
    return recommendation_key in _POSITIVE_ANALYST_KEYS


def _is_analyst_neutral(analyst_item):
    if not _has_analyst_data(analyst_item):
        return False

    recommendation_key = str(
        analyst_item.get("recommendation_key") or ""
    ).lower().strip()
    return recommendation_key in _NEUTRAL_ANALYST_KEYS


def _has_strong_score(row):
    score = _safe_float(row.get("score"))
    return score is not None and score >= STRONG_SCORE_THRESHOLD


def _has_positive_relative_strength(row):
    relative_strength = _safe_float(row.get("relative_strength_20d"))
    return relative_strength is not None and relative_strength > 0


def _has_weak_fundamental_history(row):
    fundamental_history_score = _safe_float(
        row.get("fundamental_history_score")
    )
    return (
        fundamental_history_score is None
        or fundamental_history_score < QUALITY_FUNDAMENTAL_THRESHOLD
    )


def _relative_strength_why_line(relative_strength):
    if relative_strength is None:
        return None

    if relative_strength > MOMENTUM_RS_THRESHOLD:
        return f"Sterk relativ styrke ({round(relative_strength, 1)}%)"

    if relative_strength > 0:
        return f"Positiv relativ styrke ({round(relative_strength, 1)}%)"

    return None


def _build_why_interesting(row):
    why = []
    score = _safe_float(row.get("score"))
    relative_strength = _safe_float(row.get("relative_strength_20d"))
    trend_regime = row.get("trend_regime")
    rs_line = _relative_strength_why_line(relative_strength)

    if _is_strong_candidate(row):
        if score is not None and score >= STRONG_SCORE_THRESHOLD:
            why.append(f"Høy score ({int(score)})")
        if trend_regime == _STRONG_UPTREND:
            why.append("Sterk trend")
        if rs_line:
            why.append(rs_line)

    if _is_quality_candidate(row):
        why.append("Sterk fundamental kvalitet")
        why.append("Sterk fundamental utvikling")

    if _is_momentum_candidate(row):
        if rs_line and rs_line not in why:
            why.append(rs_line)
        why.append("Positiv kursutvikling")

    seen = set()
    deduped = []
    for item in why:
        if item not in seen:
            seen.add(item)
            deduped.append(item)

    return deduped


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


def _build_watch_out_for(ticker, analyst_item, sentiment_item, earnings_item):
    watch_out = []

    if _earnings_within_days(earnings_item):
        days_until = earnings_item.get("days_until")
        watch_out.append(f"Kvartalsrapport om {days_until} dager")

    if analyst_item is None or not _has_analyst_data(analyst_item):
        watch_out.append("Manglende analytikerdata")
    elif _is_analyst_weak_or_negative(analyst_item):
        label = format_recommendation_label(
            analyst_item.get("recommendation_key")
        )
        if label != "—":
            watch_out.append(f"Svak eller negativ analytikerkonsensus ({label})")
        else:
            watch_out.append("Svak eller negativ analytikerkonsensus")

    if (sentiment_item or {}).get("sentiment") == SENTIMENT_NEGATIVE:
        watch_out.append("Negativ nyhetstone")

    return watch_out


def _candidate_types(row):
    types = []
    if _is_strong_candidate(row):
        types.append("strong")
    if _is_quality_candidate(row):
        types.append("quality")
    if _is_momentum_candidate(row):
        types.append("momentum")
    return types


def _build_headline(candidate_types):
    if "strong" in candidate_types:
        return "Sterk screener-kandidat"
    if "quality" in candidate_types:
        return "Kvalitetskandidat"
    if "momentum" in candidate_types:
        return "Momentumkandidat"
    return "Screener-kandidat"


def _build_takeaway(row, analyst_item, earnings_item, watch_out_for):
    if _has_strong_score(row) and _earnings_within_days(earnings_item):
        return (
            "Interessant kandidat, men rapportdato nærmer seg. "
            "Vurder om du vil vente til etter earnings."
        )

    if _has_strong_score(row) and _is_analyst_positive(analyst_item):
        return (
            "Her peker både modellen og analytikerkonsensus i positiv retning."
        )

    if _has_strong_score(row) and _is_analyst_neutral(analyst_item):
        return (
            "Modellen er mer positiv enn analytikerne. "
            "Det kan være interessant, men bør dobbeltsjekkes."
        )

    if _has_strong_score(row) and _is_quality_candidate(row):
        return (
            "Dette ser ut som en kvalitetskandidat, "
            "ikke bare et kortsiktig momentum-case."
        )

    if _has_strong_score(row) and _has_positive_relative_strength(row):
        base = (
            "Dette er en kandidat der modellen både liker totalbildet "
            "og kursutviklingen."
        )
        if not watch_out_for:
            return (
                f"{base} Siden det ikke er tydelige forbehold, "
                "kan den være verdt nærmere analyse."
            )
        return f"{base} Den bør vurderes nærmere."

    if _has_strong_score(row) and _has_weak_fundamental_history(row):
        return (
            "Kandidaten ser teknisk sterk ut, "
            "men kvalitetsbildet er mindre komplett."
        )

    if watch_out_for:
        return f"Vurder med forbehold: {watch_out_for[0]}."

    return "Ingen tydelige styrker identifisert i screener-reglene."


def _compute_priority(candidate_types, watch_out_for):
    if not candidate_types:
        return 3

    if len(watch_out_for) >= 2:
        return 3

    if "strong" in candidate_types and not watch_out_for:
        return 1

    if len(watch_out_for) <= 1:
        return 2

    return 3


def build_opportunity_advisor_item(
    row,
    analyst_item=None,
    sentiment_item=None,
    earnings_item=None,
):
    row = row or {}
    ticker = str(row.get("ticker") or "").strip().upper()
    candidate_types = _candidate_types(row)
    why_interesting = _build_why_interesting(row)
    watch_out_for = _build_watch_out_for(
        ticker,
        analyst_item,
        sentiment_item,
        earnings_item,
    )

    return {
        "ticker": ticker,
        "headline": _build_headline(candidate_types),
        "why_interesting": why_interesting,
        "watch_out_for": watch_out_for,
        "takeaway": _build_takeaway(
            row,
            analyst_item,
            earnings_item,
            watch_out_for,
        ),
        "priority": _compute_priority(candidate_types, watch_out_for),
    }


def build_opportunity_advisor(
    screener_results,
    analyst_summary=None,
    sentiment_summary=None,
    earnings_summary=None,
    news_summary=None,
    limit=SUPPORT_ENRICH_LIMIT,
    use_cache=True,
):
    if screener_results is None:
        return _empty_opportunity_advisor()

    if isinstance(screener_results, pd.DataFrame):
        if screener_results.empty:
            return _empty_opportunity_advisor()
    elif not list(screener_results):
        return _empty_opportunity_advisor()

    analyst_summary, sentiment_summary, earnings_summary, news_summary = (
        enrich_support_summaries_for_screener(
            screener_results,
            analyst_summary=analyst_summary,
            sentiment_summary=sentiment_summary,
            earnings_summary=earnings_summary,
            news_summary=news_summary,
            limit=limit,
            use_cache=use_cache,
        )
    )

    if isinstance(screener_results, pd.DataFrame):
        rows = screener_results.head(limit).to_dict("records")
    else:
        rows = list(screener_results)[:limit]
        if not rows:
            return _empty_opportunity_advisor()

    analyst_by_ticker = _index_by_ticker((analyst_summary or {}).get("items"))
    sentiment_by_ticker = _index_by_ticker((sentiment_summary or {}).get("items"))
    earnings_by_ticker = _index_by_ticker((earnings_summary or {}).get("items"))

    items = []
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue

        items.append(
            build_opportunity_advisor_item(
                row,
                analyst_item=analyst_by_ticker.get(ticker),
                sentiment_item=sentiment_by_ticker.get(ticker),
                earnings_item=earnings_by_ticker.get(ticker),
            )
        )

    items.sort(
        key=lambda item: (
            item.get("priority", 99),
            -len(item.get("why_interesting") or []),
            item.get("ticker", ""),
        ),
    )

    return {
        "items": items,
        "method": METHOD_RULE_V1,
        "disclaimer": DISCLAIMER,
    }


def _empty_opportunity_advisor():
    return {
        "items": [],
        "method": METHOD_RULE_V1,
        "disclaimer": DISCLAIMER,
    }
