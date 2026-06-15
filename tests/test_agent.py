import unittest
from unittest.mock import ANY, patch

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


def _analyst_summary():
    return {
        "items": [
            {
                "ticker": "NVDA",
                "in_portfolio": True,
                "recommendation_key": "strong_buy",
                "recommendation_mean": 1.3,
                "analyst_count": 59,
                "target_mean": 298.93,
                "upside_pct": 45.9,
            },
            {
                "ticker": "GOOGL",
                "in_portfolio": True,
                "recommendation_key": "buy",
                "recommendation_mean": 1.8,
                "analyst_count": 52,
                "target_mean": 432.83,
                "upside_pct": 12.5,
            },
            {
                "ticker": "EQNR.OL",
                "in_portfolio": False,
                "recommendation_key": "hold",
                "recommendation_mean": 3.28,
                "analyst_count": 24,
                "target_mean": 364.31,
                "upside_pct": 8.9,
            },
            {
                "ticker": "EMPTY",
                "in_portfolio": False,
                "recommendation_key": None,
                "recommendation_mean": None,
                "analyst_count": None,
                "target_mean": None,
                "upside_pct": None,
            },
        ],
        "portfolio_items": [],
        "watchlist_items": [],
        "material_changes": [
            {
                "ticker": "NVDA",
                "change_type": "target_mean",
                "Endring": "Kursmål opp (+5.5%)",
                "Fra": 283.0,
                "Til": 298.93,
            }
        ],
        "missing_data": ["EMPTY"],
        "last_updated": "2026-06-12T08:00:00+00:00",
    }


def _analyst_context(analyst_summary=None):
    return {
        "watchlist": ["NVDA", "GOOGL", "EQNR.OL", "EMPTY"],
        "watchlist_report": pd.DataFrame(
            [
                {"ticker": "NVDA", "score": 70, "anbefaling": "KJØP / ØK"},
                {"ticker": "GOOGL", "score": 68, "anbefaling": "KJØP / ØK"},
            ]
        ),
        "portfolio_report": None,
        "earnings_summary": {},
        "analyst_summary": analyst_summary if analyst_summary is not None else _analyst_summary(),
        "dashboard": {},
        "daily_flow": {},
    }


class AgentAnalystTests(unittest.TestCase):
    def test_ticker_analyst_question(self):
        answer = ask_agent(
            "Hva sier analytikerne om NVDA?",
            _analyst_context(),
        )

        self.assertIn("NVDA – Analytikerkonsensus", answer)
        self.assertIn("Konsensus: Sterk kjøp", answer)
        self.assertIn("Analytikere: 59", answer)
        self.assertIn("Kursmål: 298.93", answer)
        self.assertIn("Oppside %: 45.9", answer)
        self.assertIn("Endringer siden sist:", answer)
        self.assertIn("Kursmål opp (+5.5%)", answer)
        self.assertIn("støttesignal", answer.lower())

    def test_price_target_question(self):
        answer = ask_agent(
            "Hva er kursmålet på GOOGL?",
            _analyst_context(),
        )

        self.assertIn("GOOGL – Analytikerkonsensus", answer)
        self.assertIn("Kursmål: 432.83", answer)
        self.assertIn("Oppside %: 12.5", answer)

    def test_portfolio_largest_upside(self):
        answer = ask_agent(
            "Hvilke porteføljeaksjer har størst oppside?",
            _analyst_context(),
        )

        self.assertIn("Porteføljeaksjer med størst analytiker-oppside", answer)
        self.assertLess(
            answer.index("NVDA"),
            answer.index("GOOGL"),
        )
        self.assertIn("45.9% oppside", answer)

    def test_weakest_analyst_consensus(self):
        answer = ask_agent(
            "Hvilke aksjer har svakest analytikerkonsensus?",
            _analyst_context(),
        )

        self.assertIn("Svakeste analytikerkonsensus", answer)
        self.assertLess(
            answer.index("EQNR.OL"),
            answer.index("NVDA"),
        )
        self.assertIn("Hold", answer)

    def test_analyst_changes_since_last(self):
        answer = ask_agent(
            "Har analytikerne endret mening siden sist?",
            _analyst_context(),
        )

        self.assertIn("Analytikerendringer siden sist", answer)
        self.assertIn("NVDA", answer)
        self.assertIn("Kursmål opp (+5.5%)", answer)

    def test_no_analyst_changes_message(self):
        summary = _analyst_summary()
        summary["material_changes"] = []
        answer = ask_agent(
            "Har analytikerne endret mening siden sist?",
            _analyst_context(summary),
        )

        self.assertIn("Ingen materielle endringer siden sist", answer)

    def test_missing_analyst_data(self):
        answer = ask_agent(
            "Hva sier analytikerne om EMPTY?",
            _analyst_context(),
        )

        self.assertIn("Analytikerkonsensus for EMPTY: Ingen data tilgjengelig", answer)


def _screening_results():
    return pd.DataFrame(
        [
            {
                "ticker": "SUBC.OL",
                "in_watchlist": "Nei",
                "score": 94,
                "recommendation": "KJØP / ØK",
                "trend_regime": "STERK OPPTREND",
                "relative_strength_20d": 12.3,
                "fundamental_score": 80,
                "fundamental_history_score": 78,
            },
            {
                "ticker": "VOLV-B.ST",
                "in_watchlist": "Ja",
                "score": 88,
                "recommendation": "KJØP / ØK",
                "trend_regime": "MODERAT OPPTREND",
                "relative_strength_20d": 6.5,
                "fundamental_score": 72,
                "fundamental_history_score": 70,
            },
        ]
    )


def _screening_results_five():
    return pd.DataFrame(
        [
            {
                "ticker": ticker,
                "in_watchlist": "Nei",
                "score": 95 - index,
                "recommendation": "KJØP / ØK",
                "trend_regime": "STERK OPPTREND",
                "relative_strength_20d": 10.0 - index,
                "fundamental_score": 80,
                "fundamental_history_score": 78,
            }
            for index, ticker in enumerate(
                ["AAA", "BBB", "CCC", "DDD", "EEE"]
            )
        ]
    )


class AgentScreeningTests(unittest.TestCase):
    @patch("src.agent.build_opportunity_advisor")
    @patch("src.agent.screen_nordics")
    def test_nordics_question(self, mock_screen_nordics, mock_build_advisor):
        mock_screen_nordics.return_value = _screening_results()
        mock_build_advisor.return_value = {
            "items": [
                {
                    "ticker": "SUBC.OL",
                    "why_interesting": ["Høy score (94)", "Positiv relativ styrke (12.3%)"],
                    "watch_out_for": [],
                    "takeaway": "En av de sterkeste kandidatene i universet akkurat nå.",
                }
            ]
        }

        answer = ask_agent(
            "Vis meg de beste nordiske kandidatene",
            _mock_context(),
        )

        mock_screen_nordics.assert_called_once_with(
            preset="Beste kandidater",
            limit=5,
            pause_seconds=0,
            existing_watchlists=ANY,
        )
        self.assertIn("Topp 5 nordiske kandidater", answer)
        self.assertIn("1. SUBC.OL", answer)
        self.assertIn("Score: 94", answer)
        self.assertIn("Relativ styrke: 12.3 %", answer)
        self.assertIn("Kort kommentar fra Opportunity Advisor", answer)
        self.assertIn("SUBC.OL", answer.split("Kort kommentar")[-1])

    @patch("src.agent.screen_us_large")
    def test_usa_question(self, mock_screen_us_large):
        mock_screen_us_large.return_value = _screening_results()

        answer = ask_agent(
            "Finn sterke amerikanske aksjer",
            _mock_context(),
        )

        mock_screen_us_large.assert_called_once()
        self.assertIn("Topp 5 amerikanske kandidater", answer)

    @patch("src.agent.screen_obx")
    def test_obx_question(self, mock_screen_obx):
        mock_screen_obx.return_value = _screening_results()

        answer = ask_agent(
            "Vis meg de beste OBX-kandidatene",
            _mock_context(),
        )

        mock_screen_obx.assert_called_once()
        self.assertIn("Topp 5 OBX-kandidater", answer)

    @patch("src.agent.screen_nordics")
    def test_empty_screener_result(self, mock_screen_nordics):
        mock_screen_nordics.return_value = pd.DataFrame()

        answer = ask_agent(
            "Hvilke nordiske aksjer ser sterkest ut nå?",
            _mock_context(),
        )

        self.assertIn("Ingen kandidater matchet filteret", answer)

    @patch("src.agent.screen_nordics")
    def test_top5_formatting(self, mock_screen_nordics):
        mock_screen_nordics.return_value = _screening_results()

        answer = ask_agent(
            "Finn sterke nordiske aksjer",
            _mock_context(),
        )

        self.assertIn("1. SUBC.OL", answer)
        self.assertIn("2. VOLV-B.ST", answer)
        self.assertIn("Trend: STERK OPPTREND", answer)
        self.assertIn("Trend: MODERAT OPPTREND", answer)

    @patch("src.agent.build_opportunity_advisor")
    @patch("src.agent.screen_nordics")
    def test_screening_chat_includes_advisor_for_all_top5(
        self,
        mock_screen_nordics,
        mock_build_advisor,
    ):
        mock_screen_nordics.return_value = _screening_results_five()
        mock_build_advisor.return_value = {
            "items": [
                {
                    "ticker": ticker,
                    "why_interesting": [f"Høy score ({95 - index})"],
                    "watch_out_for": [],
                    "takeaway": f"Tolkning for {ticker}.",
                }
                for index, ticker in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE"])
            ]
        }

        answer = ask_agent(
            "Vis meg de beste nordiske kandidatene",
            _mock_context(),
        )

        advisor_section = answer.split("Kort kommentar fra Opportunity Advisor", 1)[1]
        for ticker in ["AAA", "BBB", "CCC", "DDD", "EEE"]:
            self.assertIn(ticker, advisor_section)
            self.assertIn(f"Tolkning for {ticker}.", advisor_section)

        mock_build_advisor.assert_called_once()
        self.assertEqual(
            mock_build_advisor.call_args.kwargs["limit"],
            5,
        )

    @patch("src.agent.build_opportunity_advisor")
    @patch("src.agent.screen_nordics")
    def test_screening_advisor_order_matches_top5(
        self,
        mock_screen_nordics,
        mock_build_advisor,
    ):
        mock_screen_nordics.return_value = _screening_results_five()
        mock_build_advisor.return_value = {
            "items": [
                {
                    "ticker": ticker,
                    "why_interesting": ["Sterk score"],
                    "watch_out_for": [],
                    "takeaway": f"Tolkning for {ticker}.",
                }
                for ticker in ["EEE", "DDD", "CCC", "BBB", "AAA"]
            ]
        }

        answer = ask_agent(
            "Vis meg de beste nordiske kandidatene",
            _mock_context(),
        )

        advisor_section = answer.split("Kort kommentar fra Opportunity Advisor", 1)[1]
        positions = [
            advisor_section.index(ticker)
            for ticker in ["AAA", "BBB", "CCC", "DDD", "EEE"]
        ]
        self.assertEqual(positions, sorted(positions))

    @patch("src.agent.build_opportunity_advisor")
    @patch("src.agent.screen_nordics")
    def test_screening_advisor_fallback_when_item_missing(
        self,
        mock_screen_nordics,
        mock_build_advisor,
    ):
        mock_screen_nordics.return_value = _screening_results_five()
        mock_build_advisor.return_value = {
            "items": [
                {
                    "ticker": "AAA",
                    "why_interesting": ["Sterk score"],
                    "watch_out_for": [],
                    "takeaway": "Tolkning for AAA.",
                }
            ]
        }

        answer = ask_agent(
            "Vis meg de beste nordiske kandidatene",
            _mock_context(),
        )

        self.assertIn(
            "Ingen tydelig advisor-kommentar, men kandidaten scorer høyt i screeneren.",
            answer,
        )
        advisor_section = answer.split("Kort kommentar fra Opportunity Advisor", 1)[1]
        self.assertIn("BBB", advisor_section)
        self.assertIn("Tolkning for AAA.", answer)


def _portfolio_report_rows():
    return pd.DataFrame(
        [
            {
                "ticker": "DNB.OL",
                "score": 72,
                "trend_regime": "MODERAT OPPTREND",
                "relative_strength_20d": -2.0,
                "market_value": 10000,
                "unrealized_gain_pct": 5.0,
                "current_price": 200,
                "cost_value": 9500,
                "portefølje_råd": "HOLD",
                "anbefaling": "HOLD / OBSERVER",
                "trailing_stop_loss": 180,
            },
            {
                "ticker": "EQNR.OL",
                "score": 75,
                "trend_regime": "SVAK / NEGATIV TREND",
                "relative_strength_20d": 1.0,
                "market_value": 12000,
                "unrealized_gain_pct": -3.0,
                "current_price": 250,
                "cost_value": 12300,
                "portefølje_råd": "FØLG MED / IKKE ØK",
                "anbefaling": "HOLD / OBSERVER",
                "trailing_stop_loss": 220,
            },
            {
                "ticker": "AAPL",
                "score": 88,
                "trend_regime": "STERK OPPTREND",
                "relative_strength_20d": 8.0,
                "market_value": 15000,
                "unrealized_gain_pct": 12.0,
                "current_price": 180,
                "cost_value": 13400,
                "portefølje_råd": "HOLD / LA VINNER LØPE",
                "anbefaling": "KJØP / ØK",
                "trailing_stop_loss": 160,
            },
        ]
    )


def _portfolio_comparison_screener_results():
    return pd.DataFrame(
        [
            {
                "ticker": "AVGO",
                "in_watchlist": "Nei",
                "score": 95,
                "recommendation": "KJØP / ØK",
                "trend_regime": "STERK OPPTREND",
                "relative_strength_20d": 14.0,
                "fundamental_score": 85,
                "fundamental_history_score": 82,
            },
            {
                "ticker": "MSFT",
                "in_watchlist": "Ja",
                "score": 80,
                "recommendation": "KJØP / ØK",
                "trend_regime": "MODERAT OPPTREND",
                "relative_strength_20d": 3.0,
                "fundamental_score": 78,
                "fundamental_history_score": 76,
            },
        ]
    )


def _portfolio_comparison_context(portfolio_report=None):
    context = _mock_context()
    context["portfolio_report"] = portfolio_report
    return context


class AgentPortfolioComparisonTests(unittest.TestCase):
    @patch("src.agent.build_opportunity_advisor")
    @patch("src.agent.screen_us_large")
    def test_question_is_recognized(self, mock_screen_us_large, mock_build_advisor):
        mock_screen_us_large.return_value = _portfolio_comparison_screener_results()
        mock_build_advisor.return_value = {
            "items": [
                {
                    "ticker": "AVGO",
                    "takeaway": "En av de sterkeste kandidatene i universet akkurat nå.",
                }
            ]
        }

        answer = ask_agent(
            "Hvilke kandidater ser bedre ut enn det jeg eier?",
            _portfolio_comparison_context(_portfolio_report_rows()),
        )

        mock_screen_us_large.assert_called_once_with(
            preset="Beste kandidater",
            limit=5,
            pause_seconds=0,
            existing_watchlists=ANY,
        )
        self.assertIn("Mest interessante kandidater akkurat nå", answer)
        self.assertIn("1. AVGO", answer)
        self.assertIn("Score: 95", answer)

    @patch("src.agent.screen_us_large")
    def test_top_candidates_and_weakest_portfolio_positions(
        self,
        mock_screen_us_large,
    ):
        mock_screen_us_large.return_value = _portfolio_comparison_screener_results()

        answer = ask_agent(
            "Finnes det sterkere kandidater enn mine svakeste posisjoner?",
            _portfolio_comparison_context(_portfolio_report_rows()),
        )

        self.assertIn("Ser sterkere ut enn:", answer)
        self.assertIn("DNB.OL (72)", answer)
        self.assertIn("EQNR.OL (75)", answer)
        self.assertNotIn("AAPL (88)", answer)
        self.assertIn("høyere score", answer)
        self.assertIn("sterkere trend", answer)
        self.assertIn("bedre relativ styrke", answer)

    @patch("src.agent.screen_nordics")
    def test_nordics_region_for_portfolio_comparison(self, mock_screen_nordics):
        mock_screen_nordics.return_value = _portfolio_comparison_screener_results()

        ask_agent(
            "Hvilke nordiske kandidater ser bedre ut enn det jeg eier?",
            _portfolio_comparison_context(_portfolio_report_rows()),
        )

        mock_screen_nordics.assert_called_once()

    @patch("src.agent.screen_obx")
    def test_obx_region_for_norsk_question(self, mock_screen_obx):
        mock_screen_obx.return_value = _portfolio_comparison_screener_results()

        ask_agent(
            "Finnes det sterkere norske kandidater enn mine svakeste posisjoner?",
            _portfolio_comparison_context(_portfolio_report_rows()),
        )

        mock_screen_obx.assert_called_once()

    @patch("src.agent.screen_us_large")
    def test_empty_portfolio_handled(self, mock_screen_us_large):
        mock_screen_us_large.return_value = _portfolio_comparison_screener_results()

        answer = ask_agent(
            "Hva er de mest interessante kjøpskandidatene akkurat nå?",
            _portfolio_comparison_context(None),
        )

        self.assertIn("Ingen porteføljeposisjoner å sammenligne med", answer)
        self.assertNotIn("Ser sterkere ut enn:", answer)

    @patch("src.agent.screen_us_large")
    def test_empty_screener_result_handled(self, mock_screen_us_large):
        mock_screen_us_large.return_value = pd.DataFrame()

        answer = ask_agent(
            "Hvilke kandidater ser bedre ut enn det jeg eier?",
            _portfolio_comparison_context(_portfolio_report_rows()),
        )

        self.assertIn("Ingen screener-kandidater matchet filteret", answer)


def _watchlist_advisor_context(**overrides):
    context = {
        "watchlist": ["NVDA", "MSFT", "INTC", "AAPL"],
        "watchlist_report": pd.DataFrame(),
        "portfolio_report": pd.DataFrame(
            [
                {
                    "ticker": "AAPL",
                    "shares": 10,
                    "buy_price": 100.0,
                    "current_price": 150.0,
                    "cost_value": 1000.0,
                    "market_value": 1500.0,
                    "unrealized_profit_loss": 500.0,
                    "unrealized_gain_pct": 50.0,
                    "score": 75,
                    "anbefaling": "HOLD / OBSERVER",
                    "trend_regime": "MODERAT OPPTREND",
                    "relative_strength_20d": 2.0,
                    "portefølje_råd": "HOLD",
                    "trailing_stop_loss": 120.0,
                }
            ]
        ),
        "watchlist_advisor_output": {
            "items": [
                {
                    "ticker": "NVDA",
                    "watchlist_action": "VURDER_KJØP",
                    "headline": "Vurder kjøp",
                    "why": ["Modellanbefaling: KJØP / ØK", "Sterk opptrend"],
                    "watch_out_for": [],
                    "takeaway": "Sterk kandidat med god trend.",
                    "priority": 1,
                },
                {
                    "ticker": "MSFT",
                    "watchlist_action": "VENT",
                    "headline": "Vent",
                    "why": ["Modellanbefaling: HOLD / OBSERVER"],
                    "watch_out_for": ["Negativ nyhetstone"],
                    "takeaway": "Ikke prioritet nå.",
                    "priority": 3,
                },
                {
                    "ticker": "INTC",
                    "watchlist_action": "FJERN_FRA_WATCHLIST",
                    "headline": "Fjern fra watchlist",
                    "why": ["Modellanbefaling: UNNGÅ / SELG"],
                    "watch_out_for": [],
                    "takeaway": "Modellen og trendbildet er svakt.",
                    "priority": 1,
                },
            ],
            "method": "rule_v1",
            "disclaimer": "Tolkningslag for watchlist.",
        },
        "dashboard": {},
        "daily_flow": {},
    }
    context.update(overrides)
    return context


class AgentWatchlistAdvisorTests(unittest.TestCase):
    def test_list_vurder_kjop_from_watchlist(self):
        answer = ask_agent(
            "Hvilke aksjer bør jeg vurdere å kjøpe fra watchlist?",
            _watchlist_advisor_context(),
        )

        self.assertIn("Watchlist-råd", answer)
        self.assertIn("Vurder kjøp:", answer)
        self.assertIn("NVDA: Sterk kandidat med god trend.", answer)
        self.assertNotIn("AAPL:", answer)

    def test_list_fjern_fra_watchlist(self):
        answer = ask_agent(
            "Hvilke aksjer bør fjernes fra watchlist?",
            _watchlist_advisor_context(),
        )

        self.assertIn("Fjern fra watchlist:", answer)
        self.assertIn("INTC: Modellen og trendbildet er svakt.", answer)
        self.assertNotIn("AAPL:", answer)

    def test_ticker_question_about_watchlist_advisor(self):
        answer = ask_agent(
            "Hva sier watchlist-advisor om NVDA?",
            _watchlist_advisor_context(),
        )

        self.assertIn("NVDA", answer)
        self.assertIn("Handling:", answer)
        self.assertIn("Vurder kjøp", answer)
        self.assertIn("Hvorfor:", answer)
        self.assertIn("Modellanbefaling: KJØP / ØK", answer)
        self.assertIn("Tolkning:", answer)
        self.assertIn("Sterk kandidat med god trend.", answer)

    def test_why_wait_with_ticker(self):
        answer = ask_agent(
            "Hvorfor sier agenten at jeg skal vente med MSFT?",
            _watchlist_advisor_context(),
        )

        self.assertIn("MSFT", answer)
        self.assertIn("Handling:", answer)
        self.assertIn("Vent", answer)
        self.assertIn("Negativ nyhetstone", answer)
        self.assertIn("Ikke prioritet nå.", answer)

    def test_unknown_ticker_returns_no_advice_message(self):
        answer = ask_agent(
            "Hva sier watchlist-advisor om UNKNOWN?",
            _watchlist_advisor_context(),
        )

        self.assertIn("Watchlist-advisor for UNKNOWN:", answer)
        self.assertIn("Ingen watchlist-råd identifisert", answer)

    def test_empty_watchlist_advisor_output(self):
        answer = ask_agent(
            "Hvilke aksjer bør jeg vente med?",
            _watchlist_advisor_context(
                watchlist_advisor_output={"items": []},
            ),
        )

        self.assertIn("Watchlist-råd", answer)
        self.assertIn("Vent:", answer)
        self.assertIn("Ingen aksjer akkurat nå.", answer)

    def test_owned_ticker_not_in_advisor_lists(self):
        answer = ask_agent(
            "Hvilke aksjer bør jeg vurdere å kjøpe fra watchlist?",
            _watchlist_advisor_context(
                watchlist_advisor_output={
                    "items": [
                        {
                            "ticker": "NVDA",
                            "watchlist_action": "VURDER_KJØP",
                            "takeaway": "Sterk kandidat.",
                            "priority": 1,
                        }
                    ]
                },
            ),
        )

        self.assertIn("NVDA:", answer)
        self.assertNotIn("AAPL:", answer)


if __name__ == "__main__":
    unittest.main()
