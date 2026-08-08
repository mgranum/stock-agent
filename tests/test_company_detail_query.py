import pandas as pd
import pytest

from src.company_detail_query import CompanyDetailQuery, PERIODS, normalize_ticker


def _prices(rows=90):
    index = pd.bdate_range("2026-01-02", periods=rows)
    close = [100.0 + position for position in range(rows)]
    return pd.DataFrame(
        {
            "open": [value - 1 for value in close],
            "high": [value + 2 for value in close],
            "low": [value - 2 for value in close],
            "close": close,
            "adjusted_close": close,
            "volume": [1_000_000 + position for position in range(rows)],
        },
        index=index,
    )


def test_returns_chart_data_without_running_stock_analysis():
    calls = []

    def loader(symbol, period, use_cache):
        calls.append((symbol, period, use_cache))
        return _prices()

    result = CompanyDetailQuery(
        loader,
        lambda ticker: "Test Company",
    ).get(
        " nvda ", "1m"
    )

    assert result.ticker == "NVDA"
    assert result.company_name == "Test Company"
    assert result.period == "1m"
    assert result.current_price == 189.0
    assert result.period_change_pct > 0
    assert result.candles[-1]["sma20"] is not None
    assert result.candles[-1]["sma50"] is not None
    assert calls == [("NVDA", "6mo", True)]


def test_supports_every_product_period():
    query = CompanyDetailQuery(
        lambda *_args, **_kwargs: _prices(900),
        lambda ticker: ticker,
    )

    for period in PERIODS:
        result = query.get("NVDA", period)
        assert result.candles
        assert result.period == period
@pytest.mark.parametrize("ticker", ["", "NVDA/../../", "NVDA $", "A" * 21])
def test_rejects_invalid_ticker(ticker):
    with pytest.raises(ValueError, match="Ugyldig ticker"):
        normalize_ticker(ticker)


def test_rejects_invalid_period():
    query = CompanyDetailQuery(
        lambda *_args, **_kwargs: _prices(),
        str,
    )
    with pytest.raises(ValueError, match="Ugyldig periode"):
        query.get("NVDA", "2m")


def test_rejects_empty_selected_period():
    query = CompanyDetailQuery(
        lambda *_args, **_kwargs: _prices().iloc[0:0],
        str,
    )
    with pytest.raises(ValueError, match="Ingen prisdata"):
        query.get("NVDA", "1m")
