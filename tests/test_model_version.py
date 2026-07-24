import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.context import (
    get_context_snapshot_metadata,
    load_context_snapshot,
    save_context_snapshot,
)
from src.model_backtest import backtest_current_model, load_snapshots
from src.model_version import LEGACY_MODEL_VERSION, MODEL_VERSION
from src.recommendation_engine import build_recommendations, limit_recommendations


class ModelVersionTests(unittest.TestCase):
    def test_recommendations_include_frozen_model_version(self):
        recommendations = build_recommendations({})

        self.assertEqual(recommendations["model_version"], MODEL_VERSION)
        self.assertEqual(
            limit_recommendations(recommendations)["model_version"],
            MODEL_VERSION,
        )

    @patch("src.model_backtest.analyze_stock")
    def test_new_model_snapshot_rows_include_model_version(self, mock_analyze):
        mock_analyze.return_value = (
            {
                "score": 80,
                "anbefaling": "KJØP / ØK",
                "trend_regime": "STERK OPPTREND",
                "technical_score": 60,
                "fundamental_score": 70,
                "fundamental_history_score": 80,
                "relative_strength_20d": 5.0,
                "kurs": 100.0,
                "stop_loss": 92.0,
                "trailing_stop_loss": 95.0,
            },
            pd.DataFrame(),
        )

        snapshot = backtest_current_model(["AAPL"])

        self.assertEqual(snapshot.iloc[0]["model_version"], MODEL_VERSION)

    def test_legacy_model_snapshots_remain_readable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshots"
            snapshot_dir.mkdir()
            pd.DataFrame(
                [{"date": "2026-07-22", "ticker": "AAPL", "score": 80}]
            ).to_csv(
                snapshot_dir / "model_snapshot_2026-07-22.csv",
                index=False,
            )

            with patch("src.model_backtest.Path", return_value=snapshot_dir):
                loaded = load_snapshots()

        self.assertEqual(
            loaded.iloc[0]["model_version"],
            LEGACY_MODEL_VERSION,
        )

    def test_context_snapshot_metadata_includes_model_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "context_snapshot_test.json"
            with patch("src.context.context_snapshot_path", return_value=snapshot_path):
                save_context_snapshot({"watchlist": ["AAPL"]})
                metadata = get_context_snapshot_metadata()
                loaded = load_context_snapshot(check_max_age=False)

                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["model_version"], MODEL_VERSION)
        self.assertEqual(metadata["model_version"], MODEL_VERSION)
        self.assertEqual(loaded["model_version"], MODEL_VERSION)

    def test_legacy_context_snapshot_without_model_version_remains_readable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "context_snapshot_test.json"
            with patch("src.context.context_snapshot_path", return_value=snapshot_path):
                save_context_snapshot({"watchlist": ["AAPL"]})
                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                payload.pop("model_version")
                snapshot_path.write_text(json.dumps(payload), encoding="utf-8")

                metadata = get_context_snapshot_metadata()
                loaded = load_context_snapshot(check_max_age=False)

        self.assertIsNone(metadata["model_version"])
        self.assertNotIn("model_version", loaded)


if __name__ == "__main__":
    unittest.main()
