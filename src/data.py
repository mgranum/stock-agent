import os
import json
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

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


def _utc_now():
    return datetime.now(timezone.utc)


def _has_missing_latest_close(df):
    if df is None or df.empty or "Close" not in df.columns:
        return False
    latest = df.sort_index().iloc[-1]
    return pd.isna(latest["Close"])


def _latest_expected_weekday(today=None):
    expected = (today or _utc_now().date()) - timedelta(days=1)
    while expected.weekday() >= 5:
        expected -= timedelta(days=1)
    return expected


def _needs_latest_quote_check(df):
    if df is None or df.empty or "Close" not in df.columns:
        return False
    if _has_missing_latest_close(df):
        return True
    latest_date = pd.Timestamp(df.sort_index().index[-1]).date()
    return latest_date < _latest_expected_weekday()


def _repair_missing_latest_close(df, symbol):
    """Fill a completed Yahoo daily row whose official close is delayed."""
    if not _needs_latest_quote_check(df):
        return df

    ticker = yf.Ticker(symbol)
    try:
        fast_info = ticker.fast_info
        latest_price = float(fast_info["lastPrice"])
        metadata = ticker.history_metadata
        quote_timestamp = int(metadata["regularMarketTime"])
        timezone_name = metadata["exchangeTimezoneName"]
        exchange_timezone = ZoneInfo(timezone_name)
    except (
        KeyError,
        TypeError,
        ValueError,
        ZoneInfoNotFoundError,
    ) as exc:
        raise ValueError(
            f"Yahoo mangler siste sluttkurs for {symbol}, "
            "og markedsmetadata kunne ikke reparere den"
        ) from exc

    if pd.isna(latest_price):
        raise ValueError(f"Yahoo mangler gyldig siste sluttkurs for {symbol}")

    quote_datetime = datetime.fromtimestamp(
        quote_timestamp,
        tz=timezone.utc,
    ).astimezone(exchange_timezone)
    now_at_exchange = _utc_now().astimezone(exchange_timezone)

    # Do not turn an intraday quote into a daily close while the session may
    # still be open. The overnight refresh only repairs a prior local date.
    if quote_datetime.date() >= now_at_exchange.date():
        return df

    sorted_prices = df.sort_index()
    latest_index = sorted_prices.index[-1]
    latest_date = pd.Timestamp(latest_index)
    localized_latest_date = latest_date
    if localized_latest_date.tzinfo is not None:
        localized_latest_date = localized_latest_date.tz_convert(exchange_timezone)

    if localized_latest_date.date() == quote_datetime.date():
        if not pd.isna(sorted_prices.iloc[-1]["Close"]):
            return df
        repaired = df.copy()
        repaired.loc[latest_index, "Close"] = latest_price
        if "Adj Close" in repaired.columns and pd.isna(
            repaired.loc[latest_index, "Adj Close"]
        ):
            repaired.loc[latest_index, "Adj Close"] = latest_price
        return repaired

    if localized_latest_date.date() > quote_datetime.date():
        raise ValueError(
            f"Yahoo mangler siste sluttkurs for {symbol}: "
            f"dagsrad {localized_latest_date.date()} og kursmetadata "
            f"{quote_datetime.date()} samsvarer ikke"
        )

    quote_values = {
        "Open": fast_info.get("open"),
        "High": fast_info.get("dayHigh"),
        "Low": fast_info.get("dayLow"),
        "Close": latest_price,
        "Adj Close": latest_price,
        "Volume": fast_info.get("lastVolume"),
    }
    required_values = [
        quote_values[column]
        for column in ("Open", "High", "Low", "Close", "Volume")
    ]
    if any(value is None or pd.isna(value) for value in required_values):
        raise ValueError(
            f"Yahoo mangler komplett siste dagsrad for {symbol}"
        )

    repaired = df.copy()
    quote_index = pd.Timestamp(quote_datetime.date())
    if isinstance(repaired.index, pd.DatetimeIndex) and repaired.index.tz is not None:
        quote_index = quote_index.tz_localize(exchange_timezone)
    for column, value in quote_values.items():
        if column in repaired.columns:
            repaired.loc[quote_index, column] = value
    return repaired


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
                incomplete_latest_row = _needs_latest_quote_check(symbol_frame)
                cleaned = _normalize_downloaded_prices(symbol_frame, symbol)
                prices[symbol] = cleaned
                # A missing latest close is still useful for the coarse
                # liquidity filter, but must not poison the daily cache. A
                # later full analysis will fetch and repair the symbol alone.
                if not incomplete_latest_row:
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

    df = _repair_missing_latest_close(df, symbol)
    incomplete_latest_row = _has_missing_latest_close(df)
    cleaned = _normalize_downloaded_prices(df, symbol)
    if not incomplete_latest_row:
        _write_price_cache(cache_file, symbol, cleaned)

    return cleaned
