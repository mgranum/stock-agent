import unittest
from unittest.mock import patch

import pandas as pd

from src.agent import ask_agent
from src.opportunity_advisor import (
    build_opportunity_advisor,
    format_relative_context_short,
)
from tests.test_strategy_profiles import _nvda_momentum_like, _nvda_quality_like


def _screen_row(ticker, score, **overrides):
    row = {
        "ticker": ticker,
        "in_watchlist": "Nei",
        "score": score,
        "recommendation": "KJØP / ØK",
        "trend_regime": "STERK OPPTREND",
        "relative_strength_20d": 12.0,
        "fundamental_score": 78,
        "fundamental_history_score": 80,
    }
    row.update(overrides)
    return row


def _value_row(ticker, score, **overrides):
    row = {
        "ticker": ticker,
        "in_watchlist": "Nei",
        "score": score,
        "recommendation": "KJØP / ØK",
        "trend_regime": "MODERAT OPPTREND",
        "trend_points": 25,
        "momentum_points": 18,
        "relative_strength_points": 8,
        "relative_strength_20d": 4.0,
        "fundamental_score": 72,
        "fundamental_history_score": 74,
        "price_to_book": 1.2,
        "return_on_equity": 0.22,
        "debt_to_equity": 40,
        "profit_margin": 0.18,
        "trailing_pe": 10,
    }
    row.update(overrides)
    return row


class RelativeRankingTests(unittest.TestCase):
    def test_rank_and_universe_size_from_full_results(self):
        full_results = pd.DataFrame(
            [
                _screen_row("AAA", 95),
                _screen_row("BBB", 90),
                _screen_row("CCC", 85),
            ]
        )

        output = build_opportunity_advisor(
            full_results.head(2),
            limit=2,
            universe_name="OBX",
            full_results=full_results,
            is_full_universe=True,
        )

        second = next(item for item in output["items"] if item["ticker"] == "BBB")
        self.assertEqual(second["rank"], 2)
        self.assertEqual(second["universe_size"], 3)
        self.assertIn("#2 av 3 i OBX", second["relative_context"])

    def test_partial_snapshot_wording(self):
        top5 = pd.DataFrame(
            [
                _screen_row("AAA", 95),
                _screen_row("BBB", 90),
                _screen_row("CCC", 85),
                _screen_row("DDD", 80),
                _screen_row("EEE", 75),
            ]
        )

        output = build_opportunity_advisor(
            top5.head(2),
            limit=2,
            universe_name="OBX",
            full_results=top5,
            is_full_universe=False,
            use_snapshot_wording=True,
        )

        second = next(item for item in output["items"] if item["ticker"] == "BBB")
        self.assertEqual(second["rank"], 2)
        self.assertEqual(second["universe_size"], 5)
        self.assertIn("#2 av topp 5 i OBX-snapshot", second["relative_context"])
        self.assertNotIn("#2 av 5 i OBX", second["relative_context"])

    def test_profile_rank_for_best_momentum_candidate(self):
        full_results = pd.DataFrame(
            [
                _nvda_quality_like(ticker="QUAL", score=90),
                _nvda_momentum_like(ticker="MOM1", score=88),
                _nvda_momentum_like(ticker="MOM2", score=84),
            ]
        )

        output = build_opportunity_advisor(
            full_results,
            limit=3,
            universe_name="OBX",
            full_results=full_results,
        )

        mom1 = next(item for item in output["items"] if item["ticker"] == "MOM1")
        mom2 = next(item for item in output["items"] if item["ticker"] == "MOM2")

        self.assertEqual(mom1["profile_rank"], 1)
        self.assertEqual(mom2["profile_rank"], 2)
        self.assertIn(
            "Beste Momentum-kandidat i OBX",
            mom1["relative_context"],
        )
        self.assertNotIn(
            "Beste Momentum-kandidat i OBX",
            mom2["relative_context"],
        )

    def test_top_three_value_candidate_context(self):
        full_results = pd.DataFrame(
            [
                _value_row("VAL1", 95),
                _value_row("VAL2", 92),
                _value_row("VAL3", 90),
                _value_row("VAL4", 88),
            ]
        )

        output = build_opportunity_advisor(
            full_results.head(3),
            limit=3,
            universe_name="USA",
            full_results=full_results,
        )

        third = next(item for item in output["items"] if item["ticker"] == "VAL3")
        fourth = build_opportunity_advisor(
            full_results.iloc[[3]],
            limit=1,
            universe_name="USA",
            full_results=full_results,
        )["items"][0]

        self.assertEqual(third["profile_rank"], 3)
        self.assertIn("Topp 3 Value-kandidat i USA", third["relative_context"])
        self.assertEqual(fourth["profile_rank"], 4)
        self.assertNotIn("Topp 3 Value-kandidat i USA", fourth["relative_context"])

    def test_relative_context_enriches_why_and_takeaway(self):
        full_results = pd.DataFrame(
            [
                _nvda_momentum_like(ticker="LEAD", score=95),
                _nvda_momentum_like(ticker="RUNR", score=90),
            ]
        )

        output = build_opportunity_advisor(
            full_results.iloc[[1]],
            limit=1,
            universe_name="OBX",
            full_results=full_results,
        )
        item = output["items"][0]

        self.assertIn(
            "Topp 3 Momentum-kandidat i OBX",
            item["why_interesting"],
        )
        self.assertIn(
            "Dette er ikke bare en sterk kandidat isolert sett; "
            "den er også #2 av 2 i OBX.",
            item["takeaway"],
        )

    def test_without_universe_name_omits_relative_fields(self):
        output = build_opportunity_advisor(
            pd.DataFrame([_screen_row("AAA", 95)]),
            limit=1,
        )
        item = output["items"][0]

        self.assertNotIn("rank", item)
        self.assertNotIn("relative_context", item)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings", return_value={"ticker": "AAA"})
    @patch("src.opportunity_advisor.get_analyst", return_value={"ticker": "AAA"})
    def test_format_relative_context_short_handles_missing_context(
        self,
        _mock_analyst,
        _mock_earnings,
        _mock_news,
    ):
        self.assertEqual(format_relative_context_short(None), "")
        self.assertEqual(format_relative_context_short([]), "")

        output = build_opportunity_advisor(pd.DataFrame([_screen_row("AAA", 95)]))
        item = output["items"][0]
        self.assertEqual(format_relative_context_short(item.get("relative_context")), "")


class AgentRelativeContextTests(unittest.TestCase):
    @patch("src.agent.build_opportunity_advisor")
    @patch("src.agent.screen_obx")
    def test_screening_chat_includes_relative_context_for_top3(
        self,
        mock_screen_obx,
        mock_build_advisor,
    ):
        mock_screen_obx.return_value = pd.DataFrame(
            [
                _screen_row("AAA", 95),
                _screen_row("BBB", 90),
                _screen_row("CCC", 85),
                _screen_row("DDD", 80),
            ]
        )
        mock_build_advisor.return_value = {
            "items": [
                {
                    "ticker": ticker,
                    "why_interesting": ["Sterk score"],
                    "watch_out_for": [],
                    "takeaway": f"Tolkning for {ticker}.",
                    "relative_context": [
                        f"#{index + 1} av 4 i OBX",
                        "Beste Momentum-kandidat i OBX",
                    ],
                }
                for index, ticker in enumerate(["AAA", "BBB", "CCC", "DDD"])
            ]
        }

        answer = ask_agent(
            "Vis meg de beste OBX-kandidatene",
            {
                "watchlist": [],
                "watchlist_report": pd.DataFrame(),
                "portfolio_report": None,
                "dashboard": {},
                "daily_flow": {},
            },
        )

        advisor_section = answer.split("Kort kommentar fra Opportunity Advisor", 1)[1]
        self.assertIn("Relativ kontekst: #1 av 4 i OBX", advisor_section)
        self.assertIn("Relativ kontekst: #3 av 4 i OBX", advisor_section)
        self.assertNotIn("Relativ kontekst: #4 av 4 i OBX", advisor_section)

        mock_build_advisor.assert_called_once()
        self.assertEqual(mock_build_advisor.call_args.kwargs["universe_name"], "OBX")


if __name__ == "__main__":
    unittest.main()
