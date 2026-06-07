import json
from pathlib import Path


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

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )

    return path


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


def load_watchlists():
    watchlists = load_json_config(
        "watchlists.json",
        DEFAULT_WATCHLISTS,
    )

    all_watchlist = []

    for symbols in watchlists.values():
        all_watchlist.extend(symbols)

    watchlists["Alle"] = sorted(
        list(set(all_watchlist))
    )

    return watchlists


def load_backtest_config():
    return load_json_config(
        "backtest_config.json",
        DEFAULT_BACKTEST_CONFIG,
    )