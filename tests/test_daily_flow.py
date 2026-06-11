import unittest

import pandas as pd

from src.daily_flow import (
    _large_drawdown_positions,
    _positions_near_trailing_stop,
)


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


class DailyFlowPortfolioAlertTests(unittest.TestCase):
    def test_nan_unrealized_gain_pct_does_not_trigger_drawdown_alert(self):
        df = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="NVDA",
                    unrealized_gain_pct=float("nan"),
                    current_price=float("nan"),
                    market_value=float("nan"),
                ),
            ]
        )

        alerts = _large_drawdown_positions(df)

        self.assertTrue(alerts.empty)

    def test_nan_current_price_does_not_trigger_near_trailing_stop_alert(self):
        df = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="NVDA",
                    current_price=float("nan"),
                    market_value=float("nan"),
                    unrealized_gain_pct=float("nan"),
                    trailing_stop_loss=200.0,
                ),
            ]
        )

        alerts = _positions_near_trailing_stop(df)

        self.assertTrue(alerts.empty)


if __name__ == "__main__":
    unittest.main()
