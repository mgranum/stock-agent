import json
from functools import lru_cache
from pathlib import Path

import yfinance as yf


def _cache_dir():
    project_root = Path(__file__).resolve().parent.parent
    cache_dir = project_root / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


def _cache_file(symbol):
    return _cache_dir() / f"{symbol}_company_name.json"


def _read_cache(symbol):
    cache_file = _cache_file(symbol)
    if not cache_file.exists():
        return None

    with open(cache_file, "r", encoding="utf-8") as f:
        cached = json.load(f)

    return cached.get("name")


def _write_cache(symbol, name):
    cache_file = _cache_file(symbol)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "symbol": symbol,
                "name": name,
                "source": "yfinance",
            },
            f,
            indent=2,
            ensure_ascii=False,
        )


def _fetch_company_name(symbol):
    info = yf.Ticker(symbol).info or {}
    return (
        info.get("longName")
        or info.get("shortName")
        or info.get("name")
    )


@lru_cache(maxsize=512)
def get_company_name(symbol):
    symbol = symbol.strip().upper()
    if not symbol:
        return ""

    cached = _read_cache(symbol)
    if cached:
        return cached

    try:
        name = _fetch_company_name(symbol)
    except Exception:
        name = None

    _write_cache(symbol, name)
    return name or ""
