import streamlit as st
import pandas as pd

from src.agent import ask_agent
from src.context import (
    build_agent_context,
    load_context_snapshot,
    resolve_portfolio_report,
    save_context_snapshot,
)
from src.ranking import ranking_table
from src.model_backtest import save_model_snapshot, compare_snapshots
from src.signal_backtest import backtest_signal_watchlist
from src.backtest_report import summarize_backtest_result
from src.walk_forward import rolling_walk_forward
from src.walk_forward_report import summarize_rolling_walk_forward
from src.portfolio_allocation import build_portfolio_allocation
from src.orders import analyze_pending_orders, analyze_order_history
from src.environment import environment_label, is_prod
from src.storage import (
    load_portfolio,
    load_pending_orders,
    load_order_history,
)
from src.order_editor import (
    create_buy_order,
    create_sell_order,
    execute_order,
    cancel_order,
)
from src.portfolio import (
    summarize_portfolio,
    valid_portfolio_rows,
)
from src.config import (
    load_watchlists,
    load_backtest_config,
    add_symbol_to_watchlist,
    remove_symbol_from_watchlist,
)
from src.strategy_classification import STRATEGY_TYPES, add_strategy_types
from src.analysis import analyze_stock
from src.company_names import get_company_name
from src.opportunity_advisor import build_opportunity_advisor
from src.screener import (
    SCREEN_OUTPUT_COLUMNS,
    SCREEN_PRESETS,
    load_screening_universe,
    screen_explore_universe,
    screening_universe_options,
    suggest_watchlist_additions,
)
from src.alerts import (
    ACTION_ADD_TO_WATCHLIST,
    ACTION_ARCHIVE_RESEARCH,
    ACTION_PREPARE_SELL_ORDER,
    ACTION_PROTECT_PROFIT,
    ACTION_REVIEW_ORDER,
    ACTION_REVIEW_SELL,
    build_alerts,
)
from src.daily_flow import (
    DAILY_AGENDA_DISPLAY_LIMIT,
    build_daily_actions,
    build_daily_agenda_table,
    build_whats_new_table,
)
from src.advisor import (
    advisor_detail_tickers,
    advisor_items_by_ticker,
    build_advisor_details,
    format_advisor_cell,
)
from src.analyst import (
    DISCLAIMER as ANALYST_DISCLAIMER,
    build_analyst_changes_table,
    build_analyst_table,
)
from src.earnings import build_earnings_table
from src.news import build_news_table
from src.research_ideas import (
    STATUS_WATCHLIST,
    load_research_ideas,
    add_research_idea,
    remove_research_idea,
    update_research_ideas,
    research_idea_status,
)


WATCHLISTS = load_watchlists()
BACKTEST_CONFIG = load_backtest_config()


st.set_page_config(
    page_title="Aksjeagent",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Aksjeagent")
st.caption("Beslutningsstøtte for aksjer – ikke automatisk handel.")

if is_prod():
    st.error(environment_label())
else:
    st.info(environment_label())


PORTFOLIO = load_portfolio([])
PENDING_ORDERS = load_pending_orders([])
ORDER_HISTORY = load_order_history([])
RESEARCH_IDEAS = load_research_ideas()


if "messages" not in st.session_state:
    st.session_state.messages = []

if "selected_watchlist_name" not in st.session_state:
    st.session_state.selected_watchlist_name = "Alle"


def reload_watchlists():
    global WATCHLISTS
    WATCHLISTS = load_watchlists()


def get_active_watchlist():
    return WATCHLISTS[
        st.session_state.selected_watchlist_name
    ]


def editable_watchlist_names():
    return [
        name for name in WATCHLISTS.keys()
        if name != "Alle"
    ]


def get_active_backtest_config():
    if st.session_state.selected_watchlist_name == "OBX":
        config = BACKTEST_CONFIG["obx"]
    else:
        config = BACKTEST_CONFIG["baseline"]

    return {
        "period": "2y",
        "initial_cash": 10000,
        **config,
    }


if "context" not in st.session_state:
    cached_context = load_context_snapshot()
    if cached_context is not None:
        st.session_state.context = cached_context
    else:
        with st.spinner("Analyserer watchlist og portefølje..."):
            st.session_state.context = build_agent_context(
                get_active_watchlist(),
                load_portfolio([]),
                pending_orders=load_pending_orders([]),
                research_ideas=RESEARCH_IDEAS,
                pause_seconds=1,
            )
            save_context_snapshot(st.session_state.context)


def refresh_context():
    with st.spinner("Oppdaterer analyser..."):
        st.session_state.context = build_agent_context(
            get_active_watchlist(),
            load_portfolio([]),
            pending_orders=load_pending_orders([]),
            research_ideas=load_research_ideas(),
            pause_seconds=1,
        )
        save_context_snapshot(st.session_state.context)


def rank_report(df):
    return df.sort_values(
        by=[
            "score",
            "fundamental_history_score",
            "fundamental_score",
            "relative_strength_20d",
        ],
        ascending=[False, False, False, False],
    )


def show_ranking_table(df):
    st.dataframe(
        ranking_table(df),
        width="stretch",
        hide_index=True,
    )


EXTERNAL_SCREEN_COLUMNS = [
    "ticker",
    "company_name",
    "score",
    "recommendation",
    "strategy_type",
    "trend_regime",
    "relative_strength_20d",
]


def show_screening_diagnostics(diagnostics):
    if not diagnostics:
        return

    lines = [
        f"- Universe: {diagnostics.get('total_universe', 0)}",
        f"- Already in watchlists: {diagnostics.get('already_in_watchlists', 0)}",
        f"- Analyzed: {diagnostics.get('analyzed', 0)}",
        f"- Passed filters: {diagnostics.get('passed_filters', 0)}",
        f"- Low score: {diagnostics.get('filtered_low_score', 0)}",
        f"- UNNGÅ / SELG: {diagnostics.get('filtered_unnga_selg', 0)}",
    ]

    failed = diagnostics.get("failed", 0)
    if failed:
        lines.insert(4, f"- Failed: {failed}")

    st.markdown("\n".join(lines))


def show_external_screen_results(df, target_watchlist, source_universe):
    header_cols = st.columns([1, 2, 0.6, 1.2, 1.1, 1.4, 0.7, 1.0])
    for col, label in zip(
        header_cols,
        [
            "Ticker",
            "Selskap",
            "Score",
            "Anbefaling",
            "Strategi",
            "Trend",
            "RS %",
            "Handling",
        ],
    ):
        col.caption(f"**{label}**")

    for idx, row in df.iterrows():
        cols = st.columns([1, 2, 0.6, 1.2, 1.1, 1.4, 0.7, 1.0])
        cols[0].write(row["ticker"])
        cols[1].write(row.get("company_name") or "")
        cols[2].write(int(row["score"]) if pd.notna(row["score"]) else "")
        cols[3].write(row["recommendation"])
        cols[4].write(row["strategy_type"])
        cols[5].write(row["trend_regime"])
        rs = row["relative_strength_20d"]
        cols[6].write(f"{rs:.1f}" if pd.notna(rs) else "")

        with cols[7]:
            if st.button(
                "Legg til",
                key=f"external_screen_add_{target_watchlist}_{row['ticker']}_{idx}",
            ):
                try:
                    add_symbol_to_watchlist(target_watchlist, row["ticker"])
                    reload_watchlists()
                    st.session_state.external_screen_feedback = (
                        f"La til {row['ticker']} i {target_watchlist}."
                    )
                    st.session_state.external_screen_results = (
                        df[df["ticker"] != row["ticker"]]
                        .reset_index(drop=True)
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

            if st.button(
                "Lagre som idé",
                key=(
                    f"external_screen_save_{source_universe}_"
                    f"{row['ticker']}_{idx}"
                ),
            ):
                try:
                    add_research_idea(row.to_dict(), source_universe)
                    st.session_state.external_screen_feedback = (
                        f"Lagret {row['ticker']} som research-idé."
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def show_research_ideas(ideas, target_watchlist):
    sorted_ideas = sorted(
        ideas,
        key=lambda idea: idea.get("last_updated_at")
        or idea.get("saved_at")
        or "",
        reverse=True,
    )

    header_cols = st.columns([1, 1.6, 0.5, 1.0, 1.0, 0.9, 1.0, 1.1])
    for col, label in zip(
        header_cols,
        [
            "Ticker",
            "Selskap",
            "Score",
            "Anbefaling",
            "Status",
            "Strategi",
            "Oppdatert",
            "Handling",
        ],
    ):
        col.caption(f"**{label}**")

    for idx, idea in enumerate(sorted_ideas):
        cols = st.columns([1, 1.6, 0.5, 1.0, 1.0, 0.9, 1.0, 1.1])
        cols[0].write(idea.get("ticker", ""))
        cols[1].write(idea.get("company_name") or "")
        score = idea.get("score")
        cols[2].write(
            int(score) if score is not None and pd.notna(score) else ""
        )
        cols[3].write(idea.get("recommendation") or "")
        cols[4].write(idea.get("status") or "")
        cols[5].write(idea.get("strategy_type") or "")
        updated_at = idea.get("last_updated_at") or idea.get("saved_at") or ""
        cols[6].write(updated_at.replace("T", " ")[:16])

        with cols[7]:
            if st.button(
                "Legg til",
                key=f"research_idea_add_{target_watchlist}_{idea.get('ticker')}_{idx}",
            ):
                try:
                    add_symbol_to_watchlist(
                        target_watchlist,
                        idea.get("ticker"),
                    )
                    reload_watchlists()
                    st.session_state.research_ideas_feedback = (
                        f"La til {idea.get('ticker')} i {target_watchlist}."
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

            if st.button(
                "Fjern",
                key=f"research_idea_remove_{idea.get('ticker')}_{idx}",
            ):
                try:
                    remove_research_idea(idea.get("ticker"))
                    st.session_state.research_ideas_feedback = (
                        f"Fjernet {idea.get('ticker')} fra research-idéer."
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def show_daily_agenda(actions):
    if not actions:
        return

    header_cols = st.columns([1, 1, 2])
    for col, label in zip(
        header_cols,
        ["Prioritet", "Ticker", "Handling"],
    ):
        col.caption(f"**{label}**")

    table = build_daily_agenda_table(actions)
    for action, (_, row) in zip(actions, table.iterrows()):
        cols = st.columns([1, 1, 2])
        cols[0].write(row["Prioritet"])
        cols[1].write(row["Ticker"])
        cols[2].write(row["Handling"])

        message = action.get("message", "")
        if message:
            st.caption(message)


def show_dataframe(df):
    if df is None:
        st.info("Ingen data.")
        return

    if isinstance(df, pd.DataFrame):
        if df.empty:
            st.info("Ingen data.")
            return

        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
        )
        return

    if len(df) == 0:
        st.info("Ingen data.")
        return

    st.dataframe(
        pd.DataFrame(df),
        width="stretch",
        hide_index=True,
    )


PORTFOLIO_ACTION_SORT = {
    "REDUSER / SELG": 0,
    "VURDER REDUKSJON": 1,
    "VURDER GEVINSTSIKRING": 2,
    "FØLG MED / IKKE ØK": 3,
    "HOLD / FØLG MED": 4,
    "HOLD": 5,
    "HOLD / LA VINNER LØPE": 6,
}

PORTFOLIO_ACTION_COLUMNS = [
    "ticker",
    "company_name",
    "market_value",
    "unrealized_gain_pct",
    "score",
    "anbefaling",
    "portefølje_råd",
    "Advisor",
    "trend_regime",
    "relative_strength_20d",
]

OPPORTUNITY_COLUMNS = [
    "ticker",
    "company_name",
    "source",
    "score",
    "recommendation",
    "strategy_type",
    "trend_regime",
    "relative_strength_20d",
]


def owned_tickers(portfolio_report, portfolio):
    tickers = set()
    for position in portfolio or []:
        ticker = position.get("ticker")
        if ticker:
            tickers.add(str(ticker).strip().upper())

    if portfolio_report is not None and not portfolio_report.empty:
        tickers.update(
            portfolio_report["ticker"].astype(str).str.strip().str.upper()
        )

    return tickers


def build_portfolio_actions_table(portfolio_report, advisor_output=None):
    df = valid_portfolio_rows(portfolio_report)

    if df.empty:
        return pd.DataFrame()

    df["company_name"] = df["ticker"].apply(get_company_name)
    advisor_map = advisor_items_by_ticker(advisor_output)
    df["Advisor"] = df["ticker"].astype(str).str.strip().str.upper().map(
        lambda ticker: format_advisor_cell(advisor_map.get(ticker, {}))
    )
    df["_sort"] = df["portefølje_råd"].map(
        lambda action: PORTFOLIO_ACTION_SORT.get(action, 99)
    )
    df = df.sort_values("_sort").drop(columns="_sort")

    columns = [col for col in PORTFOLIO_ACTION_COLUMNS if col in df.columns]
    return df[columns].reset_index(drop=True)


def render_advisor_detail(detail):
    if not detail:
        return

    advisor = detail.get("advisor") or {}
    st.markdown("**Advisor**")
    st.write(advisor.get("takeaway") or "")

    st.markdown("**Taler for varsomhet**")
    caution_signals = detail.get("caution_signals") or []
    if caution_signals:
        for signal in caution_signals:
            st.markdown(f"- {signal}")
    else:
        st.markdown("- Ingen tydelige varsomhetssignaler identifisert.")

    st.markdown("**Taler for å holde/vente**")
    hold_signals = detail.get("hold_signals") or []
    if hold_signals:
        for signal in hold_signals:
            st.markdown(f"- {signal}")
    else:
        st.markdown("- Ingen tydelige holde-/ventesignaler identifisert.")

    interpretation = detail.get("practical_interpretation")
    if interpretation:
        st.markdown("**Praktisk tolkning**")
        st.write(interpretation)


def build_new_opportunities(watchlist_report, research_ideas, owned):
    rows = []
    seen = set()

    if watchlist_report is not None and not watchlist_report.empty:
        classified = add_strategy_types(watchlist_report)
        buys = classified[classified["anbefaling"] == "KJØP / ØK"]

        for _, row in buys.iterrows():
            ticker = str(row["ticker"]).strip().upper()
            if ticker in owned or ticker in seen:
                continue

            seen.add(ticker)
            rows.append({
                "ticker": row["ticker"],
                "company_name": get_company_name(row["ticker"]) or "",
                "source": "WATCHLIST",
                "score": row["score"],
                "recommendation": row["anbefaling"],
                "strategy_type": row.get("strategy_type", ""),
                "trend_regime": row.get("trend_regime", ""),
                "relative_strength_20d": row.get("relative_strength_20d"),
            })

    for idea in research_ideas or []:
        ticker = str(idea.get("ticker", "")).strip().upper()
        if not ticker or ticker in owned or ticker in seen:
            continue

        status = idea.get("status") or research_idea_status(idea)
        if status != STATUS_WATCHLIST:
            continue

        seen.add(ticker)
        rows.append({
            "ticker": idea.get("ticker"),
            "company_name": idea.get("company_name") or get_company_name(ticker) or "",
            "source": "RESEARCH",
            "score": idea.get("score"),
            "recommendation": idea.get("recommendation") or "",
            "strategy_type": idea.get("strategy_type", ""),
            "trend_regime": idea.get("trend_regime", ""),
            "relative_strength_20d": idea.get("relative_strength_20d"),
        })

    if not rows:
        return pd.DataFrame(columns=OPPORTUNITY_COLUMNS)

    df = pd.DataFrame(rows)
    return df.sort_values(
        by=["score", "relative_strength_20d"],
        ascending=[False, False],
    )[OPPORTUNITY_COLUMNS].reset_index(drop=True)


_ALERT_UI_GROUPS = (
    (ACTION_REVIEW_SELL, "Selg"),
    (ACTION_PREPARE_SELL_ORDER, "Følg stop-nivå"),
    (ACTION_PROTECT_PROFIT, "Gevinstsikring"),
    (ACTION_REVIEW_ORDER, "Ventende ordre"),
    (ACTION_ADD_TO_WATCHLIST, "Watchlist"),
    (ACTION_ARCHIVE_RESEARCH, "Arkiver"),
)

_PRIORITY_LABELS = {
    1: "Høy",
    2: "Medium",
    3: "Lav",
}


def sort_alerts_for_display(alerts):
    return sorted(
        alerts,
        key=lambda alert: (
            alert.get("priority", 99),
            alert.get("ticker", ""),
        ),
    )


def _alert_priority_label(alert):
    return _PRIORITY_LABELS.get(alert.get("priority"), "Lav")


def _escape_markdown_table_cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def _build_alert_group_table(alerts):
    lines = [
        "| Prioritet | Ticker | Handling | Varsel |",
        "| --- | --- | --- | --- |",
    ]
    for alert in alerts:
        lines.append(
            "| "
            f"{_alert_priority_label(alert)} | "
            f"{_escape_markdown_table_cell(alert.get('ticker', ''))} | "
            f"{_escape_markdown_table_cell(alert.get('action_label', ''))} | "
            f"{_escape_markdown_table_cell(alert.get('message', ''))} |"
        )
    return "\n".join(lines)


def show_alerts_compact(alerts):
    if not alerts:
        st.caption("Ingen viktige varsler akkurat nå.")
        return

    sorted_alerts = sort_alerts_for_display(alerts)
    alerts_by_action = {}
    for alert in sorted_alerts:
        alerts_by_action.setdefault(alert.get("action"), []).append(alert)

    known_actions = {action for action, _ in _ALERT_UI_GROUPS}
    rendered_any = False

    for action, heading in _ALERT_UI_GROUPS:
        group = alerts_by_action.get(action, [])
        if not group:
            continue

        rendered_any = True
        st.markdown(f"**{heading}**")
        st.markdown(_build_alert_group_table(group))

    unknown_alerts = [
        alert
        for alert in sorted_alerts
        if alert.get("action") not in known_actions
    ]
    if unknown_alerts:
        st.markdown("**Annet**")
        st.markdown(_build_alert_group_table(unknown_alerts))
        rendered_any = True

    if not rendered_any:
        st.caption("Ingen viktige varsler akkurat nå.")


def show_strategy_type_metrics(strategy_counts):
    if not strategy_counts or sum(strategy_counts.values()) == 0:
        st.info("Ingen strategidata tilgjengelig.")
        return

    strategy_labels = {
        "QUALITY_COMPOUNDER": "Quality",
        "COMPOUNDER": "Compounder",
        "MOMENTUM": "Momentum",
        "CYCLICAL": "Cyclical",
        "WEAK/AVOID": "Weak/Avoid",
        "UNKNOWN": "Unknown",
    }
    columns = st.columns(len(STRATEGY_TYPES))
    for column, strategy_type in zip(columns, STRATEGY_TYPES):
        column.metric(
            strategy_labels.get(strategy_type, strategy_type),
            strategy_counts.get(strategy_type, 0),
        )


def _geo_buckets_table(buckets):
    if not buckets:
        return pd.DataFrame()

    rows = []
    for bucket in buckets:
        tickers = bucket.get("tickers") or []
        rows.append({
            "Marked": bucket.get("label", bucket.get("market", "")),
            "Andel %": bucket.get("allocation_pct", 0),
            "Markedsverdi": bucket.get("market_value", 0),
            "Posisjoner": bucket.get("position_count", 0),
            "Tickers": ", ".join(tickers),
        })

    return pd.DataFrame(rows)


def show_portfolio_risk_section(portfolio_risk):
    st.markdown("### Porteføljerisiko")

    if not portfolio_risk or not portfolio_risk.get("available"):
        st.info("Ingen portefølje – risiko kan ikke beregnes.")
        return

    risk_level = portfolio_risk.get("risk_level") or {}
    concentration = portfolio_risk.get("concentration") or {}
    diversification = portfolio_risk.get("diversification") or {}
    geographic = portfolio_risk.get("geographic_exposure") or {}

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Risikonivå", risk_level.get("level", "–"))
    r2.metric(
        "Topp posisjon",
        f"{concentration.get('top_position_pct', portfolio_risk.get('top_position_pct', 0))}%",
    )
    r3.metric(
        "Topp 3",
        f"{concentration.get('top3_concentration_pct', portfolio_risk.get('top3_concentration_pct', 0))}%",
    )
    r4.metric("Effektiv N", diversification.get("effective_n", 0))

    buckets = geographic.get("buckets") or []
    bucket_by_market = {
        bucket.get("market"): bucket
        for bucket in buckets
    }
    g1, g2, g3 = st.columns(3)
    g1.metric(
        "USA",
        f"{bucket_by_market.get('USA', {}).get('allocation_pct', 0)}%",
    )
    g2.metric(
        "OBX / Norge",
        f"{bucket_by_market.get('OBX', {}).get('allocation_pct', 0)}%",
    )
    g3.metric(
        "Øvrig Norden",
        f"{bucket_by_market.get('NORDEN', {}).get('allocation_pct', 0)}%",
    )

    reasons = risk_level.get("reasons") or []
    if reasons:
        st.markdown("\n".join(f"- {reason}" for reason in reasons))

    with st.expander("Detaljer", expanded=False):
        st.markdown("**Største posisjoner**")
        show_dataframe(concentration.get("largest_positions"))
        st.markdown("**Geografisk fordeling**")
        show_dataframe(_geo_buckets_table(buckets))


with st.sidebar:
    st.header("Kontrollpanel")
    st.caption(environment_label())

    selected = st.selectbox(
        "Watchlist",
        list(WATCHLISTS.keys()),
        index=list(WATCHLISTS.keys()).index(
            st.session_state.selected_watchlist_name
        ),
    )

    if selected != st.session_state.selected_watchlist_name:
        st.session_state.selected_watchlist_name = selected
        refresh_context()
        st.rerun()

    if st.button("Oppdater analyser"):
        refresh_context()
        st.success("Analyser oppdatert.")

    if st.button("Lagre snapshot"):
        _, path = save_model_snapshot(
            get_active_watchlist()
        )
        st.success(f"Snapshot lagret: {path}")


watchlist_report = st.session_state.context["watchlist_report"]
portfolio_report = resolve_portfolio_report(
    st.session_state.context,
    load_portfolio([]),
)
dashboard = st.session_state.context["dashboard"]
daily_flow = st.session_state.context["daily_flow"]
dashboard_alerts = build_alerts(
    portfolio_report,
    PENDING_ORDERS,
    RESEARCH_IDEAS,
    earnings_summary=st.session_state.context.get("earnings_summary"),
)
ranked = rank_report(watchlist_report)


tab_dashboard, tab_ranking, tab_screening, tab_watchlists, tab_allocation, tab_orders, tab_portfolio, tab_history, tab_snapshots, tab_backtest, tab_walk_forward, tab_chat = st.tabs(
    [
        "Dashboard",
        "Rangering",
        "Screening",
        "Watchlists",
        "Allocation",
        "Ordre",
        "Portefølje",
        "Historikk",
        "Snapshots",
        "Backtest",
        "Walk-forward",
        "Chat",
    ]
)


with tab_dashboard:
    st.markdown("### Dagens agenda")
    st.caption("Hva krever oppmerksomhet først?")
    agenda = build_daily_actions(
        dashboard_alerts,
        PENDING_ORDERS,
        portfolio_report,
    )[:DAILY_AGENDA_DISPLAY_LIMIT]
    if not agenda:
        st.caption("Ingen prioriterte handlinger akkurat nå.")
    else:
        show_daily_agenda(agenda)

    st.markdown("### Nytt i dag")
    st.caption("Siden sist lagrede snapshot")
    whats_new = daily_flow.get("whats_new_today") or {}
    if not whats_new.get("available"):
        st.caption("Lagre snapshot for å spore endringer.")
    elif not whats_new.get("has_changes"):
        st.caption("Ingen vesentlige endringer siden sist snapshot.")
    else:
        show_dataframe(build_whats_new_table(daily_flow))

    current_portfolio = load_portfolio([])
    portfolio_summary = summarize_portfolio(portfolio_report)
    owned = owned_tickers(portfolio_report, current_portfolio)

    if current_portfolio and valid_portfolio_rows(portfolio_report).empty:
        st.warning(
            "Porteføljeanalyse mangler markedsverdi. "
            "Trykk «Oppdater analyser» i sidepanelet."
        )

    st.markdown("### Portefølje totalt")
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Markedsverdi", portfolio_summary["total_market_value"])
    t2.metric(
        "Urealisert gevinst/tap",
        portfolio_summary["total_unrealized_profit_loss"],
    )
    t3.metric(
        "Urealisert %",
        f"{portfolio_summary['total_unrealized_gain_pct']}%",
    )
    t4.metric("Posisjoner", portfolio_summary["positions"])

    show_portfolio_risk_section(dashboard.get("portfolio_risk"))

    st.markdown("### Mine posisjoner – hva bør jeg gjøre?")
    advisor_output = st.session_state.context.get("advisor_output") or {}
    analyst_summary = st.session_state.context.get("analyst_summary") or {}
    sentiment_summary = st.session_state.context.get("sentiment_summary") or {}
    earnings_summary = st.session_state.context.get("earnings_summary") or {}
    advisor_details = build_advisor_details(
        advisor_output,
        portfolio_report,
        analyst_summary=analyst_summary,
        sentiment_summary=sentiment_summary,
        earnings_summary=earnings_summary,
        alerts=dashboard_alerts,
    )
    actions_table = build_portfolio_actions_table(
        portfolio_report,
        advisor_output=advisor_output,
    )
    if actions_table.empty:
        st.info("Ingen porteføljeposisjoner.")
    else:
        show_dataframe(actions_table)
        advisor_tickers = advisor_detail_tickers(advisor_output)
        for index, ticker in enumerate(advisor_tickers):
            detail = advisor_details.get(ticker)
            if not detail:
                continue
            with st.expander(f"Hvorfor sier agenten dette om {ticker}?"):
                render_advisor_detail(detail)
            if index < len(advisor_tickers) - 1:
                st.markdown("")

    st.markdown("### Nye muligheter")
    opportunities = build_new_opportunities(
        watchlist_report,
        RESEARCH_IDEAS,
        owned,
    )
    if opportunities.empty:
        st.info("Ingen nye kjøpskandidater utenfor porteføljen.")
    else:
        show_dataframe(opportunities)

    st.markdown("### Kommende earnings")
    earnings_table = build_earnings_table(earnings_summary)
    if earnings_table.empty:
        st.info("Ingen earnings-data for portefølje eller watchlist.")
    else:
        show_dataframe(earnings_table)
        last_updated = earnings_summary.get("last_updated")
        if last_updated:
            st.caption(f"Sist oppdatert: {last_updated}")

    st.markdown("### Analytikerkonsensus")
    analyst_table = build_analyst_table(analyst_summary)
    if analyst_table.empty:
        st.info("Ingen analytikerdata for portefølje eller watchlist.")
    else:
        show_dataframe(analyst_table)
        st.caption(ANALYST_DISCLAIMER)
        analyst_changes = analyst_summary.get("material_changes") or []
        if analyst_changes:
            st.markdown("#### Endringer siden sist")
            show_dataframe(build_analyst_changes_table(analyst_summary))
        analyst_last_updated = analyst_summary.get("last_updated")
        if analyst_last_updated:
            st.caption(f"Sist oppdatert: {analyst_last_updated}")

    st.markdown("### Nyheter")
    news_summary = st.session_state.context.get("news_summary") or {}
    news_table = build_news_table(news_summary)
    if news_table.empty:
        st.info("Ingen nyheter for portefølje eller watchlist.")
    else:
        show_dataframe(news_table.drop(columns=["URL"], errors="ignore"))
        st.caption("Sentiment er basert på overskrifter og påvirker ikke anbefalingene.")
        news_last_updated = news_summary.get("last_updated")
        if news_last_updated:
            st.caption(f"Sist oppdatert: {news_last_updated}")

    st.markdown("### Viktige varsler")
    st.caption("Full varslingsliste")
    show_alerts_compact(dashboard_alerts)


with tab_ranking:
    st.subheader("Rangert watchlist")
    show_ranking_table(ranked)

    market = dashboard["market_summary"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Kjøpskandidater", market["buy_count"])
    m2.metric("Hold / observer", market["hold_count"])
    m3.metric("Unngå / selg", market["avoid_count"])
    m4.metric("Aksjer analysert", market["total_symbols"])

    with st.expander("Strategityper", expanded=False):
        show_strategy_type_metrics(
            dashboard.get("strategy_type_counts", {}),
        )

    with st.expander("Strategiprofiler", expanded=False):
        strategy_profiles = dashboard.get("strategy_profiles")
        if strategy_profiles is None or strategy_profiles.empty:
            st.info("Ingen strategiprofiler tilgjengelig.")
        else:
            show_dataframe(strategy_profiles)

    with st.expander("Topp kjøpskandidater", expanded=False):
        show_dataframe(dashboard["top_buy_candidates"])

    market_regime = dashboard["market_regime"]
    with st.expander("Markedsregime", expanded=False):
        if not market_regime.get("available"):
            st.info(
                market_regime.get(
                    "message",
                    "Markedsregime utilgjengelig.",
                )
            )
        else:
            st.markdown(f"**{market_regime['regime_label']}**")
            r1, r2, r3, r4, r5 = st.columns(5)
            r1.metric("Benchmark", market_regime["benchmark_symbol"])
            r2.metric("Kurs", market_regime["benchmark_price"])
            r3.metric("SMA20", market_regime["sma20"])
            r4.metric("SMA50", market_regime["sma50"])
            r5.metric("SMA100", market_regime["sma100"])
            if market_regime["reasons"]:
                st.caption(" · ".join(market_regime["reasons"]))
            st.info(market_regime["interpretation"])
            kpis = market_regime["watchlist_kpis"]
            k1, k2, k3 = st.columns(3)
            k1.metric("Sterk opptrend", f"{kpis['strong_uptrend_pct']}%")
            k2.metric("Svak/negativ trend", f"{kpis['weak_trend_pct']}%")
            k3.metric(
                "Snitt relativ styrke",
                f"{kpis['avg_relative_strength']}%",
            )


with tab_screening:
    st.subheader("Screening")

    st.markdown("### Utforsk univers")
    st.caption(
        "Screen hele universet. Aksjer du allerede følger markeres i tabellen."
    )

    explore_universe_options = screening_universe_options()
    screener_cols = st.columns([2, 2, 1])
    with screener_cols[0]:
        if explore_universe_options:
            explore_universe = st.selectbox(
                "Univers",
                explore_universe_options,
                key="explore_screen_universe",
            )
        else:
            explore_universe = None
            st.warning(
                "Ingen screening-univers konfigurert. "
                "Legg til data/config/screening_universe.json."
            )
    with screener_cols[1]:
        screen_preset = st.selectbox(
            "Preset",
            list(SCREEN_PRESETS),
            key="watchlist_screen_preset",
        )
    with screener_cols[2]:
        watchlist_screen_limit = st.number_input(
            "Maks antall",
            min_value=1,
            value=20,
            step=1,
            key="watchlist_screen_limit",
        )

    if explore_universe_options and st.button(
        "Kjør screening",
        key="run_watchlist_screen",
    ):
        with st.spinner(f"Screener {explore_universe}..."):
            st.session_state.watchlist_screen_results = (
                screen_explore_universe(
                    explore_universe,
                    preset=screen_preset,
                    limit=int(watchlist_screen_limit),
                    pause_seconds=1,
                    existing_watchlists=WATCHLISTS,
                )
            )

    watchlist_screen_results = st.session_state.get(
        "watchlist_screen_results"
    )
    if watchlist_screen_results is not None:
        if watchlist_screen_results.empty:
            st.info("Ingen aksjer matchet filteret.")
        else:
            display_columns = [
                col
                for col in SCREEN_OUTPUT_COLUMNS
                if col in watchlist_screen_results.columns
            ]
            st.dataframe(
                watchlist_screen_results[display_columns],
                width="stretch",
                hide_index=True,
            )

            opportunity_advisor = build_opportunity_advisor(
                watchlist_screen_results,
                analyst_summary=st.session_state.context.get(
                    "analyst_summary"
                ),
                sentiment_summary=st.session_state.context.get(
                    "sentiment_summary"
                ),
                earnings_summary=st.session_state.context.get(
                    "earnings_summary"
                ),
                news_summary=st.session_state.context.get("news_summary"),
                limit=5,
            )
            advisor_items = opportunity_advisor.get("items") or []
            if advisor_items:
                st.markdown("#### Tolkning")
                for item in advisor_items:
                    with st.expander(
                        f"Hvorfor er {item['ticker']} interessant?"
                    ):
                        st.markdown(f"**{item['headline']}**")
                        st.markdown("**Hvorfor interessant**")
                        if item.get("why_interesting"):
                            for line in item["why_interesting"]:
                                st.markdown(f"- {line}")
                        else:
                            st.markdown("- Ingen tydelige styrker identifisert.")

                        st.markdown("**Forbehold**")
                        if item.get("watch_out_for"):
                            for line in item["watch_out_for"]:
                                st.markdown(f"- {line}")
                        else:
                            st.markdown("- Ingen tydelige forbehold identifisert.")

                        st.markdown("**Tolkning**")
                        st.write(item.get("takeaway") or "")
                st.caption(opportunity_advisor.get("disclaimer") or "")

    st.divider()
    st.markdown("### Finn nye kandidater")
    st.caption(
        "Screen universer utenfor watchlistene dine, lagre idéer, "
        "eller legg kandidater direkte til watchlist."
    )

    external_feedback = st.session_state.pop("external_screen_feedback", None)
    if external_feedback:
        st.success(external_feedback)

    universe_options = sorted(load_screening_universe())
    if not universe_options:
        st.warning(
            "Ingen screening-univers konfigurert. "
            "Legg til data/config/screening_universe.json."
        )
    else:
        control_cols = st.columns([2, 1, 2])
        with control_cols[0]:
            external_universe = st.selectbox(
                "Univers",
                universe_options,
                key="external_screen_universe",
            )
        with control_cols[1]:
            external_max_results = st.number_input(
                "Maks antall forslag",
                min_value=0,
                value=0,
                step=1,
                help="0 = vis alle forslag etter filtrering",
                key="external_screen_max_results",
            )
        with control_cols[2]:
            external_target_watchlist = st.selectbox(
                "Legg til i",
                editable_watchlist_names(),
                key="external_screen_target_watchlist",
            )

        if st.button("Kjør screening", key="run_external_screen"):
            max_results = (
                None
                if external_max_results == 0
                else int(external_max_results)
            )
            with st.spinner(f"Screener {external_universe}..."):
                screen_result = suggest_watchlist_additions(
                    external_universe,
                    WATCHLISTS,
                    max_results=max_results,
                    pause_seconds=1,
                )
                st.session_state.external_screen_results = (
                    screen_result["candidates"]
                )
                st.session_state.external_screen_diagnostics = (
                    screen_result["diagnostics"]
                )
                st.session_state.external_screen_rejected = (
                    screen_result["rejected"]
                )
                st.session_state.external_screen_source_universe = (
                    external_universe
                )

        external_results = st.session_state.get("external_screen_results")
        external_diagnostics = st.session_state.get(
            "external_screen_diagnostics"
        )
        external_rejected = st.session_state.get("external_screen_rejected")
        external_source_universe = st.session_state.get(
            "external_screen_source_universe",
            external_universe,
        )
        if external_results is not None:
            if external_results.empty:
                st.info("Ingen nye kandidater funnet.")
                show_screening_diagnostics(external_diagnostics)
                if (
                    external_rejected is not None
                    and not external_rejected.empty
                ):
                    with st.expander("Se forkastede kandidater"):
                        show_dataframe(external_rejected)
            else:
                display_df = external_results[
                    [
                        col for col in EXTERNAL_SCREEN_COLUMNS
                        if col in external_results.columns
                    ]
                ]
                show_external_screen_results(
                    display_df,
                    external_target_watchlist,
                    external_source_universe,
                )

    st.divider()
    st.markdown("### Research ideas")
    st.caption(
        "Lagrede kandidater fra screening. Oppdater for ferske scorer "
        "og handlingsstatus."
    )

    research_feedback = st.session_state.pop("research_ideas_feedback", None)
    if research_feedback:
        st.success(research_feedback)

    research_control_cols = st.columns([2, 1, 2])
    with research_control_cols[0]:
        research_target_watchlist = st.selectbox(
            "Legg til i",
            editable_watchlist_names(),
            key="research_target_watchlist",
        )
    with research_control_cols[2]:
        if st.button(
            "Oppdater research ideas",
            key="update_research_ideas",
        ):
            if not RESEARCH_IDEAS:
                st.session_state.research_ideas_feedback = (
                    "Ingen research-idéer å oppdatere."
                )
            else:
                with st.spinner("Oppdaterer research-idéer..."):
                    result = update_research_ideas(pause_seconds=1)
                message = (
                    f"Oppdaterte {len(result['ideas'])} research-idéer."
                )
                if result["failed"]:
                    failed_tickers = ", ".join(
                        item["ticker"] for item in result["failed"]
                    )
                    message += f" Feilet for: {failed_tickers}."
                st.session_state.research_ideas_feedback = message
            st.rerun()

    if not RESEARCH_IDEAS:
        st.info("Ingen lagrede research-idéer.")
    else:
        show_research_ideas(RESEARCH_IDEAS, research_target_watchlist)


with tab_watchlists:
    st.subheader("Watchlists")

    feedback = st.session_state.pop("watchlist_feedback", None)
    if feedback:
        if feedback["type"] == "success":
            st.success(feedback["message"])
        else:
            st.error(feedback["message"])

    st.caption(
        "Rediger symboler i USA, Norden og OBX. "
        "Watchlisten «Alle» bygges automatisk fra de andre listene."
    )
    st.info(
        "Endringer i watchlist oppdaterer ikke analysene automatisk. "
        "Trykk Oppdater analyser når du vil reanalysere hele listen."
    )

    editable_names = editable_watchlist_names()

    if "watchlist_editor_name" not in st.session_state:
        st.session_state.watchlist_editor_name = editable_names[0]

    editor_list = st.selectbox(
        "Velg watchlist",
        editable_names,
        index=editable_names.index(
            st.session_state.watchlist_editor_name
        )
        if st.session_state.watchlist_editor_name in editable_names
        else 0,
        key="watchlist_editor_select",
    )
    st.session_state.watchlist_editor_name = editor_list

    symbols = WATCHLISTS.get(editor_list, [])
    st.markdown(f"**{len(symbols)} symboler**")

    if symbols:
        for symbol in symbols:
            col_ticker, col_remove = st.columns([5, 1])
            company_name = get_company_name(symbol)
            if company_name:
                col_ticker.markdown(f"**{symbol}** — {company_name}")
            else:
                col_ticker.markdown(f"**{symbol}**")
            if col_remove.button(
                "Fjern",
                key=f"watchlist_remove_{editor_list}_{symbol}",
            ):
                try:
                    remove_symbol_from_watchlist(
                        editor_list,
                        symbol,
                    )
                    reload_watchlists()
                    st.session_state.watchlist_feedback = {
                        "type": "success",
                        "message": (
                            f"Fjernet {symbol} fra {editor_list}."
                        ),
                    }
                    st.rerun()
                except ValueError as exc:
                    st.session_state.watchlist_feedback = {
                        "type": "error",
                        "message": str(exc),
                    }
                    st.rerun()
    else:
        st.info("Ingen symboler i denne listen.")

    with st.form("add_watchlist_symbol_form"):
        new_ticker = st.text_input("Legg til ticker")
        add_submit = st.form_submit_button("Legg til")

        if add_submit:
            try:
                ticker = new_ticker.strip().upper()
                add_symbol_to_watchlist(editor_list, ticker)
                reload_watchlists()

                validation_note = ""
                try:
                    with st.spinner(f"Validerer {ticker}..."):
                        result, _ = analyze_stock(ticker)
                    validation_note = (
                        f" Validering OK: score {result['score']}, "
                        f"{result['anbefaling']}."
                    )
                except Exception as exc:
                    validation_note = (
                        f" Ticker lagret, men validering feilet: {exc}"
                    )

                st.session_state.watchlist_feedback = {
                    "type": "success",
                    "message": (
                        f"La til {ticker} i {editor_list}."
                        f"{validation_note}"
                    ),
                }
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    with st.expander("Alle (kun visning)", expanded=False):
        alle_symbols = WATCHLISTS.get("Alle", [])
        st.caption(
            f"{len(alle_symbols)} unike symboler fra alle lister."
        )
        show_dataframe(
            pd.DataFrame({
                "Ticker": alle_symbols,
                "Selskap": [
                    get_company_name(symbol)
                    for symbol in alle_symbols
                ],
            })
            if alle_symbols
            else pd.DataFrame(columns=["Ticker", "Selskap"])
        )


with tab_allocation:
    st.subheader("Kapitalallokering")

    allocation = build_portfolio_allocation(
        watchlist_report
    )

    st.markdown("### Kan økes")
    show_dataframe(allocation["buy_allocation"])

    st.markdown("### Behold / ikke øk")
    show_dataframe(allocation["hold_list"])

    st.markdown("### Ikke kjøp / vurder salg")
    show_dataframe(allocation["avoid_list"])


with tab_orders:
    st.subheader("Pending ordre")

    current_orders = load_pending_orders([])
    current_portfolio = load_portfolio([])

    pending_orders = analyze_pending_orders(
        current_orders,
        watchlist_report,
    )

    show_dataframe(pending_orders)

    st.markdown("## Ny kjøpsordre")

    with st.form("buy_order_form"):
        buy_ticker = st.text_input(
            "Ticker",
            value="AAPL",
        )

        buy_shares = st.number_input(
            "Antall aksjer",
            min_value=1.0,
            value=1.0,
            step=1.0,
        )

        buy_limit = st.number_input(
            "Limit-kurs",
            min_value=0.0,
            value=0.0,
            step=1.0,
        )

        buy_note = st.text_input(
            "Notat",
            value="",
        )

        buy_submit = st.form_submit_button(
            "Opprett kjøpsordre"
        )

        if buy_submit:
            create_buy_order(
                current_orders,
                ticker=buy_ticker,
                shares=buy_shares,
                limit_price=buy_limit if buy_limit > 0 else None,
                note=buy_note,
            )

            st.success("Kjøpsordre opprettet.")
            st.rerun()

    st.markdown("## Ny salgsordre")

    if current_portfolio:
        position_options = {
            (
                f"{p['ticker']} | "
                f"{p['shares']} aksjer | "
                f"kjøpt {p.get('buy_datetime', 'ukjent')}"
            ): p
            for p in current_portfolio
        }

        with st.form("sell_order_form"):
            selected_position_label = st.selectbox(
                "Velg posisjon",
                list(position_options.keys()),
            )

            selected_position = position_options[
                selected_position_label
            ]

            sell_shares = st.number_input(
                "Antall aksjer å selge",
                min_value=1.0,
                max_value=float(selected_position["shares"]),
                value=float(selected_position["shares"]),
                step=1.0,
            )

            sell_limit = st.number_input(
                "Limit-kurs",
                min_value=0.0,
                value=0.0,
                step=1.0,
            )

            sell_note = st.text_input(
                "Notat",
                value="",
                key="sell_note",
            )

            sell_submit = st.form_submit_button(
                "Opprett salgsordre"
            )

            if sell_submit:
                create_sell_order(
                    current_orders,
                    current_portfolio,
                    position_id=selected_position["position_id"],
                    shares=sell_shares,
                    limit_price=sell_limit if sell_limit > 0 else None,
                    note=sell_note,
                )

                st.success("Salgsordre opprettet.")
                st.rerun()
    else:
        st.info("Ingen posisjoner å selge fra.")

    st.markdown("## Effektuer / kanseller ordre")

    if current_orders:
        order_options = {
            f"{o['ticker']} | {o['action']} | {o['shares']} aksjer": o
            for o in current_orders
        }

        selected_order_label = st.selectbox(
            "Velg pending ordre",
            list(order_options.keys()),
        )

        selected_order = order_options[
            selected_order_label
        ]

        execution_price = st.number_input(
            "Effektuert kurs",
            min_value=0.0,
            value=float(
                selected_order.get("limit_price") or 0.0
            ),
            step=1.0,
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Bekreft effektuering"):
                execute_order(
                    current_orders,
                    current_portfolio,
                    order_id=selected_order["order_id"],
                    executed_price=execution_price,
                )

                refresh_context()

                st.success("Ordre effektuert.")
                st.rerun()

        with col2:
            if st.button("Ordre ikke effektuert"):
                cancel_order(
                    current_orders,
                    selected_order["order_id"],
                )

                st.warning("Ordre kansellert.")
                st.rerun()
    else:
        st.info("Ingen pending ordre.")


with tab_portfolio:
    st.subheader("Portefølje")

    if valid_portfolio_rows(portfolio_report).empty:
        st.info("Ingen portefølje.")
    else:
        summary = summarize_portfolio(portfolio_report)

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Kostverdi",
            summary["total_cost_value"],
        )

        col2.metric(
            "Markedsverdi",
            summary["total_market_value"],
        )

        col3.metric(
            "Urealisert gevinst/tap",
            summary["total_unrealized_profit_loss"],
        )

        col4.metric(
            "Urealisert %",
            f"{summary['total_unrealized_gain_pct']}%",
        )

        st.markdown("### Posisjoner")

        st.dataframe(
            valid_portfolio_rows(portfolio_report),
            width="stretch",
            hide_index=True,
        )

    pr = dashboard.get("portfolio_risk", {})
    with st.expander("Portfolio risk", expanded=False):
        r1, r2, r3 = st.columns(3)
        r1.metric(
            "Antall posisjoner",
            pr.get("positions", dashboard["portfolio_summary"].get("positions", 0)),
        )
        r2.metric("Topp posisjon %", f"{pr.get('top_position_pct', 0)}%")
        r3.metric(
            "Top 3 konsentrasjon %",
            f"{pr.get('top3_concentration_pct', 0)}%",
        )
        st.caption("Topp posisjoner")
        show_dataframe(pr.get("top_positions"))
        st.caption("Allokering (topp 10)")
        allocations = pr.get("allocations")
        if allocations is not None and not allocations.empty:
            show_dataframe(allocations.head(10))
        else:
            st.info("Ingen allokeringsdata.")

    with st.expander("Svekkende posisjoner", expanded=False):
        show_dataframe(dashboard.get("weakening_positions"))

    with st.expander("Sterke vinnere", expanded=False):
        show_dataframe(dashboard.get("strong_winners"))

    with st.expander("Porteføljevarsler", expanded=False):
        show_dataframe(dashboard.get("risk_alerts"))

    st.markdown("### Rå porteføljedata")
    show_dataframe(load_portfolio([]))


with tab_history:
    st.subheader("Ordrehistorikk")

    history_report = analyze_order_history(
        load_order_history([])
    )

    show_dataframe(history_report)


with tab_snapshots:
    st.subheader("Snapshot-historikk")

    snapshot_changes = dashboard.get("changes_since_last_snapshot")
    if snapshot_changes is None:
        st.info(
            "Ingen snapshot lagret ennå. "
            "Lagre et snapshot fra kontrollpanelet for å se endringer."
        )
    else:
        with st.expander("Endringer siden sist snapshot", expanded=True):
            st.markdown("#### Anbefaling endret")
            recommendation_changed = snapshot_changes[
                "recommendation_changed"
            ]
            if recommendation_changed.empty:
                st.info("Ingen endringer i anbefaling.")
            else:
                show_dataframe(recommendation_changed)

            st.markdown("#### Store score-endringer")
            large_score_changes = snapshot_changes["large_score_changes"]
            if large_score_changes.empty:
                st.info("Ingen store score-endringer.")
            else:
                show_dataframe(large_score_changes)

    snapshots = compare_snapshots()

    if snapshots.empty:
        st.info("Ingen snapshots lagret ennå.")
    else:
        st.dataframe(
            snapshots,
            width="stretch",
            hide_index=True,
        )


with tab_backtest:
    st.subheader("Backtest av signalmodell")

    active_config = get_active_backtest_config()

    st.write("Aktiv backtest-konfig:")
    st.json(active_config)

    strategy_specific = st.checkbox(
        "Bruk strategi-spesifikke exits",
        value=False,
    )

    if st.button("Kjør backtest"):
        with st.spinner("Kjører backtest..."):
            st.session_state.backtest_result = backtest_signal_watchlist(
                get_active_watchlist(),
                strategy_specific=strategy_specific,
                **active_config,
            )
            st.session_state.backtest_mode = (
                "Strategy-specific exits"
                if strategy_specific
                else "Baseline"
            )

    if "backtest_result" in st.session_state:
        st.markdown(
            f"**Modus:** {st.session_state.get('backtest_mode', 'Baseline')}"
        )

        st.dataframe(
            st.session_state.backtest_result,
            width="stretch",
            hide_index=True,
        )

        st.text(
            summarize_backtest_result(
                st.session_state.backtest_result
            )
        )


with tab_walk_forward:
    st.subheader("Rolling walk-forward")

    if st.button("Kjør walk-forward"):
        with st.spinner("Kjører rolling walk-forward..."):
            st.session_state.walk_forward_result = rolling_walk_forward(
                get_active_watchlist()
            )

    if "walk_forward_result" in st.session_state:
        st.dataframe(
            st.session_state.walk_forward_result,
            width="stretch",
            hide_index=True,
        )

        st.text(
            summarize_rolling_walk_forward(
                st.session_state.walk_forward_result
            )
        )


with tab_chat:
    chat_title_col, chat_clear_col = st.columns(
        [5, 1],
        vertical_alignment="center",
    )
    with chat_title_col:
        st.subheader("Chat")
    with chat_clear_col:
        if st.button("Tøm chat", key="clear_chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    chat_history = st.container(height=500, autoscroll=True)
    with chat_history:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    question = st.chat_input(
        "Still et spørsmål om aksjene dine..."
    )

    if question:
        st.session_state.messages.append(
            {"role": "user", "content": question}
        )

        answer = ask_agent(
            question,
            st.session_state.context,
        )

        st.session_state.messages.append(
            {"role": "assistant", "content": answer}
        )

        st.rerun()

