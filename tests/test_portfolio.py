import unittest
from unittest.mock import patch

import pandas as pd

from src.portfolio import (
    build_portfolio_display_table,
    compute_position_metrics,
    position_cost_per_share,
    valid_portfolio_rows,
)


class PositionCostPerShareTests(unittest.TestCase):
    def test_uses_average_cost_when_present(self):
        position = {
            "ticker": "MSFT",
            "shares": 100,
            "average_cost": 215.40,
            "buy_price": 150.0,
        }

        self.assertEqual(position_cost_per_share(position), 215.40)

    def test_falls_back_to_buy_price(self):
        position = {
            "ticker": "MSFT",
            "shares": 100,
            "buy_price": 150.0,
        }

        self.assertEqual(position_cost_per_share(position), 150.0)

    def test_requires_cost_basis(self):
        with self.assertRaises(ValueError):
            position_cost_per_share({"ticker": "MSFT", "shares": 100})


class ComputePositionMetricsTests(unittest.TestCase):
    def test_average_cost_drives_gain_loss(self):
        position = {
            "ticker": "MSFT",
            "shares": 100,
            "average_cost": 200.0,
            "buy_price": 150.0,
        }

        metrics = compute_position_metrics(position, current_price=250.0)

        self.assertEqual(metrics["cost_per_share"], 200.0)
        self.assertEqual(metrics["cost_value"], 20000.0)
        self.assertEqual(metrics["market_value"], 25000.0)
        self.assertEqual(metrics["unrealized_profit_loss"], 5000.0)
        self.assertEqual(metrics["unrealized_gain_pct"], 25.0)

    def test_buy_price_fallback(self):
        position = {
            "ticker": "AAPL",
            "shares": 10,
            "buy_price": 100.0,
        }

        metrics = compute_position_metrics(position, current_price=110.0)

        self.assertEqual(metrics["cost_per_share"], 100.0)
        self.assertEqual(metrics["unrealized_profit_loss"], 100.0)
        self.assertEqual(metrics["unrealized_gain_pct"], 10.0)

    def test_snapshot_position_without_buy_price(self):
        position = {
            "ticker": "MSFT",
            "shares": 50,
            "average_cost": 215.40,
        }

        metrics = compute_position_metrics(position, current_price=300.0)

        self.assertEqual(metrics["cost_per_share"], 215.40)
        self.assertEqual(metrics["cost_value"], 10770.0)
        self.assertEqual(metrics["market_value"], 15000.0)
        self.assertEqual(metrics["unrealized_profit_loss"], 4230.0)
        self.assertAlmostEqual(metrics["unrealized_gain_pct"], 39.28, places=2)


class MixedPortfolioMetricsTests(unittest.TestCase):
    def test_mixed_portfolio_positions(self):
        positions = [
            {"ticker": "AAPL", "shares": 10, "buy_price": 100.0},
            {
                "ticker": "MSFT",
                "shares": 100,
                "average_cost": 200.0,
                "buy_price": 150.0,
            },
        ]
        prices = {"AAPL": 110.0, "MSFT": 250.0}

        metrics = [
            compute_position_metrics(position, prices[position["ticker"]])
            for position in positions
        ]

        self.assertEqual(metrics[0]["unrealized_gain_pct"], 10.0)
        self.assertEqual(metrics[1]["unrealized_gain_pct"], 25.0)

        total_cost = sum(row["cost_value"] for row in metrics)
        total_market = sum(row["market_value"] for row in metrics)
        total_pl = total_market - total_cost
        total_gain_pct = (total_pl / total_cost) * 100

        self.assertEqual(total_cost, 21000.0)
        self.assertEqual(total_market, 26100.0)
        self.assertEqual(total_pl, 5100.0)
        self.assertAlmostEqual(total_gain_pct, 24.29, places=2)


class AnalyzePortfolioTests(unittest.TestCase):
    @patch("src.portfolio.analyze_stock")
    def test_analyze_portfolio_uses_average_cost(self, mock_analyze):
        from src.portfolio import analyze_portfolio

        mock_analyze.return_value = (
            {
                "kurs": 250.0,
                "score": 60,
                "anbefaling": "HOLD",
                "trend_score": 3,
                "trend_regime": "MODERAT OPPTREND",
                "relative_strength_20d": 1.5,
                "trailing_stop_triggered": False,
                "kursmål": 280.0,
                "stop_loss": 200.0,
                "atr_stop_loss": 210.0,
                "trailing_stop_loss": 220.0,
                "tidshorisont": "uker",
            },
            pd.DataFrame(),
        )

        portfolio = [
            {
                "ticker": "MSFT",
                "shares": 100,
                "average_cost": 200.0,
                "buy_price": 150.0,
            }
        ]

        report = analyze_portfolio(portfolio, pause_seconds=0)
        row = report.iloc[0]

        self.assertEqual(row["cost_per_share"], 200.0)
        self.assertEqual(row["average_cost"], 200.0)
        self.assertEqual(row["buy_price"], 150.0)
        self.assertEqual(row["unrealized_gain_pct"], 25.0)

    @patch("src.portfolio.analyze_stock")
    def test_analyze_portfolio_buy_price_fallback(self, mock_analyze):
        from src.portfolio import analyze_portfolio

        mock_analyze.return_value = (
            {
                "kurs": 110.0,
                "score": 55,
                "anbefaling": "HOLD",
                "trend_score": 2,
                "trend_regime": "MODERAT OPPTREND",
                "relative_strength_20d": 0.5,
                "trailing_stop_triggered": False,
                "kursmål": 120.0,
                "stop_loss": 95.0,
                "atr_stop_loss": 98.0,
                "trailing_stop_loss": 100.0,
                "tidshorisont": "uker",
            },
            pd.DataFrame(),
        )

        portfolio = [{"ticker": "AAPL", "shares": 10, "buy_price": 100.0}]

        report = analyze_portfolio(portfolio, pause_seconds=0)
        row = report.iloc[0]

        self.assertEqual(row["cost_per_share"], 100.0)
        self.assertEqual(row["buy_price"], 100.0)
        self.assertNotIn("average_cost", report.columns)
        self.assertEqual(row["unrealized_gain_pct"], 10.0)


class PortfolioDisplayTableTests(unittest.TestCase):
    def test_display_table_shows_cost_and_gain_columns(self):
        df = pd.DataFrame(
            [
                {
                    "ticker": "MSFT",
                    "shares": 100,
                    "cost_per_share": 215.40,
                    "current_price": 250.0,
                    "cost_value": 21540.0,
                    "market_value": 25000.0,
                    "unrealized_profit_loss": 3460.0,
                    "unrealized_gain_pct": 16.06,
                    "portefølje_råd": "HOLD",
                    "anbefaling": "HOLD",
                    "trailing_stop_loss": 220.0,
                }
            ]
        )

        display = build_portfolio_display_table(df)

        self.assertIn("Gjennomsnittlig kostpris", display.columns)
        self.assertIn("Nåværende kurs", display.columns)
        self.assertIn("Gevinst/tap %", display.columns)
        self.assertEqual(display.iloc[0]["Gjennomsnittlig kostpris"], 215.40)


class ValidPortfolioRowsTests(unittest.TestCase):
    def test_keeps_only_rows_with_valid_metric_columns(self):
        df = pd.DataFrame(
            [
                {
                    "ticker": "AAPL",
                    "market_value": 2905.5,
                    "unrealized_gain_pct": 62.32,
                    "current_price": 290.55,
                    "cost_value": 1790.0,
                    "portefølje_råd": "HOLD",
                    "anbefaling": "HOLD / OBSERVER",
                    "trailing_stop_loss": 250.0,
                },
                {
                    "ticker": "NVDA",
                    "market_value": 2081.9,
                    "unrealized_gain_pct": 79.47,
                    "current_price": float("nan"),
                    "cost_value": 1160.0,
                    "portefølje_råd": "REDUSER / SELG",
                    "anbefaling": "UNNGÅ / SELG",
                    "trailing_stop_loss": 180.0,
                },
            ]
        )

        valid = valid_portfolio_rows(df)

        self.assertEqual(len(valid), 1)
        self.assertEqual(valid.iloc[0]["ticker"], "AAPL")
        self.assertEqual(valid.iloc[0]["current_price"], 290.55)


if __name__ == "__main__":
    unittest.main()
