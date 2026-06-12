from datetime import datetime, timezone

import pandas as pd

from src.analyst import format_recommendation_label
from src.portfolio import valid_portfolio_rows
from src.sentiment import SENTIMENT_NEGATIVE, SENTIMENT_POSITIVE

NEAR_TRAILING_STOP_PCT = 3.0
EARNINGS_NEAR_DAYS = 7
ANALYST_UPSIDE_PCT_THRESHOLD = 10.0
GAIN_VS_STOP_PCT_THRESHOLD = 15.0
STRONG_SCORE_THRESHOLD = 70

METHOD_RULE_V1 = "rule_v1"

DISCLAIMER = (
    "Tolkningslag basert på eksisterende signaler. "
    "Endrer ikke score, anbefaling eller porteføljehandlinger."
)

CONFLICT_SELL_VS_ANALYST = "SELL_VS_ANALYST"
CONFLICT_BUY_NEAR_EARNINGS = "BUY_NEAR_EARNINGS"
CONFLICT_GAIN_VS_STOP = "GAIN_VS_STOP"
CONFLICT_NEGATIVE_NEWS_STRONG_TREND = "NEGATIVE_NEWS_STRONG_TREND"

_RULE_PRIORITY = {
    CONFLICT_GAIN_VS_STOP: 1,
    CONFLICT_SELL_VS_ANALYST: 1,
    CONFLICT_BUY_NEAR_EARNINGS: 2,
    CONFLICT_NEGATIVE_NEWS_STRONG_TREND: 3,
}

_RULE_ORDER = {
    CONFLICT_GAIN_VS_STOP: 0,
    CONFLICT_SELL_VS_ANALYST: 1,
    CONFLICT_BUY_NEAR_EARNINGS: 2,
    CONFLICT_NEGATIVE_NEWS_STRONG_TREND: 3,
}

_RULE_DEFINITIONS = {
    CONFLICT_SELL_VS_ANALYST: {
        "headline": "Analytikere positive, risiko peker mot reduksjon",
        "takeaway": (
            "Analytikere er positive, men trend/risiko peker mot reduksjon. "
            "Prioriter risikostyring fremfor kursmål."
        ),
    },
    CONFLICT_BUY_NEAR_EARNINGS: {
        "headline": "Kjøpssignal, rapport nær",
        "takeaway": (
            "Kjøpssignal finnes, men kvartalsrapport er nær. "
            "Vurder om du vil ta rapport-risiko."
        ),
    },
    CONFLICT_GAIN_VS_STOP: {
        "headline": "Gevinst høy, stop nær",
        "takeaway": (
            "Du har betydelig gevinst, men kursen er nær stop-nivået. "
            "Beslutningen handler nå mer om gevinstsikring enn selskapets kvalitet."
        ),
    },
    CONFLICT_NEGATIVE_NEWS_STRONG_TREND: {
        "headline": "Negativ nyhet, sterk trend",
        "takeaway": (
            "Nyhetsbildet er negativt, men trend/score er fortsatt sterk. "
            "Ikke la én nyhet alene overstyre trendbildet."
        ),
    },
}

_PRACTICAL_INTERPRETATIONS = {
    CONFLICT_SELL_VS_ANALYST: (
        "Jeg ville fulgt kursutvikling og stop-nivå tettere enn analytikernes "
        "kursmål akkurat nå."
    ),
    CONFLICT_GAIN_VS_STOP: (
        "Jeg ville prioritert gevinstsikring og stop-nivå fremfor å vurdere "
        "om selskapet fortsatt er «godt nok»."
    ),
    CONFLICT_BUY_NEAR_EARNINGS: (
        "Jeg ville vurdert om kjøpet kan vente til etter rapporten, eller "
        "redusert størrelse for å begrense event-risiko."
    ),
    CONFLICT_NEGATIVE_NEWS_STRONG_TREND: (
        "Jeg ville ikke solgt blindt på én negativ overskrift så lenge trend "
        "og score fortsatt er sterke."
    ),
}

_SELL_PORTFOLIO_ACTIONS = {
    "REDUSER / SELG",
    "VURDER REDUKSJON",
}

_BULLISH_ANALYST_KEYS = {
    "buy",
    "strong_buy",
}

_BUY_RECOMMENDATION = "KJØP / ØK"
_AVOID_RECOMMENDATION = "UNNGÅ / SELG"
_STRONG_UPTREND = "STERK OPPTREND"
_MODERATE_UPTREND = "MODERAT OPPTREND"
_WEAK_TREND = "SVAK / NEGATIV TREND"

_CAUTION_PORTFOLIO_ACTIONS = {
    "REDUSER / SELG",
    "VURDER REDUKSJON",
    "VURDER GEVINSTSIKRING",
}

_HOLD_PORTFOLIO_ACTIONS = {
    "HOLD / LA VINNER LØPE",
    "HOLD",
    "HOLD / FØLG MED",
    "FØLG MED / IKKE ØK",
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


def _is_analyst_bullish(analyst_item):
    if not analyst_item:
        return False

    recommendation_key = str(analyst_item.get("recommendation_key") or "").lower()
    if recommendation_key in _BULLISH_ANALYST_KEYS:
        return True

    upside_pct = _safe_float(analyst_item.get("upside_pct"))
    return upside_pct is not None and upside_pct > ANALYST_UPSIDE_PCT_THRESHOLD


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


def _is_trailing_stop_near_or_triggered(row):
    if row.get("trailing_stop_triggered") is True:
        return True

    price = _safe_float(row.get("current_price"))
    trailing = _safe_float(row.get("trailing_stop_loss"))

    if price is None or trailing is None or price <= 0:
        return False

    if price <= trailing:
        return True

    distance_pct = (price - trailing) / price * 100
    return distance_pct <= NEAR_TRAILING_STOP_PCT


def _sentiment_is_negative(sentiment_item):
    return (sentiment_item or {}).get("sentiment") == SENTIMENT_NEGATIVE


def _make_conflict(ticker, conflict_id):
    definition = _RULE_DEFINITIONS[conflict_id]
    return {
        "ticker": ticker,
        "conflict_id": conflict_id,
        "headline": definition["headline"],
        "takeaway": definition["takeaway"],
        "priority": _RULE_PRIORITY[conflict_id],
    }


def _evaluate_ticker_conflicts(ticker, row, analyst_item, sentiment_item, earnings_item):
    conflicts = []

    portefølje_råd = row.get("portefølje_råd")
    if portefølje_råd in _SELL_PORTFOLIO_ACTIONS and _is_analyst_bullish(analyst_item):
        conflicts.append(_make_conflict(ticker, CONFLICT_SELL_VS_ANALYST))

    if row.get("anbefaling") == _BUY_RECOMMENDATION and _earnings_within_days(
        earnings_item,
    ):
        conflicts.append(_make_conflict(ticker, CONFLICT_BUY_NEAR_EARNINGS))

    gain_pct = _safe_float(row.get("unrealized_gain_pct"))
    if (
        gain_pct is not None
        and gain_pct > GAIN_VS_STOP_PCT_THRESHOLD
        and _is_trailing_stop_near_or_triggered(row)
    ):
        conflicts.append(_make_conflict(ticker, CONFLICT_GAIN_VS_STOP))

    score = _safe_float(row.get("score"))
    if _sentiment_is_negative(sentiment_item) and (
        row.get("trend_regime") == _STRONG_UPTREND
        or (score is not None and score >= STRONG_SCORE_THRESHOLD)
    ):
        conflicts.append(_make_conflict(ticker, CONFLICT_NEGATIVE_NEWS_STRONG_TREND))

    return conflicts


def _sort_conflicts(conflicts):
    return sorted(
        conflicts,
        key=lambda item: (
            item["priority"],
            _RULE_ORDER[item["conflict_id"]],
        ),
    )


def _resolve_ticker_conflicts(all_conflicts):
    by_ticker = {}
    for conflict in all_conflicts:
        ticker = conflict["ticker"]
        by_ticker.setdefault(ticker, []).append(conflict)

    items = []
    secondary_items = []

    for ticker in sorted(by_ticker):
        sorted_conflicts = _sort_conflicts(by_ticker[ticker])
        items.append(sorted_conflicts[0])
        secondary_items.extend(sorted_conflicts[1:])

    items = _sort_conflicts(items)
    secondary_items = _sort_conflicts(secondary_items)
    return items, secondary_items


def build_advisor_output(
    portfolio_report,
    analyst_summary=None,
    sentiment_summary=None,
    earnings_summary=None,
):
    df = valid_portfolio_rows(portfolio_report)
    if df.empty:
        return _empty_advisor_output()

    analyst_by_ticker = _index_by_ticker((analyst_summary or {}).get("items"))
    sentiment_by_ticker = _index_by_ticker((sentiment_summary or {}).get("items"))
    earnings_by_ticker = _index_by_ticker((earnings_summary or {}).get("items"))

    all_conflicts = []
    for _, row in df.iterrows():
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue

        all_conflicts.extend(
            _evaluate_ticker_conflicts(
                ticker,
                row,
                analyst_by_ticker.get(ticker),
                sentiment_by_ticker.get(ticker),
                earnings_by_ticker.get(ticker),
            )
        )

    items, secondary_items = _resolve_ticker_conflicts(all_conflicts)

    return {
        "items": items,
        "secondary_items": secondary_items,
        "last_updated": _utc_now_iso(),
        "method": METHOD_RULE_V1,
        "disclaimer": DISCLAIMER,
    }


def _empty_advisor_output():
    return {
        "items": [],
        "secondary_items": [],
        "last_updated": _utc_now_iso(),
        "method": METHOD_RULE_V1,
        "disclaimer": DISCLAIMER,
    }


def advisor_items_by_ticker(advisor_output):
    return {
        str(item.get("ticker") or "").strip().upper(): item
        for item in (advisor_output or {}).get("items") or []
        if item.get("ticker")
    }


def format_advisor_cell(advisor_item):
    if not advisor_item:
        return ""

    headline = advisor_item.get("headline") or ""
    takeaway = advisor_item.get("takeaway") or ""
    if headline and takeaway:
        return f"{headline}: {takeaway}"
    return headline or takeaway


def _portfolio_row_for_ticker(portfolio_report, ticker):
    df = valid_portfolio_rows(portfolio_report)
    if df.empty:
        return None

    normalized = str(ticker or "").strip().upper()
    matches = df[df["ticker"].astype(str).str.strip().str.upper() == normalized]
    if matches.empty:
        return None

    return matches.iloc[0].to_dict()


def _alert_signals_for_ticker(alerts, ticker):
    normalized = str(ticker or "").strip().upper()
    signals = []

    for alert in alerts or []:
        if str(alert.get("ticker") or "").strip().upper() != normalized:
            continue

        title = str(alert.get("title") or "").strip()
        if title and title not in signals:
            signals.append(title)

    return signals


def _collect_caution_signals(row, analyst_item, sentiment_item, earnings_item, alerts, ticker):
    signals = []
    row = row or {}

    trend_regime = row.get("trend_regime")
    if trend_regime == _WEAK_TREND:
        signals.append("Svak / negativ trend")

    portefølje_råd = row.get("portefølje_råd")
    if portefølje_råd in _CAUTION_PORTFOLIO_ACTIONS:
        signals.append(f"Porteføljehandling: {portefølje_råd}")

    if row.get("anbefaling") == _AVOID_RECOMMENDATION:
        signals.append(f"Modellanbefaling: {_AVOID_RECOMMENDATION}")

    if row.get("trailing_stop_triggered") is True:
        signals.append("Trailing stop trigget")
    elif _is_trailing_stop_near_or_triggered(row):
        signals.append("Nær trailing stop")

    gain_pct = _safe_float(row.get("unrealized_gain_pct"))
    if gain_pct is not None and gain_pct > GAIN_VS_STOP_PCT_THRESHOLD:
        signals.append(f"Stor gevinst i porteføljen ({round(gain_pct, 1)}%)")

    relative_strength = _safe_float(row.get("relative_strength_20d"))
    if relative_strength is not None and relative_strength < -5:
        signals.append(f"Svak relativ styrke ({round(relative_strength, 1)}%)")

    if _sentiment_is_negative(sentiment_item):
        signals.append("Negativ nyhetstone")

    earnings_item = earnings_item or {}
    days_until = earnings_item.get("days_until")
    if _earnings_within_days(earnings_item):
        signals.append(f"Kvartalsrapport om {days_until} dager")

    for alert_signal in _alert_signals_for_ticker(alerts, ticker):
        if alert_signal not in signals:
            signals.append(alert_signal)

    return signals


def _collect_hold_signals(row, analyst_item, sentiment_item, earnings_item):
    signals = []
    row = row or {}
    analyst_item = analyst_item or {}

    if _is_analyst_bullish(analyst_item):
        recommendation_key = analyst_item.get("recommendation_key")
        label = format_recommendation_label(recommendation_key)
        if label != "—":
            signals.append(f"Analytikere er positive ({label})")
        else:
            signals.append("Analytikere er positive")

    upside_pct = _safe_float(analyst_item.get("upside_pct"))
    if upside_pct is not None and upside_pct > 0:
        signals.append(f"Kursmål viser {round(upside_pct, 1)}% oppside")

    trend_regime = row.get("trend_regime")
    if trend_regime in {_STRONG_UPTREND, _MODERATE_UPTREND}:
        signals.append(trend_regime)

    score = _safe_float(row.get("score"))
    if score is not None and score >= STRONG_SCORE_THRESHOLD:
        signals.append(f"Sterk total score ({int(score)})")

    if row.get("anbefaling") == _BUY_RECOMMENDATION:
        signals.append(f"Modellanbefaling: {_BUY_RECOMMENDATION}")

    portefølje_råd = row.get("portefølje_råd")
    if portefølje_råd in _HOLD_PORTFOLIO_ACTIONS:
        signals.append(f"Porteføljehandling: {portefølje_råd}")

    relative_strength = _safe_float(row.get("relative_strength_20d"))
    if relative_strength is not None and relative_strength > 0:
        signals.append(f"Positiv relativ styrke ({round(relative_strength, 1)}%)")

    if (sentiment_item or {}).get("sentiment") == SENTIMENT_POSITIVE:
        signals.append("Positiv nyhetstone")

    if not _earnings_within_days(earnings_item or {}) and (earnings_item or {}).get(
        "earnings_date",
    ):
        signals.append("Ingen umiddelbar rapport-risiko de neste 7 dagene")

    return signals


def build_advisor_detail(
    ticker,
    advisor_item,
    portfolio_report=None,
    analyst_summary=None,
    sentiment_summary=None,
    earnings_summary=None,
    alerts=None,
):
    if not advisor_item:
        return None

    normalized = str(ticker or "").strip().upper()
    if not normalized:
        return None

    row = _portfolio_row_for_ticker(portfolio_report, normalized)
    analyst_by_ticker = _index_by_ticker((analyst_summary or {}).get("items"))
    sentiment_by_ticker = _index_by_ticker((sentiment_summary or {}).get("items"))
    earnings_by_ticker = _index_by_ticker((earnings_summary or {}).get("items"))

    conflict_id = advisor_item.get("conflict_id")
    caution_signals = _collect_caution_signals(
        row,
        analyst_by_ticker.get(normalized),
        sentiment_by_ticker.get(normalized),
        earnings_by_ticker.get(normalized),
        alerts,
        normalized,
    )
    hold_signals = _collect_hold_signals(
        row,
        analyst_by_ticker.get(normalized),
        sentiment_by_ticker.get(normalized),
        earnings_by_ticker.get(normalized),
    )

    return {
        "ticker": normalized,
        "advisor": {
            "headline": advisor_item.get("headline"),
            "takeaway": advisor_item.get("takeaway"),
            "conflict_id": conflict_id,
        },
        "caution_signals": caution_signals,
        "hold_signals": hold_signals,
        "practical_interpretation": _PRACTICAL_INTERPRETATIONS.get(conflict_id, ""),
    }


def build_advisor_details(
    advisor_output,
    portfolio_report,
    analyst_summary=None,
    sentiment_summary=None,
    earnings_summary=None,
    alerts=None,
):
    details = {}
    for ticker, advisor_item in advisor_items_by_ticker(advisor_output).items():
        detail = build_advisor_detail(
            ticker,
            advisor_item,
            portfolio_report=portfolio_report,
            analyst_summary=analyst_summary,
            sentiment_summary=sentiment_summary,
            earnings_summary=earnings_summary,
            alerts=alerts,
        )
        if detail:
            details[ticker] = detail

    return details


def advisor_detail_tickers(advisor_output):
    return [
        str(item.get("ticker") or "").strip().upper()
        for item in (advisor_output or {}).get("items") or []
        if item.get("ticker")
    ]


def _format_advisor_detail_lines(detail, summary_heading):
    if not detail:
        return []

    lines = [
        summary_heading,
        detail["advisor"].get("takeaway") or "",
        "",
        "Taler for varsomhet:",
    ]
    caution_signals = detail.get("caution_signals") or []
    if caution_signals:
        lines.extend(f"- {signal}" for signal in caution_signals)
    else:
        lines.append("- Ingen tydelige varsomhetssignaler identifisert.")

    lines.extend(["", "Taler for å holde/vente:"])
    hold_signals = detail.get("hold_signals") or []
    if hold_signals:
        lines.extend(f"- {signal}" for signal in hold_signals)
    else:
        lines.append("- Ingen tydelige holde-/ventesignaler identifisert.")

    interpretation = detail.get("practical_interpretation")
    if interpretation:
        lines.extend(["", "Praktisk tolkning:", interpretation])

    return lines


def format_advisor_detail_markdown(detail):
    if not detail:
        return ""

    lines = _format_advisor_detail_lines(detail, "**Advisor**")
    markdown_lines = []
    for line in lines:
        if line == "Taler for varsomhet:":
            markdown_lines.append("**Taler for varsomhet**")
        elif line == "Taler for å holde/vente:":
            markdown_lines.append("**Taler for å holde/vente**")
        elif line == "Praktisk tolkning:":
            markdown_lines.append("**Praktisk tolkning**")
        else:
            markdown_lines.append(line)

    return "\n".join(markdown_lines)


def format_advisor_detail_answer(detail):
    if not detail:
        return ""

    ticker = detail.get("ticker") or ""
    lines = [ticker, ""] if ticker else []
    lines.extend(_format_advisor_detail_lines(detail, "Kort oppsummering:"))
    return "\n".join(lines).strip()
