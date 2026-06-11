from src.analysis import analyze_watchlist
from src.portfolio import analyze_portfolio
from src.dashboard import build_dashboard
from src.daily_flow import build_daily_flow


def build_agent_context(
    watchlist,
    portfolio=None,
    pending_orders=None,
    research_ideas=None,
    pause_seconds=1,
):
    print("Analyserer watchlist...")

    watchlist_report = analyze_watchlist(
        watchlist,
        pause_seconds=pause_seconds
    )

    portfolio = portfolio or []
    portfolio_report = None

    if len(portfolio) > 0:
        print("Analyserer portefølje...")

        portfolio_report = analyze_portfolio(
            portfolio,
            pause_seconds=pause_seconds
        )

    orders = pending_orders or []
    dashboard = build_dashboard(
        watchlist_report=watchlist_report,
        portfolio_report=portfolio_report,
        pending_orders=orders,
        watchlist_symbols=watchlist,
        research_ideas=research_ideas or [],
    )
    daily_flow = build_daily_flow(
        watchlist_report=watchlist_report,
        portfolio_report=portfolio_report,
        dashboard=dashboard,
        pending_orders=orders,
    )

    context = {
        "watchlist": watchlist,
        "watchlist_report": watchlist_report,
        "portfolio_report": portfolio_report,
        "dashboard": dashboard,
        "daily_flow": daily_flow,
    }

    return context