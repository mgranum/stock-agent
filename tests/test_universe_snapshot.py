import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.universe_snapshot import normalize_universes, save_universe_snapshot


class UniverseSnapshotTests(unittest.TestCase):
    def test_normalizes_and_deduplicates_symbols(self):
        result = normalize_universes(
            {"USA": [" aapl ", "AAPL", "", None], "INVALID": "AAPL"}
        )

        self.assertEqual(result, {"USA": ["AAPL"]})

    def test_saves_dated_reproducible_universe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "src.universe_snapshot._project_root",
                return_value=Path(temp_dir),
            ):
                path = save_universe_snapshot(
                    {"USA": ["AAPL", "MSFT"]},
                    snapshot_date=date(2026, 7, 24),
                )

            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(path.name, "screening_universe_2026-07-24.json")
        self.assertEqual(payload["snapshot_date"], "2026-07-24")
        self.assertEqual(payload["universes"]["USA"], ["AAPL", "MSFT"])
