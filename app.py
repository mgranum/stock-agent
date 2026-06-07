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
from src.config import load_watchlists, load_backtest_config
from src.dashboard import build_dashboard


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


def get_active_watchlist():
    return WATCHLISTS[
        st.session_state.selected_watchlist_name
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
            pause_seconds=1,
        )


def refresh_context():
    with st.spinner("Oppdaterer analyser..."):
        st.session_state.context = build_agent_context(
            get_active_watchlist(),
            load_portfolio([]),
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
ranked = rank_report(watchlist_report)

dashboard = build_dashboard(
    watchlist_report=watchlist_report,
    portfolio_report=portfolio_report,
    pending_orders=load_pending_orders([]),
)


tab_dashboard, tab_ranking, tab_screening, tab_allocation, tab_orders, tab_portfolio, tab_history, tab_snapshots, tab_backtest, tab_walk_forward, tab_chat = st.tabs(
    [
        "Dashboard",
        "Rangering",
        "Screening",
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

    buy_candidates = rank_report(
        watchlist_report[
            watchlist_report["anbefaling"] == "KJØP / ØK"
        ]
    )

    quality_companies = rank_report(
        watchlist_report[
            (watchlist_report["fundamental_score"] >= 70)
            & (watchlist_report["fundamental_history_score"] >= 70)
            & (watchlist_report["score"] >= 55)
        ]
    )

    growth_with_trend = rank_report(
        watchlist_report[
            (watchlist_report["score"] >= 60)
            & (watchlist_report["fundamental_history_score"] >= 70)
            & (watchlist_report["relative_strength_20d"] > 0)
            & (watchlist_report["trend_regime"] == "STERK OPPTREND")
        ]
    )

    quality_not_buy = rank_report(
        watchlist_report[
            (watchlist_report["fundamental_score"] >= 70)
            & (watchlist_report["fundamental_history_score"] >= 70)
            & (watchlist_report["anbefaling"] != "KJØP / ØK")
        ]
    )

    st.markdown("### Kjøpskandidater")
    show_ranking_table(buy_candidates)

    st.markdown("### Kvalitetsselskaper")
    show_ranking_table(quality_companies)

    st.markdown("### Vekst med sterk trend")
    show_ranking_table(growth_with_trend)

    st.markdown("### Sterke fundamentals, men ikke kjøp nå")
    show_ranking_table(quality_not_buy)


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

    if st.button("Kjør backtest"):
        with st.spinner("Kjører backtest..."):
            st.session_state.backtest_result = backtest_signal_watchlist(
                get_active_watchlist(),
                **active_config,
            )

    if "backtest_result" in st.session_state:
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