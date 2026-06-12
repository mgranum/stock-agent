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


def _risk_rows(*rows):
    return pd.DataFrame([_portfolio_row(**row) for row in rows])


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
        self.assertTrue(risk["available"])

    def test_empty_portfolio_has_available_false(self):
        risk = _portfolio_risk(pd.DataFrame())

        self.assertFalse(risk["available"])
        self.assertIsNone(risk["risk_level"]["level"])
        self.assertEqual(risk["geographic_exposure"]["buckets"], [])

    def test_single_position_is_high_risk(self):
        risk = _portfolio_risk(_risk_rows({"ticker": "AAPL", "market_value": 1000}))

        self.assertEqual(risk["risk_level"]["level"], "HØY")
        self.assertIn("SINGLE_POSITION", risk["risk_level"]["drivers"])
        self.assertEqual(risk["diversification"]["effective_n"], 1.0)

    def test_obx_ticker_classified_as_obx(self):
        risk = _portfolio_risk(
            _risk_rows({"ticker": "EQNR.OL", "market_value": 1000})
        )

        obx = next(
            bucket
            for bucket in risk["geographic_exposure"]["buckets"]
            if bucket["market"] == "OBX"
        )
        self.assertEqual(obx["label"], "OBX / Norge")
        self.assertEqual(obx["allocation_pct"], 100.0)
        self.assertEqual(risk["geographic_exposure"]["dominant_market"], "OBX")

    def test_nordic_suffixes_classified_as_norden(self):
        for ticker in ("VOLV-B.ST", "NOVO-B.CO", "NOKIA.HE"):
            with self.subTest(ticker=ticker):
                risk = _portfolio_risk(
                    _risk_rows({"ticker": ticker, "market_value": 1000})
                )
                norden = next(
                    bucket
                    for bucket in risk["geographic_exposure"]["buckets"]
                    if bucket["market"] == "NORDEN"
                )
                self.assertEqual(norden["label"], "Øvrig Norden")
                self.assertEqual(norden["allocation_pct"], 100.0)

    def test_usa_ticker_classified_as_usa(self):
        risk = _portfolio_risk(_risk_rows({"ticker": "AAPL", "market_value": 1000}))

        usa = next(
            bucket
            for bucket in risk["geographic_exposure"]["buckets"]
            if bucket["market"] == "USA"
        )
        self.assertEqual(usa["allocation_pct"], 100.0)
        self.assertEqual(risk["geographic_exposure"]["dominant_market"], "USA")

    def test_effective_n_for_equal_weight_portfolio(self):
        risk = _portfolio_risk(
            _risk_rows(
                {"ticker": "AAPL", "market_value": 2500},
                {"ticker": "MSFT", "market_value": 2500},
                {"ticker": "NVDA", "market_value": 2500},
                {"ticker": "GOOG", "market_value": 2500},
            )
        )

        self.assertEqual(risk["diversification"]["effective_n"], 4.0)
        self.assertEqual(risk["diversification"]["hhi"], 0.25)
        self.assertEqual(risk["diversification"]["equal_weight_pct"], 25.0)
        self.assertEqual(risk["diversification"]["max_deviation_from_equal_pct"], 0.0)

    def test_dominant_market_is_largest_bucket(self):
        risk = _portfolio_risk(
            _risk_rows(
                {"ticker": "AAPL", "market_value": 6000},
                {"ticker": "EQNR.OL", "market_value": 3000},
                {"ticker": "VOLV-B.ST", "market_value": 1000},
            )
        )

        self.assertEqual(risk["geographic_exposure"]["dominant_market"], "USA")
        self.assertEqual(risk["geographic_exposure"]["dominant_market_pct"], 60.0)

    def test_high_concentration_gives_high_risk_level_and_reasons(self):
        risk = _portfolio_risk(
            _risk_rows(
                {"ticker": "NVDA", "market_value": 4000},
                {"ticker": "AAPL", "market_value": 2000},
                {"ticker": "MSFT", "market_value": 2000},
                {"ticker": "GOOG", "market_value": 2000},
            )
        )

        self.assertEqual(risk["top_position_pct"], 40.0)
        self.assertEqual(risk["top3_concentration_pct"], 80.0)
        self.assertEqual(risk["risk_level"]["level"], "HØY")
        self.assertIn("TOP1_HIGH", risk["risk_level"]["drivers"])
        self.assertIn("TOP3_HIGH", risk["risk_level"]["drivers"])
        self.assertTrue(
            any("NVDA utgjør 40" in reason for reason in risk["risk_level"]["reasons"])
        )
        self.assertTrue(
            any("Topp 3 utgjør 80" in reason for reason in risk["risk_level"]["reasons"])
        )

    def test_moderate_concentration_gives_medium_risk_level(self):
        risk = _portfolio_risk(
            _risk_rows(
                {"ticker": "AAPL", "market_value": 2000},
                {"ticker": "MSFT", "market_value": 2000},
                {"ticker": "NVDA", "market_value": 2000},
                {"ticker": "GOOG", "market_value": 2000},
                {"ticker": "AMZN", "market_value": 2000},
            )
        )

        self.assertEqual(risk["top_position_pct"], 20.0)
        self.assertEqual(risk["top3_concentration_pct"], 60.0)
        self.assertEqual(risk["risk_level"]["level"], "MEDIUM")
        self.assertIn("TOP3_ELEVATED", risk["risk_level"]["drivers"])
        self.assertIn("GEO_DOMINANT_HIGH", risk["risk_level"]["drivers"])


if __name__ == "__main__":
    unittest.main()
