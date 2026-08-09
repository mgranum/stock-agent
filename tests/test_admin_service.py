import pytest

from src.admin_service import AdminMutationService, AdminWritesDisabled
from src.config import add_symbol_to_watchlist
from src.storage import load_json, save_json


@pytest.fixture
def test_data(monkeypatch, tmp_path):
    monkeypatch.setenv("STOCK_AGENT_ENV", "test")
    monkeypatch.setattr("src.storage._data_dir", lambda: tmp_path)
    save_json(
        "portfolio.json",
        [{"ticker": "NVDA", "shares": 10, "buy_price": 100, "note": "behold"}],
    )
    save_json("watchlists.json", {"USA": ["NVDA"], "Norden": []})
    return tmp_path


def test_update_stock_preserves_legacy_fields_and_updates_memberships(test_data):
    result = AdminMutationService().update_stock(
        "nvda",
        owned=True,
        average_cost=125.5,
        watchlists=["Norden"],
    )

    position = load_json("portfolio.json", [])[0]
    assert position == {
        "ticker": "NVDA",
        "shares": 10,
        "buy_price": 125.5,
        "note": "behold",
    }
    assert load_json("watchlists.json", {}) == {"USA": [], "Norden": ["NVDA"]}
    assert result["backup_id"]


def test_new_position_gets_compatibility_quantity_and_can_be_removed(test_data):
    service = AdminMutationService()
    service.update_stock("MSFT", owned=True, average_cost=250, watchlists=["USA"])
    created = next(row for row in load_json("portfolio.json", []) if row["ticker"] == "MSFT")

    assert created["shares"] == 1.0
    assert created["buy_price"] == 250.0

    service.update_stock("MSFT", owned=False, average_cost=None, watchlists=[])
    assert all(row["ticker"] != "MSFT" for row in load_json("portfolio.json", []))


def test_backup_can_restore_both_files(test_data):
    service = AdminMutationService()
    result = service.update_stock("NVDA", owned=False, average_cost=None, watchlists=[])

    restored = service.rollback(result["backup_id"])

    assert restored["restored"] is True
    assert load_json("portfolio.json", [])[0]["ticker"] == "NVDA"
    assert load_json("watchlists.json", {})["USA"] == ["NVDA"]


def test_invalid_input_does_not_create_backup(test_data):
    with pytest.raises(ValueError, match="GAV"):
        AdminMutationService().update_stock(
            "NVDA", owned=True, average_cost=0, watchlists=[]
        )
    assert not (test_data / "backups").exists()


def test_prod_writes_are_blocked(monkeypatch):
    monkeypatch.setenv("STOCK_AGENT_ENV", "prod")
    with pytest.raises(AdminWritesDisabled, match="bare aktivert i TEST"):
        AdminMutationService().update_stock(
            "NVDA", owned=False, average_cost=None, watchlists=[]
        )


def test_failed_second_write_restores_previous_data(test_data, monkeypatch):
    import src.admin_service as module

    real_save = module.save_json
    failed = False

    def fail_once(filename, data):
        nonlocal failed
        if filename == "watchlists.json" and not failed:
            failed = True
            raise OSError("disk full")
        return real_save(filename, data)

    monkeypatch.setattr(module, "save_json", fail_once)
    with pytest.raises(OSError, match="disk full"):
        AdminMutationService().update_stock(
            "NVDA", owned=False, average_cost=None, watchlists=[]
        )

    assert load_json("portfolio.json", [])[0]["ticker"] == "NVDA"
    assert load_json("watchlists.json", {})["USA"] == ["NVDA"]


def test_react_claim_blocks_legacy_watchlist_writer(test_data):
    AdminMutationService().update_stock(
        "NVDA", owned=True, average_cost=100, watchlists=["USA"]
    )

    with pytest.raises(RuntimeError, match="eies av 'react'"):
        add_symbol_to_watchlist("USA", "MSFT")
