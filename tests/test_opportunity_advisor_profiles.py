import unittest
from unittest.mock import patch

from src.opportunity_advisor import build_opportunity_advisor_item
from tests.test_strategy_profiles import (
    _cyclical_stock,
    _nvda_momentum_like,
    _nvda_quality_like,
)


def _value_stock(**overrides):
    base = {
        "ticker": "JPM",
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
    base.update(overrides)
    return base


class ProfileClassificationTests(unittest.TestCase):
    def test_momentum_profile_gives_momentum_candidate(self):
        item = build_opportunity_advisor_item(_nvda_momentum_like())

        self.assertEqual(item["candidate_type"], "Momentum-kandidat")
        self.assertEqual(item["primary_profile"], "momentum")
        self.assertEqual(item["headline"], "Momentum-kandidat med sterk trend")
        self.assertIn("Primær profil: Momentum", item["why_interesting"])
        self.assertIn(
            "Sterk trend og positiv relativ styrke",
            item["why_interesting"],
        )
        self.assertIn("momentum-case", item["takeaway"])

    def test_quality_profile_gives_quality_candidate(self):
        item = build_opportunity_advisor_item(_nvda_quality_like())

        self.assertEqual(item["candidate_type"], "Kvalitetskandidat")
        self.assertEqual(item["primary_profile"], "quality")
        self.assertEqual(
            item["headline"],
            "Kvalitetskandidat med solid fundamentalprofil",
        )
        self.assertIn("Primær profil: Quality", item["why_interesting"])
        self.assertIn(
            "Sterk fundamental kvalitet eller historikk",
            item["why_interesting"],
        )
        self.assertIn("kvalitetskandidat", item["takeaway"])

    def test_value_profile_gives_value_candidate(self):
        item = build_opportunity_advisor_item(_value_stock())

        self.assertEqual(item["candidate_type"], "Value-kandidat")
        self.assertEqual(item["primary_profile"], "value")
        self.assertEqual(item["headline"], "Value-kandidat med attraktiv verdsettelse")
        self.assertIn("Primær profil: Value", item["why_interesting"])
        self.assertIn(
            "Attraktiv verdsettelse relativt til fundamentale nøkkeltall",
            item["why_interesting"],
        )
        self.assertIn("value-kandidat", item["takeaway"])

    def test_cyclical_profile_gives_syklisk_candidate(self):
        item = build_opportunity_advisor_item(_cyclical_stock())

        self.assertEqual(item["candidate_type"], "Syklisk kandidat")
        self.assertEqual(item["primary_profile"], "cyclical")
        self.assertEqual(
            item["headline"],
            "Syklisk kandidat – følg syklusen tett",
        )
        self.assertIn("Primær profil: Cyclical", item["why_interesting"])
        self.assertIn(
            "Syklisk aksje – timing og markedsfase er ekstra viktig",
            item["why_interesting"],
        )
        self.assertIn("syklisk kandidat", item["takeaway"])

    def test_profile_scores_present_in_output(self):
        item = build_opportunity_advisor_item(_nvda_momentum_like())

        self.assertIn("profile_scores", item)
        self.assertEqual(
            set(item["profile_scores"].keys()),
            {"momentum", "quality", "value", "cyclical"},
        )
        self.assertIsInstance(item["profile_scores"]["momentum"], int)

    def test_v1_output_fields_still_present(self):
        item = build_opportunity_advisor_item(_nvda_momentum_like())

        for field in (
            "ticker",
            "headline",
            "why_interesting",
            "watch_out_for",
            "takeaway",
            "priority",
        ):
            self.assertIn(field, item)

    def test_missing_profile_data_falls_back_without_crash(self):
        item = build_opportunity_advisor_item(
            {
                "ticker": "BROKEN",
                "score": 60,
                "trend_regime": "SVAK / NEGATIV TREND",
            }
        )

        self.assertEqual(item["ticker"], "BROKEN")
        self.assertIsInstance(item["headline"], str)
        self.assertTrue(item["headline"])
        self.assertIsInstance(item["why_interesting"], list)
        self.assertIsInstance(item["watch_out_for"], list)
        self.assertIn("priority", item)

    @patch("src.opportunity_advisor.build_strategy_profile", side_effect=RuntimeError("boom"))
    def test_strategy_profile_failure_falls_back(self, _mock_profile):
        item = build_opportunity_advisor_item(
            {
                "ticker": "FAIL",
                "score": 85,
                "trend_regime": "STERK OPPTREND",
                "relative_strength_20d": 12.0,
            }
        )

        self.assertEqual(item["headline"], "Screener-kandidat")
        self.assertNotIn("candidate_type", item)
        self.assertNotIn("primary_profile", item)
        self.assertNotIn("profile_scores", item)


if __name__ == "__main__":
    unittest.main()
