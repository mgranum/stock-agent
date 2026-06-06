import streamlit as st

from src.agent import ask_agent
from src.context import build_agent_context
from src.ranking import ranking_table
from src.watchlists import WATCHLIST_ALL, WATCHLIST_US, WATCHLIST_NORDICS
from src.model_backtest import save_model_snapshot, compare_snapshots
from src.signal_backtest import backtest_signal_watchlist
from src.backtest_report import summarize_backtest_result
from src.backtest_config import (
    SIGNAL_BACKTEST_BASELINE,
    SIGNAL_BACKTEST_OBX,
)
from src.walk_forward import rolling_walk_forward
from src.walk_forward_report import summarize_rolling_walk_forward
from src.portfolio_allocation import build_portfolio_allocation
from src.orders import analyze_pending_orders
from src.environment import (
    environment_label,
    is_prod,
)

if is_prod():
    from src.user_data_prod import (
        PORTFOLIO,
        PENDING_ORDERS,
    )
else:
    from src.user_data import (
        PORTFOLIO,
        PENDING_ORDERS,
    )

try:
    from src.watchlists import WATCHLIST_OBX
except ImportError:
    WATCHLIST_OBX = []


WATCHLISTS = {
    "Alle": WATCHLIST_ALL,
    "USA": WATCHLIST_US,
    "Norden": WATCHLIST_NORDICS,
    "OBX": WATCHLIST_OBX,
}


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
        return SIGNAL_BACKTEST_OBX

    return SIGNAL_BACKTEST_BASELINE


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
            PORTFOLIO,
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
    if df is None or df.empty:
        st.info("Ingen data å vise.")
    else:
        st.dataframe(
            df,
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
        df, path = save_model_snapshot(
            get_active_watchlist()
        )
        st.success(f"Snapshot lagret: {path}")

    if st.button("Tøm chat"):
        st.session_state.messages = []
        st.rerun()


watchlist_report = st.session_state.context["watchlist_report"]
portfolio_report = st.session_state.context["portfolio_report"]
ranked = rank_report(watchlist_report)

tab_ranking, tab_screening, tab_allocation, tab_orders, tab_portfolio, tab_snapshots, tab_backtest, tab_walk_forward, tab_chat = st.tabs(
    [
        "Rangering",
        "Screening",
        "Allocation",
        "Ordre",
        "Portefølje",
        "Snapshots",
        "Backtest",
        "Walk-forward",
        "Chat",
    ]
)

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

    pending_orders = analyze_pending_orders(
        PENDING_ORDERS,
        watchlist_report,
    )

    show_dataframe(pending_orders)

with tab_portfolio:
    st.subheader("Portefølje")

    if portfolio_report is None or portfolio_report.empty:
        st.info("Ingen portefølje lagt inn.")
    else:
        st.dataframe(
            portfolio_report,
            width="stretch",
            hide_index=True,
        )

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