import unittest

import pandas as pd

from src.dashboard import _portfolio_risk


def _portfolio_row(**overrides):
    base = {
        "ticker": "AAPL",
        "market_value": 2905.5,
        "unrealized_gain_pct": 62.32,
        "current_price": 290.55,
        "cost_value": 1790.0,
        "portefølje_råd": "HOLD",
        "anbefaling": "HOLD / OBSERVER",
        "trailing_stop_loss": 250.0,
    }
    base.update(overrides)
    return base


class PortfolioRiskTests(unittest.TestCase):
    def test_ignores_rows_with_invalid_metric_columns(self):
        df = pd.DataFrame(
            [
                _portfolio_row(ticker="AAPL", market_value=2905.5),
                _portfolio_row(
                    ticker="NVDA",
                    market_value=float("nan"),
                    current_price=float("nan"),
                    unrealized_gain_pct=float("nan"),
                ),
            ]
        )

        risk = _portfolio_risk(df)

        self.assertEqual(risk["positions"], 1)
        self.assertEqual(risk["total_market_value"], 2905.5)


if __name__ == "__main__":
    unittest.main()
