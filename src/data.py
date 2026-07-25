import os
import json
import pandas as pd
import yfinance as yf
from pathlib import Path

from dotenv import load_dotenv
from datetime import date

# Last inn miljøvariabler fra .env
load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

# Lokal cache-mappe
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)
PRICE_COLUMNS = ["open", "high", "low", "close", "adjusted_close", "volume"]
YFINANCE_PRICE_COLUMNS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adjusted_close",
    "Volume": "volume",
}


def _prepare_daily_prices(df, symbol):
    if df is None or df.empty:
        raise ValueError(f"Ingen prisdata for {symbol}")

    if "close" not in df.columns:
        raise ValueError(f"Prisdata for {symbol} mangler close-kolonne")

    cleaned = df.copy()
    cleaned.index = pd.to_datetime(cleaned.index)
    cleaned = cleaned.sort_index()
    cleaned = cleaned[cleaned["close"].notna()]

    if cleaned.empty:
        raise ValueError(
            f"Ingen gyldige close-priser for {symbol} etter opprydding"
        )

    return cleaned.astype(float)


def _write_price_cache(cache_file, symbol, df):
    today = date.today().isoformat()
    cache_data = df.copy()
    cache_data["date_index"] = cache_data.index.astype(str)

    with open(cache_file, "w") as f:
        json.dump({
            "date": today,
            "symbol": symbol,
            "source": "yfinance",
            "data": cache_data.to_dict(orient="records"),
        }, f)


def _price_cache_file(symbol):
    project_root = Path(__file__).resolve().parent.parent
    cache_dir = project_root / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / f"{symbol}_yf_daily.json"


def _read_current_price_cache(symbol):
    cache_file = _price_cache_file(symbol)
    if not cache_file.exists():
        return None
    with open(cache_file, "r") as stream:
        cached = json.load(stream)
    if cached.get("date") != date.today().isoformat():
        return None
    df = pd.DataFrame(cached["data"])
    df.index = pd.to_datetime(df["date_index"])
    return _prepare_daily_prices(df.drop(columns=["date_index"]), symbol)


def _normalize_downloaded_prices(df, symbol):
    normalized = df.rename(columns=YFINANCE_PRICE_COLUMNS)
    missing = [column for column in PRICE_COLUMNS if column not in normalized.columns]
    if missing:
        raise ValueError(f"Prisdata for {symbol} mangler: {', '.join(missing)}")
    return _prepare_daily_prices(normalized[PRICE_COLUMNS], symbol)


def get_daily_prices_batch(symbols, period="6mo", use_cache=True, batch_size=200):
    symbols = list(dict.fromkeys(str(symbol).strip().upper() for symbol in symbols))
    prices = {}
    errors = {}
    missing = []

    for symbol in symbols:
        if use_cache:
            try:
                cached = _read_current_price_cache(symbol)
            except Exception:
                cached = None
            if cached is not None:
                prices[symbol] = cached
                continue
        missing.append(symbol)

    if not missing:
        return prices, errors

    for start in range(0, len(missing), batch_size):
        batch = missing[start : start + batch_size]
        downloaded = yf.download(
            batch,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
            group_by="column",
            threads=True,
        )

        for symbol in batch:
            try:
                if downloaded.empty:
                    raise ValueError(f"Fant ikke Yahoo Finance-data for {symbol}")
                if isinstance(downloaded.columns, pd.MultiIndex):
                    symbol_frame = downloaded.xs(symbol, axis=1, level=1)
                elif len(batch) == 1:
                    symbol_frame = downloaded
                else:
                    raise ValueError(f"Uventet batchformat for {symbol}")
                cleaned = _normalize_downloaded_prices(symbol_frame, symbol)
                prices[symbol] = cleaned
                _write_price_cache(_price_cache_file(symbol), symbol, cleaned)
            except Exception as exc:
                errors[symbol] = str(exc) or exc.__class__.__name__

    return prices, errors


def get_daily_prices(symbol, period="6mo", use_cache=True):
    cache_file = _price_cache_file(symbol)

    if use_cache:
        cached_prices = _read_current_price_cache(symbol)
        if cached_prices is not None:
            print(f"Bruker cache for {symbol}")
            return cached_prices

    print(f"Henter Yahoo Finance-data for {symbol}")

    df = yf.download(
        symbol,
        period=period,
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.empty:
        raise ValueError(f"Fant ikke Yahoo Finance-data for {symbol}")

    cleaned = _normalize_downloaded_prices(df, symbol)
    _write_price_cache(cache_file, symbol, cleaned)

    return cleaned
