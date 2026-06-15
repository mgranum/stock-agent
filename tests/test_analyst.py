import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.analyst import (
    SOURCE_YFINANCE,
    _apply_change_detection,
    _collect_item_material_changes,
    _write_analyst_cache,
    build_analyst_changes_table,
    build_analyst_summary,
    build_analyst_table,
    build_material_changes,
    compute_upside_pct,
    format_recommendation_label,
    get_analyst,
    sort_analyst_items,
)


class ComputeUpsidePctTests(unittest.TestCase):
    def test_computes_positive_upside(self):
        self.assertEqual(compute_upside_pct(200.0, 250.0), 25.0)

    def test_returns_none_when_price_missing(self):
        self.assertIsNone(compute_upside_pct(None, 250.0))
        self.assertIsNone(compute_upside_pct(0, 250.0))


class FormatRecommendationLabelTests(unittest.TestCase):
    def test_formats_known_key(self):
        self.assertEqual(format_recommendation_label("strong_buy"), "Sterk kjøp")

    def test_returns_dash_for_missing_key(self):
        self.assertEqual(format_recommendation_label(None), "—")


class AnalystCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cache_root = Path(self.temp_dir.name)

        self.temp_dir_patcher = patch(
            "src.analyst._cache_dir",
            return_value=self.cache_root,
        )
        self.temp_dir_patcher.start()
        self.addCleanup(self.temp_dir_patcher.stop)

    @patch("src.analyst._fetch_yfinance_analyst")
    def test_get_analyst_writes_and_reads_cache(self, mock_fetch):
        mock_fetch.return_value = {
            "ticker": "AAPL",
            "recommendation_key": "buy",
            "recommendation_mean": 2.0,
            "analyst_count": 42,
            "target_mean": 250.0,
            "target_median": 245.0,
            "target_high": 300.0,
            "target_low": 200.0,
            "current_price": 200.0,
            "upside_pct": 25.0,
            "currency": "USD",
            "distribution": {
                "strong_buy": 7,
                "buy": 23,
                "hold": 10,
                "sell": 1,
                "strong_sell": 1,
            },
            "source": SOURCE_YFINANCE,
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        first = get_analyst("AAPL", use_cache=True, today=date(2026, 6, 12))
        second = get_analyst("AAPL", use_cache=True, today=date(2026, 6, 12))

        mock_fetch.assert_called_once()
        self.assertEqual(first["target_mean"], 250.0)
        self.assertEqual(second["analyst_count"], 42)

        cache_file = self.cache_root / "AAPL_analyst.json"
        self.assertTrue(cache_file.exists())
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(cached["date"], "2026-06-12")
        self.assertEqual(cached["data"]["recommendation_key"], "buy")

    @patch("src.analyst._fetch_yfinance_analyst")
    def test_cache_refresh_on_new_day(self, mock_fetch):
        cache_file = self.cache_root / "MSFT_analyst.json"
        _write_analyst_cache(
            cache_file,
            "MSFT",
            {
                "ticker": "MSFT",
                "recommendation_key": "hold",
                "recommendation_mean": 3.0,
                "analyst_count": 30,
                "target_mean": 500.0,
                "target_median": 495.0,
                "target_high": 550.0,
                "target_low": 450.0,
                "current_price": 480.0,
                "upside_pct": 4.2,
                "currency": "USD",
                "distribution": None,
                "source": SOURCE_YFINANCE,
                "last_updated": "2026-06-11T08:00:00+00:00",
            },
            today=date(2026, 6, 11),
        )

        mock_fetch.return_value = {
            "ticker": "MSFT",
            "recommendation_key": "buy",
            "recommendation_mean": 2.5,
            "analyst_count": 31,
            "target_mean": 510.0,
            "target_median": 505.0,
            "target_high": 560.0,
            "target_low": 460.0,
            "current_price": 485.0,
            "upside_pct": 5.2,
            "currency": "USD",
            "distribution": None,
            "source": SOURCE_YFINANCE,
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        result = get_analyst("MSFT", use_cache=True, today=date(2026, 6, 12))

        mock_fetch.assert_called_once()
        self.assertEqual(result["recommendation_key"], "buy")
        self.assertEqual(result["analyst_count"], 31)

    @patch("src.analyst._fetch_yfinance_analyst")
    def test_empty_fetch_does_not_overwrite_useful_cache(self, mock_fetch):
        cache_file = self.cache_root / "NVDA_analyst.json"
        _write_analyst_cache(
            cache_file,
            "NVDA",
            {
                "ticker": "NVDA",
                "recommendation_key": "strong_buy",
                "recommendation_mean": 1.3,
                "analyst_count": 59,
                "target_mean": 298.93,
                "source": SOURCE_YFINANCE,
                "last_updated": "2026-06-11T08:00:00+00:00",
            },
            today=date(2026, 6, 11),
        )
        mock_fetch.return_value = {
            "ticker": "NVDA",
            "recommendation_key": None,
            "recommendation_mean": None,
            "analyst_count": None,
            "target_mean": None,
            "target_median": None,
            "target_high": None,
            "target_low": None,
            "current_price": None,
            "upside_pct": None,
            "currency": None,
            "distribution": None,
            "source": SOURCE_YFINANCE,
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        result = get_analyst("NVDA", use_cache=True, today=date(2026, 6, 12))

        self.assertEqual(result["recommendation_key"], "strong_buy")
        self.assertEqual(result["analyst_count"], 59)
        self.assertEqual(result["fetch_error"], "missing analyst data")
        self.assertIn("last_attempted_at", result)

        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(cached["date"], "2026-06-12")
        self.assertEqual(cached["data"]["analyst_count"], 59)

    @patch("src.analyst._fetch_yfinance_analyst")
    def test_empty_fetch_can_be_saved_without_existing_cache(self, mock_fetch):
        mock_fetch.return_value = {
            "ticker": "UNKNOWN",
            "recommendation_key": None,
            "recommendation_mean": None,
            "analyst_count": None,
            "target_mean": None,
            "target_median": None,
            "target_high": None,
            "target_low": None,
            "current_price": None,
            "upside_pct": None,
            "currency": None,
            "distribution": None,
            "source": SOURCE_YFINANCE,
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        result = get_analyst("UNKNOWN", use_cache=True, today=date(2026, 6, 12))

        self.assertIsNone(result["recommendation_key"])
        self.assertNotIn("fetch_error", result)

        cache_file = self.cache_root / "UNKNOWN_analyst.json"
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertIsNone(cached["data"]["analyst_count"])

    @patch("src.analyst._fetch_yfinance_analyst")
    def test_network_exception_preserves_existing_cache(self, mock_fetch):
        cache_file = self.cache_root / "MSFT_analyst.json"
        _write_analyst_cache(
            cache_file,
            "MSFT",
            {
                "ticker": "MSFT",
                "recommendation_key": "buy",
                "recommendation_mean": 2.5,
                "analyst_count": 31,
                "target_mean": 510.0,
                "source": SOURCE_YFINANCE,
                "last_updated": "2026-06-11T08:00:00+00:00",
            },
            today=date(2026, 6, 11),
        )
        mock_fetch.side_effect = ConnectionError("network down")

        result = get_analyst("MSFT", use_cache=True, today=date(2026, 6, 12))

        self.assertEqual(result["analyst_count"], 31)
        self.assertIn("network down", result["fetch_error"])

        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(cached["data"]["analyst_count"], 31)


class FetchAnalystDataTests(unittest.TestCase):
    @patch("src.analyst.yf.Ticker")
    def test_valid_ticker_maps_yfinance_fields(self, mock_ticker_cls):
        mock_stock = mock_ticker_cls.return_value
        mock_stock.info = {
            "recommendationKey": "strong_buy",
            "recommendationMean": 1.3,
            "numberOfAnalystOpinions": 59,
            "targetMeanPrice": 298.93,
            "targetMedianPrice": 288.0,
            "targetHighPrice": 500.0,
            "targetLowPrice": 180.0,
            "currentPrice": 204.87,
            "currency": "USD",
        }
        mock_stock.recommendations_summary = pd.DataFrame(
            [
                {
                    "period": "0m",
                    "strongBuy": 10,
                    "buy": 49,
                    "hold": 2,
                    "sell": 1,
                    "strongSell": 0,
                }
            ]
        )

        from src.analyst import _fetch_yfinance_analyst

        data = _fetch_yfinance_analyst("NVDA")

        self.assertEqual(data["ticker"], "NVDA")
        self.assertEqual(data["recommendation_key"], "strong_buy")
        self.assertEqual(data["analyst_count"], 59)
        self.assertEqual(data["target_mean"], 298.93)
        self.assertEqual(data["upside_pct"], 45.9)
        self.assertEqual(
            data["distribution"],
            {
                "strong_buy": 10,
                "buy": 49,
                "hold": 2,
                "sell": 1,
                "strong_sell": 0,
            },
        )

    @patch("src.analyst.yf.Ticker")
    def test_nordic_ticker(self, mock_ticker_cls):
        mock_stock = mock_ticker_cls.return_value
        mock_stock.info = {
            "recommendationKey": "hold",
            "recommendationMean": 3.28,
            "numberOfAnalystOpinions": 24,
            "targetMeanPrice": 364.46,
            "targetMedianPrice": 370.34,
            "targetHighPrice": 427.18,
            "targetLowPrice": 267.48,
            "currentPrice": 334.6,
            "currency": "NOK",
        }
        mock_stock.recommendations_summary = pd.DataFrame(
            [
                {
                    "period": "0m",
                    "strongBuy": 0,
                    "buy": 2,
                    "hold": 15,
                    "sell": 3,
                    "strongSell": 5,
                }
            ]
        )

        from src.analyst import _fetch_yfinance_analyst

        data = _fetch_yfinance_analyst("EQNR.OL")

        self.assertEqual(data["currency"], "NOK")
        self.assertEqual(data["analyst_count"], 24)
        self.assertAlmostEqual(data["upside_pct"], 8.9, places=1)

    @patch("src.analyst.yf.Ticker")
    def test_invalid_ticker_returns_missing_fields(self, mock_ticker_cls):
        mock_stock = mock_ticker_cls.return_value
        mock_stock.info = {}
        mock_stock.recommendations_summary = pd.DataFrame()

        from src.analyst import _fetch_yfinance_analyst

        data = _fetch_yfinance_analyst("NOTAREALTICKER")

        self.assertEqual(data["ticker"], "NOTAREALTICKER")
        self.assertIsNone(data["recommendation_key"])
        self.assertIsNone(data["analyst_count"])
        self.assertIsNone(data["target_mean"])
        self.assertIsNone(data["upside_pct"])

    @patch("src.analyst.yf.Ticker")
    def test_missing_analyst_data_when_info_unavailable(self, mock_ticker_cls):
        mock_stock = mock_ticker_cls.return_value
        mock_stock.info = None
        mock_stock.recommendations_summary = None

        from src.analyst import _fetch_yfinance_analyst

        data = _fetch_yfinance_analyst("UNKNOWN")

        self.assertIsNone(data["recommendation_key"])
        self.assertIsNone(data["distribution"])


class BuildAnalystSummaryTests(unittest.TestCase):
    @patch("src.analyst.get_analyst")
    def test_build_analyst_summary_groups_and_sorts(self, mock_get_analyst):
        def side_effect(ticker, use_cache=True, today=None):
            data = {
                "NVDA": {
                    "recommendation_key": "strong_buy",
                    "recommendation_mean": 1.3,
                    "analyst_count": 59,
                    "target_mean": 298.93,
                    "target_median": 288.0,
                    "target_high": 500.0,
                    "target_low": 180.0,
                    "current_price": 204.87,
                    "upside_pct": 45.9,
                    "currency": "USD",
                    "distribution": None,
                },
                "EQNR.OL": {
                    "recommendation_key": "hold",
                    "recommendation_mean": 3.28,
                    "analyst_count": 24,
                    "target_mean": 364.46,
                    "target_median": 370.34,
                    "target_high": 427.18,
                    "target_low": 267.48,
                    "current_price": 334.6,
                    "upside_pct": 8.9,
                    "currency": "NOK",
                    "distribution": None,
                },
                "MSFT": {
                    "recommendation_key": "buy",
                    "recommendation_mean": 2.0,
                    "analyst_count": 40,
                    "target_mean": 500.0,
                    "target_median": 495.0,
                    "target_high": 550.0,
                    "target_low": 450.0,
                    "current_price": 480.0,
                    "upside_pct": 4.2,
                    "currency": "USD",
                    "distribution": None,
                },
                "EMPTY": {
                    "recommendation_key": None,
                    "recommendation_mean": None,
                    "analyst_count": None,
                    "target_mean": None,
                    "target_median": None,
                    "target_high": None,
                    "target_low": None,
                    "current_price": None,
                    "upside_pct": None,
                    "currency": None,
                    "distribution": None,
                },
            }[ticker]

            return {
                "ticker": ticker,
                "source": SOURCE_YFINANCE,
                "last_updated": "2026-06-12T08:00:00+00:00",
                **data,
            }

        mock_get_analyst.side_effect = side_effect

        summary = build_analyst_summary(
            portfolio=[{"ticker": "NVDA"}],
            watchlist=["EQNR.OL", "MSFT", "EMPTY"],
            use_cache=False,
            today=date(2026, 6, 12),
        )

        self.assertEqual(
            [item["ticker"] for item in summary["items"]],
            ["NVDA", "MSFT", "EQNR.OL", "EMPTY"],
        )
        self.assertEqual(len(summary["portfolio_items"]), 1)
        self.assertEqual(len(summary["watchlist_items"]), 3)
        self.assertEqual(summary["missing_data"], ["EMPTY"])
        self.assertEqual(summary["last_updated"], "2026-06-12T08:00:00+00:00")

    def test_build_analyst_table_columns(self):
        summary = {
            "items": [
                {
                    "ticker": "NVDA",
                    "recommendation_key": "strong_buy",
                    "analyst_count": 59,
                    "target_mean": 298.93,
                    "upside_pct": 45.9,
                }
            ]
        }

        table = build_analyst_table(summary)

        self.assertEqual(
            list(table.columns),
            ["Ticker", "Konsensus", "Analytikere", "Kursmål", "Oppside %"],
        )
        self.assertEqual(table.iloc[0]["Ticker"], "NVDA")
        self.assertEqual(table.iloc[0]["Konsensus"], "Sterk kjøp")
        self.assertEqual(table.iloc[0]["Analytikere"], "59")
        self.assertEqual(table.iloc[0]["Kursmål"], "298.93")
        self.assertEqual(table.iloc[0]["Oppside %"], "45.9")

    def test_build_analyst_table_arrow_compatible_with_missing_values(self):
        import pyarrow as pa

        summary = {
            "items": [
                {
                    "ticker": "NVDA",
                    "recommendation_key": "strong_buy",
                    "analyst_count": 42,
                    "target_mean": 298.93,
                    "upside_pct": 45.9,
                },
                {
                    "ticker": "EMPTY",
                    "recommendation_key": None,
                    "analyst_count": None,
                    "target_mean": None,
                    "upside_pct": None,
                },
            ]
        }

        table = build_analyst_table(summary)

        for column in ("Analytikere", "Kursmål", "Oppside %"):
            self.assertTrue(
                all(isinstance(value, str) for value in table[column]),
                msg=f"{column} should contain only strings",
            )

        self.assertEqual(table.iloc[0]["Analytikere"], "42")
        self.assertEqual(table.iloc[1]["Analytikere"], "—")
        self.assertEqual(table.iloc[1]["Kursmål"], "—")
        self.assertEqual(table.iloc[1]["Oppside %"], "—")

        pa.Table.from_pandas(table)


class SortAnalystItemsTests(unittest.TestCase):
    def test_sorts_portfolio_first_then_highest_analyst_count(self):
        items = [
            {"ticker": "EQNR.OL", "analyst_count": 24},
            {"ticker": "NVDA", "analyst_count": 59},
            {"ticker": "MSFT", "analyst_count": 40},
        ]

        sorted_items = sort_analyst_items(items, {"NVDA"})

        self.assertEqual(
            [item["ticker"] for item in sorted_items],
            ["NVDA", "MSFT", "EQNR.OL"],
        )


class AnalystChangeDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cache_root = Path(self.temp_dir.name)

        self.temp_dir_patcher = patch(
            "src.analyst._cache_dir",
            return_value=self.cache_root,
        )
        self.temp_dir_patcher.start()
        self.addCleanup(self.temp_dir_patcher.stop)

    def _base_item(self, **overrides):
        item = {
            "ticker": "AAPL",
            "recommendation_key": "buy",
            "recommendation_mean": 2.0,
            "target_mean": 100.0,
            "previous_target_mean": 100.0,
            "previous_recommendation_mean": 2.0,
            "previous_recommendation_key": "buy",
            "target_mean_delta": 0.0,
            "target_mean_delta_pct": 0.0,
            "recommendation_mean_delta": 0.0,
            "recommendation_changed": False,
        }
        item.update(overrides)
        return item

    def test_target_mean_up_more_than_five_percent(self):
        item = self._base_item(
            target_mean=106.0,
            target_mean_delta=6.0,
            target_mean_delta_pct=6.0,
        )

        changes = _collect_item_material_changes(item)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["change_type"], "target_mean")
        self.assertIn("opp", changes[0]["Endring"])
        self.assertEqual(changes[0]["Fra"], 100.0)
        self.assertEqual(changes[0]["Til"], 106.0)

    def test_target_mean_down_more_than_five_percent(self):
        item = self._base_item(
            target_mean=94.0,
            target_mean_delta=-6.0,
            target_mean_delta_pct=-6.0,
        )

        changes = _collect_item_material_changes(item)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["change_type"], "target_mean")
        self.assertIn("ned", changes[0]["Endring"])
        self.assertEqual(changes[0]["Fra"], 100.0)
        self.assertEqual(changes[0]["Til"], 94.0)

    def test_recommendation_mean_changed(self):
        item = self._base_item(
            recommendation_mean=2.3,
            recommendation_mean_delta=0.3,
        )

        changes = _collect_item_material_changes(item)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["change_type"], "recommendation_mean")
        self.assertEqual(changes[0]["Fra"], 2.0)
        self.assertEqual(changes[0]["Til"], 2.3)

    def test_recommendation_key_changed(self):
        item = self._base_item(
            recommendation_key="hold",
            previous_recommendation_key="buy",
            recommendation_changed=True,
        )

        changes = _collect_item_material_changes(item)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["change_type"], "recommendation_key")
        self.assertEqual(changes[0]["Fra"], "Kjøp")
        self.assertEqual(changes[0]["Til"], "Hold")

    def test_no_material_change_below_threshold(self):
        item = self._base_item(
            target_mean=103.0,
            target_mean_delta=3.0,
            target_mean_delta_pct=3.0,
            recommendation_mean=2.1,
            recommendation_mean_delta=0.1,
        )

        changes = _collect_item_material_changes(item)

        self.assertEqual(changes, [])

    def test_first_cache_without_previous_has_no_change(self):
        data = {
            "ticker": "AAPL",
            "recommendation_key": "buy",
            "recommendation_mean": 2.0,
            "target_mean": 100.0,
        }

        result = _apply_change_detection(data, None)

        self.assertIsNone(result.get("previous_target_mean"))
        self.assertIsNone(result.get("target_mean_delta_pct"))
        self.assertFalse(result.get("recommendation_changed"))
        self.assertEqual(_collect_item_material_changes(result), [])

    @patch("src.analyst._fetch_yfinance_analyst")
    def test_get_analyst_detects_changes_on_cache_refresh(self, mock_fetch):
        cache_file = self.cache_root / "AAPL_analyst.json"
        _write_analyst_cache(
            cache_file,
            "AAPL",
            {
                "ticker": "AAPL",
                "recommendation_key": "hold",
                "recommendation_mean": 3.0,
                "analyst_count": 30,
                "target_mean": 100.0,
                "current_price": 95.0,
                "upside_pct": 5.3,
                "source": SOURCE_YFINANCE,
                "last_updated": "2026-06-11T08:00:00+00:00",
            },
            today=date(2026, 6, 11),
        )

        mock_fetch.return_value = {
            "ticker": "AAPL",
            "recommendation_key": "buy",
            "recommendation_mean": 2.0,
            "analyst_count": 31,
            "target_mean": 110.0,
            "current_price": 95.0,
            "upside_pct": 15.8,
            "source": SOURCE_YFINANCE,
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        result = get_analyst("AAPL", use_cache=True, today=date(2026, 6, 12))

        self.assertEqual(result["previous_target_mean"], 100.0)
        self.assertEqual(result["target_mean_delta_pct"], 10.0)
        self.assertEqual(result["recommendation_mean_delta"], -1.0)
        self.assertTrue(result["recommendation_changed"])

        changes = build_material_changes([result])
        change_types = {change["change_type"] for change in changes}
        self.assertEqual(
            change_types,
            {"target_mean", "recommendation_mean", "recommendation_key"},
        )

    def test_build_analyst_changes_table_columns(self):
        summary = {
            "material_changes": [
                {
                    "ticker": "AAPL",
                    "Endring": "Kursmål opp (+10.0%)",
                    "Fra": 100.0,
                    "Til": 110.0,
                }
            ]
        }

        table = build_analyst_changes_table(summary)

        self.assertEqual(
            list(table.columns),
            ["Ticker", "Endring", "Fra", "Til"],
        )
        self.assertEqual(table.iloc[0]["Ticker"], "AAPL")
        self.assertEqual(table.iloc[0]["Fra"], "100")
        self.assertEqual(table.iloc[0]["Til"], "110")

    @patch("src.analyst.get_analyst")
    def test_build_analyst_summary_includes_material_changes(self, mock_get_analyst):
        mock_get_analyst.return_value = {
            "ticker": "NVDA",
            "recommendation_key": "buy",
            "recommendation_mean": 2.0,
            "target_mean": 110.0,
            "previous_target_mean": 100.0,
            "previous_recommendation_mean": 3.0,
            "previous_recommendation_key": "hold",
            "target_mean_delta_pct": 10.0,
            "recommendation_mean_delta": -1.0,
            "recommendation_changed": True,
            "analyst_count": 59,
            "upside_pct": 45.9,
            "source": SOURCE_YFINANCE,
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        summary = build_analyst_summary(
            portfolio=[{"ticker": "NVDA"}],
            watchlist=[],
            use_cache=False,
            today=date(2026, 6, 12),
        )

        self.assertEqual(len(summary["material_changes"]), 3)


if __name__ == "__main__":
    unittest.main()
