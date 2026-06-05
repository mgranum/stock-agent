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


def get_daily_prices(symbol, period="6mo", use_cache=True):
    today = date.today().isoformat()

    project_root = Path(__file__).resolve().parent.parent
    cache_dir = project_root / "cache"
    cache_dir.mkdir(exist_ok=True)

    cache_file = cache_dir / f"{symbol}_yf_daily.json"

    if use_cache and cache_file.exists():
        with open(cache_file, "r") as f:
            cached = json.load(f)

        if cached.get("date") == today:
            print(f"Bruker cache for {symbol}")
            df = pd.DataFrame(cached["data"])
            df.index = pd.to_datetime(df["date_index"])
            df = df.drop(columns=["date_index"])
            return df.astype(float)

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

    df = df.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adjusted_close",
        "Volume": "volume",
    })

    df = df[[
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume"
    ]]

    df.index = pd.to_datetime(df.index)

    cache_data = df.copy()
    cache_data["date_index"] = cache_data.index.astype(str)

    with open(cache_file, "w") as f:
        json.dump({
            "date": today,
            "symbol": symbol,
            "source": "yfinance",
            "data": cache_data.to_dict(orient="records"),
        }, f)

    return df