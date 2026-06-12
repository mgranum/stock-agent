import unittest

import pandas as pd

from src.agent import ask_agent


def _mock_context(earnings_summary=None):
    return {
        "watchlist": ["AAPL", "MSFT"],
        "watchlist_report": pd.DataFrame(
            [
                {"ticker": "AAPL", "score": 70, "anbefaling": "HOLD / OBSERVER"},
                {"ticker": "MSFT", "score": 65, "anbefaling": "HOLD / OBSERVER"},
            ]
        ),
        "portfolio_report": None,
        "earnings_summary": earnings_summary or {},
        "dashboard": {},
        "daily_flow": {},
    }


def _earnings_summary():
    return {
        "items": [],
        "upcoming_14_days": [
            {
                "ticker": "AAPL",
                "earnings_date": "2026-06-15",
                "days_until": 3,
                "status": "confirmed",
                "in_portfolio": True,
            },
            {
                "ticker": "MSFT",
                "earnings_date": "2026-06-20",
                "days_until": 8,
                "status": "estimated",
                "in_portfolio": False,
            },
            {
                "ticker": "UNKNOWN",
                "earnings_date": None,
                "days_until": None,
                "status": "unknown",
                "in_portfolio": False,
            },
        ],
        "unknown": [],
        "last_updated": "2026-06-12T08:00:00+00:00",
    }


class AgentEarningsTests(unittest.TestCase):
    def test_who_reports_soon_lists_upcoming_14_days(self):
        answer = ask_agent(
            "Hvem rapporterer snart?",
            _mock_context(_earnings_summary()),
        )

        self.assertIn("Kommende earnings (14 dager)", answer)
        self.assertIn("Portefølje:", answer)
        self.assertIn("AAPL: 2026-06-15", answer)
        self.assertIn("Watchlist:", answer)
        self.assertIn("MSFT: 2026-06-20", answer)
        self.assertNotIn("UNKNOWN", answer)

    def test_portfolio_earnings_this_week(self):
        answer = ask_agent(
            "Har jeg earnings denne uken?",
            _mock_context(_earnings_summary()),
        )

        self.assertIn("Portefølje:", answer)
        self.assertIn("AAPL", answer)
        self.assertNotIn("MSFT", answer)

    def test_portfolio_tickers_only(self):
        answer = ask_agent(
            "Hvilke porteføljeaksjer rapporterer?",
            _mock_context(_earnings_summary()),
        )

        self.assertIn("AAPL", answer)
        self.assertNotIn("Watchlist:", answer)
        self.assertNotIn("MSFT", answer)

    def test_follow_before_earnings_includes_guidance(self):
        answer = ask_agent(
            "Hva bør jeg følge med på før earnings?",
            _mock_context(_earnings_summary()),
        )

        self.assertIn("Følg med på:", answer)
        self.assertIn("trailing stop", answer.lower())
        self.assertIn("Portefølje med rapport innen 7 dager: AAPL", answer)

    def test_no_upcoming_earnings_message(self):
        answer = ask_agent(
            "Hvem rapporterer snart?",
            _mock_context({"upcoming_14_days": [], "unknown": []}),
        )

        self.assertIn("Ingen kommende rapporter innen 14 dager", answer)


if __name__ == "__main__":
    unittest.main()
