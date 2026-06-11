import streamlit as st
import pandas as pd

from src.agent import ask_agent
from src.context import build_agent_context
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
from src.portfolio import summarize_portfolio
from src.config import (
    load_watchlists,
    load_backtest_config,
    add_symbol_to_watchlist,
    remove_symbol_from_watchlist,
)
from src.strategy_classification import STRATEGY_TYPES
from src.analysis import analyze_stock
from src.company_names import get_company_name
from src.screener import suggest_watchlist_additions, load_screening_universe
from src.research_ideas import (
    load_research_ideas,
    add_research_idea,
    remove_research_idea,
    update_research_ideas,
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
    with st.spinner("Analyserer watchlist og portefølje..."):
        st.session_state.context = build_agent_context(
            get_active_watchlist(),
            PORTFOLIO,
            pending_orders=PENDING_ORDERS,
            pause_seconds=1,
        )


def refresh_context():
    with st.spinner("Oppdaterer analyser..."):
        st.session_state.context = build_agent_context(
            get_active_watchlist(),
            load_portfolio([]),
            pending_orders=load_pending_orders([]),
            pause_seconds=1,
        )


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

    if st.button("Tøm chat"):
        st.session_state.messages = []
        st.rerun()


watchlist_report = st.session_state.context["watchlist_report"]
portfolio_report = st.session_state.context["portfolio_report"]
dashboard = st.session_state.context["dashboard"]
daily_flow = st.session_state.context["daily_flow"]
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
    st.markdown("### Morning Briefing")

    regime = daily_flow["market_regime"]
    regime_signals = regime["signals"]

    st.markdown(f"**{regime['label']}**")
    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric("Kjøp", regime_signals["buy_count"])
    b2.metric("Svake/unngå", regime_signals["weak_avoid_count"])
    b3.metric("Snitt RS", f"{regime_signals['avg_relative_strength']}%")
    b4.metric("Snitt score", regime_signals["avg_score"])
    b5.metric("Unngå/selg", regime_signals["avoid_count"])

    for bullet in daily_flow["summary_bullets"]:
        st.markdown(f"- {bullet}")

    with st.expander("Detaljer", expanded=False):
        st.markdown("#### Muligheter")
        opportunities = daily_flow["key_opportunities"]

        st.caption("Topp kjøpskandidater")
        show_dataframe(opportunities["new_buy_candidates"])

        c1, c2 = st.columns(2)
        with c1:
            st.caption("Sterkest momentum")
            show_dataframe(opportunities["strongest_momentum"])
        with c2:
            st.caption("Sterkeste quality compounders")
            show_dataframe(opportunities["strongest_quality_compounders"])

        st.markdown("#### Risikovarsler")
        alerts = daily_flow["risk_alerts"]
        risk_frames = [
            alerts["near_trailing_stop"],
            alerts["weakening_positions"],
            alerts["large_drawdowns"],
            alerts["other_alerts"],
        ]
        combined_alerts = pd.concat(
            [df for df in risk_frames if df is not None and not df.empty],
            ignore_index=True,
        )

        concentration = alerts["concentration_risk"]
        if concentration.get("has_risk"):
            for item in concentration["alerts"]:
                st.warning(f"{item['alert']}: {item['details']}")

        if combined_alerts.empty and not concentration.get("has_risk"):
            st.info("Ingen risikovarsler.")
        else:
            show_dataframe(combined_alerts)

        st.markdown("#### Ventende ordre")
        pending = daily_flow["pending_orders"]
        st.caption(pending["summary"])
        show_dataframe(pending["orders"])

    st.divider()

    st.markdown("### Markedsregime")
    market_regime = dashboard["market_regime"]

    if not market_regime.get("available"):
        st.info(market_regime.get("message", "Markedsregime utilgjengelig."))
    else:
        st.markdown(f"**{market_regime['regime_label']}**")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Benchmark", market_regime["benchmark_symbol"])
        m2.metric("Kurs", market_regime["benchmark_price"])
        m3.metric("SMA20", market_regime["sma20"])
        m4.metric("SMA50", market_regime["sma50"])
        m5.metric("SMA100", market_regime["sma100"])

        if market_regime["reasons"]:
            st.caption(" · ".join(market_regime["reasons"]))

        st.info(market_regime["interpretation"])

        kpis = market_regime["watchlist_kpis"]
        k1, k2, k3 = st.columns(3)
        k1.metric(
            "Sterk opptrend",
            f"{kpis['strong_uptrend_pct']}%",
        )
        k2.metric(
            "Svak/negativ trend",
            f"{kpis['weak_trend_pct']}%",
        )
        k3.metric(
            "Snitt relativ styrke",
            f"{kpis['avg_relative_strength']}%",
        )

    st.subheader("Dagens situasjon")

    market = dashboard["market_summary"]
    portfolio_summary = dashboard["portfolio_summary"]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Kjøpskandidater",
        market["buy_count"],
    )

    col2.metric(
        "Hold / observer",
        market["hold_count"],
    )

    col3.metric(
        "Unngå / selg",
        market["avoid_count"],
    )

    col4.metric(
        "Aksjer analysert",
        market["total_symbols"],
    )

    st.markdown("### Strategityper")
    strategy_counts = dashboard.get("strategy_type_counts", {})
    if not strategy_counts or sum(strategy_counts.values()) == 0:
        st.info("Ingen strategidata tilgjengelig.")
    else:
        strategy_labels = {
            "QUALITY_COMPOUNDER": "Quality Compounder",
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

    st.markdown("### Strategiprofiler")
    strategy_profiles = dashboard.get("strategy_profiles")
    if strategy_profiles is None or strategy_profiles.empty:
        st.info("Ingen strategiprofiler tilgjengelig.")
    else:
        show_dataframe(strategy_profiles)

    st.markdown("### Endringer siden sist snapshot")
    snapshot_changes = dashboard.get("changes_since_last_snapshot")
    if snapshot_changes is None:
        st.info(
            "Ingen snapshot lagret ennå. "
            "Lagre et snapshot fra kontrollpanelet for å se endringer."
        )
    else:
        st.markdown("#### Anbefaling endret")
        recommendation_changed = snapshot_changes["recommendation_changed"]
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

    st.markdown("### Portefølje")

    p1, p2, p3, p4 = st.columns(4)

    p1.metric(
        "Kostverdi",
        portfolio_summary["total_cost_value"],
    )

    p2.metric(
        "Markedsverdi",
        portfolio_summary["total_market_value"],
    )

    p3.metric(
        "Urealisert gevinst/tap",
        portfolio_summary["total_unrealized_profit_loss"],
    )

    p4.metric(
        "Urealisert %",
        f"{portfolio_summary['total_unrealized_gain_pct']}%",
    )

    # Portfolio risk section
    st.markdown("### Portfolio Risk")
    pr = dashboard.get("portfolio_risk", {})

    r1, r2, r3 = st.columns(3)
    r1.metric(
        "Antall posisjoner",
        pr.get("positions", portfolio_summary.get("positions", 0)),
    )

    r2.metric(
        "Topp posisjon %",
        f"{pr.get('top_position_pct', 0)}%",
    )

    r3.metric(
        "Top 3 konsentrasjon %",
        f"{pr.get('top3_concentration_pct', 0)}%",
    )

    st.markdown("Topp posisjoner")
    try:
        show_dataframe(pr.get("top_positions", None))
    except Exception:
        st.info("Ingen topp posisjoner.")

    st.markdown("Allokering (topp 10)")
    try:
        show_dataframe(pr.get("allocations", None).head(10))
    except Exception:
        st.info("Ingen allokeringst data.")

    # Weakening positions
    st.markdown("### Svekkende posisjoner")
    show_dataframe(dashboard.get("weakening_positions"))

    # Strong existing winners
    st.markdown("### Sterke vinnere i porteføljen")
    show_dataframe(dashboard.get("strong_winners"))

    st.markdown("### Topp kjøpskandidater")
    show_dataframe(dashboard["top_buy_candidates"])

    st.markdown("### Viktigste varsler")
    show_dataframe(dashboard["risk_alerts"])

    st.markdown("### Pending ordre")
    show_dataframe(dashboard["pending_orders"])


with tab_ranking:
    st.subheader("Rangert watchlist")
    show_ranking_table(ranked)


with tab_screening:
    st.subheader("Screening")
    st.caption(
        "Screen universer utenfor watchlistene dine, lagre idéer, "
        "eller legg kandidater direkte til watchlist."
    )

    st.markdown("### Finn nye kandidater")
    st.caption(
        "Analyserer hele universet, filtrerer bort symboler som allerede "
        "ligger på watchlistene dine, og viser de beste forslagene."
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
            research_ideas = load_research_ideas()
            if not research_ideas:
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

    research_ideas = load_research_ideas()
    if not research_ideas:
        st.info("Ingen lagrede research-idéer.")
    else:
        show_research_ideas(research_ideas, research_target_watchlist)


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

    if portfolio_report is None or portfolio_report.empty:
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
            portfolio_report,
            width="stretch",
            hide_index=True,
        )

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

        with st.chat_message("user"):
            st.markdown(question)

        answer = ask_agent(
            question,
            st.session_state.context,
        )

        st.session_state.messages.append(
            {"role": "assistant", "content": answer}
        )

        with st.chat_message("assistant"):
            st.markdown(answer)