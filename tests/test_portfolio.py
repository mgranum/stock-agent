import unittest

import pandas as pd

from src.portfolio import valid_portfolio_rows


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
