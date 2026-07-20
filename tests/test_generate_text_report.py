import unittest
from unittest.mock import patch

import pandas as pd

from src.agent import ask_agent
from src.analysis import generate_text_report


def _watchlist_report():
    return pd.DataFrame(
        [
            {
                "ticker": "EQNR.OL",
                "score": 80,
                "anbefaling": "KJØP / ØK",
                "trend_regime": "STERK OPPTREND",
                "fundamental_score": 70,
                "fundamental_history_score": 75,
                "relative_strength_20d": 5.2,
            }
        ]
    )


def _portfolio_row(**overrides):
    row = {
        "ticker": "NVDA",
        "portefølje_råd": "HOLD",
        "score": 85,
    }
    row.update(overrides)
    return row


class GenerateTextReportTests(unittest.TestCase):
    def test_portfolio_report_with_gain_pct(self):
        portfolio_report = pd.DataFrame(
            [_portfolio_row(gain_pct=12.5, unrealized_gain_pct=15.0)]
        )

        report = generate_text_report(_watchlist_report(), portfolio_report)

        self.assertIn("Portefølje:", report)
        self.assertIn("gevinst/tap 12.5%", report)
        self.assertIn("NVDA: HOLD", report)

    def test_portfolio_report_with_unrealized_gain_pct(self):
        portfolio_report = pd.DataFrame(
            [_portfolio_row(unrealized_gain_pct=18.2)]
        )

        report = generate_text_report(_watchlist_report(), portfolio_report)

        self.assertIn("gevinst/tap 18.2%", report)

    def test_portfolio_report_without_gain_fields_does_not_crash(self):
        portfolio_report = pd.DataFrame([_portfolio_row()])

        report = generate_text_report(_watchlist_report(), portfolio_report)

        self.assertIn("Portefølje:", report)
        self.assertIn("gevinst/tap —%", report)
        self.assertIn("NVDA: HOLD", report)

    def test_empty_portfolio_report_skips_portfolio_section(self):
        report = generate_text_report(_watchlist_report(), pd.DataFrame())

        self.assertNotIn("Portefølje:", report)


class AgentNorskeKandidaterTests(unittest.TestCase):
    @patch("src.agent.screen_obx")
    def test_norske_kandidater_use_obx_screening(self, mock_screen_obx):
        mock_screen_obx.return_value = pd.DataFrame(
            [
                {
                    "ticker": "EQNR.OL",
                    "score": 82,
                    "trend_regime": "STERK OPPTREND",
                    "relative_strength_20d": 4.5,
                }
            ]
        )

        context = {
            "watchlist": ["BRK-B"],
            "watchlist_report": pd.DataFrame(
                [
                    {
                        "ticker": "BRK-B",
                        "score": 100,
                        "anbefaling": "KJØP / ØK",
                        "relative_strength_20d": 8.0,
                        "trend_regime": "STERK OPPTREND",
                    }
                ]
            ),
            "portfolio_report": pd.DataFrame(
                [
                    {
                        "ticker": "NVDA",
                        "portefølje_råd": "HOLD",
                        "score": 85,
                        "unrealized_gain_pct": 10.0,
                    }
                ]
            ),
            "dashboard": {},
            "daily_flow": {},
        }

        answer = ask_agent("Vis meg de beste norske kandidatene", context)

        mock_screen_obx.assert_called_once()
        self.assertIn("Topp 5 norske kandidater", answer)
        self.assertIn("EQNR.OL", answer)
        self.assertNotIn("BRK-B", answer)
        self.assertNotIn("Portefølje:", answer)
        self.assertNotIn("DAGENS RÅD", answer)

    def test_dagens_råd_with_unrealized_gain_pct_does_not_crash(self):
        context = {
            "watchlist": ["EQNR.OL"],
            "watchlist_report": _watchlist_report(),
            "portfolio_report": pd.DataFrame(
                [
                    {
                        "ticker": "NVDA",
                        "portefølje_råd": "HOLD",
                        "score": 85,
                        "unrealized_gain_pct": 10.0,
                    }
                ]
            ),
            "dashboard": {},
            "daily_flow": {},
        }

        answer = ask_agent("Vis meg dagens råd", context)

        self.assertIn("Dagens anbefalinger", answer)
        self.assertIn("Ingen viktige handlinger anbefales i dag.", answer)


if __name__ == "__main__":
    unittest.main()
