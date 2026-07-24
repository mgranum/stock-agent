import unittest
from unittest.mock import patch

import pandas as pd

from src.data import _prepare_daily_prices, get_daily_prices_batch


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


if __name__ == "__main__":
    unittest.main()
