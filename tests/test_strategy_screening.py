import unittest
from unittest.mock import patch

import pandas as pd

from src.agent import ask_agent


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
                _screening_row("NVDA", 95, "momentum", momentum=92, quality=60),
                _screening_row("JPM", 88, "value", value=85, momentum=40),
            ]
        ),
        "NORDEN": pd.DataFrame(
            [
                _screening_row("VOLV-B.ST", 90, "quality", quality=88, momentum=55),
            ]
        ),
        "OBX": pd.DataFrame(
            [
                _screening_row("FRO.OL", 98, "cyclical", cyclical=90, momentum=45),
                _screening_row("SUBC.OL", 99, "momentum", momentum=88, cyclical=40),
                _screening_row("AKRBP.OL", 91, "cyclical", cyclical=80, momentum=50),
            ]
        ),
        "meta": {
            "USA": {"universe_size": 2, "is_full_universe": True},
            "NORDEN": {"universe_size": 1, "is_full_universe": True},
            "OBX": {"universe_size": 3, "is_full_universe": True},
        },
        "generated_at": "2026-06-18T08:00:00+00:00",
    }
    base.update(overrides)
    return base


def _mock_context(**overrides):
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


class StrategyScreeningRoutingTests(unittest.TestCase):
    @patch("src.agent.screen_obx")
    @patch("src.agent.screen_us_large")
    @patch("src.agent.screen_nordics")
    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_momentum_question_uses_snapshot_without_live_screening(
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
            _mock_context(),
        )

        mock_screen_nordics.assert_not_called()
        mock_screen_us.assert_not_called()
        mock_screen_obx.assert_not_called()
        self.assertIn("Topp 5 momentum-kandidater", answer)
        self.assertIn("NVDA", answer)
        self.assertIn("Momentum: 92", answer)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_quality_question(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "VOLV-B.ST"}
        mock_get_earnings.return_value = {"ticker": "VOLV-B.ST"}

        answer = ask_agent(
            "Hvilke quality-kandidater har vi nå?",
            _mock_context(),
        )

        self.assertIn("Topp 5 quality-kandidater", answer)
        self.assertIn("VOLV-B.ST", answer)
        self.assertIn("Quality: 88", answer)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_value_question(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "JPM"}
        mock_get_earnings.return_value = {"ticker": "JPM"}

        answer = ask_agent(
            "Vis de sterkeste value-kandidatene",
            _mock_context(),
        )

        self.assertIn("Topp 5 value-kandidater", answer)
        self.assertIn("JPM", answer)
        self.assertIn("Value: 85", answer)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_cyclical_question(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "FRO.OL"}
        mock_get_earnings.return_value = {"ticker": "FRO.OL"}

        answer = ask_agent(
            "Vis meg de beste sykliske aksjene",
            _mock_context(),
        )

        self.assertIn("Topp 5 sykliske kandidater", answer)
        self.assertIn("1. FRO.OL", answer)
        self.assertIn("Cyclical: 90", answer)
        self.assertIn("2. AKRBP.OL", answer)
        self.assertIn("Cyclical: 80", answer)
        self.assertNotIn("SUBC.OL", answer.split("Kort kommentar")[0])

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_vekstaksjer_maps_to_momentum(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "NVDA"}
        mock_get_earnings.return_value = {"ticker": "NVDA"}

        answer = ask_agent(
            "Vis meg de beste vekstaksjene",
            _mock_context(),
        )

        self.assertIn("Topp 5 momentum-kandidater", answer)
        self.assertIn("NVDA", answer)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_shipping_maps_to_cyclical(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "FRO.OL"}
        mock_get_earnings.return_value = {"ticker": "FRO.OL"}

        answer = ask_agent(
            "Hva er de beste shipping-kandidatene akkurat nå?",
            _mock_context(),
        )

        self.assertIn("Topp 5 sykliske kandidater", answer)
        self.assertIn("FRO.OL", answer)

    def test_fallback_when_profile_data_missing(self):
        legacy_row = {
            "ticker": "AAA",
            "in_watchlist": "Nei",
            "score": 90,
            "recommendation": "KJØP / ØK",
            "trend_regime": "STERK OPPTREND",
            "relative_strength_20d": 8.0,
            "fundamental_score": 75,
            "fundamental_history_score": 78,
        }
        context = _mock_context(
            screening_results={
                "USA": pd.DataFrame([legacy_row]),
                "NORDEN": pd.DataFrame(),
                "OBX": pd.DataFrame(),
                "generated_at": "2026-06-18T08:00:00+00:00",
            }
        )

        answer = ask_agent("Vis meg de beste momentum-aksjene", context)

        self.assertIn(
            "Strategy-profiler er ikke tilgjengelige i snapshot. Kjør Oppdater analyser.",
            answer,
        )

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_sorting_uses_profile_score_then_total_score(
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
                            "LOW-MOM",
                            99,
                            "momentum",
                            momentum=70,
                        ),
                        _screening_row(
                            "HIGH-MOM",
                            90,
                            "momentum",
                            momentum=95,
                        ),
                    ]
                )
            )
        )

        answer = ask_agent("Vis meg de beste momentum-aksjene", context)

        self.assertLess(
            answer.index("HIGH-MOM"),
            answer.index("LOW-MOM"),
        )

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_advisor_section_includes_headline_and_takeaway_for_top3(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "FRO.OL"}
        mock_get_earnings.return_value = {"ticker": "FRO.OL"}

        answer = ask_agent(
            "Vis meg de beste sykliske aksjene",
            _mock_context(),
        )

        advisor_section = answer.split("Kort kommentar fra Opportunity Advisor", 1)[1]
        self.assertIn("FRO.OL", advisor_section)
        self.assertIn("Syklisk kandidat", advisor_section)


if __name__ == "__main__":
    unittest.main()
