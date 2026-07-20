import unittest
from unittest.mock import patch

import pandas as pd

from src.screener import (
    IN_WATCHLIST_NO,
    IN_WATCHLIST_YES,
    SCREEN_PRESETS,
    get_preset_filters,
    screen_explore_universe,
    screen_stocks,
    screening_universe_options,
    suggest_watchlist_additions,
)


def _analysis_result(
    ticker,
    score,
    recommendation="HOLD / OBSERVER",
    trend_regime="OPPTREND",
    relative_strength_20d=5.0,
    fundamental_score=60,
    fundamental_history_score=65,
):
    return {
        "ticker": ticker,
        "score": score,
        "anbefaling": recommendation,
        "trend_regime": trend_regime,
        "relative_strength_20d": relative_strength_20d,
        "fundamental_score": fundamental_score,
        "fundamental_history_score": fundamental_history_score,
    }


class ScreenStocksTests(unittest.TestCase):
    @patch("src.screener.analyze_stock")
    def test_filters_by_min_score(self, mock_analyze):
        mock_analyze.side_effect = [
            (_analysis_result("AAA", 80), None),
            (_analysis_result("BBB", 40), None),
        ]

        result = screen_stocks(
            ["AAA", "BBB"],
            min_score=55,
            limit=None,
            pause_seconds=0,
            watchlist_symbols=set(),
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["ticker"], "AAA")

    @patch("src.screener.analyze_stock")
    def test_filters_by_relative_strength(self, mock_analyze):
        mock_analyze.side_effect = [
            (_analysis_result("AAA", 70, relative_strength_20d=10.0), None),
            (_analysis_result("BBB", 70, relative_strength_20d=-2.0), None),
        ]

        result = screen_stocks(
            ["AAA", "BBB"],
            min_relative_strength=0,
            limit=None,
            pause_seconds=0,
            watchlist_symbols=set(),
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["ticker"], "AAA")

    @patch("src.screener.analyze_stock")
    def test_limit_works(self, mock_analyze):
        mock_analyze.side_effect = [
            (_analysis_result("AAA", 90), None),
            (_analysis_result("BBB", 80), None),
            (_analysis_result("CCC", 70), None),
        ]

        result = screen_stocks(
            ["AAA", "BBB", "CCC"],
            limit=2,
            pause_seconds=0,
            watchlist_symbols=set(),
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(list(result["ticker"]), ["AAA", "BBB"])

    @patch("src.screener.analyze_stock")
    def test_sorts_by_score_descending(self, mock_analyze):
        mock_analyze.side_effect = [
            (_analysis_result("LOW", 50), None),
            (_analysis_result("MID", 70), None),
            (_analysis_result("HIGH", 90), None),
        ]

        result = screen_stocks(
            ["LOW", "MID", "HIGH"],
            limit=None,
            pause_seconds=0,
            watchlist_symbols=set(),
        )

        self.assertEqual(list(result["ticker"]), ["HIGH", "MID", "LOW"])
        self.assertTrue(
            list(result["score"]) == sorted(result["score"], reverse=True)
        )

    @patch("src.screener.analyze_stock")
    def test_empty_result_handled(self, mock_analyze):
        mock_analyze.side_effect = Exception("no data")

        result = screen_stocks(
            ["AAA"],
            pause_seconds=0,
            watchlist_symbols=set(),
        )

        self.assertTrue(result.empty)
        self.assertEqual(
            list(result.columns),
            [
                "ticker",
                "in_watchlist",
                "score",
                "recommendation",
                "trend_regime",
                "relative_strength_20d",
                "fundamental_score",
                "fundamental_history_score",
                "primary_profile",
                "profile_score_momentum",
                "profile_score_quality",
                "profile_score_value",
                "profile_score_cyclical",
            ],
        )

    @patch("src.screener.analyze_stock")
    def test_filters_by_trend_regimes(self, mock_analyze):
        mock_analyze.side_effect = [
            (
                _analysis_result(
                    "AAA",
                    70,
                    trend_regime="STERK OPPTREND",
                ),
                None,
            ),
            (
                _analysis_result(
                    "BBB",
                    70,
                    trend_regime="SVAK / SIDEWAYS",
                ),
                None,
            ),
        ]

        result = screen_stocks(
            ["AAA", "BBB"],
            trend_regimes=["STERK OPPTREND"],
            limit=None,
            pause_seconds=0,
            watchlist_symbols=set(),
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["ticker"], "AAA")

    @patch("src.screener.analyze_stock")
    def test_in_watchlist_set_correctly(self, mock_analyze):
        mock_analyze.side_effect = [
            (_analysis_result("AAPL", 80), None),
            (_analysis_result("JPM", 75), None),
        ]

        result = screen_stocks(
            ["AAPL", "JPM"],
            limit=None,
            pause_seconds=0,
            watchlist_symbols={"AAPL"},
        )

        by_ticker = {
            row["ticker"]: row["in_watchlist"]
            for _, row in result.iterrows()
        }
        self.assertEqual(by_ticker["AAPL"], IN_WATCHLIST_YES)
        self.assertEqual(by_ticker["JPM"], IN_WATCHLIST_NO)


class ScreenExploreUniverseTests(unittest.TestCase):
    @patch("src.screener.screen_stocks")
    @patch("src.screener._universe_symbols")
    def test_uses_screening_universe_symbols(
        self,
        mock_universe_symbols,
        mock_screen_stocks,
    ):
        mock_universe_symbols.return_value = [
            "AAPL",
            "MSFT",
            "JPM",
        ]
        mock_screen_stocks.return_value = pd.DataFrame()

        watchlists = {
            "USA": ["AAPL"],
            "Norden": [],
            "OBX": [],
            "Alle": ["AAPL"],
        }

        screen_explore_universe(
            "US_LARGE_CAP",
            preset="Sterk trend",
            limit=10,
            pause_seconds=0,
            existing_watchlists=watchlists,
        )

        mock_universe_symbols.assert_called_once_with("US_LARGE_CAP")
        mock_screen_stocks.assert_called_once_with(
            ["AAPL", "MSFT", "JPM"],
            trend_regimes=["STERK OPPTREND"],
            limit=10,
            pause_seconds=0,
            watchlist_symbols={"AAPL"},
        )

    @patch("src.screener.load_json_config")
    def test_screening_universe_options_sorted(self, mock_load_json):
        mock_load_json.return_value = {
            "OBX": ["EQNR.OL"],
            "NORDICS": ["VOLV-B.ST"],
            "US_LARGE_CAP": ["AAPL"],
        }

        self.assertEqual(
            screening_universe_options(),
            ["NORDICS", "OBX", "US_LARGE_CAP"],
        )


class ScreenPresetTests(unittest.TestCase):
    def test_presets_defined(self):
        self.assertIn("Beste kandidater", SCREEN_PRESETS)
        self.assertIn("Sterk trend", SCREEN_PRESETS)
        self.assertIn("Positiv relativ styrke", SCREEN_PRESETS)
        self.assertIn("Høy kvalitet + trend", SCREEN_PRESETS)

    def test_get_preset_filters_beste_kandidater(self):
        filters = get_preset_filters("Beste kandidater")
        self.assertEqual(filters, {"min_score": 70})

    def test_get_preset_filters_sterk_trend(self):
        filters = get_preset_filters("Sterk trend")
        self.assertEqual(
            filters,
            {"trend_regimes": ["STERK OPPTREND"]},
        )

    def test_get_preset_filters_hoy_kvalitet(self):
        filters = get_preset_filters("Høy kvalitet + trend")
        self.assertEqual(
            filters,
            {"min_score": 75, "min_relative_strength": 0},
        )

    def test_get_preset_filters_unknown_raises(self):
        with self.assertRaises(ValueError):
            get_preset_filters("Ukjent preset")


class SuggestWatchlistAdditionsTests(unittest.TestCase):
    @patch("src.screener.analyze_watchlist")
    @patch("src.screener._universe_symbols")
    def test_excludes_watchlist_symbols(
        self,
        mock_universe_symbols,
        mock_analyze_watchlist,
    ):
        mock_universe_symbols.return_value = [
            "AAPL",
            "MSFT",
            "JPM",
        ]
        mock_analyze_watchlist.return_value = pd.DataFrame(
            [
                {
                    "ticker": "MSFT",
                    "score": 80,
                    "anbefaling": "KJØP / ØK",
                    "trend_regime": "STERK OPPTREND",
                    "relative_strength_20d": 5.0,
                    "fundamental_score": 70,
                    "fundamental_history_score": 70,
                },
                {
                    "ticker": "JPM",
                    "score": 78,
                    "anbefaling": "KJØP / ØK",
                    "trend_regime": "STERK OPPTREND",
                    "relative_strength_20d": 4.0,
                    "fundamental_score": 68,
                    "fundamental_history_score": 68,
                },
            ]
        )

        watchlists = {
            "USA": ["AAPL"],
            "Norden": [],
            "OBX": [],
            "Alle": ["AAPL"],
        }

        result = suggest_watchlist_additions(
            "US_LARGE_CAP",
            watchlists,
            pause_seconds=0,
        )

        analyzed_symbols = mock_analyze_watchlist.call_args[0][0]
        self.assertEqual(analyzed_symbols, ["MSFT", "JPM"])
        self.assertNotIn("AAPL", result["candidates"]["ticker"].tolist())
        self.assertEqual(result["diagnostics"]["already_in_watchlists"], 1)


if __name__ == "__main__":
    unittest.main()
