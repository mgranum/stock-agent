from src.analysis import analyze_watchlist
from src.portfolio import analyze_portfolio


def build_agent_context(
    watchlist,
    portfolio=None,
    pause_seconds=1,
):
    print("Analyserer watchlist...")

    watchlist_report = analyze_watchlist(
        watchlist,
        pause_seconds=pause_seconds
    )

    portfolio_report = None

    if portfolio:
        print("Analyserer portefølje...")

        portfolio_report = analyze_portfolio(
            portfolio,
            pause_seconds=pause_seconds
        )

    context = {
        "watchlist": watchlist,
        "watchlist_report": watchlist_report,
        "portfolio_report": portfolio_report,
    }

    return context