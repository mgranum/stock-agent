from src.advisor import build_advisor_details, build_advisor_output
from src.alerts import build_alerts
from src.analysis import analyze_watchlist
from src.analyst import build_analyst_summary
from src.dashboard import build_dashboard, build_portfolio_risk
from src.daily_flow import build_daily_flow
from src.earnings import build_earnings_summary
from src.news import build_news_summary
from src.portfolio import analyze_portfolio, ensure_portfolio_report, summarize_portfolio
from src.sentiment import build_sentiment_summary, merge_sentiment_into_news_summary


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
    earnings_summary = build_earnings_summary(
        portfolio=portfolio,
        watchlist=watchlist,
    )
    analyst_summary = build_analyst_summary(
        portfolio=portfolio,
        watchlist=watchlist,
    )
    news_summary = build_news_summary(
        portfolio=portfolio,
        watchlist=watchlist,
    )
    sentiment_summary = build_sentiment_summary(news_summary)
    news_summary = merge_sentiment_into_news_summary(news_summary, sentiment_summary)
    dashboard = build_dashboard(
        watchlist_report=watchlist_report,
        portfolio_report=portfolio_report,
        pending_orders=orders,
        watchlist_symbols=watchlist,
        research_ideas=research_ideas or [],
    )
    dashboard["earnings_summary"] = earnings_summary
    dashboard["analyst_summary"] = analyst_summary
    dashboard["news_summary"] = news_summary
    dashboard["sentiment_summary"] = sentiment_summary
    advisor_output = build_advisor_output(
        portfolio_report=portfolio_report,
        analyst_summary=analyst_summary,
        sentiment_summary=sentiment_summary,
        earnings_summary=earnings_summary,
    )
    dashboard["advisor_output"] = advisor_output
    alerts = build_alerts(
        portfolio_report,
        orders,
        research_ideas or [],
        earnings_summary=earnings_summary,
    )
    advisor_details = build_advisor_details(
        advisor_output,
        portfolio_report,
        analyst_summary=analyst_summary,
        sentiment_summary=sentiment_summary,
        earnings_summary=earnings_summary,
        alerts=alerts,
    )
    daily_flow = build_daily_flow(
        watchlist_report=watchlist_report,
        portfolio_report=portfolio_report,
        dashboard=dashboard,
        pending_orders=orders,
        alerts=alerts,
        portfolio=portfolio,
    )

    context = {
        "watchlist": watchlist,
        "watchlist_report": watchlist_report,
        "portfolio_report": portfolio_report,
        "dashboard": dashboard,
        "daily_flow": daily_flow,
        "earnings_summary": earnings_summary,
        "analyst_summary": analyst_summary,
        "news_summary": news_summary,
        "sentiment_summary": sentiment_summary,
        "advisor_output": advisor_output,
        "advisor_details": advisor_details,
        "alerts": alerts,
    }

    return context


def resolve_portfolio_report(context, portfolio):
    report = ensure_portfolio_report(
        context.get("portfolio_report"),
        portfolio,
    )

    if report is not None:
        context["portfolio_report"] = report
        dashboard = context.setdefault("dashboard", {})
        dashboard["portfolio_summary"] = summarize_portfolio(report)
        dashboard["portfolio_risk"] = build_portfolio_risk(report)

    return report
