import io
import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.analyst import SOURCE_YFINANCE, _write_analyst_cache, get_analyst
from src.daily_refresh import (
    acquire_refresh_lock,
    build_refresh_summary,
    execute_daily_refresh,
    format_refresh_panel_status,
    load_refresh_state,
    main,
    parse_args,
    refresh_lock_path,
    refresh_state_path,
    release_refresh_lock,
    run_daily_refresh,
    save_refresh_state,
    should_run_refresh,
    wait_for_network_ready,
)
from src.daily_refresh import _refresh_analyst, _refresh_earnings
from src.earnings import (
    STATUS_CONFIRMED,
    STATUS_UNKNOWN,
    _write_earnings_cache,
    get_earnings,
)


def _success_result(**overrides):
    base = {
        "success": True,
        "started_at": "2026-06-12T08:00:00+00:00",
        "finished_at": "2026-06-12T08:05:00+00:00",
        "duration_seconds": 300.0,
        "symbols_processed": 4,
        "portfolio_positions": 2,
        "watchlist_symbols": 4,
        "earnings_updated": True,
        "analyst_updated": True,
        "news_updated": True,
        "sentiment_updated": True,
        "screening_updated": True,
        "snapshot_updated": True,
        "errors": [],
    }
    base.update(overrides)
    return base


class BuildRefreshSummaryTests(unittest.TestCase):
    def test_builds_expected_summary(self):
        summary = build_refresh_summary(_success_result())

        self.assertIn("Daily Refresh Fullført", summary)
        self.assertIn("- 4 symboler analysert", summary)
        self.assertIn("- 2 porteføljeposisjoner", summary)
        self.assertIn("- Earnings oppdatert", summary)
        self.assertIn("- Analyst consensus oppdatert", summary)
        self.assertIn("- News oppdatert", summary)
        self.assertIn("- Screening oppdatert", summary)

    def test_includes_error_count(self):
        summary = build_refresh_summary(
            _success_result(
                success=False,
                errors=[{"symbol": "BAD", "step": "news", "error": "fail"}],
            )
        )

        self.assertIn("- 1 feil under oppdatering", summary)


class RunDailyRefreshTests(unittest.TestCase):
    @patch("src.daily_refresh.save_context_snapshot")
    @patch("src.daily_refresh.save_model_snapshot")
    @patch("src.daily_refresh.build_agent_context")
    @patch("src.daily_refresh.build_sentiment_summary")
    @patch("src.daily_refresh.build_news_summary", return_value={"items": [], "last_updated": "2026-06-12T08:00:00+00:00"})
    @patch("src.daily_refresh.get_news")
    @patch("src.daily_refresh.get_analyst")
    @patch("src.daily_refresh.get_earnings")
    @patch("src.daily_refresh.analyze_fundamental_history")
    @patch("src.daily_refresh.get_fundamentals")
    @patch("src.daily_refresh.analyze_technicals")
    @patch("src.daily_refresh.get_benchmark_for_symbol", return_value="^GSPC")
    @patch("src.daily_refresh.add_indicators", side_effect=lambda df: df)
    @patch("src.daily_refresh.get_daily_prices")
    @patch("src.daily_refresh.load_research_ideas", return_value=[])
    @patch("src.daily_refresh.load_portfolio")
    @patch("src.daily_refresh.load_watchlists")
    def test_runs_without_exception(
        self,
        mock_load_watchlists,
        mock_load_portfolio,
        _mock_research,
        _mock_prices,
        _mock_indicators,
        _mock_benchmark,
        _mock_technicals,
        _mock_fundamentals,
        _mock_history,
        _mock_earnings,
        _mock_analyst,
        mock_get_news,
        _mock_build_news_summary,
        _mock_sentiment,
        mock_build_context,
        _mock_save_snapshot,
        _mock_save_context,
    ):
        mock_load_watchlists.return_value = {
            "Alle": ["AAPL", "MSFT"],
            "USA": ["AAPL", "MSFT"],
        }
        mock_load_portfolio.return_value = [
            {"ticker": "AAPL", "buy_price": 100, "shares": 10},
        ]
        mock_get_news.return_value = []
        mock_build_context.return_value = {
            "watchlist": ["AAPL", "MSFT"],
            "dashboard": {"portfolio_summary": {"positions": 1}},
            "screening_results": {"USA": pd.DataFrame(), "NORDEN": pd.DataFrame(), "OBX": pd.DataFrame()},
        }

        result = run_daily_refresh(pause_seconds=0, today=date(2026, 6, 12))

        self.assertTrue(result["success"])
        self.assertEqual(result["symbols_processed"], 2)
        self.assertEqual(result["portfolio_positions"], 1)
        self.assertEqual(result["watchlist_symbols"], 2)
        self.assertIn("started_at", result)
        self.assertIn("finished_at", result)
        self.assertIsInstance(result["duration_seconds"], float)
        mock_build_context.assert_called_once()

    @patch("src.daily_refresh.save_context_snapshot")
    @patch("src.daily_refresh.save_model_snapshot")
    @patch("src.daily_refresh.build_agent_context")
    @patch("src.daily_refresh.build_sentiment_summary")
    @patch("src.daily_refresh.build_news_summary", return_value={"items": [], "last_updated": "2026-06-12T08:00:00+00:00"})
    @patch("src.daily_refresh.get_news")
    @patch("src.daily_refresh.get_analyst")
    @patch("src.daily_refresh.get_earnings")
    @patch("src.daily_refresh.analyze_fundamental_history")
    @patch("src.daily_refresh.get_fundamentals")
    @patch("src.daily_refresh.analyze_technicals")
    @patch("src.daily_refresh.get_benchmark_for_symbol", return_value="^GSPC")
    @patch("src.daily_refresh.add_indicators", side_effect=lambda df: df)
    @patch("src.daily_refresh.get_daily_prices")
    @patch("src.daily_refresh.load_research_ideas", return_value=[])
    @patch("src.daily_refresh.load_portfolio")
    @patch("src.daily_refresh.load_watchlists")
    def test_one_ticker_error_does_not_stop_refresh(
        self,
        mock_load_watchlists,
        mock_load_portfolio,
        _mock_research,
        mock_get_prices,
        _mock_indicators,
        _mock_benchmark,
        _mock_technicals,
        mock_get_fundamentals,
        _mock_history,
        _mock_earnings,
        _mock_analyst,
        mock_get_news,
        _mock_build_news_summary,
        _mock_sentiment,
        mock_build_context,
        _mock_save_snapshot,
        _mock_save_context,
    ):
        mock_load_watchlists.return_value = {
            "Alle": ["AAPL", "BAD"],
            "USA": ["AAPL", "BAD"],
        }
        mock_load_portfolio.return_value = []
        mock_get_fundamentals.side_effect = [
            {"symbol": "AAPL"},
            RuntimeError("fundamentals failed"),
        ]
        mock_get_prices.return_value = pd.DataFrame(
            {"close": [100.0], "rsi": [50.0], "sma20": [99.0], "sma50": [98.0],
             "macd": [1.0], "macd_signal": [0.5], "volume": [1000.0],
             "volume_avg20": [900.0]},
            index=pd.to_datetime(["2026-06-12"]),
        )
        mock_get_news.return_value = []
        mock_build_context.return_value = {
            "watchlist": ["AAPL", "BAD"],
            "dashboard": {"portfolio_summary": {"positions": 0}},
            "screening_results": {"USA": pd.DataFrame(), "NORDEN": pd.DataFrame(), "OBX": pd.DataFrame()},
        }

        result = run_daily_refresh(pause_seconds=0, today=date(2026, 6, 12))

        self.assertFalse(result["success"])
        self.assertEqual(result["symbols_processed"], 2)
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["symbol"], "BAD")
        self.assertEqual(result["errors"][0]["step"], "fundamentals")
        mock_build_context.assert_called_once()

    @patch("src.daily_refresh.save_context_snapshot")
    @patch("src.daily_refresh.save_model_snapshot")
    @patch("src.daily_refresh.build_agent_context")
    @patch("src.daily_refresh.build_sentiment_summary")
    @patch("src.daily_refresh.build_news_summary", return_value={"items": [], "last_updated": "2026-06-12T08:00:00+00:00"})
    @patch("src.daily_refresh.get_news", return_value=[])
    @patch("src.daily_refresh.get_analyst")
    @patch("src.daily_refresh.get_earnings")
    @patch("src.daily_refresh.analyze_fundamental_history")
    @patch("src.daily_refresh.get_fundamentals")
    @patch("src.daily_refresh.analyze_technicals")
    @patch("src.daily_refresh.get_benchmark_for_symbol", return_value="^GSPC")
    @patch("src.daily_refresh.add_indicators", side_effect=lambda df: df)
    @patch("src.daily_refresh.get_daily_prices")
    @patch("src.daily_refresh.load_research_ideas", return_value=[])
    @patch("src.daily_refresh.load_portfolio", return_value=[])
    @patch("src.daily_refresh.load_watchlists")
    def test_empty_portfolio_handled(
        self,
        mock_load_watchlists,
        mock_load_portfolio,
        _mock_research,
        _mock_prices,
        _mock_indicators,
        _mock_benchmark,
        _mock_technicals,
        _mock_fundamentals,
        _mock_history,
        _mock_earnings,
        _mock_analyst,
        _mock_news,
        _mock_build_news_summary,
        _mock_sentiment,
        mock_build_context,
        _mock_save_snapshot,
        _mock_save_context,
    ):
        mock_load_watchlists.return_value = {
            "Alle": ["AAPL"],
            "USA": ["AAPL"],
        }
        mock_build_context.return_value = {
            "watchlist": ["AAPL"],
            "dashboard": {"portfolio_summary": {"positions": 0}},
            "screening_results": {"USA": pd.DataFrame(), "NORDEN": pd.DataFrame(), "OBX": pd.DataFrame()},
        }

        result = run_daily_refresh(pause_seconds=0, today=date(2026, 6, 12))

        self.assertTrue(result["success"])
        self.assertEqual(result["portfolio_positions"], 0)
        mock_load_portfolio.assert_called_once()
        mock_build_context.assert_called_once_with(
            ["AAPL"],
            portfolio=[],
            research_ideas=[],
            pause_seconds=0,
        )


class DailyRefreshMainTests(unittest.TestCase):
    @patch("src.daily_refresh.execute_daily_refresh")
    def test_main_runs_refresh_and_prints_summary(self, mock_execute):
        mock_execute.return_value = _success_result(symbols_processed=21, portfolio_positions=5)

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        mock_execute.assert_called_once_with(force=False, dry_run=False)
        output = buffer.getvalue()
        self.assertIn("Daily Refresh Fullført", output)
        self.assertIn("- 21 symboler analysert", output)
        self.assertIn("- 5 porteføljeposisjoner", output)
        self.assertIn("- Dashboard/context snapshot oppdatert", output)

    @patch("src.daily_refresh.execute_daily_refresh")
    def test_main_returns_non_zero_exit_code_on_failure(self, mock_execute):
        mock_execute.return_value = _success_result(
            success=False,
            errors=[{
                "symbol": "BAD",
                "step": "fundamentals",
                "error": "fundamentals failed",
            }],
        )

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main([])

        self.assertEqual(exit_code, 1)
        output = buffer.getvalue()
        self.assertIn("- 1 feil under oppdatering", output)
        self.assertIn("Feil:", output)
        self.assertIn("BAD (fundamentals): fundamentals failed", output)


class RefreshStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)
        self.state_path = self.cache_dir / "daily_refresh_state.json"
        self.lock_path = self.cache_dir / "daily_refresh.lock"
        self.state_patcher = patch(
            "src.daily_refresh.refresh_state_path",
            return_value=self.state_path,
        )
        self.lock_patcher = patch(
            "src.daily_refresh.refresh_lock_path",
            return_value=self.lock_path,
        )
        self.state_patcher.start()
        self.lock_patcher.start()
        release_refresh_lock()
        self.network_patcher = patch(
            "src.daily_refresh.wait_for_network_ready",
            return_value=(True, None),
        )
        self.network_patcher.start()

    def tearDown(self):
        self.network_patcher.stop()
        release_refresh_lock()
        self.state_patcher.stop()
        self.lock_patcher.stop()
        self.temp_dir.cleanup()

    def test_should_run_refresh_skips_when_today_is_successful(self):
        save_refresh_state({
            "last_successful_date": "2026-06-14",
            "last_started_at": "2026-06-14T04:00:00+00:00",
            "last_finished_at": "2026-06-14T04:10:00+00:00",
            "last_status": "success",
            "last_error_count": 0,
            "duration_seconds": 600.0,
        })

        self.assertFalse(
            should_run_refresh(today=date(2026, 6, 14), force=False)
        )

    def test_force_overrides_skip(self):
        save_refresh_state({
            "last_successful_date": "2026-06-14",
            "last_started_at": "2026-06-14T04:00:00+00:00",
            "last_finished_at": "2026-06-14T04:10:00+00:00",
            "last_status": "success",
            "last_error_count": 0,
            "duration_seconds": 600.0,
        })

        self.assertTrue(
            should_run_refresh(today=date(2026, 6, 14), force=True)
        )

    def test_lock_prevents_double_run(self):
        self.assertTrue(acquire_refresh_lock())
        self.assertFalse(acquire_refresh_lock())
        release_refresh_lock()
        self.assertTrue(acquire_refresh_lock())
        release_refresh_lock()

    @patch("src.daily_refresh.run_daily_refresh")
    def test_state_updated_on_success(self, mock_run):
        mock_run.return_value = _success_result(
            started_at="2026-06-14T04:00:00+00:00",
            finished_at="2026-06-14T04:05:00+00:00",
            duration_seconds=300.0,
        )

        result = execute_daily_refresh(today=date(2026, 6, 14))

        self.assertTrue(result["success"])
        state = load_refresh_state()
        assert state is not None
        self.assertEqual(state["last_successful_date"], "2026-06-14")
        self.assertEqual(state["last_status"], "success")
        self.assertEqual(state["last_error_count"], 0)
        self.assertEqual(state["duration_seconds"], 300.0)

    @patch("src.daily_refresh.run_daily_refresh")
    def test_state_updated_on_failure(self, mock_run):
        mock_run.return_value = _success_result(
            success=False,
            started_at="2026-06-14T04:00:00+00:00",
            finished_at="2026-06-14T04:05:00+00:00",
            duration_seconds=300.0,
            errors=[{"symbol": "BAD", "step": "news", "error": "fail"}],
        )

        result = execute_daily_refresh(today=date(2026, 6, 14))

        self.assertFalse(result["success"])
        state = load_refresh_state()
        assert state is not None
        self.assertIsNone(state["last_successful_date"])
        self.assertEqual(state["last_status"], "failed")
        self.assertEqual(state["last_error_count"], 1)

    @patch("src.daily_refresh.run_daily_refresh")
    def test_execute_skips_when_already_completed(self, mock_run):
        save_refresh_state({
            "last_successful_date": "2026-06-14",
            "last_started_at": "2026-06-14T04:00:00+00:00",
            "last_finished_at": "2026-06-14T04:10:00+00:00",
            "last_status": "success",
            "last_error_count": 0,
            "duration_seconds": 600.0,
        })

        result = execute_daily_refresh(today=date(2026, 6, 14))

        mock_run.assert_not_called()
        self.assertTrue(result["skipped"])
        state = load_refresh_state()
        assert state is not None
        self.assertEqual(state["last_status"], "skipped")

    @patch("src.daily_refresh.run_daily_refresh")
    def test_force_runs_even_when_already_completed(self, mock_run):
        save_refresh_state({
            "last_successful_date": "2026-06-14",
            "last_started_at": "2026-06-14T04:00:00+00:00",
            "last_finished_at": "2026-06-14T04:10:00+00:00",
            "last_status": "success",
            "last_error_count": 0,
            "duration_seconds": 600.0,
        })
        mock_run.return_value = _success_result(
            started_at="2026-06-14T05:00:00+00:00",
            finished_at="2026-06-14T05:05:00+00:00",
        )

        execute_daily_refresh(today=date(2026, 6, 14), force=True)

        mock_run.assert_called_once()

    @patch("src.daily_refresh.check_network_ready", return_value=(True, None))
    @patch("src.daily_refresh.run_daily_refresh")
    def test_dry_run_does_not_execute_refresh(self, mock_run, _mock_network):
        result = execute_daily_refresh(dry_run=True, today=date(2026, 6, 14))

        mock_run.assert_not_called()
        self.assertTrue(result["dry_run"])
        self.assertIn("dry-run", result["message"])
        self.assertTrue(result["network_ready"])
        self.assertIsNone(result["network_error"])

    def test_parse_args_supports_force_and_dry_run(self):
        args = parse_args(["--force", "--dry-run"])
        self.assertTrue(args.force)
        self.assertTrue(args.dry_run)


class FormatRefreshPanelStatusTests(unittest.TestCase):
    def test_formats_ok(self):
        status = format_refresh_panel_status(
            refresh_state={
                "last_successful_date": "2026-06-14",
                "last_finished_at": "2026-06-14T04:12:00+00:00",
                "last_status": "success",
            },
            snapshot_metadata=None,
            today=date(2026, 6, 14),
        )

        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["status_label"], "OK")
        self.assertNotEqual(status["updated_at"], "–")

    def test_formats_failed(self):
        status = format_refresh_panel_status(
            refresh_state={
                "last_successful_date": "2026-06-13",
                "last_finished_at": "2026-06-14T04:12:00+00:00",
                "last_status": "failed",
            },
            today=date(2026, 6, 14),
        )

        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["status_label"], "Feilet")

    def test_formats_stale(self):
        status = format_refresh_panel_status(
            refresh_state={
                "last_successful_date": "2026-06-13",
                "last_finished_at": "2026-06-13T04:12:00+00:00",
                "last_status": "success",
            },
            today=date(2026, 6, 14),
        )

        self.assertEqual(status["status"], "stale")
        self.assertEqual(status["status_label"], "Ikke oppdatert i dag")

    def test_formats_skipped_network(self):
        status = format_refresh_panel_status(
            refresh_state={
                "last_successful_date": "2026-06-13",
                "last_finished_at": "2026-06-14T04:12:00+00:00",
                "last_status": "skipped_network",
                "last_error_count": 1,
            },
            today=date(2026, 6, 14),
        )

        self.assertEqual(status["status"], "skipped_network")
        self.assertEqual(
            status["status_label"],
            "Nettverksfeil – bruker siste vellykkede data",
        )

    @patch("src.daily_refresh.get_context_snapshot_metadata", return_value=None)
    @patch("src.daily_refresh.load_refresh_state", return_value=None)
    def test_formats_unknown_without_state_or_snapshot(
        self,
        _mock_load_state,
        _mock_snapshot_metadata,
    ):
        status = format_refresh_panel_status(today=date(2026, 6, 14))

        self.assertEqual(status["status"], "unknown")
        self.assertEqual(status["status_label"], "Ukjent")
        self.assertEqual(status["updated_at"], "–")


class NetworkPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)
        self.state_path = self.cache_dir / "daily_refresh_state.json"
        self.lock_path = self.cache_dir / "daily_refresh.lock"
        self.state_patcher = patch(
            "src.daily_refresh.refresh_state_path",
            return_value=self.state_path,
        )
        self.lock_patcher = patch(
            "src.daily_refresh.refresh_lock_path",
            return_value=self.lock_path,
        )
        self.state_patcher.start()
        self.lock_patcher.start()
        release_refresh_lock()

    def tearDown(self):
        release_refresh_lock()
        self.state_patcher.stop()
        self.lock_patcher.stop()
        self.temp_dir.cleanup()

    def test_wait_for_network_ready_retries(self):
        side_effect = [
            (False, "Could not resolve host: query1.finance.yahoo.com"),
            (False, "Could not resolve host: query1.finance.yahoo.com"),
            (True, None),
        ]

        with patch(
            "src.daily_refresh.check_network_ready",
            side_effect=side_effect,
        ) as mock_check:
            ready, error = wait_for_network_ready(
                retries=3,
                retry_delay_seconds=0,
                sleep_fn=lambda _seconds: None,
            )

        self.assertTrue(ready)
        self.assertIsNone(error)
        self.assertEqual(mock_check.call_count, 3)

    @patch("src.daily_refresh.run_daily_refresh")
    @patch(
        "src.daily_refresh.wait_for_network_ready",
        return_value=(True, None),
    )
    def test_preflight_success_runs_refresh(self, _mock_network, mock_run):
        mock_run.return_value = _success_result()

        result = execute_daily_refresh(today=date(2026, 6, 14))

        mock_run.assert_called_once()
        self.assertTrue(result["success"])
        state = load_refresh_state()
        assert state is not None
        self.assertEqual(state["last_status"], "success")

    @patch("src.daily_refresh.run_daily_refresh")
    @patch(
        "src.daily_refresh.wait_for_network_ready",
        return_value=(
            False,
            "Could not resolve host: query1.finance.yahoo.com",
        ),
    )
    def test_preflight_fail_skips_refresh_and_preserves_success_date(
        self,
        _mock_network,
        mock_run,
    ):
        save_refresh_state({
            "last_successful_date": "2026-06-13",
            "last_started_at": "2026-06-13T04:00:00+00:00",
            "last_finished_at": "2026-06-13T04:10:00+00:00",
            "last_status": "success",
            "last_error_count": 0,
            "duration_seconds": 600.0,
        })

        result = execute_daily_refresh(today=date(2026, 6, 14))

        mock_run.assert_not_called()
        self.assertTrue(result["skipped_network"])
        self.assertTrue(result["success"])

        state = load_refresh_state()
        assert state is not None
        self.assertEqual(state["last_status"], "skipped_network")
        self.assertEqual(state["last_error_count"], 1)
        self.assertEqual(state["last_successful_date"], "2026-06-13")

    @patch(
        "src.daily_refresh.wait_for_network_ready",
        return_value=(
            False,
            "Could not resolve host: query1.finance.yahoo.com",
        ),
    )
    def test_network_skip_exits_with_zero(self, _mock_network):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("nettverk utilgjengelig", output.lower())

    @patch("src.daily_refresh.check_network_ready", return_value=(False, "dns fail"))
    def test_dry_run_reports_network_unavailable(self, _mock_network):
        result = execute_daily_refresh(dry_run=True, today=date(2026, 6, 14))

        self.assertTrue(result["dry_run"])
        self.assertFalse(result["network_ready"])
        self.assertEqual(result["network_error"], "dns fail")

        summary = build_refresh_summary(result)
        self.assertIn("Nettverk: utilgjengelig", summary)


class DailyRefreshCachePreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cache_root = Path(self.temp_dir.name)

        self.earnings_cache_patcher = patch(
            "src.earnings._cache_dir",
            return_value=self.cache_root,
        )
        self.analyst_cache_patcher = patch(
            "src.analyst._cache_dir",
            return_value=self.cache_root,
        )
        self.earnings_cache_patcher.start()
        self.analyst_cache_patcher.start()
        self.addCleanup(self.earnings_cache_patcher.stop)
        self.addCleanup(self.analyst_cache_patcher.stop)

    @patch("src.earnings._fetch_yfinance_earnings")
    def test_refresh_earnings_records_error_and_reuses_preserved_cache(self, mock_fetch):
        cache_file = self.cache_root / "AAPL_earnings.json"
        _write_earnings_cache(
            cache_file,
            "AAPL",
            {
                "ticker": "AAPL",
                "earnings_date": "2026-07-30",
                "days_until": 48,
                "status": STATUS_CONFIRMED,
                "source": "yfinance",
                "last_updated": "2026-06-11T08:00:00+00:00",
            },
            today=date(2026, 6, 11),
        )
        mock_fetch.return_value = {
            "ticker": "AAPL",
            "earnings_date": None,
            "days_until": None,
            "status": STATUS_UNKNOWN,
            "source": "yfinance",
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        errors = []
        _refresh_earnings("AAPL", errors, today=date(2026, 6, 12))

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["symbol"], "AAPL")
        self.assertEqual(errors[0]["step"], "earnings")

        cached_result = get_earnings("AAPL", use_cache=True, today=date(2026, 6, 12))
        self.assertEqual(cached_result["earnings_date"], "2026-07-30")
        mock_fetch.assert_called_once()

        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(cached["data"]["earnings_date"], "2026-07-30")

    @patch("src.analyst._fetch_yfinance_analyst")
    def test_refresh_analyst_records_error_and_reuses_preserved_cache(self, mock_fetch):
        cache_file = self.cache_root / "NVDA_analyst.json"
        _write_analyst_cache(
            cache_file,
            "NVDA",
            {
                "ticker": "NVDA",
                "recommendation_key": "strong_buy",
                "recommendation_mean": 1.3,
                "analyst_count": 59,
                "target_mean": 298.93,
                "source": SOURCE_YFINANCE,
                "last_updated": "2026-06-11T08:00:00+00:00",
            },
            today=date(2026, 6, 11),
        )
        mock_fetch.return_value = {
            "ticker": "NVDA",
            "recommendation_key": None,
            "recommendation_mean": None,
            "analyst_count": None,
            "target_mean": None,
            "target_median": None,
            "target_high": None,
            "target_low": None,
            "current_price": None,
            "upside_pct": None,
            "currency": None,
            "distribution": None,
            "source": SOURCE_YFINANCE,
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        errors = []
        _refresh_analyst("NVDA", errors, today=date(2026, 6, 12))

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["symbol"], "NVDA")
        self.assertEqual(errors[0]["step"], "analyst")

        cached_result = get_analyst("NVDA", use_cache=True, today=date(2026, 6, 12))
        self.assertEqual(cached_result["analyst_count"], 59)
        mock_fetch.assert_called_once()

        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(cached["data"]["analyst_count"], 59)


if __name__ == "__main__":
    unittest.main()
