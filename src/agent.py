import re

import pandas as pd

from src.analysis import _format_gain_pct, generate_text_report
from src.ranking import ranking_table
from src.advisor import build_advisor_details, format_advisor_detail_answer
from src.config import load_watchlists
from src.context import screening_region_meta
from src.opportunity_advisor import build_opportunity_advisor, format_relative_context_short
from src.portfolio import valid_portfolio_rows
from src.watchlist_advisor import (
    ACTION_AVVENT_EARNINGS,
    ACTION_FJERN_FRA_WATCHLIST,
    ACTION_FLYTT_TIL_RESEARCH,
    ACTION_FOLG_MED,
    ACTION_VENT,
    ACTION_VURDER_KJOP,
    format_watchlist_action_label,
    format_watchlist_advisor_detail,
)
from src.screener import screen_nordics, screen_obx, screen_us_large
from src.analyst import (
    DISCLAIMER as ANALYST_DISCLAIMER,
    analyst_tickers,
    find_analyst_item,
    format_analyst_item_answer,
    format_analyst_material_changes_answer,
    format_portfolio_analyst_upside_answer,
    format_weakest_analyst_consensus_answer,
)
from src.score_explainability import (
    build_score_explanation,
    extract_score_explanation_ticker,
    find_stock_analysis,
    format_score_explanation,
    is_score_explanation_question,
)
from src.strategy_profiles import (
    _PROFILE_LABELS,
    format_strategy_profile_answer,
    is_strategy_profile_question,
)


def format_buy_recommendation(recommendation):
    if recommendation == "UNNGÅ / SELG":
        return "IKKE NY KJØPSKANDIDAT NÅ"

    if recommendation == "KJØP / ØK":
        return "AKTUELL KJØPSKANDIDAT"

    if recommendation == "HOLD / OBSERVER":
        return "OBSERVER / VENT PÅ BEDRE INNGANG"

    return recommendation


def _format_reasons(reasons):
    if isinstance(reasons, list):
        return "\n".join(f"- {reason}" for reason in reasons)

    if reasons is None:
        return "- Ingen begrunnelse tilgjengelig"

    return str(reasons)


def _format_ranking_table(df, limit=10):
    table = ranking_table(df).head(limit)

    if table.empty:
        return "Ingen aksjer å vise."

    lines = []

    for i, (_, row) in enumerate(table.iterrows(), start=1):
        lines.append(
            f"{i}. {row['ticker']} | "
            f"score {row['score']} | "
            f"{row['anbefaling']} | "
            f"{row['trend_regime']} | "
            f"RS {row['relative_strength_20d']}% | "
            f"fund {row['fundamental_score']} | "
            f"hist {row['fundamental_history_score']}"
        )

    return "\n".join(lines)


def _rank_watchlist_report(watchlist_report):
    return watchlist_report.sort_values(
        by=[
            "score",
            "fundamental_history_score",
            "fundamental_score",
            "relative_strength_20d",
        ],
        ascending=[False, False, False, False],
    )


def _screen_buy_candidates(watchlist_report):
    return _rank_watchlist_report(
        watchlist_report[
            watchlist_report["anbefaling"] == "KJØP / ØK"
        ]
    )


def _screen_quality_companies(watchlist_report):
    return _rank_watchlist_report(
        watchlist_report[
            (watchlist_report["fundamental_score"] >= 70)
            & (watchlist_report["fundamental_history_score"] >= 70)
            & (watchlist_report["score"] >= 55)
        ]
    )


def _screen_growth_with_trend(watchlist_report):
    return _rank_watchlist_report(
        watchlist_report[
            (watchlist_report["score"] >= 60)
            & (watchlist_report["fundamental_history_score"] >= 70)
            & (watchlist_report["relative_strength_20d"] > 0)
            & (watchlist_report["trend_regime"] == "STERK OPPTREND")
        ]
    )


def _screen_strong_fundamentals_not_buy(watchlist_report):
    return _rank_watchlist_report(
        watchlist_report[
            (watchlist_report["fundamental_score"] >= 70)
            & (watchlist_report["fundamental_history_score"] >= 70)
            & (watchlist_report["anbefaling"] != "KJØP / ØK")
        ]
    )


def _format_ticker_list(df, limit=3):
    if df is None or df.empty or "ticker" not in df.columns:
        return "Ingen"

    return ", ".join(df["ticker"].head(limit).tolist())


def _format_risk_lines(risk_alerts, limit=5):
    if not risk_alerts:
        return ["Ingen kritiske risikovarsler."]

    lines = []

    for key in (
        "near_trailing_stop",
        "weakening_positions",
        "large_drawdowns",
        "other_alerts",
    ):
        df = risk_alerts.get(key)
        if df is None or df.empty:
            continue

        for _, row in df.iterrows():
            detail = row.get("details") or row.get("alert", "")
            lines.append(f"- {row['ticker']}: {detail}")

    concentration = risk_alerts.get("concentration_risk") or {}
    for item in concentration.get("alerts", []):
        lines.append(f"- {item['alert']}: {item['details']}")

    if not lines:
        return ["Ingen kritiske risikovarsler."]

    return lines[:limit]


def _get_dashboard(context):
    return context.get("dashboard") or {}


def _get_daily_flow(context):
    return context.get("daily_flow") or {}


def _get_earnings_summary(context):
    return (
        context.get("earnings_summary")
        or _get_dashboard(context).get("earnings_summary")
        or {}
    )


def _get_analyst_summary(context):
    return (
        context.get("analyst_summary")
        or _get_dashboard(context).get("analyst_summary")
        or {}
    )


def _get_advisor_output(context):
    return (
        context.get("advisor_output")
        or _get_dashboard(context).get("advisor_output")
        or {}
    )


def _get_advisor_details(context):
    details = context.get("advisor_details")
    if details is not None:
        return details

    dashboard = _get_dashboard(context)
    return build_advisor_details(
        _get_advisor_output(context),
        context.get("portfolio_report"),
        analyst_summary=(
            context.get("analyst_summary")
            or dashboard.get("analyst_summary")
        ),
        sentiment_summary=(
            context.get("sentiment_summary")
            or dashboard.get("sentiment_summary")
        ),
        earnings_summary=_get_earnings_summary(context),
        alerts=context.get("alerts") or [],
    )


def _is_advisor_question(question):
    if any(
        phrase in question
        for phrase in [
            "motstridende signal",
            "advisor-signalet",
            "advisor signalet",
            "advisor-tolkning",
            "advisor tolkning",
            "konflikten i",
            "konflikt i",
            "hvorfor sier agenten",
            "forklar advisor",
        ]
    ):
        return True

    if "advisor" in question and any(
        word in question
        for word in ["forklar", "konflikt", "hvorfor", "signal", "tolkning"]
    ):
        return True

    return False


def _is_advisor_list_question(question):
    return any(
        phrase in question
        for phrase in [
            "hvilke aksjer",
            "motstridende signaler",
            "motstridende signal",
        ]
    )


def _advisor_tickers_for_matching(context):
    tickers = set()

    for item in (_get_advisor_output(context).get("items") or []):
        ticker = str(item.get("ticker") or "").strip().upper()
        if ticker:
            tickers.add(ticker)

    for ticker in context.get("watchlist") or []:
        normalized = str(ticker).strip().upper()
        if normalized:
            tickers.add(normalized)

    portfolio_report = context.get("portfolio_report")
    if portfolio_report is not None and not portfolio_report.empty:
        if "ticker" in portfolio_report.columns:
            for ticker in portfolio_report["ticker"]:
                normalized = str(ticker).strip().upper()
                if normalized:
                    tickers.add(normalized)

    return sorted(tickers, key=len, reverse=True)


def _extract_advisor_ticker(question, context):
    for ticker in _advisor_tickers_for_matching(context):
        if ticker.lower() in question:
            return ticker

    return None


def _format_advisor_list_answer(context):
    items = _get_advisor_output(context).get("items") or []
    if not items:
        return "Advisor: Ingen motstridende signaler i porteføljen akkurat nå."

    lines = ["Aksjer med motstridende signaler:", ""]
    for item in items:
        headline = item.get("headline") or item.get("conflict_id") or "Konflikt"
        lines.append(f"- {item['ticker']}: {headline}")

    return "\n".join(lines)


def _format_advisor_ticker_answer(context, ticker):
    normalized = str(ticker or "").strip().upper()
    detail = _get_advisor_details(context).get(normalized)
    if not detail:
        advisor_item = next(
            (
                item
                for item in (_get_advisor_output(context).get("items") or [])
                if str(item.get("ticker") or "").strip().upper() == normalized
            ),
            None,
        )
        if advisor_item:
            return (
                f"Advisor for {normalized}: {advisor_item.get('takeaway', '')}"
            ).strip()

        return (
            f"Advisor for {normalized}: Ingen motstridende signaler identifisert."
        )

    return format_advisor_detail_answer(detail)


def _format_advisor_answer(context, question):
    if _is_advisor_list_question(question):
        return _format_advisor_list_answer(context)

    ticker = _extract_advisor_ticker(question, context)
    if ticker:
        return _format_advisor_ticker_answer(context, ticker)

    items = _get_advisor_output(context).get("items") or []
    if len(items) == 1:
        return _format_advisor_ticker_answer(context, items[0]["ticker"])

    if items:
        return _format_advisor_list_answer(context)

    return (
        "Advisor: Ingen motstridende signaler i porteføljen. "
        "Spesifiser ticker, for eksempel «Hvorfor sier agenten dette om NVDA?»."
    )


_WATCHLIST_ADVISOR_GROUP_ORDER = (
    (ACTION_VURDER_KJOP, "Vurder kjøp"),
    (ACTION_AVVENT_EARNINGS, "Avvent earnings"),
    (ACTION_FOLG_MED, "Følg med"),
    (ACTION_VENT, "Vent"),
    (ACTION_FJERN_FRA_WATCHLIST, "Fjern fra watchlist"),
    (ACTION_FLYTT_TIL_RESEARCH, "Flytt til research"),
)


def _get_watchlist_advisor_output(context):
    return context.get("watchlist_advisor_output") or {}


def _watchlist_advisor_items_by_ticker(context):
    return {
        str(item.get("ticker") or "").strip().upper(): item
        for item in (_get_watchlist_advisor_output(context).get("items") or [])
        if item.get("ticker")
    }


def _watchlist_advisor_tickers_for_matching(context):
    return sorted(
        _watchlist_advisor_items_by_ticker(context).keys(),
        key=len,
        reverse=True,
    )


def _is_watchlist_advisor_question(question):
    if any(
        phrase in question
        for phrase in [
            "watchlist-advisor",
            "watchlist advisor",
            "watchlist-råd",
            "watchlist råd",
        ]
    ):
        return True

    if any(
        phrase in question
        for phrase in [
            "hvilke aksjer bør jeg vurdere å kjøpe fra watchlist",
            "hvilke aksjer bør jeg vente med",
            "hvilke aksjer bør fjernes fra watchlist",
            "hvilke aksjer avventer earnings",
        ]
    ):
        return True

    if "hvorfor sier agenten at jeg skal" in question:
        return True

    if "watchlist" in question and any(
        phrase in question
        for phrase in [
            "vurdere å kjøpe",
            "fjernes",
            "fjern fra",
            "avventer earnings",
        ]
    ):
        return True

    return False


def _is_watchlist_advisor_list_question(question):
    return "hvilke aksjer" in question


def _watchlist_advisor_filter_action(question):
    if any(
        phrase in question
        for phrase in [
            "vurdere å kjøpe",
            "vurdere a kjope",
            "kjøpe fra watchlist",
            "kjope fra watchlist",
        ]
    ):
        return ACTION_VURDER_KJOP

    if "avventer earnings" in question or "avvent earnings" in question:
        return ACTION_AVVENT_EARNINGS

    if (
        "fjernes fra watchlist" in question
        or "fjern fra watchlist" in question
    ):
        return ACTION_FJERN_FRA_WATCHLIST

    if "vente med" in question or "bør jeg vente" in question:
        return ACTION_VENT

    if "følg med" in question or "folg med" in question:
        return ACTION_FOLG_MED

    if "flytt til research" in question:
        return ACTION_FLYTT_TIL_RESEARCH

    return None


def _extract_explicit_watchlist_ticker(question):
    patterns = (
        r"\bom\s+([a-z0-9.\-]+)\b",
        r"\bvente med\s+([a-z0-9.\-]+)\b",
        r"\bvent med\s+([a-z0-9.\-]+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, question)
        if match:
            return str(match.group(1)).strip().upper()

    return None


def _extract_watchlist_advisor_ticker(question, context):
    for ticker in _watchlist_advisor_tickers_for_matching(context):
        if ticker.lower() in question:
            return ticker

    return _extract_explicit_watchlist_ticker(question)


def _is_watchlist_advisor_ticker_question(question):
    return any(
        phrase in question
        for phrase in [
            "watchlist-advisor",
            "watchlist advisor",
            "watchlist-råd",
            "watchlist råd",
            "hvorfor sier agenten at jeg skal",
            "hva sier",
        ]
    )


def _format_watchlist_advisor_grouped_answer(context, action_filter=None):
    items = _get_watchlist_advisor_output(context).get("items") or []
    if action_filter:
        items = [
            item
            for item in items
            if item.get("watchlist_action") == action_filter
        ]

    if action_filter:
        label = format_watchlist_action_label(action_filter)
        lines = ["Watchlist-råd", "", f"{label}:"]
        if not items:
            lines.append("- Ingen aksjer akkurat nå.")
            return "\n".join(lines)

        for item in items:
            lines.append(
                f"- {item['ticker']}: {item.get('takeaway', '')}"
            )
        return "\n".join(lines)

    if not items:
        return (
            "Watchlist-råd\n\n"
            "Ingen tydelige watchlist-råd akkurat nå."
        )

    by_action = {}
    for item in items:
        by_action.setdefault(item.get("watchlist_action"), []).append(item)

    lines = ["Watchlist-råd", ""]
    for action, label in _WATCHLIST_ADVISOR_GROUP_ORDER:
        lines.append(f"{label}:")
        group = by_action.get(action) or []
        if group:
            for item in group:
                lines.append(
                    f"- {item['ticker']}: {item.get('takeaway', '')}"
                )
        else:
            lines.append("- Ingen")
        lines.append("")

    return "\n".join(lines).strip()


def _format_watchlist_advisor_ticker_answer(context, ticker):
    normalized = str(ticker or "").strip().upper()
    item = _watchlist_advisor_items_by_ticker(context).get(normalized)
    if not item:
        return (
            f"Watchlist-advisor for {normalized}: "
            "Ingen watchlist-råd identifisert. "
            "Aksjen kan være eid, ikke på watchlist, eller uten tydelig råd."
        )

    detail = format_watchlist_advisor_detail(item) or {}
    label = format_watchlist_action_label(item.get("watchlist_action"))

    lines = [
        normalized,
        "",
        "Handling:",
        label,
        "",
        "Hvorfor:",
    ]
    why = detail.get("why") or []
    if why:
        lines.extend(f"- {line}" for line in why)
    else:
        lines.append("- Ingen tydelige årsaker identifisert.")

    lines.extend(["", "Forbehold:"])
    watch_out_for = detail.get("watch_out_for") or []
    if watch_out_for:
        lines.extend(f"- {line}" for line in watch_out_for)
    else:
        lines.append("- Ingen tydelige forbehold identifisert.")

    lines.extend(["", "Tolkning:", detail.get("takeaway") or ""])
    return "\n".join(lines)


def _answer_watchlist_advisor_question(context, question):
    items = _get_watchlist_advisor_output(context).get("items") or []
    action_filter = _watchlist_advisor_filter_action(question)
    ticker = _extract_watchlist_advisor_ticker(question, context)

    if ticker and _is_watchlist_advisor_ticker_question(question):
        return _format_watchlist_advisor_ticker_answer(context, ticker)

    if _is_watchlist_advisor_list_question(question) or action_filter:
        return _format_watchlist_advisor_grouped_answer(
            context,
            action_filter=action_filter,
        )

    if ticker:
        return _format_watchlist_advisor_ticker_answer(context, ticker)

    if len(items) == 1:
        return _format_watchlist_advisor_ticker_answer(
            context,
            items[0]["ticker"],
        )

    return _format_watchlist_advisor_grouped_answer(context)


def _is_pending_orders_question(question):
    if any(
        phrase in question
        for phrase in [
            "pending ordre",
            "ventende ordre",
            "pending order",
        ]
    ):
        return True

    if "ordrehistorikk" in question or "ordre historikk" in question:
        return False

    if "ordre" not in question:
        return False

    if question.strip() in {"ordre", "ordre?"}:
        return True

    return any(
        word in question
        for word in [
            "pending",
            "ventende",
            "vis",
            "har jeg",
            "status",
            "liste",
        ]
    )


def _is_portfolio_summary_question(question):
    if "portefølje" not in question and "portefolje" not in question:
        return False

    if any(
        phrase in question
        for phrase in [
            "bør jeg holde",
            "bør jeg selge",
            "bør jeg redusere",
            "bør jeg øke",
            "min posisjon",
        ]
    ):
        return False

    return True


def _is_weakest_positions_question(question):
    return any(
        phrase in question
        for phrase in [
            "svakeste posisjon",
            "svakeste posisjoner",
            "svekkende posisjon",
            "svekkende posisjoner",
            "svake posisjon",
            "svake posisjoner",
        ]
    )


def _is_strong_winners_question(question):
    return any(
        phrase in question
        for phrase in [
            "største gevinst",
            "største gevinster",
            "sterke vinnere",
            "største vinner",
            "største vinnere",
            "beste vinner",
        ]
    )


def _is_trailing_stop_question(question):
    return "trailing stop" in question or "trailingstop" in question


def _is_risk_question(question):
    return any(
        phrase in question
        for phrase in [
            "risiko",
            "risikovarsel",
            "risikovarsler",
            "varsler",
        ]
    )


def _format_pending_orders_answer(context):
    daily_flow = _get_daily_flow(context)
    pending = daily_flow.get("pending_orders") or {}
    summary = pending.get("summary", "Ingen ventende ordre.")
    orders_df = pending.get("orders")

    if orders_df is None or orders_df.empty:
        return f"Pending ordre: {summary}"

    lines = ["Pending ordre:", summary, ""]

    for _, row in orders_df.head(5).iterrows():
        parts = [str(row.get("action", "?")), str(row.get("ticker", "?"))]
        if row.get("shares") is not None:
            parts.append(f"{row['shares']} aksjer")
        if row.get("limit_price") is not None:
            parts.append(f"limit {row['limit_price']}")
        lines.append(f"- {' · '.join(parts)}")

    if len(orders_df) > 5:
        lines.append(f"... og {len(orders_df) - 5} til.")

    return "\n".join(lines)


def _format_portfolio_summary_answer(context):
    dashboard = _get_dashboard(context)
    summary = dashboard.get("portfolio_summary") or {}
    risk = dashboard.get("portfolio_risk") or {}

    positions = summary.get("positions", 0)
    if positions == 0:
        return "Portefølje: Ingen posisjoner."

    lines = [
        "Portefølje:",
        f"- {positions} posisjoner",
        f"- Kostverdi: {summary.get('total_cost_value', 0)}",
        f"- Markedsverdi: {summary.get('total_market_value', 0)}",
        (
            f"- Urealisert: {summary.get('total_unrealized_profit_loss', 0)} "
            f"({summary.get('total_unrealized_gain_pct', 0)}%)"
        ),
    ]

    top_pct = risk.get("top_position_pct")
    top3_pct = risk.get("top3_concentration_pct")
    if top_pct:
        lines.append(f"- Topp posisjon: {top_pct}%")
    if top3_pct:
        lines.append(f"- Topp 3 konsentrasjon: {top3_pct}%")

    top_positions = risk.get("top_positions")
    if top_positions is not None and not top_positions.empty:
        tickers = ", ".join(top_positions["ticker"].head(3).tolist())
        lines.append(f"- Største posisjoner: {tickers}")

    return "\n".join(lines)


def _format_weakening_positions_answer(context):
    dashboard = _get_dashboard(context)
    df = dashboard.get("weakening_positions")

    if df is None or df.empty:
        return "Svekkende posisjoner: Ingen identifisert."

    lines = ["Svekkende / svakeste posisjoner:"]

    for _, row in df.head(5).iterrows():
        trend = row.get("trend_regime", "")
        rs = row.get("relative_strength_20d", "N/A")
        gain = row.get("unrealized_gain_pct", "N/A")
        lines.append(
            f"- {row['ticker']}: {trend}, RS {rs}%, urealisert {gain}%"
        )

    return "\n".join(lines)


def _format_strong_winners_answer(context):
    dashboard = _get_dashboard(context)
    df = dashboard.get("strong_winners")

    if df is None or df.empty:
        return "Sterke vinnere: Ingen posisjoner over 15% gevinst med god trend."

    lines = ["Sterke vinnere (største gevinst):"]

    for _, row in df.head(5).iterrows():
        gain = row.get("unrealized_gain_pct", "N/A")
        trend = row.get("trend_regime", "")
        value = row.get("market_value", "")
        lines.append(
            f"- {row['ticker']}: +{gain}% · {trend} · verdi {value}"
        )

    return "\n".join(lines)


def _format_risk_alerts_answer(context):
    daily_flow = _get_daily_flow(context)
    risk_alerts = daily_flow.get("risk_alerts")

    if not risk_alerts:
        dashboard = _get_dashboard(context)
        dashboard_alerts = dashboard.get("risk_alerts")
        if dashboard_alerts is not None and not dashboard_alerts.empty:
            lines = ["Risikovarsler:"]
            for _, row in dashboard_alerts.head(5).iterrows():
                lines.append(
                    f"- {row['ticker']}: {row.get('alert', '')} "
                    f"({row.get('severity', '')})"
                )
            return "\n".join(lines)

        return "Risikovarsler: Ingen aktive varsler."

    lines = ["Risikovarsler:"]
    lines.extend(_format_risk_lines(risk_alerts, limit=8))
    return "\n".join(lines)


def _format_trailing_stop_answer(context):
    daily_flow = _get_daily_flow(context)
    risk_alerts = daily_flow.get("risk_alerts") or {}
    near_stop = risk_alerts.get("near_trailing_stop")

    lines = ["Trailing stop:"]

    if near_stop is not None and not near_stop.empty:
        lines.append("Nær stop:")
        for _, row in near_stop.head(5).iterrows():
            lines.append(f"- {row['ticker']}: {row.get('details', '')}")
    else:
        lines.append("Nær stop: Ingen posisjoner innen 3% av trailing stop.")

    dashboard = _get_dashboard(context)
    triggered = dashboard.get("risk_alerts")
    if triggered is not None and not triggered.empty:
        triggered_rows = triggered[
            triggered["alert"] == "Trailing stop trigget"
        ]
        if not triggered_rows.empty:
            lines.append("")
            lines.append("Trigget:")
            for _, row in triggered_rows.iterrows():
                lines.append(f"- {row['ticker']}")

    return "\n".join(lines)


SCREENING_TOP_LIMIT = 5
SCREENING_PRESET = "Beste kandidater"
SCREENING_ADVISOR_FALLBACK = (
    "Ingen tydelig advisor-kommentar, men kandidaten scorer høyt i screeneren."
)

_SCREENING_REGIONS = {
    "nordics": {
        "title": "Topp 5 nordiske kandidater",
        "markers": ("nordisk", "nordiske", "norden"),
    },
    "usa": {
        "title": "Topp 5 amerikanske kandidater",
        "markers": ("amerikansk", "amerikanske", "usa", " us", "us "),
    },
    "obx": {
        "title": "Topp 5 norske kandidater",
        "markers": ("obx",),
    },
}

_NORWEGIAN_MARKERS = (
    "norske kandidater",
    "norske aksjer",
    "beste norske",
    "sterke norske",
    "norsk kandidat",
    "norsk aksje",
    "norske",
    "norsk",
)

_SCREENING_ACTION_MARKERS = (
    "beste",
    "sterkest",
    "sterke",
    "best ut",
    "sterkest ut",
    "finn sterke",
    "vis meg",
    "kandidat",
    "aksjer",
    "aksje",
)

_SCREENING_SNAPSHOT_KEYS = {
    "usa": "USA",
    "nordics": "NORDEN",
    "obx": "OBX",
}

_SCREENING_SNAPSHOT_FALLBACK_NOTE = (
    "(Bruker live screening fordi snapshot mangler.)"
)

_STRATEGY_SCREENING_SNAPSHOT_KEYS = ("USA", "NORDEN", "OBX")

_STRATEGY_SCREENING_PROFILES = {
    "momentum": ("momentum", "vekstaksj", "growth", "trendaksj"),
    "quality": ("quality", "kvalitetsaksj", "kvalitetsselskap"),
    "value": ("value", "verdiaksj", "billige aksjer"),
    "cyclical": (
        "cyclical",
        "sykliske",
        "sykliske aksjer",
        "shipping",
        "råvareaksjer",
    ),
}

_STRATEGY_SCREENING_ACTION_MARKERS = (
    "beste",
    "sterkeste",
    "sterke",
    "vis meg",
    "vis ",
    "hvilke",
    "hva er",
    "kandidat",
    "aksjer",
    "aksje",
)

_STRATEGY_SCREENING_TITLES = {
    "momentum": "Topp 5 momentum-kandidater",
    "quality": "Topp 5 quality-kandidater",
    "value": "Topp 5 value-kandidater",
    "cyclical": "Topp 5 sykliske kandidater",
}

_STRATEGY_PROFILE_UNAVAILABLE_MSG = (
    "Strategy-profiler er ikke tilgjengelige i snapshot. Kjør Oppdater analyser."
)


def _detect_screening_region(question):
    if "obx" in question:
        return "obx"

    if any(marker in question for marker in _SCREENING_REGIONS["usa"]["markers"]):
        return "usa"

    if any(marker in question for marker in _SCREENING_REGIONS["nordics"]["markers"]):
        return "nordics"

    if any(marker in question for marker in _NORWEGIAN_MARKERS):
        return "obx"

    return None


def _is_screening_question(question):
    region = _detect_screening_region(question)
    if region is None:
        return False

    return any(marker in question for marker in _SCREENING_ACTION_MARKERS)


def _screening_function_for_region(region):
    if region == "nordics":
        return screen_nordics
    if region == "usa":
        return screen_us_large
    if region == "obx":
        return screen_obx
    raise ValueError(f"Unknown screening region '{region}'")


def _format_screening_relative_strength(value):
    if value is None:
        return "—"

    try:
        if pd.isna(value):
            return "—"
    except TypeError:
        pass

    return f"{round(float(value), 1)} %"


def _format_screening_top5(results, title):
    lines = [title, ""]

    if results is None or results.empty:
        lines.append(
            'Ingen kandidater matchet filteret «Beste kandidater» akkurat nå.'
        )
        return "\n".join(lines)

    for index, row in enumerate(results.itertuples(index=False), start=1):
        lines.append(f"{index}. {row.ticker}")
        lines.append(f"   Score: {int(row.score)}")
        lines.append(f"   Trend: {row.trend_regime}")
        lines.append(
            "   Relativ styrke: "
            f"{_format_screening_relative_strength(row.relative_strength_20d)}"
        )
        lines.append("")

    return "\n".join(lines).rstrip()


def _detect_strategy_screening_profile(question):
    for profile, markers in _STRATEGY_SCREENING_PROFILES.items():
        if any(marker in question for marker in markers):
            return profile
    return None


def _is_strategy_screening_question(question):
    profile = _detect_strategy_screening_profile(question)
    if profile is None:
        return False

    return any(marker in question for marker in _STRATEGY_SCREENING_ACTION_MARKERS)


def _merged_screening_snapshot(context):
    screening_results = context.get("screening_results") or {}
    frames = []

    for key in _STRATEGY_SCREENING_SNAPSHOT_KEYS:
        region_results = screening_results.get(key)
        if isinstance(region_results, pd.DataFrame) and not region_results.empty:
            frames.append(region_results)

    if not frames:
        return None

    return pd.concat(frames, ignore_index=True)


def _screening_has_strategy_profiles(results):
    if results is None or results.empty:
        return False

    if "primary_profile" not in results.columns:
        return False

    return results["primary_profile"].notna().any()


def _profile_score_column(profile):
    return f"profile_score_{profile}"


def _filter_strategy_candidates(results, profile):
    return results[results["primary_profile"] == profile].copy()


def _sort_strategy_candidates(results, profile):
    score_column = _profile_score_column(profile)
    sort_columns = [score_column, "score"]
    available_columns = [column for column in sort_columns if column in results.columns]

    if not available_columns:
        return results.reset_index(drop=True)

    return results.sort_values(
        by=available_columns,
        ascending=[False] * len(available_columns),
        na_position="last",
    ).reset_index(drop=True)


def _format_strategy_profile_score(value):
    if value is None:
        return "—"

    try:
        if pd.isna(value):
            return "—"
    except TypeError:
        pass

    return str(int(value))


def _format_strategy_screening_top5(results, profile):
    title = _STRATEGY_SCREENING_TITLES[profile]
    label = _PROFILE_LABELS[profile]
    score_column = _profile_score_column(profile)
    lines = [title, ""]

    if results is None or results.empty:
        lines.append(
            f"Ingen {label.lower()}-kandidater funnet i snapshot akkurat nå."
        )
        return "\n".join(lines)

    for index, row in enumerate(results.head(SCREENING_TOP_LIMIT).itertuples(index=False), start=1):
        profile_score = getattr(row, score_column, None)
        lines.append(f"{index}. {row.ticker}")
        lines.append(
            f"   {label}: {_format_strategy_profile_score(profile_score)}"
        )
        lines.append(f"   Score: {int(row.score)}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _format_strategy_screening_advisor_commentary(context, top_results, full_results):
    if top_results is None or top_results.empty:
        return ""

    advisor_results = top_results.head(3)
    dashboard = _get_dashboard(context)
    advisor = build_opportunity_advisor(
        advisor_results,
        analyst_summary=_get_analyst_summary(context),
        sentiment_summary=(
            context.get("sentiment_summary")
            or dashboard.get("sentiment_summary")
        ),
        earnings_summary=_get_earnings_summary(context),
        news_summary=context.get("news_summary") or dashboard.get("news_summary"),
        limit=3,
        use_cache=True,
        full_results=full_results,
        is_full_universe=True,
    )

    items_by_ticker = {
        item["ticker"]: item
        for item in advisor.get("items") or []
        if item.get("ticker")
    }

    lines = ["", "Kort kommentar fra Opportunity Advisor", ""]

    for row in advisor_results.itertuples(index=False):
        ticker = row.ticker
        item = items_by_ticker.get(ticker)

        lines.append(ticker)

        if item is None:
            lines.append(SCREENING_ADVISOR_FALLBACK)
            lines.append("")
            continue

        headline = item.get("headline")
        if headline:
            lines.append(headline)

        relative_context = format_relative_context_short(
            item.get("relative_context")
        )
        if relative_context:
            lines.append(f"Relativ kontekst: {relative_context}")

        lines.append(item.get("takeaway") or SCREENING_ADVISOR_FALLBACK)
        lines.append("")

    return "\n".join(lines).rstrip()


def _answer_strategy_screening_question(context, question):
    profile = _detect_strategy_screening_profile(question)
    merged = _merged_screening_snapshot(context)

    if merged is None or merged.empty or not _screening_has_strategy_profiles(merged):
        return _STRATEGY_PROFILE_UNAVAILABLE_MSG

    filtered = _filter_strategy_candidates(merged, profile)
    ranked = _sort_strategy_candidates(filtered, profile)
    top5 = ranked.head(SCREENING_TOP_LIMIT)

    answer = _format_strategy_screening_top5(top5, profile)
    if not top5.empty:
        advisor_section = _format_strategy_screening_advisor_commentary(
            context,
            top5,
            filtered,
        )
        if advisor_section:
            answer = f"{answer}{advisor_section}"

    return answer


def _format_screening_advisor_bullet(line):
    if line.startswith("Høy score"):
        return "Sterk score"

    if "relativ styrke" in line.lower():
        return "Positiv relativ styrke"

    return line


def _format_screening_advisor_commentary(context, results, region=None):
    if results is None or results.empty:
        return ""

    top_results = results.head(SCREENING_TOP_LIMIT)
    dashboard = _get_dashboard(context)
    full_results = None
    universe_name = None
    is_full_universe = False
    use_snapshot_wording = False
    if region:
        snapshot_key = _SCREENING_SNAPSHOT_KEYS.get(region)
        universe_name = snapshot_key
        screening_results = context.get("screening_results") or {}
        snapshot_results = screening_results.get(snapshot_key)
        meta = screening_region_meta(screening_results, snapshot_key)

        if (
            snapshot_results is not None
            and isinstance(snapshot_results, pd.DataFrame)
            and not snapshot_results.empty
        ):
            full_results = snapshot_results
            if meta:
                is_full_universe = bool(meta.get("is_full_universe"))
                use_snapshot_wording = bool(
                    meta.get("use_snapshot_wording", not is_full_universe)
                )
        else:
            full_results = results
            is_full_universe = False
            use_snapshot_wording = False

    advisor = build_opportunity_advisor(
        top_results,
        analyst_summary=_get_analyst_summary(context),
        sentiment_summary=(
            context.get("sentiment_summary")
            or dashboard.get("sentiment_summary")
        ),
        earnings_summary=_get_earnings_summary(context),
        news_summary=context.get("news_summary") or dashboard.get("news_summary"),
        limit=SCREENING_TOP_LIMIT,
        use_cache=True,
        universe_name=universe_name,
        full_results=full_results if full_results is not None else results,
        is_full_universe=is_full_universe,
        use_snapshot_wording=use_snapshot_wording,
    )

    items_by_ticker = {
        item["ticker"]: item
        for item in advisor.get("items") or []
        if item.get("ticker")
    }

    lines = ["", "Kort kommentar fra Opportunity Advisor", ""]

    for index, row in enumerate(top_results.itertuples(index=False)):
        ticker = row.ticker
        item = items_by_ticker.get(ticker)

        lines.append(ticker)

        if item is None:
            lines.append(f"- {SCREENING_ADVISOR_FALLBACK}")
            lines.append("")
            lines.append("Tolkning:")
            lines.append(SCREENING_ADVISOR_FALLBACK)
            lines.append("")
            continue

        relative_context = format_relative_context_short(
            item.get("relative_context")
        )
        if index < 3 and relative_context:
            lines.append(f"Relativ kontekst: {relative_context}")

        for bullet in item.get("why_interesting") or []:
            lines.append(f"- {_format_screening_advisor_bullet(bullet)}")

        watch_out = item.get("watch_out_for") or []
        if not watch_out:
            lines.append("- Ingen tydelige forbehold")
        else:
            for bullet in watch_out:
                lines.append(f"- {bullet}")

        lines.append("")
        lines.append("Tolkning:")
        lines.append(item.get("takeaway") or SCREENING_ADVISOR_FALLBACK)
        lines.append("")

    return "\n".join(lines).rstrip()


def _screening_results_from_snapshot(context, region):
    snapshot_key = _SCREENING_SNAPSHOT_KEYS.get(region)
    if not snapshot_key:
        return None

    screening_results = context.get("screening_results") or {}
    results = screening_results.get(snapshot_key)
    if results is None or not isinstance(results, pd.DataFrame) or results.empty:
        return None

    return results.head(SCREENING_TOP_LIMIT)


def _answer_screening_question(context, question):
    region = _detect_screening_region(question)
    config = _SCREENING_REGIONS[region]
    results = _screening_results_from_snapshot(context, region)
    used_live_screening = results is None

    if used_live_screening:
        screen_fn = _screening_function_for_region(region)
        results = screen_fn(
            preset=SCREENING_PRESET,
            limit=SCREENING_TOP_LIMIT,
            pause_seconds=0,
            existing_watchlists=load_watchlists(),
        )

    answer = _format_screening_top5(results, config["title"])
    if used_live_screening:
        answer = f"{answer}\n\n{_SCREENING_SNAPSHOT_FALLBACK_NOTE}"
    if results is not None and not results.empty:
        advisor_section = _format_screening_advisor_commentary(
            context,
            results,
            region=region,
        )
        if advisor_section:
            answer = f"{answer}{advisor_section}"

    return answer


PORTFOLIO_COMPARISON_WEAK_LIMIT = 3
PORTFOLIO_COMPARISON_SCORE_GAP = 10

_PORTFOLIO_COMPARISON_MARKERS = (
    "bedre ut enn det jeg eier",
    "bedre ut enn det jeg har",
    "sterkere kandidater enn mine svakeste",
    "sterkere kandidater enn de svakeste",
    "mest interessante kjøpskandidat",
)

_TREND_RANK = {
    "STERK OPPTREND": 2,
    "MODERAT OPPTREND": 1,
    "SVAK / NEGATIV TREND": 0,
}


def _detect_portfolio_comparison_region(question):
    if "obx" in question or "norsk" in question:
        return "obx"

    if any(
        marker in question
        for marker in _SCREENING_REGIONS["nordics"]["markers"]
    ):
        return "nordics"

    return "usa"


def _is_portfolio_comparison_question(question):
    if any(marker in question for marker in _PORTFOLIO_COMPARISON_MARKERS):
        return True

    if "bedre ut enn" in question and any(
        phrase in question for phrase in ("det jeg eier", "det jeg har")
    ):
        return True

    if "sterkere" in question and "svakeste posisjon" in question:
        return True

    return False


def _comparison_numeric(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _comparison_row_value(row, key):
    if isinstance(row, dict):
        return row.get(key)

    if hasattr(row, key):
        return getattr(row, key)

    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return None


def _trend_rank(value):
    return _TREND_RANK.get(value, -1)


def _weakest_portfolio_positions(portfolio_report, limit=PORTFOLIO_COMPARISON_WEAK_LIMIT):
    df = valid_portfolio_rows(portfolio_report)
    if df.empty:
        return pd.DataFrame()

    return (
        df.sort_values(
            by=["score", "relative_strength_20d"],
            ascending=[True, True],
            na_position="last",
        )
        .head(limit)
        .reset_index(drop=True)
    )


def _candidate_stronger_than_holding(candidate, holding):
    candidate_score = _comparison_numeric(_comparison_row_value(candidate, "score"))
    holding_score = _comparison_numeric(_comparison_row_value(holding, "score"))
    if candidate_score is None or holding_score is None:
        return False

    if candidate_score >= holding_score + PORTFOLIO_COMPARISON_SCORE_GAP:
        return True

    if holding_score <= candidate_score < holding_score + PORTFOLIO_COMPARISON_SCORE_GAP:
        candidate_trend = _trend_rank(
            _comparison_row_value(candidate, "trend_regime")
        )
        holding_trend = _trend_rank(
            _comparison_row_value(holding, "trend_regime")
        )
        candidate_rs = _comparison_numeric(
            _comparison_row_value(candidate, "relative_strength_20d")
        )
        if candidate_trend > holding_trend and candidate_rs is not None and candidate_rs > 0:
            return True

    return False


def _holdings_beaten_by_candidate(candidate, weak_holdings):
    beaten = []
    for _, holding in weak_holdings.iterrows():
        if _candidate_stronger_than_holding(candidate, holding):
            beaten.append(holding)
    return beaten


def _portfolio_comparison_reasons(candidate, beaten_holdings):
    reasons = []
    candidate_score = _comparison_numeric(_comparison_row_value(candidate, "score"))
    candidate_trend = _trend_rank(_comparison_row_value(candidate, "trend_regime"))
    candidate_rs = _comparison_numeric(
        _comparison_row_value(candidate, "relative_strength_20d")
    )

    if any(
        candidate_score is not None
        and _comparison_numeric(holding["score"]) is not None
        and candidate_score > _comparison_numeric(holding["score"])
        for holding in beaten_holdings
    ):
        reasons.append("høyere score")

    if any(
        candidate_trend > _trend_rank(holding.get("trend_regime"))
        for holding in beaten_holdings
    ):
        reasons.append("sterkere trend")

    if any(
        candidate_rs is not None
        and _comparison_numeric(holding.get("relative_strength_20d")) is not None
        and candidate_rs > _comparison_numeric(holding.get("relative_strength_20d"))
        for holding in beaten_holdings
    ):
        reasons.append("bedre relativ styrke")

    return reasons


def _portfolio_comparison_advisor_by_ticker(context, results, region=None):
    if results is None or results.empty:
        return {}

    dashboard = _get_dashboard(context)
    universe_name = _SCREENING_SNAPSHOT_KEYS.get(region) if region else None
    advisor = build_opportunity_advisor(
        results,
        analyst_summary=_get_analyst_summary(context),
        sentiment_summary=(
            context.get("sentiment_summary")
            or dashboard.get("sentiment_summary")
        ),
        earnings_summary=_get_earnings_summary(context),
        news_summary=context.get("news_summary") or dashboard.get("news_summary"),
        limit=SCREENING_TOP_LIMIT,
        use_cache=True,
        universe_name=universe_name,
        full_results=results,
    )

    return {
        item["ticker"]: item
        for item in advisor.get("items") or []
    }


def _format_portfolio_comparison_candidates(context, results, weak_holdings, region=None):
    lines = ["Mest interessante kandidater akkurat nå", ""]

    if results is None or results.empty:
        lines.append(
            'Ingen screener-kandidater matchet filteret «Beste kandidater» akkurat nå.'
        )
        return "\n".join(lines)

    if weak_holdings.empty:
        lines.append(
            "Ingen porteføljeposisjoner å sammenligne med akkurat nå."
        )
        lines.append("")
        lines.append(
            "Legg til analyserte posisjoner i porteføljen for å sammenligne "
            "screener-kandidater mot det du eier."
        )
        return "\n".join(lines)

    interesting = []
    for candidate in results.itertuples(index=False):
        beaten = _holdings_beaten_by_candidate(candidate, weak_holdings)
        if beaten:
            interesting.append((candidate, beaten))

    if not interesting:
        lines.append(
            "Ingen screener-kandidater ser tydelig sterkere ut enn de svakeste "
            "porteføljeaksjene akkurat nå."
        )
        return "\n".join(lines)

    advisor_by_ticker = _portfolio_comparison_advisor_by_ticker(
        context,
        results.head(SCREENING_TOP_LIMIT),
        region=region,
    )

    for index, (candidate, beaten) in enumerate(
        interesting[:SCREENING_TOP_LIMIT],
        start=1,
    ):
        lines.append(f"{index}. {candidate.ticker}")
        lines.append(f"Score: {int(candidate.score)}")
        lines.append("")
        lines.append("Ser sterkere ut enn:")
        for holding in beaten:
            lines.append(
                f"- {holding['ticker']} ({int(holding['score'])})"
            )
        lines.append("")
        lines.append("Hvorfor:")
        for reason in _portfolio_comparison_reasons(candidate, beaten):
            lines.append(f"- {reason}")
        lines.append("")
        lines.append("Tolkning:")
        advisor_item = advisor_by_ticker.get(candidate.ticker)
        takeaway = advisor_item.get("takeaway") if advisor_item else None
        lines.append(
            takeaway
            or "Kan være verdt nærmere analyse dersom du vurderer nye posisjoner."
        )
        lines.append("")

    return "\n".join(lines).rstrip()


def _answer_portfolio_comparison_question(context, question):
    region = _detect_portfolio_comparison_region(question)
    screen_fn = _screening_function_for_region(region)

    results = screen_fn(
        preset=SCREENING_PRESET,
        limit=SCREENING_TOP_LIMIT,
        pause_seconds=0,
        existing_watchlists=load_watchlists(),
    )

    weak_holdings = _weakest_portfolio_positions(context.get("portfolio_report"))
    return _format_portfolio_comparison_candidates(
        context,
        results,
        weak_holdings,
        region=region,
    )


def _is_earnings_question(question):
    if any(
        phrase in question
        for phrase in [
            "earnings",
            "kvartalsrapport",
            "rapporterer snart",
            "kommende earnings",
            "kommende rapport",
            "før earnings",
            "hvem rapporterer",
            "porteføljeaksjer rapporterer",
            "portefølje rapporterer",
            "forbered kvartalsrapport",
            "følge med på før earnings",
        ]
    ):
        return True

    if "denne uken" in question and any(
        word in question
        for word in ["earnings", "kvartalsrapport", "rapport", "rapporterer"]
    ):
        return True

    if "har jeg" in question and any(
        word in question
        for word in ["earnings", "kvartalsrapport", "rapport"]
    ):
        return True

    return False


def _is_portfolio_earnings_question(question):
    return any(
        phrase in question
        for phrase in [
            "porteføljeaksjer rapporterer",
            "portefølje rapporterer",
            "min portefølje",
            "har jeg earnings",
            "i porteføljen",
        ]
    )


def _format_earnings_when(days_until):
    if days_until == 0:
        return "i dag"
    if days_until == 1:
        return "i morgen"
    return f"om {days_until} dager"


def _format_earnings_item_line(item):
    days_until = item.get("days_until")
    when = _format_earnings_when(days_until)
    return (
        f"- {item['ticker']}: {item['earnings_date']} "
        f"({when}, {item.get('status', 'unknown')})"
    )


def _upcoming_earnings_items(earnings_summary, question=""):
    upcoming = [
        item
        for item in (earnings_summary.get("upcoming_14_days") or [])
        if item.get("status") != "unknown" and item.get("earnings_date")
    ]

    if "denne uken" in question:
        upcoming = [
            item
            for item in upcoming
            if item.get("days_until") is not None and item["days_until"] <= 7
        ]

    if _is_portfolio_earnings_question(question):
        upcoming = [item for item in upcoming if item.get("in_portfolio")]

    return upcoming


def _format_earnings_answer(context, question=""):
    earnings_summary = _get_earnings_summary(context)
    if not earnings_summary:
        return "Earnings: Ingen data tilgjengelig. Oppdater analyser."

    upcoming = _upcoming_earnings_items(earnings_summary, question=question)
    portfolio_only = _is_portfolio_earnings_question(question)

    if not upcoming:
        if portfolio_only or "har jeg" in question:
            return "Portefølje earnings: Ingen rapporter innen 14 dager."
        if "denne uken" in question:
            return "Earnings: Ingen rapporter denne uken."
        return "Earnings: Ingen kommende rapporter innen 14 dager."

    portfolio_items = [item for item in upcoming if item.get("in_portfolio")]
    watchlist_items = [item for item in upcoming if not item.get("in_portfolio")]

    lines = ["Kommende earnings (14 dager):", ""]

    if portfolio_items:
        lines.append("Portefølje:")
        lines.extend(_format_earnings_item_line(item) for item in portfolio_items)
        lines.append("")

    if watchlist_items and not portfolio_only:
        lines.append("Watchlist:")
        lines.extend(_format_earnings_item_line(item) for item in watchlist_items)
        lines.append("")

    if any(
        phrase in question
        for phrase in [
            "følge med",
            "før earnings",
            "forbered",
        ]
    ):
        lines.append("Følg med på:")
        within_7_portfolio = [
            item
            for item in portfolio_items
            if item.get("days_until") is not None and item["days_until"] <= 7
        ]
        if within_7_portfolio:
            tickers = ", ".join(item["ticker"] for item in within_7_portfolio)
            lines.append(f"- Portefølje med rapport innen 7 dager: {tickers}")
        lines.append(
            "- Sjekk posisjonsstørrelse, trailing stop og porteføljeråd før rapport"
        )
        lines.append(
            "- Vurder om du vil redusere eksponering før volatilitet"
        )
        lines.append("")

    last_updated = earnings_summary.get("last_updated")
    if last_updated:
        lines.append(f"Sist oppdatert: {last_updated}")

    return "\n".join(lines).strip()


def _is_analyst_changes_question(question):
    return any(
        phrase in question
        for phrase in [
            "endret mening siden sist",
            "endringer siden sist",
            "analytikerendringer",
            "har analytikerne endret",
        ]
    )


def _is_portfolio_analyst_upside_question(question):
    return (
        "størst oppside" in question or "stor oppside" in question
    ) and "portefølje" in question


def _is_weakest_analyst_consensus_question(question):
    return any(
        phrase in question
        for phrase in [
            "svakest analytiker",
            "svakeste analytiker",
            "svakest konsensus",
            "svakeste konsensus",
            "svakeste analytikerkonsensus",
            "svakest analytikerkonsensus",
        ]
    )


def _is_analyst_price_target_question(question):
    return "kursmål" in question or "kursmålet" in question


def _is_analyst_ticker_question(question):
    return any(
        phrase in question
        for phrase in [
            "analytiker",
            "analytikere",
            "analytikerkonsensus",
            "konsensus",
        ]
    )


def _is_analyst_question(question):
    if _is_analyst_changes_question(question):
        return True
    if _is_portfolio_analyst_upside_question(question):
        return True
    if _is_weakest_analyst_consensus_question(question):
        return True
    if _is_analyst_price_target_question(question):
        return True
    return _is_analyst_ticker_question(question)


def _analyst_tickers_for_matching(context):
    tickers = set(analyst_tickers(_get_analyst_summary(context)))

    for ticker in context.get("watchlist") or []:
        normalized = str(ticker).strip().upper()
        if normalized:
            tickers.add(normalized)

    portfolio_report = context.get("portfolio_report")
    if portfolio_report is not None and not portfolio_report.empty:
        if "ticker" in portfolio_report.columns:
            for ticker in portfolio_report["ticker"]:
                normalized = str(ticker).strip().upper()
                if normalized:
                    tickers.add(normalized)

    return sorted(tickers, key=len, reverse=True)


def _extract_analyst_ticker(question, context):
    for ticker in _analyst_tickers_for_matching(context):
        if ticker.lower() in question:
            return ticker

    return None


def _format_analyst_answer(context, question):
    analyst_summary = _get_analyst_summary(context)
    if not analyst_summary:
        return (
            "Analytikerkonsensus: Ingen data tilgjengelig. Oppdater analyser.\n\n"
            f"{ANALYST_DISCLAIMER}"
        )

    if _is_analyst_changes_question(question):
        return format_analyst_material_changes_answer(analyst_summary)

    if _is_portfolio_analyst_upside_question(question):
        return format_portfolio_analyst_upside_answer(analyst_summary)

    if _is_weakest_analyst_consensus_question(question):
        return format_weakest_analyst_consensus_answer(analyst_summary)

    ticker = _extract_analyst_ticker(question, context)
    if ticker:
        item = find_analyst_item(analyst_summary, ticker)
        if item is None:
            return (
                f"Analytikerkonsensus for {ticker}: Ingen data tilgjengelig.\n\n"
                f"{ANALYST_DISCLAIMER}"
            )
        return format_analyst_item_answer(
            item,
            material_changes=analyst_summary.get("material_changes"),
        )

    return (
        "Analytikerkonsensus: Spesifiser ticker, for eksempel "
        "«Hva sier analytikerne om NVDA?» eller "
        "«Hva er kursmålet på GOOGL?».\n\n"
        f"{ANALYST_DISCLAIMER}"
    )


def _is_daily_flow_question(question):
    explicit_phrases = [
        "morning briefing",
        "morgenbrief",
        "morgen briefing",
        "daily flow",
        "dagens situasjon",
        "dagens oversikt",
        "viktigst nå",
        "følge med",
    ]
    if any(phrase in question for phrase in explicit_phrases):
        return True

    if "i dag" in question and any(
        word in question
        for word in ["hva", "viktig", "følge", "situasjon", "oversikt"]
    ):
        return True

    if "dashboard" in question and any(
        word in question
        for word in ["oppsummer", "status", "oversikt", "vis"]
    ):
        return True

    if question.startswith("oppsummer") and "dashboard" in question:
        return True

    return False


def _format_daily_flow_answer(context):
    daily_flow = context.get("daily_flow")
    if not daily_flow:
        return (
            "Morning Briefing er ikke tilgjengelig. "
            "Oppdater analyser og prøv igjen."
        )

    regime = daily_flow["market_regime"]
    signals = regime["signals"]
    opportunities = daily_flow["key_opportunities"]
    risk_alerts = daily_flow["risk_alerts"]
    pending = daily_flow["pending_orders"]

    lines = [
        "Morning Briefing",
        "",
        f"Marked: {regime['label']} "
        f"({signals['buy_count']} kjøp, "
        f"{signals['weak_avoid_count']} svake/unngå, "
        f"snitt RS {signals['avg_relative_strength']}%, "
        f"snitt score {signals['avg_score']})",
        "",
        "Oppsummering:",
    ]

    for bullet in daily_flow.get("summary_bullets", []):
        lines.append(f"- {bullet}")

    lines.extend([
        "",
        "Muligheter:",
        f"- Kjøpskandidater: {_format_ticker_list(opportunities.get('new_buy_candidates'))}",
        f"- Momentum: {_format_ticker_list(opportunities.get('strongest_momentum'))}",
        f"- Quality compounders: {_format_ticker_list(opportunities.get('strongest_quality_compounders'))}",
        "",
        "Risiko:",
    ])
    lines.extend(_format_risk_lines(risk_alerts))

    lines.extend([
        "",
        f"Ordre: {pending.get('summary', 'Ingen ventende ordre.')}",
    ])

    return "\n".join(lines)


def ask_agent(question, context):
    question = question.lower()

    watchlist = context["watchlist"]
    watchlist_report = context["watchlist_report"]
    portfolio_report = context["portfolio_report"]

    if _is_earnings_question(question):
        return _format_earnings_answer(context, question=question)

    if _is_analyst_question(question):
        return _format_analyst_answer(context, question)

    if _is_watchlist_advisor_question(question):
        return _answer_watchlist_advisor_question(context, question)

    if _is_advisor_question(question):
        return _format_advisor_answer(context, question)

    if _is_strategy_screening_question(question):
        return _answer_strategy_screening_question(context, question)

    if _is_screening_question(question):
        return _answer_screening_question(context, question)

    if _is_portfolio_comparison_question(question):
        return _answer_portfolio_comparison_question(context, question)

    if _is_daily_flow_question(question):
        return _format_daily_flow_answer(context)

    if _is_trailing_stop_question(question):
        return _format_trailing_stop_answer(context)

    if _is_risk_question(question):
        return _format_risk_alerts_answer(context)

    if _is_pending_orders_question(question):
        return _format_pending_orders_answer(context)

    if _is_weakest_positions_question(question):
        return _format_weakening_positions_answer(context)

    if _is_strong_winners_question(question):
        return _format_strong_winners_answer(context)

    if _is_portfolio_summary_question(question):
        return _format_portfolio_summary_answer(context)

    if is_strategy_profile_question(question):
        return format_strategy_profile_answer(context, question)

    if is_score_explanation_question(question):
        ticker = extract_score_explanation_ticker(question, context)
        if ticker:
            stock = find_stock_analysis(
                ticker,
                watchlist_report,
                portfolio_report,
            )
            if stock is not None:
                explanation = build_score_explanation(stock)
                return format_score_explanation(explanation)

            return f"Fant ikke analysedata for {ticker}."

        return (
            "Spesifiser ticker, for eksempel:\n"
            "- Hvorfor scorer BRK-B 100?\n"
            "- Forklar scoren til NVDA\n"
            "- Hvordan er BRK-B satt sammen?\n"
            "- Vis score-forklaring for MSFT"
        )

    is_portfolio_question = any(
        phrase in question
        for phrase in [
            "bør jeg holde",
            "bør jeg selge",
            "bør jeg redusere",
            "bør jeg øke",
            "gevinstsikre",
            "beholde",
            "min posisjon",
            "i porteføljen",
        ]
    )

    is_ranking_question = any(
        phrase in question
        for phrase in [
            "rank",
            "ranking",
            "ranger",
            "rangering",
            "sorter",
            "liste",
            "oversikt",
        ]
    )

    if (
        "kjøpskandidater" in question
        or "kjøpskandidatene" in question
        or "vis kjøp" in question
    ):
        screened = _screen_buy_candidates(watchlist_report)

        return (
            "Kjøpskandidater:\n\n"
            + _format_ranking_table(screened)
        )

    if (
        "kvalitetsselskaper" in question
        or "kvalitetsaksjer" in question
        or "sterke fundamentale" in question
        or "sterk fundamental" in question
    ):
        screened = _screen_quality_companies(watchlist_report)

        return (
            "Kvalitetsselskaper:\n\n"
            + _format_ranking_table(screened)
        )

    if (
        "vekst med trend" in question
        or "vekstaksjer med trend" in question
        or "sterk trend" in question
    ):
        screened = _screen_growth_with_trend(watchlist_report)

        return (
            "Vekst/trend-kandidater:\n\n"
            + _format_ranking_table(screened)
        )

    if (
        "sterke fundamentals men ikke kjøp" in question
        or "sterk fundamental men ikke kjøp" in question
        or "kvalitet men ikke kjøp" in question
    ):
        screened = _screen_strong_fundamentals_not_buy(watchlist_report)

        return (
            "Sterke fundamentals, men ikke kjøpskandidater nå:\n\n"
            + _format_ranking_table(screened)
        )

    if is_ranking_question:
        ranked = _rank_watchlist_report(watchlist_report)

        return (
            "Rangering av watchlist:\n\n"
            + _format_ranking_table(ranked)
        )

    if (
        ("beste" in question or "dagens råd" in question)
        and not _is_screening_question(question)
    ):
        filtered = watchlist_report[
            (watchlist_report["score"] >= 55)
            & (watchlist_report["relative_strength_20d"] > 0)
            & (watchlist_report["anbefaling"] != "UNNGÅ / SELG")
        ]

        top = filtered.sort_values(
            "score",
            ascending=False
        ).head(5)

        return generate_text_report(
            top,
            portfolio_report
        )

    for symbol in watchlist:
        if symbol.lower() in question:

            if (
                is_portfolio_question
                and portfolio_report is not None
            ):
                portfolio_match = portfolio_report[
                    portfolio_report["ticker"] == symbol
                ]

                if not portfolio_match.empty:
                    stock = portfolio_match.iloc[0]

                    return f"""
{symbol}

Porteføljeråd:
{stock.get('portefølje_råd', '—')}

Begrunnelse:
{stock.get('begrunnelse', '—')}

Gevinst/tap:
{_format_gain_pct(stock)} %

Trend:
{stock.get('trend_regime', '—')}

Total score:
{stock.get('score', '—')}

Relativ styrke:
{stock['relative_strength_20d']} %

Trailing stop trigget:
{stock['trailing_stop_triggered']}

Kursmål:
{stock['kursmål']}

Stop-loss:
{stock['stop_loss']}

Trailing stop-loss:
{stock['trailing_stop_loss']}
"""

            stock = watchlist_report[
                watchlist_report["ticker"] == symbol
            ].iloc[0]

            buy_recommendation = format_buy_recommendation(
                stock["anbefaling"]
            )

            fundamental_text = _format_reasons(
                stock.get("fundamental_reasons")
            )

            fundamental_history_text = _format_reasons(
                stock.get("fundamental_history_reasons")
            )

            return f"""
{symbol}

Kjøpsvurdering:
{buy_recommendation}

Trend:
{stock['trend_regime']}

Total score:
{stock['score']}

Teknisk score:
- Trendpoeng: {stock['trend_points']}
- Momentumpoeng: {stock['momentum_points']}
- Volumpoeng: {stock['volume_points']}
- Relativ styrke: {stock['relative_strength_20d']} %

Fundamentalt snapshot:
- Fundamental score: {stock['fundamental_score']}
- Fundamental vurdering: {stock['fundamental_label']}

Fundamental begrunnelse:
{fundamental_text}

Fundamental historikk:
- Historikk-score: {stock.get('fundamental_history_score', 'N/A')}
- Historikk-vurdering: {stock.get('fundamental_history_label', 'N/A')}

Historisk begrunnelse:
{fundamental_history_text}

Kursmål:
{stock['kursmål']}

Stop-loss:
{stock['stop_loss']}

Trailing stop-loss:
{stock['trailing_stop_loss']}
"""

    return (
        "Jeg forstod ikke spørsmålet.\n\n"
        "Prøv for eksempel:\n"
        "- Ranger watchlist\n"
        "- Vis kjøpskandidater\n"
        "- Vis kvalitetsselskaper\n"
        "- Vis vekst med trend\n"
        "- Kvalitet men ikke kjøp\n"
        "- Hva bør jeg følge med på i dag?\n"
        "- Oppsummer dashboardet\n"
        "- Vis pending ordre\n"
        "- Portefølje status\n"
        "- Svakeste posisjoner\n"
        "- Største gevinst\n"
        "- Risikovarsler\n"
        "- Trailing stop\n"
        "- Hvem rapporterer snart?\n"
        "- Har jeg earnings denne uken?\n"
        "- Hvilke porteføljeaksjer rapporterer?\n"
        "- Hva bør jeg følge med på før earnings?\n"
        "- Hva sier analytikerne om NVDA?\n"
        "- Hva er kursmålet på GOOGL?\n"
        "- Hvilke porteføljeaksjer har størst oppside?\n"
        "- Hvilke aksjer har svakest analytikerkonsensus?\n"
        "- Har analytikerne endret mening siden sist?\n"
        "- Er NVDA en kjøpskandidat?\n"
        "- Bør jeg holde NVDA?"
    )