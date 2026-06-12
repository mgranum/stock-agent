import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from src.daily_refresh import build_refresh_summary, run_daily_refresh


def _success_result(**overrides):
    base = {
        "success": True,
        "started_at": "2026-06-12T08:00:00+00:00",
        "finished_at": "2026-06-12T08:05:00+00:00",
        "duration_seconds": 300.0,
        "symbols_processed": 4,
        "portfolio_positions": 2,
        "watchlist_symbols": 4,
        "earnings_updated": True,
        "analyst_updated": True,
        "news_updated": True,
        "sentiment_updated": True,
        "screening_updated": True,
        "snapshot_updated": True,
        "errors": [],
    }
    base.update(overrides)
    return base


class BuildRefreshSummaryTests(unittest.TestCase):
    def test_builds_expected_summary(self):
        summary = build_refresh_summary(_success_result())

        self.assertIn("Daily Refresh Fullført", summary)
        self.assertIn("- 4 symboler analysert", summary)
        self.assertIn("- 2 porteføljeposisjoner", summary)
        self.assertIn("- Earnings oppdatert", summary)
        self.assertIn("- Analyst consensus oppdatert", summary)
        self.assertIn("- News oppdatert", summary)
        self.assertIn("- Screening oppdatert", summary)

    def test_includes_error_count(self):
        summary = build_refresh_summary(
            _success_result(
                success=False,
                errors=[{"symbol": "BAD", "step": "news", "error": "fail"}],
            )
        )

        self.assertIn("- 1 feil under oppdatering", summary)


class RunDailyRefreshTests(unittest.TestCase):
    @patch("src.daily_refresh.save_context_snapshot")
    @patch("src.daily_refresh.save_model_snapshot")
    @patch("src.daily_refresh.build_agent_context")
    @patch("src.daily_refresh.screen_obx")
    @patch("src.daily_refresh.screen_nordics")
    @patch("src.daily_refresh.screen_us_large")
    @patch("src.daily_refresh.build_sentiment_summary")
    @patch("src.daily_refresh.build_news_summary", return_value={"items": [], "last_updated": "2026-06-12T08:00:00+00:00"})
    @patch("src.daily_refresh.get_news")
    @patch("src.daily_refresh.get_analyst")
    @patch("src.daily_refresh.get_earnings")
    @patch("src.daily_refresh.analyze_fundamental_history")
    @patch("src.daily_refresh.get_fundamentals")
    @patch("src.daily_refresh.analyze_technicals")
    @patch("src.daily_refresh.get_benchmark_for_symbol", return_value="^GSPC")
    @patch("src.daily_refresh.add_indicators", side_effect=lambda df: df)
    @patch("src.daily_refresh.get_daily_prices")
    @patch("src.daily_refresh.load_research_ideas", return_value=[])
    @patch("src.daily_refresh.load_pending_orders", return_value=[])
    @patch("src.daily_refresh.load_portfolio")
    @patch("src.daily_refresh.load_watchlists")
    def test_runs_without_exception(
        self,
        mock_load_watchlists,
        mock_load_portfolio,
        _mock_pending,
        _mock_research,
        _mock_prices,
        _mock_indicators,
        _mock_benchmark,
        _mock_technicals,
        _mock_fundamentals,
        _mock_history,
        _mock_earnings,
        _mock_analyst,
        mock_get_news,
        _mock_build_news_summary,
        _mock_sentiment,
        _mock_screen_us,
        _mock_screen_nordics,
        _mock_screen_obx,
        mock_build_context,
        _mock_save_snapshot,
        _mock_save_context,
    ):
        mock_load_watchlists.return_value = {
            "Alle": ["AAPL", "MSFT"],
            "USA": ["AAPL", "MSFT"],
        }
        mock_load_portfolio.return_value = [
            {"ticker": "AAPL", "buy_price": 100, "shares": 10},
        ]
        mock_get_news.return_value = []
        mock_build_context.return_value = {
            "watchlist": ["AAPL", "MSFT"],
            "dashboard": {"portfolio_summary": {"positions": 1}},
        }

        result = run_daily_refresh(pause_seconds=0, today=date(2026, 6, 12))

        self.assertTrue(result["success"])
        self.assertEqual(result["symbols_processed"], 2)
        self.assertEqual(result["portfolio_positions"], 1)
        self.assertEqual(result["watchlist_symbols"], 2)
        self.assertIn("started_at", result)
        self.assertIn("finished_at", result)
        self.assertIsInstance(result["duration_seconds"], float)
        mock_build_context.assert_called_once()

    @patch("src.daily_refresh.save_context_snapshot")
    @patch("src.daily_refresh.save_model_snapshot")
    @patch("src.daily_refresh.build_agent_context")
    @patch("src.daily_refresh.screen_obx")
    @patch("src.daily_refresh.screen_nordics")
    @patch("src.daily_refresh.screen_us_large")
    @patch("src.daily_refresh.build_sentiment_summary")
    @patch("src.daily_refresh.build_news_summary", return_value={"items": [], "last_updated": "2026-06-12T08:00:00+00:00"})
    @patch("src.daily_refresh.get_news")
    @patch("src.daily_refresh.get_analyst")
    @patch("src.daily_refresh.get_earnings")
    @patch("src.daily_refresh.analyze_fundamental_history")
    @patch("src.daily_refresh.get_fundamentals")
    @patch("src.daily_refresh.analyze_technicals")
    @patch("src.daily_refresh.get_benchmark_for_symbol", return_value="^GSPC")
    @patch("src.daily_refresh.add_indicators", side_effect=lambda df: df)
    @patch("src.daily_refresh.get_daily_prices")
    @patch("src.daily_refresh.load_research_ideas", return_value=[])
    @patch("src.daily_refresh.load_pending_orders", return_value=[])
    @patch("src.daily_refresh.load_portfolio")
    @patch("src.daily_refresh.load_watchlists")
    def test_one_ticker_error_does_not_stop_refresh(
        self,
        mock_load_watchlists,
        mock_load_portfolio,
        _mock_pending,
        _mock_research,
        mock_get_prices,
        _mock_indicators,
        _mock_benchmark,
        _mock_technicals,
        mock_get_fundamentals,
        _mock_history,
        _mock_earnings,
        _mock_analyst,
        mock_get_news,
        _mock_build_news_summary,
        _mock_sentiment,
        _mock_screen_us,
        _mock_screen_nordics,
        _mock_screen_obx,
        mock_build_context,
        _mock_save_snapshot,
        _mock_save_context,
    ):
        mock_load_watchlists.return_value = {
            "Alle": ["AAPL", "BAD"],
            "USA": ["AAPL", "BAD"],
        }
        mock_load_portfolio.return_value = []
        mock_get_fundamentals.side_effect = [
            {"symbol": "AAPL"},
            RuntimeError("fundamentals failed"),
        ]
        mock_get_prices.return_value = pd.DataFrame(
            {"close": [100.0], "rsi": [50.0], "sma20": [99.0], "sma50": [98.0],
             "macd": [1.0], "macd_signal": [0.5], "volume": [1000.0],
             "volume_avg20": [900.0]},
            index=pd.to_datetime(["2026-06-12"]),
        )
        mock_get_news.return_value = []
        mock_build_context.return_value = {
            "watchlist": ["AAPL", "BAD"],
            "dashboard": {"portfolio_summary": {"positions": 0}},
        }

        result = run_daily_refresh(pause_seconds=0, today=date(2026, 6, 12))

        self.assertFalse(result["success"])
        self.assertEqual(result["symbols_processed"], 2)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["symbol"], "BAD")
        self.assertEqual(result["errors"][0]["step"], "fundamentals")
        mock_build_context.assert_called_once()

    @patch("src.daily_refresh.save_context_snapshot")
    @patch("src.daily_refresh.save_model_snapshot")
    @patch("src.daily_refresh.build_agent_context")
    @patch("src.daily_refresh.screen_obx")
    @patch("src.daily_refresh.screen_nordics")
    @patch("src.daily_refresh.screen_us_large")
    @patch("src.daily_refresh.build_sentiment_summary")
    @patch("src.daily_refresh.build_news_summary", return_value={"items": [], "last_updated": "2026-06-12T08:00:00+00:00"})
    @patch("src.daily_refresh.get_news", return_value=[])
    @patch("src.daily_refresh.get_analyst")
    @patch("src.daily_refresh.get_earnings")
    @patch("src.daily_refresh.analyze_fundamental_history")
    @patch("src.daily_refresh.get_fundamentals")
    @patch("src.daily_refresh.analyze_technicals")
    @patch("src.daily_refresh.get_benchmark_for_symbol", return_value="^GSPC")
    @patch("src.daily_refresh.add_indicators", side_effect=lambda df: df)
    @patch("src.daily_refresh.get_daily_prices")
    @patch("src.daily_refresh.load_research_ideas", return_value=[])
    @patch("src.daily_refresh.load_pending_orders", return_value=[])
    @patch("src.daily_refresh.load_portfolio", return_value=[])
    @patch("src.daily_refresh.load_watchlists")
    def test_empty_portfolio_handled(
        self,
        mock_load_watchlists,
        mock_load_portfolio,
        _mock_pending,
        _mock_research,
        _mock_prices,
        _mock_indicators,
        _mock_benchmark,
        _mock_technicals,
        _mock_fundamentals,
        _mock_history,
        _mock_earnings,
        _mock_analyst,
        _mock_news,
        _mock_build_news_summary,
        _mock_sentiment,
        _mock_screen_us,
        _mock_screen_nordics,
        _mock_screen_obx,
        mock_build_context,
        _mock_save_snapshot,
        _mock_save_context,
    ):
        mock_load_watchlists.return_value = {
            "Alle": ["AAPL"],
            "USA": ["AAPL"],
        }
        mock_build_context.return_value = {
            "watchlist": ["AAPL"],
            "dashboard": {"portfolio_summary": {"positions": 0}},
        }

        result = run_daily_refresh(pause_seconds=0, today=date(2026, 6, 12))

        self.assertTrue(result["success"])
        self.assertEqual(result["portfolio_positions"], 0)
        mock_load_portfolio.assert_called_once()
        mock_build_context.assert_called_once_with(
            ["AAPL"],
            portfolio=[],
            pending_orders=[],
            research_ideas=[],
            pause_seconds=0,
        )


if __name__ == "__main__":
    unittest.main()
