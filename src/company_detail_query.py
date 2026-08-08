from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import re

import pandas as pd

from src.company_names import get_company_name
from src.data import get_daily_prices


PERIODS = ("1u", "1m", "3m", "6m", "i år", "1 år", "3 år", "maks")
_DOWNLOAD_PERIOD = {
    "1u": "6mo",
    "1m": "6mo",
    "3m": "1y",
    "6m": "2y",
    "i år": "2y",
    "1 år": "2y",
    "3 år": "5y",
    "maks": "max",
}
_TICKER_PATTERN = re.compile(r"^[A-Z0-9^][A-Z0-9.^-]{0,19}$")


@lru_cache(maxsize=128)
def _load_chart_prices(symbol: str, period: str, use_cache: bool = True):
    # The existing disk cache is keyed only by ticker and can contain a shorter
    # history than the chart requests. Fetch once per process and period until
    # the shared cache gains period-aware metadata.
    return get_daily_prices(symbol, period=period, use_cache=False)


@dataclass(frozen=True)
class CompanyDetail:
    ticker: str
    company_name: str
    period: str
    currency: str | None
    as_of: str
    current_price: float
    period_change_pct: float
    candles: list[dict]


def normalize_ticker(ticker: str) -> str:
    normalized = str(ticker or "").strip().upper()
    if not _TICKER_PATTERN.fullmatch(normalized):
        raise ValueError("Ugyldig ticker")
    return normalized


def _period_start(index: pd.DatetimeIndex, period: str) -> pd.Timestamp | None:
    last = index[-1]
    if period == "1u":
        return last - pd.Timedelta(days=7)
    if period == "1m":
        return last - pd.DateOffset(months=1)
    if period == "3m":
        return last - pd.DateOffset(months=3)
    if period == "6m":
        return last - pd.DateOffset(months=6)
    if period == "i år":
        return pd.Timestamp(year=last.year, month=1, day=1)
    if period == "1 år":
        return last - pd.DateOffset(years=1)
    if period == "3 år":
        return last - pd.DateOffset(years=3)
    return None


def _finite_float(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 4)


def _candles(prices: pd.DataFrame, period: str) -> list[dict]:
    if prices is None or prices.empty:
        raise ValueError("Ingen prisdata i valgt periode")

    enriched = prices.copy().sort_index()
    enriched["sma20"] = enriched["close"].rolling(20).mean()
    enriched["sma50"] = enriched["close"].rolling(50).mean()
    start = _period_start(enriched.index, period)
    if start is not None:
        enriched = enriched[enriched.index >= start]
    if enriched.empty:
        raise ValueError("Ingen prisdata i valgt periode")

    result = []
    for timestamp, row in enriched.iterrows():
        result.append(
            {
                "time": timestamp.strftime("%Y-%m-%d"),
                "open": _finite_float(row.get("open")),
                "high": _finite_float(row.get("high")),
                "low": _finite_float(row.get("low")),
                "close": _finite_float(row.get("close")),
                "volume": _finite_float(row.get("volume")),
                "sma20": _finite_float(row.get("sma20")),
                "sma50": _finite_float(row.get("sma50")),
            }
        )
    return result


class CompanyDetailQuery:
    def __init__(
        self,
        price_loader: Callable = _load_chart_prices,
        company_name_loader: Callable = get_company_name,
    ):
        self._price_loader = price_loader
        self._company_name_loader = company_name_loader

    def get(self, ticker: str, period: str = "3m") -> CompanyDetail:
        symbol = normalize_ticker(ticker)
        if period not in PERIODS:
            raise ValueError("Ugyldig periode")

        prices = self._price_loader(
            symbol,
            period=_DOWNLOAD_PERIOD[period],
            use_cache=True,
        )
        candles = _candles(prices, period)
        first_close = candles[0]["close"]
        current_price = candles[-1]["close"]
        if first_close in (None, 0) or current_price is None:
            change_pct = 0.0
        else:
            change_pct = round((current_price / first_close - 1) * 100, 2)

        return CompanyDetail(
            ticker=symbol,
            company_name=self._company_name_loader(symbol) or symbol,
            period=period,
            currency=None,
            as_of=datetime.now(timezone.utc).isoformat(),
            current_price=round(current_price, 2),
            period_change_pct=change_pct,
            candles=candles,
        )
