import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from src.data import (
    _prepare_daily_prices,
    _repair_missing_latest_close,
    get_daily_prices_batch,
)


class PrepareDailyPricesTests(unittest.TestCase):
    def test_drops_nan_close_and_sorts(self):
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0],
                "high": [101.0, 102.0, 103.0],
                "low": [99.0, 100.0, 101.0],
                "close": [100.5, float("nan"), 102.5],
                "adjusted_close": [100.5, 101.5, 102.5],
                "volume": [1000, 1100, 1200],
            },
            index=pd.to_datetime(
                ["2026-06-08", "2026-06-10", "2026-06-09"]
            ),
        )

        cleaned = _prepare_daily_prices(df, "TEST")

        self.assertEqual(len(cleaned), 2)
        self.assertTrue(cleaned.index.is_monotonic_increasing)
        self.assertTrue(cleaned["close"].notna().all())
        self.assertEqual(cleaned.iloc[-1]["close"], 102.5)

    def test_raises_when_all_close_missing(self):
        df = pd.DataFrame(
            {
                "close": [float("nan"), float("nan")],
            },
            index=pd.to_datetime(["2026-06-08", "2026-06-09"]),
        )

        with self.assertRaisesRegex(
            ValueError,
            "Ingen gyldige close-priser",
        ):
            _prepare_daily_prices(df, "TEST")


class DailyPricesBatchTests(unittest.TestCase):
    @patch(
        "src.data._utc_now",
        return_value=datetime(2026, 1, 4, 12, 0, tzinfo=ZoneInfo("UTC")),
    )
    @patch("src.data._write_price_cache")
    @patch("src.data._price_cache_file")
    @patch("src.data._read_current_price_cache", return_value=None)
    @patch("src.data.yf.download")
    def test_splits_multi_ticker_download(
        self,
        mock_download,
        _mock_cache_read,
        mock_cache_file,
        mock_cache_write,
        _mock_now,
    ):
        index = pd.date_range("2026-01-01", periods=3)
        columns = pd.MultiIndex.from_product(
            [
                ["Open", "High", "Low", "Close", "Adj Close", "Volume"],
                ["AAA", "BBB"],
            ]
        )
        values = []
        for _ in index:
            values.append(
                [10, 20, 11, 21, 9, 19, 10.5, 20.5, 10.5, 20.5, 1000, 2000]
            )
        mock_download.return_value = pd.DataFrame(values, index=index, columns=columns)
        mock_cache_file.side_effect = lambda symbol: f"/tmp/{symbol}.json"

        prices, errors = get_daily_prices_batch(["AAA", "BBB"])

        self.assertEqual(set(prices), {"AAA", "BBB"})
        self.assertEqual(errors, {})
        self.assertEqual(prices["AAA"].iloc[-1]["close"], 10.5)
        self.assertEqual(prices["BBB"].iloc[-1]["volume"], 2000)
        self.assertEqual(mock_cache_write.call_count, 2)

    @patch("src.data.yf.download")
    @patch("src.data._read_current_price_cache")
    def test_uses_cache_without_download(self, mock_cache_read, mock_download):
        cached = pd.DataFrame(
            {"close": [10.0], "volume": [1000.0]},
            index=pd.to_datetime(["2026-07-24"]),
        )
        mock_cache_read.return_value = cached

        prices, errors = get_daily_prices_batch(["AAA"])

        mock_download.assert_not_called()
        self.assertIs(prices["AAA"], cached)
        self.assertEqual(errors, {})

    @patch("src.data._write_price_cache")
    @patch(
        "src.data._utc_now",
        return_value=datetime(2026, 8, 14, 4, 0, tzinfo=ZoneInfo("UTC")),
    )
    @patch("src.data._price_cache_file")
    @patch("src.data._read_current_price_cache", return_value=None)
    @patch("src.data.yf.download")
    def test_does_not_cache_symbol_with_missing_latest_close(
        self,
        mock_download,
        _mock_cache_read,
        mock_cache_file,
        _mock_now,
        mock_cache_write,
    ):
        index = pd.to_datetime(["2026-08-12", "2026-08-13"])
        fields = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
        columns = pd.MultiIndex.from_product([fields, ["AAA", "BBB"]])
        mock_download.return_value = pd.DataFrame(
            [
                [10, 20, 11, 21, 9, 19, 10.5, 20.5, 10.5, 20.5, 1000, 2000],
                [11, 21, 12, 22, 10, 20, 11.5, float("nan"), 11.5, float("nan"), 1100, 2100],
            ],
            index=index,
            columns=columns,
        )
        mock_cache_file.side_effect = lambda symbol: f"/tmp/{symbol}.json"

        prices, errors = get_daily_prices_batch(["AAA", "BBB"])

        self.assertEqual(errors, {})
        self.assertEqual(prices["AAA"].index[-1].date().isoformat(), "2026-08-13")
        self.assertEqual(prices["BBB"].index[-1].date().isoformat(), "2026-08-12")
        mock_cache_write.assert_called_once()
        self.assertEqual(mock_cache_write.call_args.args[1], "AAA")


class RepairLatestCloseTests(unittest.TestCase):
    @patch("src.data._utc_now")
    @patch("src.data.yf.Ticker")
    def test_repairs_completed_session_from_regular_market_metadata(
        self,
        mock_ticker,
        mock_now,
    ):
        oslo = ZoneInfo("Europe/Oslo")
        mock_now.return_value = datetime(2026, 8, 14, 4, 0, tzinfo=ZoneInfo("UTC"))
        ticker = mock_ticker.return_value
        ticker.fast_info = {"lastPrice": 312.3}
        ticker.history_metadata = {
            "regularMarketTime": int(
                datetime(2026, 8, 13, 16, 28, tzinfo=oslo).timestamp()
            ),
            "exchangeTimezoneName": "Europe/Oslo",
        }
        prices = pd.DataFrame(
            {
                "Open": [307.0, 309.5],
                "High": [307.7, 314.5],
                "Low": [304.9, 308.2],
                "Close": [307.7, float("nan")],
                "Adj Close": [307.7, float("nan")],
                "Volume": [1237405, 1733075],
            },
            index=pd.to_datetime(["2026-08-12", "2026-08-13"]),
        )

        repaired = _repair_missing_latest_close(prices, "DNB.OL")

        self.assertEqual(repaired.iloc[-1]["Close"], 312.3)
        self.assertEqual(repaired.iloc[-1]["Adj Close"], 312.3)
        self.assertTrue(pd.isna(prices.iloc[-1]["Close"]))

    @patch("src.data._utc_now")
    @patch("src.data.yf.Ticker")
    def test_appends_completed_session_when_daily_row_is_omitted(
        self,
        mock_ticker,
        mock_now,
    ):
        oslo = ZoneInfo("Europe/Oslo")
        mock_now.return_value = datetime(2026, 8, 14, 4, 0, tzinfo=ZoneInfo("UTC"))
        ticker = mock_ticker.return_value
        ticker.fast_info = {
            "lastPrice": 43.0,
            "open": 43.55,
            "dayHigh": 43.55,
            "dayLow": 43.05,
            "lastVolume": 166970,
        }
        ticker.history_metadata = {
            "regularMarketTime": int(
                datetime(2026, 8, 13, 16, 28, tzinfo=oslo).timestamp()
            ),
            "exchangeTimezoneName": "Europe/Oslo",
        }
        prices = pd.DataFrame(
            {
                "Open": [43.85],
                "High": [44.10],
                "Low": [43.40],
                "Close": [43.40],
                "Adj Close": [43.40],
                "Volume": [149977],
            },
            index=pd.to_datetime(["2026-08-12"]),
        )

        repaired = _repair_missing_latest_close(prices, "BOUV.OL")

        self.assertEqual(repaired.index[-1].date().isoformat(), "2026-08-13")
        self.assertEqual(repaired.iloc[-1]["Close"], 43.0)
        self.assertEqual(repaired.iloc[-1]["Volume"], 166970)

    @patch("src.data._utc_now")
    @patch("src.data.yf.Ticker")
    def test_does_not_use_quote_from_current_trading_date(
        self,
        mock_ticker,
        mock_now,
    ):
        oslo = ZoneInfo("Europe/Oslo")
        mock_now.return_value = datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("UTC"))
        ticker = mock_ticker.return_value
        ticker.fast_info = {"lastPrice": 311.0}
        ticker.history_metadata = {
            "regularMarketTime": int(
                datetime(2026, 8, 13, 14, 0, tzinfo=oslo).timestamp()
            ),
            "exchangeTimezoneName": "Europe/Oslo",
        }
        prices = pd.DataFrame(
            {"Close": [307.7, float("nan")], "Adj Close": [307.7, float("nan")]},
            index=pd.to_datetime(["2026-08-12", "2026-08-13"]),
        )

        unrepaired = _repair_missing_latest_close(prices, "DNB.OL")

        self.assertTrue(pd.isna(unrepaired.iloc[-1]["Close"]))


if __name__ == "__main__":
    unittest.main()
