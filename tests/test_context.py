import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.context import (
    CONTEXT_SNAPSHOT_VERSION,
    get_context_snapshot_metadata,
    load_context_snapshot,
    load_or_build_agent_context,
    reload_context_from_snapshot,
    resolve_portfolio_report,
    save_context_snapshot,
)
from src.dashboard import _empty_portfolio_risk


def _portfolio_row(**overrides):
    base = {
        "ticker": "AAPL",
        "market_value": 2905.5,
        "unrealized_gain_pct": 62.32,
        "current_price": 290.55,
        "cost_value": 1790.0,
        "portefølje_råd": "HOLD",
        "anbefaling": "HOLD / OBSERVER",
        "trailing_stop_loss": 250.0,
    }
    base.update(overrides)
    return base


class ResolvePortfolioReportTests(unittest.TestCase):
    def test_updates_stale_portfolio_risk_when_report_is_valid(self):
        report = pd.DataFrame([_portfolio_row()])
        context = {
            "portfolio_report": report,
            "dashboard": {
                "portfolio_summary": {"positions": 0},
                "portfolio_risk": _empty_portfolio_risk(),
            },
        }
        portfolio = [{"ticker": "AAPL", "buy_price": 100, "shares": 10}]

        result = resolve_portfolio_report(context, portfolio)

        self.assertIs(result, report)
        self.assertTrue(context["dashboard"]["portfolio_risk"]["available"])
        self.assertEqual(context["dashboard"]["portfolio_risk"]["positions"], 1)
        self.assertEqual(
            context["dashboard"]["portfolio_summary"]["positions"],
            1,
        )
        self.assertEqual(
            context["dashboard"]["portfolio_risk"]["total_market_value"],
            context["dashboard"]["portfolio_summary"]["total_market_value"],
        )

    @patch("src.context.ensure_portfolio_report")
    def test_lazy_analyze_updates_portfolio_risk(self, mock_ensure):
        report = pd.DataFrame([_portfolio_row(ticker="MSFT", market_value=1500)])
        mock_ensure.return_value = report
        context = {
            "portfolio_report": None,
            "dashboard": {
                "portfolio_summary": {"positions": 0},
                "portfolio_risk": _empty_portfolio_risk(),
            },
        }
        portfolio = [{"ticker": "MSFT", "buy_price": 200, "shares": 5}]

        result = resolve_portfolio_report(context, portfolio)

        mock_ensure.assert_called_once_with(None, portfolio)
        self.assertIs(result, report)
        self.assertTrue(context["dashboard"]["portfolio_risk"]["available"])
        self.assertEqual(context["dashboard"]["portfolio_risk"]["positions"], 1)
        self.assertEqual(context["dashboard"]["portfolio_risk"]["top_position_pct"], 100.0)

    def test_empty_portfolio_leaves_context_unchanged(self):
        context = {
            "portfolio_report": None,
            "dashboard": {
                "portfolio_risk": _empty_portfolio_risk(),
            },
        }

        result = resolve_portfolio_report(context, [])

        self.assertIsNone(result)
        self.assertFalse(context["dashboard"]["portfolio_risk"]["available"])


def _sample_context():
    watchlist_report = pd.DataFrame([
        {
            "ticker": "AAPL",
            "score": 75,
            "anbefaling": "HOLD / OBSERVER",
            "begrunnelse": ["Kurs over SMA20"],
            "relative_strength_20d": 5.0,
            "fundamental_score": 60,
            "fundamental_history_score": 65,
            "trend_regime": "MODERAT OPPTREND",
        },
    ])
    return {
        "watchlist": ["AAPL"],
        "watchlist_report": watchlist_report,
        "portfolio_report": None,
        "dashboard": {
            "portfolio_summary": {"positions": 0},
            "portfolio_risk": _empty_portfolio_risk(),
            "weakening_positions": pd.DataFrame(),
            "changes_since_last_snapshot": {
                "recommendation_changed": pd.DataFrame(),
                "large_score_changes": pd.DataFrame(),
            },
        },
        "daily_flow": {
            "summary_bullets": ["Test"],
            "key_opportunities": {
                "new_buy_candidates": pd.DataFrame(),
            },
        },
        "earnings_summary": {"items": [], "last_updated": "2026-06-12T08:00:00+00:00"},
        "analyst_summary": {"items": [], "last_updated": "2026-06-12T08:00:00+00:00"},
        "news_summary": {"items": [], "last_updated": "2026-06-12T08:00:00+00:00"},
        "sentiment_summary": {"items": [], "last_updated": "2026-06-12T08:00:00+00:00"},
        "advisor_output": {"items": []},
        "advisor_details": {},
        "alerts": [],
        "daily_briefing": {
            "generated_at": "2026-06-12T08:00:00+00:00",
            "date": "2026-06-12",
            "headline": "Rolig dag – ingen kritiske hendelser.",
            "critical_items": [],
            "change_items": [],
            "important_items": [],
            "watchlist_items": [],
            "candidate_items": [],
            "summary": [],
        },
    }


class ContextSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.snapshot_path = Path(self.temp_dir.name) / "context_snapshot.json"
        self.path_patcher = patch(
            "src.context.context_snapshot_path",
            return_value=self.snapshot_path,
        )
        self.path_patcher.start()

    def tearDown(self):
        self.path_patcher.stop()
        self.temp_dir.cleanup()

    def test_save_and_load_fresh_snapshot(self):
        original = _sample_context()
        with patch(
            "src.context._utc_now_iso",
            return_value="2026-06-12T08:00:00+00:00",
        ):
            save_context_snapshot(original)

        loaded = load_context_snapshot(
            max_age_hours=24,
            now=datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(loaded)
        assert loaded is not None
        pd.testing.assert_frame_equal(
            loaded["watchlist_report"],
            original["watchlist_report"],
            check_dtype=False,
        )
        self.assertEqual(loaded["watchlist"], ["AAPL"])
        self.assertIsNone(loaded["portfolio_report"])
        self.assertEqual(loaded["daily_flow"]["summary_bullets"], ["Test"])
        self.assertEqual(
            loaded["daily_briefing"]["generated_at"],
            "2026-06-12T08:00:00+00:00",
        )
        self.assertEqual(loaded["daily_briefing"]["critical_items"], [])

    def test_old_snapshot_is_ignored(self):
        save_context_snapshot(_sample_context())
        with open(self.snapshot_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        payload["built_at"] = "2026-06-10T08:00:00+00:00"
        with open(self.snapshot_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        loaded = load_context_snapshot(
            max_age_hours=24,
            now=datetime(2026, 6, 12, 8, 0, tzinfo=timezone.utc),
        )

        self.assertIsNone(loaded)

    def test_corrupt_snapshot_is_ignored(self):
        self.snapshot_path.write_text("{not valid json", encoding="utf-8")
        self.assertIsNone(load_context_snapshot())

        self.snapshot_path.write_text(
            json.dumps({"version": CONTEXT_SNAPSHOT_VERSION, "built_at": "2026-06-12T08:00:00+00:00"}),
            encoding="utf-8",
        )
        self.assertIsNone(load_context_snapshot())

    def test_legacy_metadata_only_snapshot_is_ignored(self):
        self.snapshot_path.write_text(
            json.dumps({
                "date": "2026-06-12",
                "built_at": "2026-06-12T08:00:00+00:00",
                "watchlist_symbol_count": 4,
            }),
            encoding="utf-8",
        )

        self.assertIsNone(load_context_snapshot())

    def test_get_context_snapshot_metadata(self):
        with patch(
            "src.context._utc_now_iso",
            return_value="2026-06-12T08:00:00+00:00",
        ):
            save_context_snapshot(_sample_context(), today=date(2026, 6, 12))

        metadata = get_context_snapshot_metadata()

        self.assertIsNotNone(metadata)
        assert metadata is not None
        self.assertEqual(metadata["date"], "2026-06-12")
        self.assertEqual(metadata["built_at"], "2026-06-12T08:00:00+00:00")

    def test_reload_context_from_snapshot_without_reanalysis(self):
        original = _sample_context()
        with patch(
            "src.context._utc_now_iso",
            return_value="2026-06-12T08:00:00+00:00",
        ):
            save_context_snapshot(original)

        with patch("src.context.build_agent_context") as mock_build:
            result = reload_context_from_snapshot(
                now=datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc),
            )

        mock_build.assert_not_called()
        self.assertTrue(result["loaded"])
        self.assertFalse(result["expired"])
        self.assertEqual(result["context"]["watchlist"], ["AAPL"])

    def test_reload_context_from_snapshot_warns_when_expired(self):
        save_context_snapshot(_sample_context())
        with open(self.snapshot_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        payload["built_at"] = "2026-06-10T08:00:00+00:00"
        with open(self.snapshot_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        result = reload_context_from_snapshot(
            now=datetime(2026, 6, 12, 8, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(result["loaded"])
        self.assertTrue(result["expired"])
        self.assertEqual(result["context"]["watchlist"], ["AAPL"])

    def test_reload_context_from_snapshot_missing(self):
        result = reload_context_from_snapshot()

        self.assertFalse(result["loaded"])
        self.assertEqual(result["reason"], "missing")

    @patch("src.context.build_agent_context")
    def test_load_or_build_falls_back_when_snapshot_missing(self, mock_build):
        mock_build.return_value = _sample_context()

        result = load_or_build_agent_context(
            watchlist=["AAPL"],
            portfolio=[],
            pause_seconds=0,
        )

        mock_build.assert_called_once()
        self.assertEqual(result["watchlist"], ["AAPL"])

    @patch("src.context.build_agent_context")
    def test_load_or_build_uses_snapshot_when_available(self, mock_build):
        with patch(
            "src.context._utc_now_iso",
            return_value="2026-06-12T08:00:00+00:00",
        ):
            save_context_snapshot(_sample_context())

        result = load_or_build_agent_context(
            watchlist=["MSFT"],
            portfolio=[],
            pause_seconds=0,
            now=datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc),
        )

        mock_build.assert_not_called()
        self.assertEqual(result["watchlist"], ["AAPL"])


class BuildAgentContextDailyBriefingTests(unittest.TestCase):
    @patch("src.context.build_opportunity_advisor")
    @patch("src.context.combine_discovery_candidates")
    @patch("src.context.build_screening_results")
    @patch("src.context.build_watchlist_advisor", return_value={"items": []})
    @patch("src.context.build_daily_briefing")
    @patch("src.context.build_advisor_details", return_value={})
    @patch("src.context.build_advisor_output", return_value={"items": []})
    @patch("src.context.build_analyst_summary", return_value={})
    @patch("src.context.build_earnings_summary", return_value={})
    @patch("src.context.build_dashboard", return_value={})
    @patch("src.context.build_alerts", return_value=[])
    @patch("src.context.build_daily_flow", return_value={})
    @patch("src.context.build_sentiment_summary", return_value={"items": []})
    @patch("src.context.build_news_summary", return_value={"items": []})
    @patch("src.context.analyze_watchlist")
    def test_build_agent_context_includes_daily_briefing(
        self,
        mock_analyze_watchlist,
        _mock_news,
        _mock_sentiment,
        _mock_daily_flow,
        _mock_alerts,
        _mock_dashboard,
        _mock_earnings,
        _mock_analyst,
        _mock_advisor_output,
        _mock_advisor_details,
        mock_build_daily_briefing,
        _mock_watchlist_advisor,
        mock_build_screening_results,
        mock_combine_discovery_candidates,
        mock_build_opportunity_advisor,
    ):
        from src.context import build_agent_context

        mock_analyze_watchlist.return_value = pd.DataFrame()
        mock_build_screening_results.return_value = {
            "USA": pd.DataFrame(),
            "NORDEN": pd.DataFrame(),
            "OBX": pd.DataFrame(),
            "generated_at": "2026-06-12T08:00:00+00:00",
        }
        discovery_candidates = pd.DataFrame(
            [{"ticker": "UNKNOWN", "score": 90, "in_watchlist": False}]
        )
        mock_combine_discovery_candidates.return_value = discovery_candidates
        mock_build_opportunity_advisor.return_value = {
            "items": [{"ticker": "UNKNOWN", "priority": 1}],
        }
        mock_build_daily_briefing.return_value = {
            "generated_at": "2026-06-12T08:00:00+00:00",
            "date": "2026-06-12",
            "headline": "Rolig dag – ingen kritiske hendelser.",
            "critical_items": [],
            "important_items": [],
            "watchlist_items": [],
            "candidate_items": [],
            "summary": [],
        }

        context = build_agent_context(
            watchlist=["AAPL"],
            portfolio=[],
            pause_seconds=0,
        )

        mock_build_daily_briefing.assert_called_once()
        passed_context = mock_build_daily_briefing.call_args.args[0]
        self.assertIn("advisor_output", passed_context)
        self.assertIn("daily_flow", passed_context)
        self.assertIn("daily_briefing", context)
        self.assertIn("screening_results", context)
        self.assertIs(context["discovery_candidates"], discovery_candidates)
        self.assertEqual(
            context["opportunity_advisor"]["items"][0]["ticker"],
            "UNKNOWN",
        )
        self.assertTrue(
            any(
                item.get("ticker") == "UNKNOWN"
                and item.get("source") == "opportunity_advisor"
                for item in context["recommendations"]["actions"]
            )
        )
        mock_combine_discovery_candidates.assert_called_once()
        mock_build_opportunity_advisor.assert_called_once()
        self.assertEqual(
            context["screening_results"]["generated_at"],
            "2026-06-12T08:00:00+00:00",
        )
        self.assertEqual(
            context["daily_briefing"]["generated_at"],
            "2026-06-12T08:00:00+00:00",
        )


class AppStartupContextTests(unittest.TestCase):
    @patch("src.context.save_context_snapshot")
    @patch("src.context.build_agent_context")
    @patch("src.context.load_context_snapshot")
    def test_app_startup_uses_snapshot_when_available(
        self,
        mock_load_snapshot,
        mock_build_context,
        mock_save_snapshot,
    ):
        mock_load_snapshot.return_value = _sample_context()

        context = mock_load_snapshot()
        if context is None:
            context = mock_build_context()
            mock_save_snapshot(context)

        mock_build_context.assert_not_called()
        mock_save_snapshot.assert_not_called()
        self.assertEqual(context["watchlist"], ["AAPL"])

    @patch("src.context.save_context_snapshot")
    @patch("src.context.build_agent_context")
    @patch("src.context.load_context_snapshot")
    def test_app_startup_falls_back_and_saves_snapshot(
        self,
        mock_load_snapshot,
        mock_build_context,
        mock_save_snapshot,
    ):
        mock_load_snapshot.return_value = None
        mock_build_context.return_value = _sample_context()

        context = mock_load_snapshot()
        if context is None:
            context = mock_build_context()
            mock_save_snapshot(context)

        mock_build_context.assert_called_once()
        mock_save_snapshot.assert_called_once_with(context)


if __name__ == "__main__":
    unittest.main()
