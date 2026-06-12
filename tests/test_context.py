import unittest
from unittest.mock import patch

import pandas as pd

from src.context import resolve_portfolio_report
from src.dashboard import _empty_portfolio_risk


def _portfolio_row(**overrides):
    base = {
        "ticker": "AAPL",
        "market_value": 2905.5,
        "unrealized_gain_pct": 62.32,
        "current_price": 290.55,
        "cost_value": 1790.0,
        "portefølje_råd": "HOLD",
        "anbefaling": "HOLD / OBSERVER",
        "trailing_stop_loss": 250.0,
    }
    base.update(overrides)
    return base


class ResolvePortfolioReportTests(unittest.TestCase):
    def test_updates_stale_portfolio_risk_when_report_is_valid(self):
        report = pd.DataFrame([_portfolio_row()])
        context = {
            "portfolio_report": report,
            "dashboard": {
                "portfolio_summary": {"positions": 0},
                "portfolio_risk": _empty_portfolio_risk(),
            },
        }
        portfolio = [{"ticker": "AAPL", "buy_price": 100, "shares": 10}]

        result = resolve_portfolio_report(context, portfolio)

        self.assertIs(result, report)
        self.assertTrue(context["dashboard"]["portfolio_risk"]["available"])
        self.assertEqual(context["dashboard"]["portfolio_risk"]["positions"], 1)
        self.assertEqual(
            context["dashboard"]["portfolio_summary"]["positions"],
            1,
        )
        self.assertEqual(
            context["dashboard"]["portfolio_risk"]["total_market_value"],
            context["dashboard"]["portfolio_summary"]["total_market_value"],
        )

    @patch("src.context.ensure_portfolio_report")
    def test_lazy_analyze_updates_portfolio_risk(self, mock_ensure):
        report = pd.DataFrame([_portfolio_row(ticker="MSFT", market_value=1500)])
        mock_ensure.return_value = report
        context = {
            "portfolio_report": None,
            "dashboard": {
                "portfolio_summary": {"positions": 0},
                "portfolio_risk": _empty_portfolio_risk(),
            },
        }
        portfolio = [{"ticker": "MSFT", "buy_price": 200, "shares": 5}]

        result = resolve_portfolio_report(context, portfolio)

        mock_ensure.assert_called_once_with(None, portfolio)
        self.assertIs(result, report)
        self.assertTrue(context["dashboard"]["portfolio_risk"]["available"])
        self.assertEqual(context["dashboard"]["portfolio_risk"]["positions"], 1)
        self.assertEqual(context["dashboard"]["portfolio_risk"]["top_position_pct"], 100.0)

    def test_empty_portfolio_leaves_context_unchanged(self):
        context = {
            "portfolio_report": None,
            "dashboard": {
                "portfolio_risk": _empty_portfolio_risk(),
            },
        }

        result = resolve_portfolio_report(context, [])

        self.assertIsNone(result)
        self.assertFalse(context["dashboard"]["portfolio_risk"]["available"])


if __name__ == "__main__":
    unittest.main()
