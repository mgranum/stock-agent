import unittest
from unittest.mock import patch

import pandas as pd

from src.agent import ask_agent, is_candidate_discovery_question
from src.daily_flow import format_snapshot_changes_answer, is_snapshot_changes_question
from src.recommendation_engine import is_recommendation_question
from src.screening_dedup import deduplicate_screening_results


def _screening_row(ticker, score, primary_profile, **profile_scores):
    row = {
        "ticker": ticker,
        "in_watchlist": "Nei",
        "score": score,
        "recommendation": "KJØP / ØK",
        "trend_regime": "STERK OPPTREND",
        "relative_strength_20d": 8.0,
        "fundamental_score": 75,
        "fundamental_history_score": 78,
        "primary_profile": primary_profile,
    }
    for profile in ("momentum", "quality", "value", "cyclical"):
        row[f"profile_score_{profile}"] = profile_scores.get(profile, 50)
    return row


def _screening_results(**overrides):
    base = {
        "USA": pd.DataFrame(
            [
                _screening_row("NVDA", 95, "momentum", momentum=92),
                _screening_row("JPM", 88, "value", value=85),
            ]
        ),
        "NORDEN": pd.DataFrame(
            [
                _screening_row("VOLV-B.ST", 90, "quality", quality=88),
            ]
        ),
        "OBX": pd.DataFrame(
            [
                _screening_row("FRO.OL", 98, "cyclical", cyclical=90),
            ]
        ),
        "meta": {
            "USA": {"universe_size": 2, "is_full_universe": True},
            "NORDEN": {"universe_size": 1, "is_full_universe": True},
            "OBX": {"universe_size": 1, "is_full_universe": True},
        },
        "generated_at": "2026-06-18T08:00:00+00:00",
    }
    base.update(overrides)
    return base


def _sample_context(**overrides):
    context = {
        "watchlist": [],
        "watchlist_report": pd.DataFrame(),
        "portfolio_report": None,
        "dashboard": {},
        "daily_flow": {},
        "screening_results": _screening_results(),
    }
    context.update(overrides)
    return context


def _snapshot_change_row(**overrides):
    base = {
        "ticker": "AAPL",
        "previous_score": 50,
        "current_score": 65,
        "score_change": 15,
        "previous_recommendation": "HOLD / OBSERVER",
        "current_recommendation": "KJØP / ØK",
    }
    base.update(overrides)
    return base


class RecommendationRoutingTests(unittest.TestCase):
    def test_action_recommendation_phrases_match(self):
        self.assertTrue(is_recommendation_question("Hva bør jeg gjøre i dag?"))
        self.assertTrue(
            is_recommendation_question("Hva bør jeg fokusere på i dag?")
        )
        self.assertTrue(is_recommendation_question("Hva er viktig i dag?"))

    def test_candidate_discovery_phrases_do_not_match_recommendations(self):
        self.assertFalse(
            is_recommendation_question("Hvilke aksjer bør jeg se på i dag?")
        )
        self.assertFalse(
            is_recommendation_question("Hvilke kandidater bør jeg se på?")
        )
        self.assertFalse(
            is_recommendation_question("Hvilke aksjer ser mest interessante ut?")
        )
        self.assertFalse(
            is_recommendation_question("Hvilke aksjer ser sterkest ut i dag?")
        )
        self.assertFalse(
            is_recommendation_question("Hvilke kandidater er mest interessante?")
        )
        self.assertFalse(
            is_recommendation_question("Vis de beste kandidatene i dag")
        )

    def test_candidate_discovery_phrases_match(self):
        self.assertTrue(
            is_candidate_discovery_question("Hvilke aksjer bør jeg se på i dag?")
        )
        self.assertTrue(
            is_candidate_discovery_question("Hvilke aksjer ser sterkest ut i dag?")
        )
        self.assertTrue(
            is_candidate_discovery_question("Hvilke kandidater er mest interessante?")
        )
        self.assertTrue(
            is_candidate_discovery_question("Vis de beste kandidatene i dag")
        )

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_candidate_discovery_routes_to_screening(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "NVDA"}
        mock_get_earnings.return_value = {"ticker": "NVDA"}

        answer = ask_agent(
            "Hvilke aksjer ser sterkest ut i dag?",
            _sample_context(),
        )

        self.assertIn("Topp 5 kandidater i dag", answer)
        self.assertIn("Kort kommentar fra Opportunity Advisor", answer)
        self.assertNotIn("Dagens anbefalinger", answer)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_see_pa_i_dag_routes_to_candidate_discovery(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "NVDA"}
        mock_get_earnings.return_value = {"ticker": "NVDA"}

        answer = ask_agent(
            "Hvilke aksjer bør jeg se på i dag?",
            _sample_context(),
        )

        self.assertIn("Topp 5 kandidater i dag", answer)
        self.assertNotIn("Dagens anbefalinger", answer)

    def test_action_question_routes_to_recommendations(self):
        answer = ask_agent(
            "Hva er viktig i dag?",
            _sample_context(),
        )

        self.assertIn("Dagens anbefalinger", answer)
        self.assertNotIn("Topp 5 kandidater i dag", answer)


class SnapshotChangesRoutingTests(unittest.TestCase):
    def test_snapshot_changes_phrases_match(self):
        self.assertTrue(is_snapshot_changes_question("Hva har endret seg siden i går?"))
        self.assertTrue(is_snapshot_changes_question("Hva har endret seg siden sist?"))
        self.assertTrue(
            is_snapshot_changes_question("Hva er nytt siden forrige oppdatering?")
        )

    def test_snapshot_changes_question_routes_to_existing_diff(self):
        context = _sample_context(
            dashboard={
                "changes_since_last_snapshot": {
                    "recommendation_changed": pd.DataFrame(
                        [
                            _snapshot_change_row(
                                ticker="BRK-B",
                                previous_recommendation="HOLD / OBSERVER",
                                current_recommendation="KJØP / ØK",
                            ),
                        ]
                    ),
                    "large_score_changes": pd.DataFrame([]),
                },
            },
        )

        answer = ask_agent("Hva har endret seg siden i går?", context)

        self.assertIn("Endringer siden forrige snapshot", answer)
        self.assertIn("BRK-B", answer)
        self.assertIn("HOLD", answer)
        self.assertIn("KJØP", answer)

    def test_snapshot_changes_no_data_message(self):
        answer = format_snapshot_changes_answer(_sample_context())
        self.assertIn("ikke tilgjengelig", answer)


class ScreeningDeduplicationTests(unittest.TestCase):
    def test_duplicate_ticker_keeps_best_row(self):
        merged = pd.DataFrame(
            [
                _screening_row("NVDA", 90, "momentum", momentum=80),
                _screening_row("NVDA", 95, "momentum", momentum=92),
            ]
        )

        deduped = deduplicate_screening_results(merged)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(int(deduped.iloc[0]["score"]), 95)
        self.assertEqual(int(deduped.iloc[0]["profile_score_momentum"]), 92)

    def test_duplicate_ticker_across_universes_in_strategy_screening(self):
        context = _sample_context(
            screening_results=_screening_results(
                USA=pd.DataFrame(
                    [
                        _screening_row("NVDA", 95, "momentum", momentum=92),
                        _screening_row("AMD", 90, "momentum", momentum=88),
                    ]
                ),
                NORDEN=pd.DataFrame(
                    [
                        _screening_row("NVDA", 88, "momentum", momentum=70),
                        _screening_row("VOLV-B.ST", 85, "momentum", momentum=65),
                    ]
                ),
                OBX=pd.DataFrame([]),
            )
        )

        answer = ask_agent("Vis meg de beste momentum-aksjene", context)
        listing = answer.split("Kort kommentar")[0]

        self.assertEqual(listing.count("NVDA"), 1)
        self.assertIn("Momentum: 92", listing)

    @patch("src.agent.screen_obx")
    @patch("src.agent.screen_us_large")
    @patch("src.agent.screen_nordics")
    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_existing_strategy_screening_routing_still_works(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
        mock_screen_nordics,
        mock_screen_us,
        mock_screen_obx,
    ):
        mock_get_analyst.return_value = {"ticker": "NVDA"}
        mock_get_earnings.return_value = {"ticker": "NVDA"}

        answer = ask_agent(
            "Vis meg de beste momentum-aksjene",
            _sample_context(),
        )

        mock_screen_nordics.assert_not_called()
        mock_screen_us.assert_not_called()
        mock_screen_obx.assert_not_called()
        self.assertIn("Topp 5 momentum-kandidater", answer)
        self.assertIn("NVDA", answer)

    def test_existing_comparison_routing_still_works(self):
        context = _sample_context(
            watchlist_report=pd.DataFrame(
                [
                    {
                        "ticker": "NVDA",
                        "score": 80,
                        "anbefaling": "KJØP / ØK",
                        "trend_regime": "STERK OPPTREND",
                        "relative_strength_20d": 5.0,
                        "fundamental_score": 70,
                        "fundamental_history_score": 65,
                    },
                    {
                        "ticker": "AMD",
                        "score": 75,
                        "anbefaling": "KJØP / ØK",
                        "trend_regime": "OPPTREND",
                        "relative_strength_20d": 3.0,
                        "fundamental_score": 68,
                        "fundamental_history_score": 60,
                    },
                ]
            ),
        )

        answer = ask_agent("NVDA vs AMD", context)

        self.assertIn("Sammenligning", answer)
        self.assertNotIn("Dagens anbefalinger", answer)
