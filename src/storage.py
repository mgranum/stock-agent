import json
from pathlib import Path

from src.environment import get_environment


def _project_root():
    return Path(__file__).resolve().parent.parent


def _data_dir():
    path = _project_root() / "data" / get_environment()
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_path(filename):
    return _data_dir() / filename


def load_json(filename, default):
    path = data_path(filename)

    if not path.exists():
        save_json(filename, default)
        return default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    path = data_path(filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )

    return path


def load_portfolio(default=None):
    return load_json("portfolio.json", default or [])


def save_portfolio(portfolio):
    return save_json("portfolio.json", portfolio)


def load_pending_orders(default=None):
    return load_json("pending_orders.json", default or [])


def save_pending_orders(orders):
    return save_json("pending_orders.json", orders)


def load_order_history(default=None):
    return load_json("order_history.json", default or [])


def save_order_history(history):
    return save_json("order_history.json", history)