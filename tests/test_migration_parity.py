import pandas as pd

from src.migration_parity import build_migration_parity_report
from src.presentation_queries import PresentationQueries


def _context_result(context):
    return {
        "loaded": True,
        "reason": "loaded",
        "context": context,
        "metadata": {"model_version": "test-v1", "date": "2026-08-09"},
        "expired": False,
    }


def _fixture():
    context = {
        "model_version": "test-v1",
        "watchlist_report": pd.DataFrame([
            {"ticker": "OWN", "score": 70, "anbefaling": "HOLD / OBSERVER"},
            {"ticker": "WATCH", "score": 80, "anbefaling": "KJØP / ØK"},
        ]),
        "portfolio_report": pd.DataFrame([
            {"ticker": "OWN", "stop_loss": 90, "trailing_stop_loss": 95, "unrealized_gain_pct": 20},
        ]),
        "opportunity_advisor": {"items": []},
        "dashboard": {},
    }
    portfolio = [{"ticker": "OWN", "buy_price": 100}]
    watchlists = {"Alle": ["OWN", "WATCH"]}
    queries = PresentationQueries(
        context_loader=lambda **_kwargs: _context_result(context),
        portfolio_loader=lambda _default=None: portfolio,
        watchlists_loader=lambda: watchlists,
        company_name_loader=str,
        refresh_state_loader=lambda: {},
        snapshots_loader=lambda: pd.DataFrame(),
        discovery_journal_loader=lambda: pd.DataFrame(),
    )
    return queries, context, portfolio, watchlists


def test_reports_pass_for_matching_presentations():
    queries, context, portfolio, watchlists = _fixture()

    report = build_migration_parity_report(
        queries, context, portfolio, watchlists
    )

    assert report["status"] == "PASS"
    assert report["failed"] == 0


def test_reports_field_level_difference():
    queries, context, portfolio, watchlists = _fixture()
    context["watchlist_report"].loc[
        context["watchlist_report"]["ticker"] == "WATCH", "score"
    ] = 81
    original_today = queries.today

    def changed_today():
        result = original_today()
        result["watchlist"][0]["score"] = 1
        return result

    queries.today = changed_today
    report = build_migration_parity_report(
        queries, context, portfolio, watchlists
    )

    assert report["status"] == "FAIL"
    assert any(
        check["name"] == "WATCH score" and not check["passed"]
        for check in report["checks"]
    )
