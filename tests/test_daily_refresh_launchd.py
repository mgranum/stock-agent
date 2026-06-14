import os
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DOCS_PATH = PROJECT_ROOT / "docs" / "daily_refresh_launchd.md"
RUN_SCRIPT = SCRIPTS_DIR / "run_daily_refresh.sh"
PLIST_PATH = SCRIPTS_DIR / "com.stock-agent.daily-refresh.plist"
PLIST_LABEL = "com.stock-agent.daily-refresh"


class DailyRefreshLaunchdSetupTests(unittest.TestCase):
    def test_run_script_exists_and_is_executable(self):
        self.assertTrue(RUN_SCRIPT.is_file(), "run_daily_refresh.sh must exist")
        self.assertTrue(
            os.access(RUN_SCRIPT, os.X_OK),
            "run_daily_refresh.sh must be executable",
        )

        content = RUN_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("STOCK_AGENT_ENV=prod", content)
        self.assertIn("uv run python -m src.daily_refresh", content)
        self.assertIn("logs/daily_refresh.log", content)

    def test_plist_exists_and_contains_label(self):
        self.assertTrue(PLIST_PATH.is_file(), "launchd plist template must exist")

        content = PLIST_PATH.read_text(encoding="utf-8")
        self.assertIn(f"<string>{PLIST_LABEL}</string>", content)
        self.assertIn("RunAtLoad", content)
        self.assertIn("StartCalendarInterval", content)
        self.assertIn("<integer>6</integer>", content)
        self.assertIn("run_daily_refresh.sh", content)
        self.assertNotIn("KeepAlive", content)

    def test_docs_exist(self):
        self.assertTrue(DOCS_PATH.is_file(), "daily_refresh_launchd.md must exist")

        content = DOCS_PATH.read_text(encoding="utf-8")
        self.assertIn("launchctl load", content)
        self.assertIn("launchctl unload", content)
        self.assertIn("launchctl start com.stock-agent.daily-refresh", content)
        self.assertIn("tail -f logs/daily_refresh.log", content)
        self.assertIn("__PROJECT_ROOT__", content)


if __name__ == "__main__":
    unittest.main()
