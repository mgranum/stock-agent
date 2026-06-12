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


def _advisor_detail(ticker="NVDA", conflict_id="SELL_VS_ANALYST"):
    return {
        "ticker": ticker,
        "advisor": {
            "headline": "Analytikere positive, risiko peker mot reduksjon",
            "takeaway": (
                "Analytikere er positive, men trend/risiko peker mot reduksjon. "
                "Prioriter risikostyring fremfor kursmål."
            ),
            "conflict_id": conflict_id,
        },
        "caution_signals": [
            "Svak / negativ trend",
            "Porteføljehandling: REDUSER / SELG",
        ],
        "hold_signals": [
            "Analytikere er positive (Sterk kjøp)",
            "Kursmål viser 22.0% oppside",
        ],
        "practical_interpretation": (
            "Jeg ville fulgt kursutvikling og stop-nivå tettere enn analytikernes "
            "kursmål akkurat nå."
        ),
    }


def _advisor_context():
    advisor_output = {
        "items": [
            {
                "ticker": "NVDA",
                "conflict_id": "SELL_VS_ANALYST",
                "headline": "Analytikere positive, risiko peker mot reduksjon",
                "takeaway": (
                    "Analytikere er positive, men trend/risiko peker mot reduksjon. "
                    "Prioriter risikostyring fremfor kursmål."
                ),
                "priority": 1,
            },
            {
                "ticker": "GOOGL",
                "conflict_id": "BUY_NEAR_EARNINGS",
                "headline": "Kjøpssignal, rapport nær",
                "takeaway": (
                    "Kjøpssignal finnes, men kvartalsrapport er nær. "
                    "Vurder om du vil ta rapport-risiko."
                ),
                "priority": 2,
            },
        ],
        "secondary_items": [],
    }
    return {
        "watchlist": ["NVDA", "GOOGL", "VOLV-B.ST"],
        "watchlist_report": pd.DataFrame(
            [
                {"ticker": "NVDA", "score": 42, "anbefaling": "UNNGÅ / SELG"},
                {"ticker": "GOOGL", "score": 75, "anbefaling": "KJØP / ØK"},
            ]
        ),
        "portfolio_report": None,
        "earnings_summary": {},
        "advisor_output": advisor_output,
        "advisor_details": {
            "NVDA": _advisor_detail("NVDA"),
            "GOOGL": {
                **_advisor_detail("GOOGL", conflict_id="BUY_NEAR_EARNINGS"),
                "advisor": {
                    "headline": "Kjøpssignal, rapport nær",
                    "takeaway": (
                        "Kjøpssignal finnes, men kvartalsrapport er nær. "
                        "Vurder om du vil ta rapport-risiko."
                    ),
                    "conflict_id": "BUY_NEAR_EARNINGS",
                },
            },
        },
        "dashboard": {},
        "daily_flow": {},
    }


class AgentAdvisorTests(unittest.TestCase):
    def test_why_does_agent_say_this_about_ticker(self):
        answer = ask_agent(
            "Hvorfor sier agenten dette om NVDA?",
            _advisor_context(),
        )

        self.assertIn("NVDA", answer)
        self.assertIn("Kort oppsummering:", answer)
        self.assertIn("Taler for varsomhet:", answer)
        self.assertIn("Taler for å holde/vente:", answer)
        self.assertIn("Praktisk tolkning:", answer)
        self.assertIn("Prioriter risikostyring", answer)

    def test_what_is_conflict_in_ticker(self):
        answer = ask_agent(
            "Hva er konflikten i GOOGL?",
            _advisor_context(),
        )

        self.assertIn("GOOGL", answer)
        self.assertIn("Kort oppsummering:", answer)
        self.assertIn("rapport-risiko", answer)

    def test_list_conflicting_tickers(self):
        answer = ask_agent(
            "Hvilke aksjer har motstridende signaler?",
            _advisor_context(),
        )

        self.assertIn("Aksjer med motstridende signaler:", answer)
        self.assertIn("NVDA:", answer)
        self.assertIn("GOOGL:", answer)

    def test_explain_advisor_signal_for_ticker(self):
        answer = ask_agent(
            "Forklar advisor-signalet for VOLV-B.ST",
            {
                **_advisor_context(),
                "advisor_output": {
                    "items": [
                        {
                            "ticker": "VOLV-B.ST",
                            "headline": "Gevinst høy, stop nær",
                            "takeaway": "Test takeaway for VOLV.",
                            "priority": 1,
                        }
                    ],
                    "secondary_items": [],
                },
                "advisor_details": {
                    "VOLV-B.ST": _advisor_detail(
                        "VOLV-B.ST",
                        conflict_id="GAIN_VS_STOP",
                    ),
                },
            },
        )

        self.assertIn("VOLV-B.ST", answer)
        self.assertIn("Kort oppsummering:", answer)

    def test_no_conflicts_message(self):
        answer = ask_agent(
            "Hvilke aksjer har motstridende signaler?",
            {**_advisor_context(), "advisor_output": {"items": []}, "advisor_details": {}},
        )

        self.assertIn("Ingen motstridende signaler", answer)


if __name__ == "__main__":
    unittest.main()
