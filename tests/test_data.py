import unittest

import pandas as pd

from src.data import _prepare_daily_prices


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


if __name__ == "__main__":
    unittest.main()
