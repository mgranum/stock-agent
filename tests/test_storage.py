from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.storage import data_path, load_json, save_json, update_json


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    data_dir = tmp_path / "data" / "test"
    monkeypatch.setattr("src.storage._data_dir", lambda: data_dir)
    return data_dir


def test_save_json_is_atomic_and_leaves_no_temp_file(isolated_data):
    path = save_json("portfolio.json", [{"ticker": "NVDA"}])

    assert json.loads(path.read_text(encoding="utf-8")) == [{"ticker": "NVDA"}]
    assert list(isolated_data.glob("*.tmp")) == []


def test_failed_replace_preserves_previous_file(isolated_data):
    save_json("portfolio.json", [{"ticker": "NVDA"}])

    with patch("src.storage.os.replace", side_effect=OSError("disk failure")):
        with pytest.raises(OSError, match="disk failure"):
            save_json("portfolio.json", [{"ticker": "MSFT"}])

    assert load_json("portfolio.json", []) == [{"ticker": "NVDA"}]
    assert list(isolated_data.glob("*.tmp")) == []


def test_concurrent_updates_do_not_lose_changes(isolated_data):
    save_json("counter.json", {"value": 0})

    def increment(_index):
        update_json(
            "counter.json",
            lambda current: {"value": current["value"] + 1},
            {"value": 0},
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(increment, range(50)))

    assert load_json("counter.json", {}) == {"value": 50}


@pytest.mark.parametrize("filename", ["", "../prod/portfolio.json", "a/b.json"])
def test_data_path_rejects_path_traversal(filename, isolated_data):
    with pytest.raises(ValueError, match="Ugyldig datafilnavn"):
        data_path(filename)
