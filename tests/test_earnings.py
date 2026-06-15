import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from src.earnings import (
    STATUS_CONFIRMED,
    STATUS_ESTIMATED,
    STATUS_UNKNOWN,
    _write_earnings_cache,
    build_earnings_summary,
    build_earnings_table,
    compute_days_until,
    determine_status,
    get_earnings,
    normalize_earnings_date,
    sort_earnings_items,
)


class NormalizeEarningsDateTests(unittest.TestCase):
    def test_normalizes_date_object(self):
        self.assertEqual(
            normalize_earnings_date(date(2026, 7, 22)),
            "2026-07-22",
        )

    def test_normalizes_datetime_object(self):
        self.assertEqual(
            normalize_earnings_date(datetime(2026, 7, 22, 15, 30)),
            "2026-07-22",
        )

    def test_normalizes_iso_string(self):
        self.assertEqual(
            normalize_earnings_date("2026-07-22T08:00:00Z"),
            "2026-07-22",
        )

    def test_prefers_earliest_future_date_from_list(self):
        today = date(2026, 6, 12)
        result = normalize_earnings_date(
            [date(2026, 8, 1), date(2026, 7, 1), date(2026, 5, 1)],
            today=today,
        )

        self.assertEqual(result, "2026-07-01")

    def test_returns_none_for_empty_value(self):
        self.assertIsNone(normalize_earnings_date(None))
        self.assertIsNone(normalize_earnings_date([]))


class ComputeDaysUntilTests(unittest.TestCase):
    def test_computes_days_until_earnings(self):
        self.assertEqual(
            compute_days_until("2026-06-20", today=date(2026, 6, 12)),
            8,
        )

    def test_returns_none_when_date_missing(self):
        self.assertIsNone(compute_days_until(None, today=date(2026, 6, 12)))


class DetermineStatusTests(unittest.TestCase):
    def test_unknown_when_date_missing(self):
        self.assertEqual(determine_status(None), STATUS_UNKNOWN)

    def test_confirmed_when_flag_is_false(self):
        self.assertEqual(
            determine_status("2026-07-22", is_estimate=False),
            STATUS_CONFIRMED,
        )

    def test_estimated_when_flag_is_true(self):
        self.assertEqual(
            determine_status("2026-07-22", is_estimate=True),
            STATUS_ESTIMATED,
        )


class EarningsCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cache_root = Path(self.temp_dir.name)

        self.temp_dir_patcher = patch(
            "src.earnings._cache_dir",
            return_value=self.cache_root,
        )
        self.temp_dir_patcher.start()
        self.addCleanup(self.temp_dir_patcher.stop)

    @patch("src.earnings._fetch_yfinance_earnings")
    def test_get_earnings_writes_and_reads_cache(self, mock_fetch):
        mock_fetch.return_value = {
            "ticker": "AAPL",
            "earnings_date": "2026-07-30",
            "days_until": 48,
            "status": STATUS_ESTIMATED,
            "source": "yfinance",
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        first = get_earnings("AAPL", use_cache=True, today=date(2026, 6, 12))
        second = get_earnings("AAPL", use_cache=True, today=date(2026, 6, 12))

        mock_fetch.assert_called_once()
        self.assertEqual(first["earnings_date"], "2026-07-30")
        self.assertEqual(second["earnings_date"], "2026-07-30")
        self.assertEqual(second["days_until"], 48)

        cache_file = self.cache_root / "AAPL_earnings.json"
        self.assertTrue(cache_file.exists())
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(cached["date"], "2026-06-12")
        self.assertEqual(cached["data"]["status"], STATUS_ESTIMATED)

    def test_cache_refresh_recomputes_days_until(self):
        cache_file = self.cache_root / "MSFT_earnings.json"
        _write_earnings_cache(
            cache_file,
            "MSFT",
            {
                "ticker": "MSFT",
                "earnings_date": "2026-06-20",
                "days_until": 999,
                "status": STATUS_CONFIRMED,
                "source": "yfinance",
                "last_updated": "2026-06-15T08:00:00+00:00",
            },
            today=date(2026, 6, 15),
        )

        with patch("src.earnings._fetch_yfinance_earnings") as mock_fetch:
            result = get_earnings("MSFT", use_cache=True, today=date(2026, 6, 15))

        mock_fetch.assert_not_called()
        self.assertEqual(result["days_until"], 5)

    @patch("src.earnings._fetch_yfinance_earnings")
    def test_unknown_fetch_does_not_overwrite_useful_cache(self, mock_fetch):
        cache_file = self.cache_root / "AAPL_earnings.json"
        _write_earnings_cache(
            cache_file,
            "AAPL",
            {
                "ticker": "AAPL",
                "earnings_date": "2026-07-30",
                "days_until": 48,
                "status": STATUS_ESTIMATED,
                "source": "yfinance",
                "last_updated": "2026-06-11T08:00:00+00:00",
            },
            today=date(2026, 6, 11),
        )
        mock_fetch.return_value = {
            "ticker": "AAPL",
            "earnings_date": None,
            "days_until": None,
            "status": STATUS_UNKNOWN,
            "source": "yfinance",
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        result = get_earnings("AAPL", use_cache=True, today=date(2026, 6, 12))

        self.assertEqual(result["earnings_date"], "2026-07-30")
        self.assertEqual(result["status"], STATUS_ESTIMATED)
        self.assertEqual(result["fetch_error"], "unknown earnings data")
        self.assertIn("last_attempted_at", result)

        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(cached["date"], "2026-06-12")
        self.assertEqual(cached["data"]["earnings_date"], "2026-07-30")

    @patch("src.earnings._fetch_yfinance_earnings")
    def test_unknown_fetch_can_be_saved_without_existing_cache(self, mock_fetch):
        mock_fetch.return_value = {
            "ticker": "UNKNOWN",
            "earnings_date": None,
            "days_until": None,
            "status": STATUS_UNKNOWN,
            "source": "yfinance",
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        result = get_earnings("UNKNOWN", use_cache=True, today=date(2026, 6, 12))

        self.assertEqual(result["status"], STATUS_UNKNOWN)
        self.assertNotIn("fetch_error", result)

        cache_file = self.cache_root / "UNKNOWN_earnings.json"
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(cached["data"]["status"], STATUS_UNKNOWN)

    @patch("src.earnings._fetch_yfinance_earnings")
    def test_network_exception_preserves_existing_cache(self, mock_fetch):
        cache_file = self.cache_root / "MSFT_earnings.json"
        _write_earnings_cache(
            cache_file,
            "MSFT",
            {
                "ticker": "MSFT",
                "earnings_date": "2026-06-20",
                "days_until": 8,
                "status": STATUS_CONFIRMED,
                "source": "yfinance",
                "last_updated": "2026-06-11T08:00:00+00:00",
            },
            today=date(2026, 6, 11),
        )
        mock_fetch.side_effect = ConnectionError("network down")

        result = get_earnings("MSFT", use_cache=True, today=date(2026, 6, 12))

        self.assertEqual(result["earnings_date"], "2026-06-20")
        self.assertIn("network down", result["fetch_error"])

        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(cached["data"]["earnings_date"], "2026-06-20")


class BuildEarningsSummaryTests(unittest.TestCase):
    @patch("src.earnings.get_earnings")
    def test_unknown_when_date_missing(self, mock_get_earnings):
        mock_get_earnings.return_value = {
            "ticker": "UNKNOWN",
            "earnings_date": None,
            "days_until": None,
            "status": STATUS_UNKNOWN,
            "source": "yfinance",
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        summary = build_earnings_summary(
            portfolio=[{"ticker": "UNKNOWN"}],
            watchlist=[],
            use_cache=False,
            today=date(2026, 6, 12),
        )

        self.assertEqual(len(summary["unknown"]), 1)
        self.assertEqual(summary["unknown"][0]["ticker"], "UNKNOWN")
        self.assertEqual(summary["upcoming_14_days"], [])

    @patch("src.earnings.get_earnings")
    def test_upcoming_14_days_filter(self, mock_get_earnings):
        def side_effect(ticker, use_cache=True, today=None):
            data = {
                "AAPL": ("2026-06-12", 0, STATUS_CONFIRMED),
                "MSFT": ("2026-06-20", 8, STATUS_CONFIRMED),
                "NVDA": ("2026-07-10", 28, STATUS_ESTIMATED),
            }
            earnings_date, days_until, status = data[ticker]
            return {
                "ticker": ticker,
                "earnings_date": earnings_date,
                "days_until": days_until,
                "status": status,
                "source": "yfinance",
                "last_updated": "2026-06-12T08:00:00+00:00",
            }

        mock_get_earnings.side_effect = side_effect

        summary = build_earnings_summary(
            portfolio=[{"ticker": "AAPL"}],
            watchlist=["MSFT", "NVDA"],
            use_cache=False,
            today=date(2026, 6, 12),
        )

        upcoming = [item["ticker"] for item in summary["upcoming_14_days"]]
        self.assertEqual(upcoming, ["AAPL", "MSFT"])
        self.assertEqual(len(summary["items"]), 3)

    @patch("src.earnings.get_earnings")
    def test_sorts_portfolio_first_then_nearest_date(self, mock_get_earnings):
        def side_effect(ticker, use_cache=True, today=None):
            data = {
                "AAPL": ("2026-06-20", 8, STATUS_CONFIRMED),
                "MSFT": ("2026-06-15", 3, STATUS_CONFIRMED),
                "NVDA": ("2026-06-18", 6, STATUS_ESTIMATED),
            }
            earnings_date, days_until, status = data[ticker]
            return {
                "ticker": ticker,
                "earnings_date": earnings_date,
                "days_until": days_until,
                "status": status,
                "source": "yfinance",
                "last_updated": "2026-06-12T08:00:00+00:00",
            }

        mock_get_earnings.side_effect = side_effect

        summary = build_earnings_summary(
            portfolio=[{"ticker": "NVDA"}],
            watchlist=["AAPL", "MSFT"],
            use_cache=False,
            today=date(2026, 6, 12),
        )

        tickers = [item["ticker"] for item in summary["items"]]
        self.assertEqual(tickers, ["NVDA", "MSFT", "AAPL"])


class SortEarningsItemsTests(unittest.TestCase):
    def test_unknown_sorted_last(self):
        items = [
            {"ticker": "ZZZ", "days_until": None, "status": STATUS_UNKNOWN},
            {"ticker": "AAA", "days_until": 5, "status": STATUS_CONFIRMED},
        ]

        sorted_items = sort_earnings_items(items, portfolio_tickers={"AAA"})

        self.assertEqual([item["ticker"] for item in sorted_items], ["AAA", "ZZZ"])


class BuildEarningsTableTests(unittest.TestCase):
    def test_build_earnings_table_arrow_compatible_with_missing_days(self):
        import pyarrow as pa

        summary = {
            "items": [
                {
                    "ticker": "AAPL",
                    "earnings_date": "2026-06-15",
                    "days_until": 3,
                    "status": STATUS_CONFIRMED,
                    "source": "yfinance",
                },
                {
                    "ticker": "UNKNOWN",
                    "earnings_date": None,
                    "days_until": None,
                    "status": STATUS_UNKNOWN,
                    "source": "yfinance",
                },
            ],
        }

        table = build_earnings_table(summary)

        self.assertTrue(all(isinstance(value, str) for value in table["Dager"]))
        self.assertEqual(table.iloc[0]["Dager"], "3")
        self.assertEqual(table.iloc[1]["Dager"], "—")

        pa.Table.from_pandas(table)


if __name__ == "__main__":
    unittest.main()
