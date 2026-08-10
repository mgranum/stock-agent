import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.context import context_snapshot_path, save_context_snapshot
from src.daily_refresh import refresh_lock_path, refresh_state_path
from src.environment import (
    context_snapshot_filename,
    daily_refresh_lock_filename,
    daily_refresh_state_filename,
    get_environment,
    is_prod,
    is_test,
)


class EnvironmentDefaultTests(unittest.TestCase):
    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {}, clear=True)
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def test_default_env_is_prod(self):
        self.assertEqual(get_environment(), "prod")
        self.assertTrue(is_prod())
        self.assertFalse(is_test())

    def test_stock_agent_env_test_gives_test(self):
        with patch.dict(os.environ, {"STOCK_AGENT_ENV": "test"}, clear=True):
            self.assertEqual(get_environment(), "test")
            self.assertFalse(is_prod())
            self.assertTrue(is_test())

    def test_stock_agent_env_prod_gives_prod(self):
        with patch.dict(os.environ, {"STOCK_AGENT_ENV": "prod"}, clear=True):
            self.assertEqual(get_environment(), "prod")
            self.assertTrue(is_prod())
            self.assertFalse(is_test())


class EnvironmentFilenameTests(unittest.TestCase):
    def test_context_snapshot_filenames_differ_by_env(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                context_snapshot_filename(),
                "context_snapshot_prod.json",
            )

        with patch.dict(os.environ, {"STOCK_AGENT_ENV": "test"}, clear=True):
            self.assertEqual(
                context_snapshot_filename(),
                "context_snapshot_test.json",
            )

    def test_daily_refresh_state_filenames_differ_by_env(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                daily_refresh_state_filename(),
                "daily_refresh_state_prod.json",
            )

        with patch.dict(os.environ, {"STOCK_AGENT_ENV": "test"}, clear=True):
            self.assertEqual(
                daily_refresh_state_filename(),
                "daily_refresh_state_test.json",
            )

    def test_daily_refresh_lock_filenames_differ_by_env(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                daily_refresh_lock_filename(),
                "daily_refresh_lock_prod",
            )

        with patch.dict(os.environ, {"STOCK_AGENT_ENV": "test"}, clear=True):
            self.assertEqual(
                daily_refresh_lock_filename(),
                "daily_refresh_lock_test",
            )


class EnvironmentPathIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name) / "cache"
        self.cache_dir.mkdir()
        self.cache_patcher = patch(
            "src.context._project_root",
            return_value=Path(self.temp_dir.name),
        )
        self.refresh_cache_patcher = patch(
            "src.daily_refresh._project_root",
            return_value=Path(self.temp_dir.name),
        )
        self.cache_patcher.start()
        self.refresh_cache_patcher.start()

    def tearDown(self):
        self.cache_patcher.stop()
        self.refresh_cache_patcher.stop()
        self.temp_dir.cleanup()

    def test_prod_and_test_use_different_context_snapshot_files(self):
        with patch.dict(os.environ, {"STOCK_AGENT_ENV": "prod"}, clear=True):
            prod_path = context_snapshot_path()
            save_context_snapshot({"watchlist": ["AAPL"]})

        with patch.dict(os.environ, {"STOCK_AGENT_ENV": "test"}, clear=True):
            test_path = context_snapshot_path()
            save_context_snapshot({"watchlist": ["MSFT"]})

        self.assertNotEqual(prod_path, test_path)
        self.assertTrue(prod_path.exists())
        self.assertTrue(test_path.exists())
        self.assertIn("context_snapshot_prod.json", str(prod_path))
        self.assertIn("context_snapshot_test.json", str(test_path))

    def test_prod_and_test_use_different_refresh_state_files(self):
        with patch.dict(os.environ, {"STOCK_AGENT_ENV": "prod"}, clear=True):
            prod_state = refresh_state_path()
            prod_lock = refresh_lock_path()

        with patch.dict(os.environ, {"STOCK_AGENT_ENV": "test"}, clear=True):
            test_state = refresh_state_path()
            test_lock = refresh_lock_path()

        self.assertNotEqual(prod_state, test_state)
        self.assertNotEqual(prod_lock, test_lock)
        self.assertEqual(prod_state.name, "daily_refresh_state_prod.json")
        self.assertEqual(test_state.name, "daily_refresh_state_test.json")
        self.assertEqual(prod_lock.name, "daily_refresh_lock_prod")
        self.assertEqual(test_lock.name, "daily_refresh_lock_test")


class SharedMarketDataCacheTests(unittest.TestCase):
    def test_market_data_modules_do_not_use_environment(self):
        project_root = Path(__file__).resolve().parent.parent
        shared_cache_modules = [
            project_root / "src" / "data.py",
            project_root / "src" / "fundamentals.py",
            project_root / "src" / "earnings.py",
            project_root / "src" / "analyst.py",
            project_root / "src" / "news.py",
        ]

        for module_path in shared_cache_modules:
            content = module_path.read_text(encoding="utf-8")
            self.assertNotIn("get_environment", content, module_path.name)
            self.assertNotIn("STOCK_AGENT_ENV", content, module_path.name)

    def test_price_cache_path_is_env_independent(self):
        project_root = Path(__file__).resolve().parent.parent
        with patch.dict(os.environ, {"STOCK_AGENT_ENV": "prod"}, clear=True):
            prod_path = project_root / "cache" / "AAPL_yf_daily.json"

        with patch.dict(os.environ, {"STOCK_AGENT_ENV": "test"}, clear=True):
            test_path = project_root / "cache" / "AAPL_yf_daily.json"

        self.assertEqual(prod_path, test_path)


if __name__ == "__main__":
    unittest.main()
