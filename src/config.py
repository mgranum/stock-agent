import json
from pathlib import Path

from src.storage import atomic_write_json, load_json, update_json


def _project_root():
    return Path(__file__).resolve().parent.parent


def _config_dir():
    path = _project_root() / "data" / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _config_path(filename):
    return _config_dir() / filename


def load_json_config(filename, default):
    path = _config_path(filename)

    if not path.exists():
        save_json_config(filename, default)
        return default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_config(filename, data):
    path = _config_path(filename)
    return atomic_write_json(path, data)


DEFAULT_WATCHLISTS = {
    "USA": [
        "NVDA",
        "AAPL",
        "AMZN",
        "MSFT",
        "GOOGL",
        "META",
        "TSLA",
    ],

    "Norden": [
        "EQNR.OL",
        "DNB.OL",
        "NOVO-B.CO",
        "VOLV-B.ST",
    ],

    "OBX": [
        "EQNR.OL",
        "DNB.OL",
        "AKRBP.OL",
        "NHY.OL",
        "MOWI.OL",
        "TEL.OL",
        "ORK.OL",
        "YAR.OL",
        "SALM.OL",
        "ELK.OL",
        "SUBC.OL",
    ],
}


DEFAULT_BACKTEST_CONFIG = {
    "baseline": {
        "min_hold_days": 60,
        "stop_loss_pct": 0.12,
        "trailing_sma": "sma100",
        "min_buy_score": 70,
        "min_buy_relative_strength": 0,
        "require_risk_on": False,
    },

    "obx": {
        "min_hold_days": 60,
        "stop_loss_pct": 0.08,
        "trailing_sma": "sma100",
        "min_buy_score": 70,
        "min_buy_relative_strength": 0,
        "require_risk_on": False,
    },
}


DEFAULT_BACKTEST_VALIDATION_CONFIG = {
    "execution": {
        "initial_cash": 100000,
        "signal_price": "close",
        "execution_price": "next_open",
        "use_adjusted_prices": True,
    },
    "strategy": {
        "min_technical_score": 70,
        "min_buy_relative_strength": 0,
        "min_hold_days": 60,
        "stop_loss_pct": 0.12,
        "trailing_sma": "sma100",
        "require_risk_on": False,
    },
    "costs": {
        "spread_pct_per_side": 0.001,
        "nordics": {
            "commission_pct": 0.001,
            "minimum_commission": 49,
            "fx_pct_per_side": 0.0,
        },
        "usa": {
            "commission_pct": 0.001,
            "minimum_commission": 9.9,
            "fx_pct_per_side": 0.0025,
        },
    },
    "datasets": {
        "in_sample": {
            "start": "2018-01-01",
            "end": "2022-12-31",
        },
        "calibration": {
            "start": "2023-01-01",
            "end": "2024-12-31",
        },
        "historical_test": {
            "start": "2025-01-01",
            "end": "2026-07-23",
        },
        "forward_out_of_sample": {
            "start": "2026-07-24",
            "end": "2027-07-23",
        },
    },
    "walk_forward": {
        "start": "2018-01-01",
        "end": "2026-07-23",
        "train_years": 3,
        "test_months": 6,
        "step_months": 6,
    },
}


DEFAULT_DISCOVERY_CONFIG = {
    "coarse_filter": {
        "enabled": True,
        "period": "6mo",
        "min_history_days": 60,
        "max_price_age_days": 10,
        "min_price": 1.0,
        "min_average_traded_value_20d": 2_000_000,
        "max_full_analysis": 40,
        "liquidity_top_slots": 15,
        "mid_liquidity_slots": 10,
    },
}


def _load_editable_watchlists():
    return load_json(
        "watchlists.json",
        DEFAULT_WATCHLISTS,
    )


def _derive_alle_watchlist(watchlists):
    all_symbols = []

    for symbols in watchlists.values():
        all_symbols.extend(symbols)

    watchlists["Alle"] = sorted(set(all_symbols))
    return watchlists


def load_watchlists():
    return _derive_alle_watchlist(_load_editable_watchlists())


def add_symbol_to_watchlist(list_name, symbol):
    if list_name == "Alle":
        raise ValueError("Kan ikke redigere watchlisten 'Alle'.")

    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("Ticker kan ikke være tom.")

    def add_symbol(watchlists):
        if list_name not in watchlists:
            raise ValueError(f"Watchlist '{list_name}' finnes ikke.")
        if symbol not in watchlists[list_name]:
            watchlists[list_name].append(symbol)
        return watchlists

    updated = update_json("watchlists.json", add_symbol, DEFAULT_WATCHLISTS)
    return _derive_alle_watchlist(updated)


def remove_symbol_from_watchlist(list_name, symbol):
    if list_name == "Alle":
        raise ValueError("Kan ikke redigere watchlisten 'Alle'.")

    symbol = symbol.strip().upper()
    def remove_symbol(watchlists):
        if list_name not in watchlists:
            raise ValueError(f"Watchlist '{list_name}' finnes ikke.")
        watchlists[list_name] = [
            current
            for current in watchlists[list_name]
            if current != symbol
        ]
        return watchlists

    updated = update_json("watchlists.json", remove_symbol, DEFAULT_WATCHLISTS)
    return _derive_alle_watchlist(updated)


def load_backtest_config():
    return load_json_config(
        "backtest_config.json",
        DEFAULT_BACKTEST_CONFIG,
    )


def load_discovery_config():
    loaded = load_json_config(
        "discovery_config.json",
        DEFAULT_DISCOVERY_CONFIG,
    )
    loaded_coarse = (
        loaded.get("coarse_filter")
        if isinstance(loaded, dict)
        else {}
    )
    return {
        **DEFAULT_DISCOVERY_CONFIG,
        **(loaded if isinstance(loaded, dict) else {}),
        "coarse_filter": {
            **DEFAULT_DISCOVERY_CONFIG["coarse_filter"],
            **(loaded_coarse if isinstance(loaded_coarse, dict) else {}),
        },
    }


def load_backtest_validation_config():
    return load_json_config(
        "backtest_validation_config.json",
        DEFAULT_BACKTEST_VALIDATION_CONFIG,
    )
