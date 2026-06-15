import unittest
from unittest.mock import patch

import pandas as pd

from src.analysis import analyze_stock, analyze_watchlist
from src.fundamentals import FUNDAMENTAL_VALUE_FIELDS, extract_value_fields
from src.strategy_profiles import build_strategy_profile, format_strategy_profile


def _price_df():
    index = pd.date_range("2026-01-01", periods=120, freq="D")
    return pd.DataFrame(
        {
            "close": [100.0] * 120,
            "high": [101.0] * 120,
            "low": [99.0] * 120,
            "volume": [1_000_000] * 120,
            "rsi": [55.0] * 120,
            "macd": [1.0] * 120,
            "macd_signal": [0.5] * 120,
            "sma20": [98.0] * 120,
            "sma50": [95.0] * 120,
            "sma100": [90.0] * 120,
            "volume_avg20": [900_000.0] * 120,
            "atr": [2.0] * 120,
        },
        index=index,
    )


def _fundamental_result(**overrides):
    base = {
        "symbol": "BRK-B",
        "market_cap": 900_000_000_000,
        "price_to_book": 1.45,
        "return_on_equity": 0.18,
        "debt_to_equity": 25.0,
        "profit_margin": 0.22,
        "operating_margin": 0.24,
        "trailing_pe": 12.5,
        "forward_pe": 11.8,
        "revenue_growth": 0.05,
        "earnings_growth": 0.08,
        "dividend_yield": None,
        "fundamental_score": 50,
        "fundamental_label": "AKSEPTABEL FUNDAMENTAL KVALITET",
        "fundamental_reasons": ["Moderat gjeldsgrad"],
    }
    base.update(overrides)
    return base


def _history_result(**overrides):
    base = {
        "fundamental_history_score": 60,
        "fundamental_history_label": "GOD HISTORISK FUNDAMENTAL UTVIKLING",
        "fundamental_history_reasons": ["Marginene har forbedret seg"],
    }
    base.update(overrides)
    return base


class ExtractValueFieldsTests(unittest.TestCase):
    def test_extract_value_fields_from_fundamentals(self):
        fields = extract_value_fields(_fundamental_result())

        self.assertEqual(set(fields.keys()), set(FUNDAMENTAL_VALUE_FIELDS))
        self.assertEqual(fields["price_to_book"], 1.45)
        self.assertEqual(fields["trailing_pe"], 12.5)
        self.assertNotIn("market_cap", fields)


class AnalyzeStockValueFieldsTests(unittest.TestCase):
    @patch("src.analysis.calculate_stop_levels")
    @patch("src.analysis.combine_scores")
    @patch("src.analysis.analyze_fundamental_history")
    @patch("src.analysis.analyze_fundamentals")
    @patch("src.analysis.analyze_technicals")
    @patch("src.analysis.add_indicators")
    @patch("src.analysis.get_daily_prices")
    def test_analyze_stock_includes_value_fields(
        self,
        mock_prices,
        mock_indicators,
        mock_technicals,
        mock_fundamentals,
        mock_history,
        mock_combine,
        mock_stop,
    ):
        price_df = _price_df()
        mock_prices.return_value = price_df
        mock_indicators.side_effect = lambda df: df
        mock_technicals.return_value = {
            "technical_score": 70,
            "trend_score": 3,
            "trend_regime": "STERK OPPTREND",
            "trend_points": 40,
            "momentum_points": 30,
            "volume_points": 0,
            "relative_strength_points": 10,
            "relative_strength_20d": 1.01,
            "technical_reasons": ["Kurs over SMA20"],
        }
        mock_fundamentals.return_value = _fundamental_result()
        mock_history.return_value = _history_result()
        mock_combine.return_value = {
            "score": 82,
            "anbefaling": "KJØP / ØK",
            "fundamental_points": 10,
            "fundamental_history_points": 12,
            "score_reasons": ["Akseptabel fundamental kvalitet"],
        }
        mock_stop.return_value = {
            "stop_loss": 90.0,
            "trailing_stop_loss": 95.0,
            "atr_stop_loss": 92.0,
        }

        result, _ = analyze_stock("BRK-B")

        for field in FUNDAMENTAL_VALUE_FIELDS:
            self.assertIn(field, result)
        self.assertEqual(result["price_to_book"], 1.45)
        self.assertEqual(result["score"], 82)
        self.assertEqual(result["anbefaling"], "KJØP / ØK")

    @patch("src.analysis.calculate_stop_levels")
    @patch("src.analysis.combine_scores")
    @patch("src.analysis.analyze_fundamental_history")
    @patch("src.analysis.analyze_fundamentals")
    @patch("src.analysis.analyze_technicals")
    @patch("src.analysis.add_indicators")
    @patch("src.analysis.get_daily_prices")
    def test_score_and_recommendation_unchanged_by_value_field_exposure(
        self,
        mock_prices,
        mock_indicators,
        mock_technicals,
        mock_fundamentals,
        mock_history,
        mock_combine,
        mock_stop,
    ):
        price_df = _price_df()
        mock_prices.return_value = price_df
        mock_indicators.side_effect = lambda df: df
        mock_technicals.return_value = {
            "technical_score": 55,
            "trend_score": 2,
            "trend_regime": "MODERAT OPPTREND",
            "trend_points": 25,
            "momentum_points": 15,
            "volume_points": 0,
            "relative_strength_points": 0,
            "relative_strength_20d": -2.0,
            "technical_reasons": [],
        }
        mock_fundamentals.return_value = _fundamental_result(symbol="JPM")
        mock_history.return_value = _history_result(fundamental_history_score=85)
        mock_combine.return_value = {
            "score": 64,
            "anbefaling": "HOLD / OBSERVER",
            "fundamental_points": 8,
            "fundamental_history_points": 17,
            "score_reasons": [],
        }
        mock_stop.return_value = {
            "stop_loss": 180.0,
            "trailing_stop_loss": 185.0,
            "atr_stop_loss": 182.0,
        }

        result, _ = analyze_stock("JPM")

        self.assertEqual(result["score"], 64)
        self.assertEqual(result["anbefaling"], "HOLD / OBSERVER")
        self.assertIsNotNone(result["trailing_pe"])


class WatchlistValueFieldsTests(unittest.TestCase):
    @patch("src.analysis.analyze_stock")
    @patch("src.analysis.time.sleep")
    def test_watchlist_report_preserves_value_fields(
        self,
        mock_sleep,
        mock_analyze_stock,
    ):
        mock_analyze_stock.return_value = (
            {
                "ticker": "DNB.OL",
                "score": 70,
                "anbefaling": "HOLD / OBSERVER",
                "price_to_book": 1.2,
                "return_on_equity": 0.14,
                "debt_to_equity": 120.0,
                "profit_margin": 0.31,
                "operating_margin": 0.33,
                "trailing_pe": 9.5,
                "forward_pe": 9.0,
            },
            pd.DataFrame(),
        )

        report = analyze_watchlist(["DNB.OL"], pause_seconds=0)
        row = report.iloc[0]

        self.assertEqual(row["ticker"], "DNB.OL")
        self.assertEqual(row["price_to_book"], 1.2)
        self.assertEqual(row["trailing_pe"], 9.5)


class StrategyProfileValueFieldsTests(unittest.TestCase):
    def test_value_profile_computed_when_enough_fields_exist(self):
        profile = build_strategy_profile(
            {
                "ticker": "BRK-B",
                "trend_regime": "STERK OPPTREND",
                "trend_points": 40,
                "momentum_points": 30,
                "relative_strength_points": 10,
                "relative_strength_20d": 1.01,
                "fundamental_score": 50,
                "fundamental_history_score": 60,
                "price_to_book": 1.45,
                "return_on_equity": 0.18,
                "debt_to_equity": 25.0,
                "profit_margin": 0.22,
                "trailing_pe": 12.5,
            }
        )

        self.assertIsNotNone(profile["profiles"]["value"])
        self.assertIn(
            f"Value: {profile['profiles']['value']}",
            format_strategy_profile(profile),
        )

    def test_value_unknown_with_insufficient_fields(self):
        profile = build_strategy_profile(
            {
                "ticker": "UNKNOWN",
                "fundamental_score": 50,
                "fundamental_history_score": 60,
                "price_to_book": 1.45,
            }
        )

        self.assertIsNone(profile["profiles"]["value"])
        self.assertIn("Value: ukjent", format_strategy_profile(profile))

    def test_value_unknown_without_any_fields(self):
        profile = build_strategy_profile(
            {
                "ticker": "BRK-B",
                "trend_regime": "STERK OPPTREND",
                "trend_points": 40,
                "momentum_points": 30,
                "relative_strength_points": 10,
                "relative_strength_20d": 1.01,
                "fundamental_score": 50,
                "fundamental_history_score": 60,
            }
        )

        self.assertIsNone(profile["profiles"]["value"])
        self.assertIn("Value: ukjent", format_strategy_profile(profile))


if __name__ == "__main__":
    unittest.main()
