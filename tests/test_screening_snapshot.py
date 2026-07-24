import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

import pandas as pd

from src.agent import ask_agent
from src.context import (
    build_screening_results,
    load_context_snapshot,
    save_context_snapshot,
)


def _screening_row(ticker, score=90):
    return {
        "ticker": ticker,
        "in_watchlist": "Nei",
        "score": score,
        "recommendation": "KJØP / ØK",
        "trend_regime": "STERK OPPTREND",
        "relative_strength_20d": 8.0,
        "fundamental_score": 75,
        "fundamental_history_score": 78,
    }


def _screening_results(**overrides):
    base = {
        "USA": pd.DataFrame([_screening_row("AAPL", 88)]),
        "NORDEN": pd.DataFrame([_screening_row("VOLV-B.ST", 86)]),
        "OBX": pd.DataFrame([_screening_row("SUBC.OL", 94)]),
        "meta": {
            "USA": {
                "universe_size": 1,
                "is_full_universe": True,
                "display_limit": 5,
                "use_snapshot_wording": False,
            },
            "NORDEN": {
                "universe_size": 1,
                "is_full_universe": True,
                "display_limit": 5,
                "use_snapshot_wording": False,
            },
            "OBX": {
                "universe_size": 1,
                "is_full_universe": True,
                "display_limit": 5,
                "use_snapshot_wording": False,
            },
        },
        "generated_at": "2026-06-18T08:00:00+00:00",
    }
    base.update(overrides)
    return base


def _mock_context(**overrides):
    context = {
        "watchlist": ["AAPL"],
        "watchlist_report": pd.DataFrame(
            [{"ticker": "AAPL", "score": 70, "anbefaling": "HOLD / OBSERVER"}]
        ),
        "portfolio_report": None,
        "dashboard": {},
        "daily_flow": {},
    }
    context.update(overrides)
    return context


class ScreeningSnapshotContextTests(unittest.TestCase):
    @patch("src.context.screen_obx")
    @patch("src.context.screen_nordics")
    @patch("src.context.screen_us_large")
    def test_build_screening_results_includes_all_regions(
        self,
        mock_screen_us,
        mock_screen_nordics,
        mock_screen_obx,
    ):
        mock_screen_us.return_value = pd.DataFrame([_screening_row("AAPL")])
        mock_screen_nordics.return_value = pd.DataFrame([_screening_row("VOLV-B.ST")])
        mock_screen_obx.return_value = pd.DataFrame([_screening_row("SUBC.OL")])

        results = build_screening_results(
            pause_seconds=0,
            existing_watchlists={"Alle": ["AAPL"]},
        )

        self.assertIn("generated_at", results)
        self.assertEqual(results["USA"].iloc[0]["ticker"], "AAPL")
        self.assertEqual(results["NORDEN"].iloc[0]["ticker"], "VOLV-B.ST")
        self.assertEqual(results["OBX"].iloc[0]["ticker"], "SUBC.OL")
        mock_screen_us.assert_called_once_with(
            preset="Beste kandidater",
            limit=None,
            pause_seconds=0,
            existing_watchlists={"Alle": ["AAPL"]},
        )
        self.assertTrue(results["meta"]["OBX"]["is_full_universe"])
        self.assertEqual(results["meta"]["OBX"]["display_limit"], 5)

    def test_context_snapshot_roundtrip_preserves_screening_results(self):
        with patch("src.context.context_snapshot_path") as mock_path:
            with tempfile.TemporaryDirectory() as tmpdir:
                snapshot_file = Path(tmpdir) / "context_snapshot_prod.json"
                mock_path.return_value = snapshot_file

                original = _mock_context(screening_results=_screening_results())
                save_context_snapshot(original)

                loaded = load_context_snapshot(check_max_age=False)

        self.assertIsNotNone(loaded)
        screening = loaded["screening_results"]
        self.assertEqual(screening["generated_at"], "2026-06-18T08:00:00+00:00")
        self.assertEqual(screening["OBX"].iloc[0]["ticker"], "SUBC.OL")
        self.assertEqual(screening["NORDEN"].iloc[0]["ticker"], "VOLV-B.ST")
        self.assertEqual(screening["USA"].iloc[0]["ticker"], "AAPL")
        self.assertTrue(screening["meta"]["NORDEN"]["is_full_universe"])


class AgentScreeningSnapshotTests(unittest.TestCase):
    @patch("src.agent.build_opportunity_advisor", return_value={"items": []})
    @patch("src.agent.screen_obx")
    def test_norske_kandidater_use_snapshot_without_live_screener(
        self,
        mock_screen_obx,
        _mock_advisor,
    ):
        context = _mock_context(screening_results=_screening_results())

        answer = ask_agent("Vis meg de beste norske kandidatene", context)

        mock_screen_obx.assert_not_called()
        self.assertIn("Topp 5 norske kandidater", answer)
        self.assertIn("SUBC.OL", answer)
        self.assertNotIn("Bruker live screening", answer)

    @patch("src.agent.build_opportunity_advisor", return_value={"items": []})
    @patch("src.agent.screen_nordics")
    def test_nordiske_kandidater_use_snapshot_without_live_screener(
        self,
        mock_screen_nordics,
        _mock_advisor,
    ):
        context = _mock_context(screening_results=_screening_results())

        answer = ask_agent("Vis meg de beste nordiske kandidatene", context)

        mock_screen_nordics.assert_not_called()
        self.assertIn("Topp 5 nordiske kandidater", answer)
        self.assertIn("VOLV-B.ST", answer)

    @patch("src.agent.build_opportunity_advisor", return_value={"items": []})
    @patch("src.agent.screen_us_large")
    def test_amerikanske_kandidater_use_snapshot_without_live_screener(
        self,
        mock_screen_us,
        _mock_advisor,
    ):
        context = _mock_context(screening_results=_screening_results())

        answer = ask_agent("Vis meg de beste amerikanske kandidatene", context)

        mock_screen_us.assert_not_called()
        self.assertIn("Topp 5 amerikanske kandidater", answer)
        self.assertIn("AAPL", answer)

    @patch("src.agent.build_opportunity_advisor", return_value={"items": []})
    @patch("src.agent.screen_obx")
    def test_missing_snapshot_falls_back_to_live_screener(
        self,
        mock_screen_obx,
        _mock_advisor,
    ):
        mock_screen_obx.return_value = pd.DataFrame([_screening_row("EQNR.OL")])

        answer = ask_agent("Vis meg de beste norske kandidatene", _mock_context())

        mock_screen_obx.assert_called_once_with(
            preset="Beste kandidater",
            limit=5,
            pause_seconds=0,
            existing_watchlists=ANY,
        )
        self.assertIn("Bruker live screening fordi snapshot mangler.", answer)
        self.assertIn("EQNR.OL", answer)

    @patch("src.agent.build_opportunity_advisor", return_value={"items": []})
    @patch("src.agent.screen_nordics")
    def test_empty_snapshot_falls_back_to_live_screener(
        self,
        mock_screen_nordics,
        _mock_advisor,
    ):
        mock_screen_nordics.return_value = pd.DataFrame([_screening_row("SUBC.OL")])

        context = _mock_context(
            screening_results=_screening_results(NORDEN=pd.DataFrame())
        )

        answer = ask_agent("Vis meg de beste nordiske kandidatene", context)

        mock_screen_nordics.assert_called_once()
        self.assertIn("Bruker live screening fordi snapshot mangler.", answer)


class ScreeningSnapshotRankingHonestyTests(unittest.TestCase):
    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_legacy_top5_snapshot_uses_honest_wording(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "T1"}
        mock_get_earnings.return_value = {"ticker": "T1"}

        top5 = pd.DataFrame(
            [_screening_row(f"T{i}", 95 - i) for i in range(5)]
        )
        context = _mock_context(
            screening_results={
                "OBX": top5,
                "generated_at": "2026-06-18T08:00:00+00:00",
            }
        )

        answer = ask_agent("Vis meg de beste OBX-kandidatene", context)

        self.assertIn(
            "#2 av 5 kvalifiserte kandidater i OBX-snapshot",
            answer,
        )
        self.assertNotIn("#2 av 25 i OBX", answer)
        self.assertNotIn("#2 av 5 i OBX", answer)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_full_snapshot_uses_full_universe_size(
        self,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "T1"}
        mock_get_earnings.return_value = {"ticker": "T1"}

        full = pd.DataFrame(
            [_screening_row(f"T{i}", 99 - i) for i in range(25)]
        )
        context = _mock_context(
            screening_results={
                "OBX": full,
                "meta": {
                    "OBX": {
                        "universe_size": 25,
                        "is_full_universe": True,
                        "display_limit": 5,
                        "use_snapshot_wording": False,
                    }
                },
                "generated_at": "2026-06-18T08:00:00+00:00",
            }
        )

        answer = ask_agent("Vis meg de beste OBX-kandidatene", context)

        self.assertIn("#2 av 25 i OBX", answer)
        self.assertNotIn("OBX-snapshot", answer)

    @patch("src.opportunity_advisor.get_news", return_value=[])
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    @patch("src.agent.screen_obx")
    def test_live_top5_screening_does_not_overclaim_universe_size(
        self,
        mock_screen_obx,
        mock_get_analyst,
        mock_get_earnings,
        _mock_get_news,
    ):
        mock_screen_obx.return_value = pd.DataFrame(
            [_screening_row(f"T{i}", 95 - i) for i in range(5)]
        )
        mock_get_analyst.return_value = {"ticker": "T1"}
        mock_get_earnings.return_value = {"ticker": "T1"}

        answer = ask_agent("Vis meg de beste OBX-kandidatene", _mock_context())

        mock_screen_obx.assert_called_once()
        self.assertIn("#2 av topp 5 i OBX", answer)
        self.assertNotIn("#2 av 25 i OBX", answer)
        self.assertNotIn("OBX-snapshot", answer)


if __name__ == "__main__":
    unittest.main()
