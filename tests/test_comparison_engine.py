import unittest
from unittest.mock import patch

import pandas as pd

from src.agent import ask_agent
from src.comparison_engine import (
    _dedupe_tickers_preserve_order,
    build_comparison,
    format_comparison_answer,
    is_comparison_question,
    resolve_comparison_tickers,
)


def _screening_row(ticker, score, primary_profile, **overrides):
    profile_scores = {}
    for key, value in list(overrides.items()):
        if key in ("momentum", "quality", "value", "cyclical"):
            profile_scores[f"profile_score_{key}"] = value
            overrides.pop(key)

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
        "profile_score_momentum": 50,
        "profile_score_quality": 50,
        "profile_score_value": 50,
        "profile_score_cyclical": 50,
    }
    row[f"profile_score_{primary_profile}"] = profile_scores.get(
        f"profile_score_{primary_profile}",
        80,
    )
    row.update(profile_scores)
    row.update(overrides)
    return row


def _screening_results(**overrides):
    base = {
        "USA": pd.DataFrame(
            [
                _screening_row("NVDA", 95, "momentum", momentum=92, relative_strength_20d=15.0),
                _screening_row("AMD", 89, "momentum", momentum=85, relative_strength_20d=11.0),
                _screening_row("MSFT", 91, "quality", quality=88, relative_strength_20d=6.0),
            ]
        ),
        "NORDEN": pd.DataFrame([]),
        "OBX": pd.DataFrame(
            [
                _screening_row(
                    "SUBC.OL",
                    99,
                    "cyclical",
                    cyclical=90,
                    relative_strength_20d=13.3,
                    trend_regime="STERK OPPTREND",
                ),
                _screening_row(
                    "AKRBP.OL",
                    91,
                    "cyclical",
                    cyclical=82,
                    relative_strength_20d=6.1,
                    trend_regime="MODERAT OPPTREND",
                    fundamental_score=86,
                ),
                _screening_row(
                    "FRO.OL",
                    88,
                    "cyclical",
                    cyclical=95,
                    relative_strength_20d=4.0,
                    trend_regime="MODERAT OPPTREND",
                ),
            ]
        ),
        "meta": {
            "USA": {"universe_size": 2, "is_full_universe": True},
            "NORDEN": {"universe_size": 0, "is_full_universe": True},
            "OBX": {"universe_size": 3, "is_full_universe": True},
        },
        "generated_at": "2026-06-18T08:00:00+00:00",
    }
    base.update(overrides)
    return base


def _mock_context(**overrides):
    context = {
        "watchlist": ["NVDA", "MSFT"],
        "watchlist_report": pd.DataFrame([]),
        "portfolio_report": None,
        "dashboard": {},
        "daily_flow": {},
        "screening_results": _screening_results(),
        "analyst_summary": {
            "items": [
                {
                    "ticker": "SUBC.OL",
                    "recommendation_key": "buy",
                    "target_mean": 200,
                    "upside_pct": 10,
                    "analyst_count": 12,
                },
                {
                    "ticker": "AKRBP.OL",
                    "recommendation_key": "hold",
                    "target_mean": 280,
                    "upside_pct": 5,
                    "analyst_count": 18,
                },
            ]
        },
    }
    context.update(overrides)
    return context


class ComparisonEngineTests(unittest.TestCase):
    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_two_ticker_comparison(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "SUBC.OL"}
        mock_get_earnings.return_value = {"ticker": "SUBC.OL"}

        comparison = build_comparison(["SUBC.OL", "AKRBP.OL"], _mock_context())

        self.assertEqual(len(comparison["rows"]), 2)
        self.assertEqual(comparison["winner"], "SUBC.OL")
        self.assertEqual(comparison["category_winners"]["total_score"], "SUBC.OL")
        self.assertEqual(comparison["category_winners"]["fundamentals"], "AKRBP.OL")

        answer = format_comparison_answer(comparison)
        self.assertIn("Sammenligning: SUBC.OL vs AKRBP.OL", answer)
        self.assertIn("SUBC.OL", answer)
        self.assertIn("Samlet vurdering:", answer)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_three_ticker_comparison(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "SUBC.OL"}
        mock_get_earnings.return_value = {"ticker": "SUBC.OL"}

        comparison = build_comparison(
            ["SUBC.OL", "AKRBP.OL", "FRO.OL"],
            _mock_context(),
        )

        self.assertEqual(len(comparison["rows"]), 3)
        answer = format_comparison_answer(comparison)
        self.assertIn("| Ticker | Score | Trend | RS | Fund | Profil |", answer)
        self.assertIn("FRO.OL", answer)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_winner_by_total_score(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "NVDA"}
        mock_get_earnings.return_value = {"ticker": "NVDA"}

        comparison = build_comparison(["NVDA", "MSFT"], _mock_context())

        self.assertEqual(comparison["winner"], "NVDA")
        self.assertEqual(comparison["category_winners"]["total_score"], "NVDA")

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_profile_score_tiebreaker(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "AAA"}
        mock_get_earnings.return_value = {"ticker": "AAA"}

        context = _mock_context(
            screening_results=_screening_results(
                OBX=pd.DataFrame(
                    [
                        _screening_row(
                            "AAA.OL",
                            90,
                            "momentum",
                            momentum=95,
                            trend_regime="MODERAT OPPTREND",
                            relative_strength_20d=2.0,
                        ),
                        _screening_row(
                            "BBB.OL",
                            90,
                            "momentum",
                            momentum=70,
                            trend_regime="MODERAT OPPTREND",
                            relative_strength_20d=2.0,
                        ),
                    ]
                )
            )
        )

        comparison = build_comparison(["AAA.OL", "BBB.OL"], context)

        self.assertEqual(comparison["winner"], "AAA.OL")
        self.assertEqual(comparison["category_winners"]["profile_fit"], "AAA.OL")

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_no_clear_winner_when_even(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "AAA"}
        mock_get_earnings.return_value = {"ticker": "AAA"}

        context = _mock_context(
            screening_results=_screening_results(
                OBX=pd.DataFrame(
                    [
                        _screening_row(
                            "AAA.OL",
                            90,
                            "momentum",
                            momentum=80,
                            trend_regime="MODERAT OPPTREND",
                            relative_strength_20d=5.0,
                            fundamental_score=75,
                        ),
                        _screening_row(
                            "BBB.OL",
                            90,
                            "momentum",
                            momentum=80,
                            trend_regime="MODERAT OPPTREND",
                            relative_strength_20d=5.0,
                            fundamental_score=75,
                        ),
                    ]
                )
            )
        )

        comparison = build_comparison(["AAA.OL", "BBB.OL"], context)

        self.assertIsNone(comparison["winner"])
        self.assertIn("ingen klar vinner", comparison["winner_reason"].lower())
        answer = format_comparison_answer(comparison)
        self.assertIn("Det er ingen klar vinner.", answer)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_category_winners(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "SUBC.OL"}
        mock_get_earnings.return_value = {"ticker": "SUBC.OL"}

        comparison = build_comparison(["SUBC.OL", "AKRBP.OL"], _mock_context())

        winners = comparison["category_winners"]
        self.assertEqual(winners["total_score"], "SUBC.OL")
        self.assertEqual(winners["trend"], "SUBC.OL")
        self.assertEqual(winners["relative_strength"], "SUBC.OL")
        self.assertEqual(winners["fundamentals"], "AKRBP.OL")

    def test_missing_ticker_data(self):
        comparison = build_comparison(["UNKNOWN.OL", "SUBC.OL"], _mock_context())

        self.assertIn("UNKNOWN.OL", comparison["missing_tickers"])
        answer = format_comparison_answer(comparison)
        self.assertIn("Jeg finner ikke nok snapshot-data for UNKNOWN.OL", answer)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_missing_single_fields(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "SUBC.OL"}
        mock_get_earnings.return_value = {"ticker": "SUBC.OL"}

        context = _mock_context(
            screening_results=_screening_results(
                OBX=pd.DataFrame(
                    [
                        {
                            "ticker": "SUBC.OL",
                            "score": 90,
                            "trend_regime": "STERK OPPTREND",
                            "relative_strength_20d": 10.0,
                        },
                        {
                            "ticker": "AKRBP.OL",
                            "score": 85,
                            "trend_regime": "MODERAT OPPTREND",
                            "fundamental_score": 80,
                        },
                    ]
                )
            )
        )

        comparison = build_comparison(["SUBC.OL", "AKRBP.OL"], context)

        self.assertTrue(any("mangler" in caveat for caveat in comparison["caveats"]))

    def test_maximum_five_tickers(self):
        tickers, error = resolve_comparison_tickers(
            "Sammenlign NVDA og MSFT og AMD og SUBC.OL og AKRBP.OL og FRO.OL",
            _mock_context(),
        )

        self.assertIsNone(error)
        self.assertLessEqual(len(tickers), 5)
        self.assertEqual(len(tickers), len(set(tickers)))

    def test_dedupe_preserves_order(self):
        tickers = _dedupe_tickers_preserve_order(
            ["NVDA", "MSFT", "NVDA", "AMD", "MSFT"]
        )
        self.assertEqual(tickers, ["NVDA", "MSFT", "AMD"])


class ComparisonRoutingTests(unittest.TestCase):
    def test_routing_sammenlign(self):
        self.assertTrue(
            is_comparison_question(
                "Sammenlign SUBC.OL og AKRBP.OL",
                _mock_context(),
            )
        )

    def test_routing_best_av(self):
        self.assertTrue(
            is_comparison_question(
                "Hvilken er best av NVDA og MSFT?",
                _mock_context(),
            )
        )

    def test_routing_bedre_enn(self):
        self.assertTrue(
            is_comparison_question(
                "Hvorfor er SUBC.OL bedre enn AKRBP.OL?",
                _mock_context(),
            )
        )

    @patch("src.agent.screen_obx")
    @patch("src.agent.screen_us_large")
    @patch("src.agent.screen_nordics")
    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_top_three_norwegian_candidates_use_snapshot(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
        mock_screen_nordics,
        mock_screen_us,
        mock_screen_obx,
    ):
        mock_get_analyst.return_value = {"ticker": "SUBC.OL"}
        mock_get_earnings.return_value = {"ticker": "SUBC.OL"}

        answer = ask_agent(
            "Sammenlign de tre beste norske kandidatene",
            _mock_context(),
        )

        mock_screen_nordics.assert_not_called()
        mock_screen_us.assert_not_called()
        mock_screen_obx.assert_not_called()
        self.assertIn("Sammenligning:", answer)
        self.assertIn("SUBC.OL", answer)
        self.assertIn("AKRBP.OL", answer)
        self.assertIn("FRO.OL", answer)

    @patch("src.agent.screen_obx")
    @patch("src.agent.screen_us_large")
    @patch("src.agent.screen_nordics")
    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_top_three_momentum_candidates_use_snapshot(
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
            "Sammenlign topp 3 momentum-kandidater",
            _mock_context(),
        )

        mock_screen_nordics.assert_not_called()
        mock_screen_us.assert_not_called()
        mock_screen_obx.assert_not_called()
        self.assertIn("Sammenligning:", answer)
        self.assertIn("NVDA", answer)
        self.assertIn("AMD", answer)

    @patch("src.agent.screen_obx")
    @patch("src.agent.screen_us_large")
    @patch("src.agent.screen_nordics")
    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_agent_two_ticker_question(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
        mock_screen_nordics,
        mock_screen_us,
        mock_screen_obx,
    ):
        mock_get_analyst.return_value = {"ticker": "SUBC.OL"}
        mock_get_earnings.return_value = {"ticker": "SUBC.OL"}

        answer = ask_agent(
            "Sammenlign SUBC.OL og AKRBP.OL",
            _mock_context(),
        )

        mock_screen_obx.assert_not_called()
        self.assertIn("Sammenligning: SUBC.OL vs AKRBP.OL", answer)
        self.assertIn("Samlet vurdering:", answer)
        self.assertIn("SUBC.OL", answer.split("Samlet vurdering:")[-1])


class ComparisonRegressionTests(unittest.TestCase):
    def test_best_av_does_not_extract_v_from_av(self):
        tickers, error = resolve_comparison_tickers(
            "Hvilken er best av NVDA og MSFT?",
            _mock_context(),
        )

        self.assertIsNone(error)
        self.assertEqual(tickers, ["NVDA", "MSFT"])

    def test_explicit_single_letter_v_when_in_snapshot(self):
        context = _mock_context(
            screening_results=_screening_results(
                USA=pd.DataFrame(
                    [
                        _screening_row("V", 84, "value", value=80),
                        _screening_row("MA", 82, "quality", quality=78),
                    ]
                )
            )
        )

        tickers, error = resolve_comparison_tickers(
            "Sammenlign V og MA",
            context,
        )

        self.assertIsNone(error)
        self.assertEqual(tickers, ["V", "MA"])

    def test_duplicate_ticker_across_regions_is_deduped_in_top_list(self):
        context = _mock_context(
            screening_results=_screening_results(
                USA=pd.DataFrame(
                    [
                        _screening_row("ACN", 93, "value", value=91),
                        _screening_row("JPM", 90, "value", value=86),
                        _screening_row("WMT", 88, "value", value=84),
                    ]
                ),
                NORDEN=pd.DataFrame(
                    [
                        _screening_row("YAR.OL", 92, "value", value=90),
                        _screening_row("YAR.OL", 89, "value", value=70),
                    ]
                ),
                OBX=pd.DataFrame(
                    [
                        _screening_row("YAR.OL", 91, "value", value=88),
                    ]
                ),
            )
        )

        tickers, error = resolve_comparison_tickers(
            "Sammenlign topp 3 value-kandidater",
            context,
        )

        self.assertIsNone(error)
        self.assertEqual(len(tickers), 3)
        self.assertEqual(len(set(tickers)), 3)
        self.assertEqual(tickers.count("YAR.OL"), 1)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_equal_rounded_profile_scores_show_jevnt_and_no_narrative_claim(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "SUBC.OL"}
        mock_get_earnings.return_value = {"ticker": "SUBC.OL"}

        context = _mock_context(
            screening_results=_screening_results(
                OBX=pd.DataFrame(
                    [
                        _screening_row(
                            "SUBC.OL",
                            99,
                            "cyclical",
                            cyclical=89.6,
                            relative_strength_20d=13.3,
                            trend_regime="STERK OPPTREND",
                        ),
                        _screening_row(
                            "AKRBP.OL",
                            91,
                            "cyclical",
                            cyclical=90.4,
                            relative_strength_20d=6.1,
                            trend_regime="MODERAT OPPTREND",
                            fundamental_score=86,
                        ),
                    ]
                )
            )
        )

        comparison = build_comparison(["SUBC.OL", "AKRBP.OL"], context)
        answer = format_comparison_answer(comparison)

        self.assertEqual(
            comparison["rows"][0]["primary_profile_score_display"],
            90,
        )
        self.assertEqual(
            comparison["rows"][1]["primary_profile_score_display"],
            90,
        )
        self.assertIsNone(comparison["category_winners"]["profile_fit"])
        self.assertIn("Jevnt", answer)
        self.assertNotIn("bedre profilscore", answer.lower())

    @patch("src.agent.screen_obx")
    @patch("src.agent.screen_us_large")
    @patch("src.agent.screen_nordics")
    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_best_av_agent_question_only_nvda_and_msft(
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
            "Hvilken er best av NVDA og MSFT?",
            _mock_context(),
        )

        mock_screen_obx.assert_not_called()
        self.assertIn("Sammenligning: NVDA vs MSFT", answer)
        self.assertNotIn("V vs", answer)
        self.assertNotRegex(answer, r"\bV vs\b")
