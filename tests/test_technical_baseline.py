from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from src.config import DEFAULT_BACKTEST_VALIDATION_CONFIG
from src.technical_baseline import (
    _adjust_ohlc_prices,
    _execution,
    backtest_technical_baseline,
    build_trend_momentum_reference_snapshot,
    technical_baseline_buy_signal,
    trend_momentum_reference_signal,
    validate_chronological_datasets,
)


def _price_data(rows=150):
    index = pd.bdate_range("2024-01-01", periods=rows)
    close = np.linspace(100, 140, rows)
    return pd.DataFrame(
        {
            "open": close + 1,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "adjusted_close": close,
            "volume": np.full(rows, 100000),
        },
        index=index,
    )


def _technical_result(*args, **kwargs):
    return {
        "technical_score": 80,
        "trend_regime": "STERK OPPTREND",
        "relative_strength_20d": 5,
    }


def test_frozen_technical_reference_uses_same_entry_rule_as_baseline():
    config = deepcopy(DEFAULT_BACKTEST_VALIDATION_CONFIG)

    assert technical_baseline_buy_signal(
        _technical_result(),
        "RISK_ON",
        config["strategy"],
    ) is True
    assert technical_baseline_buy_signal(
        {**_technical_result(), "relative_strength_20d": -0.01},
        "RISK_ON",
        config["strategy"],
    ) is False


def test_trend_momentum_reference_is_deliberately_simpler_than_baseline():
    assert trend_momentum_reference_signal(
        {"trend_regime": "STERK OPPTREND", "relative_strength_20d": 1.0}
    ) is True
    assert trend_momentum_reference_signal(
        {"trend_regime": "MODERAT OPPTREND", "relative_strength_20d": 1.0}
    ) is False


def test_technical_reference_snapshot_freezes_rule_and_signal_inputs():
    config = deepcopy(DEFAULT_BACKTEST_VALIDATION_CONFIG)

    snapshot = build_trend_momentum_reference_snapshot(
        _technical_result(),
        config=config,
    )

    assert snapshot["version"] == "trend_momentum_v1"
    assert snapshot["status"] == "complete"
    assert snapshot["action"] == "buy"
    assert snapshot["inputs"]["relative_strength_20d"] == 5.0
    assert snapshot["rule"]["min_relative_strength_20d"] == 0.0
    assert len(snapshot["rule_fingerprint"]) == 16


def test_technical_reference_snapshot_marks_missing_inputs_unavailable():
    snapshot = build_trend_momentum_reference_snapshot(
        {"technical_score": 80},
        config=deepcopy(DEFAULT_BACKTEST_VALIDATION_CONFIG),
    )

    assert snapshot["status"] == "unavailable"
    assert "action" not in snapshot


def test_dataset_ranges_must_be_strictly_chronological():
    parsed = validate_chronological_datasets(
        {
            "train": {"start": "2020-01-01", "end": "2020-12-31"},
            "test": {"start": "2021-01-01", "end": "2021-12-31"},
        }
    )

    assert list(parsed) == ["train", "test"]

    with pytest.raises(ValueError, match="overlapper"):
        validate_chronological_datasets(
            {
                "train": {
                    "start": "2020-01-01",
                    "end": "2021-06-30",
                },
                "test": {
                    "start": "2021-01-01",
                    "end": "2021-12-31",
                },
            }
        )


def test_dataset_validation_rejects_empty_and_invalid_ranges():
    with pytest.raises(ValueError, match="kan ikke være tom"):
        validate_chronological_datasets({})

    with pytest.raises(ValueError, match="starter etter"):
        validate_chronological_datasets(
            {
                "invalid": {
                    "start": "2022-01-02",
                    "end": "2022-01-01",
                }
            }
        )


def test_execution_applies_spread_fx_and_minimum_commission():
    costs = deepcopy(DEFAULT_BACKTEST_VALIDATION_CONFIG["costs"])
    execution = _execution("AAPL", "BUY", 100, 10, costs)

    assert execution["execution_price"] == pytest.approx(100.35)
    assert execution["commission"] == pytest.approx(9.9)
    assert execution["cash_change"] == pytest.approx(-1013.4)


def test_adjusted_prices_apply_same_factor_to_ohlc():
    prices = _price_data(2)
    prices.loc[prices.index[0], "adjusted_close"] = (
        prices.loc[prices.index[0], "close"] / 2
    )

    adjusted = _adjust_ohlc_prices(prices)

    assert adjusted.iloc[0]["close"] == pytest.approx(
        prices.iloc[0]["close"] / 2
    )
    assert adjusted.iloc[0]["open"] == pytest.approx(
        prices.iloc[0]["open"] / 2
    )
    assert adjusted.iloc[1]["close"] == pytest.approx(
        prices.iloc[1]["close"]
    )


def test_signal_on_close_executes_at_next_open(monkeypatch):
    prices = _price_data()
    config = deepcopy(DEFAULT_BACKTEST_VALIDATION_CONFIG)
    config["strategy"]["min_hold_days"] = 0
    start = prices.index[120]
    end = prices.index[130]
    exit_calls = 0

    def exit_after_first_holding_day(*args, **kwargs):
        nonlocal exit_calls
        exit_calls += 1
        return "Test-exit" if exit_calls == 2 else None

    monkeypatch.setattr(
        "src.technical_baseline._technical_result_at",
        _technical_result,
    )
    monkeypatch.setattr(
        "src.technical_baseline._market_regime_at",
        lambda *args, **kwargs: {"market_regime": "RISK_ON"},
    )
    monkeypatch.setattr(
        "src.technical_baseline._get_exit_reason",
        exit_after_first_holding_day,
    )

    summary, trades, analysis = backtest_technical_baseline(
        "AAPL",
        start,
        end,
        config=config,
        price_df=prices,
        benchmark_df=prices,
    )

    first_trade = trades.iloc[0]
    assert first_trade["signal_date"] == prices.index[120]
    assert first_trade["execution_date"] == prices.index[121]
    assert first_trade["raw_price"] == pytest.approx(
        prices.iloc[121]["open"],
        abs=0.0001,
    )
    assert trades.iloc[1]["action"] == "SELL"
    assert summary["signal_timing"] == "close_t"
    assert summary["execution_timing"] == "open_t_plus_1"
    assert summary["total_realized_costs"] > 0
    assert summary["region"] == "usa"
    assert summary["max_drawdown_pct"] is not None
    assert summary["turnover"] > 0
    assert summary["closed_trades"] == 1
    assert "portfolio_value" in analysis.columns
    assert "buy_and_hold_value" in analysis.columns


def test_baseline_rejects_period_without_evaluable_days():
    prices = _price_data(20)

    with pytest.raises(ValueError, match="Ingen evaluerbare handelsdager"):
        backtest_technical_baseline(
            "AAPL",
            prices.index[0],
            prices.index[-1],
            config=deepcopy(DEFAULT_BACKTEST_VALIDATION_CONFIG),
            price_df=prices,
            benchmark_df=prices,
        )


def test_baseline_rejects_unsupported_execution_timing():
    prices = _price_data()
    config = deepcopy(DEFAULT_BACKTEST_VALIDATION_CONFIG)
    config["execution"]["execution_price"] = "same_close"

    with pytest.raises(ValueError, match="neste open"):
        backtest_technical_baseline(
            "AAPL",
            prices.index[120],
            prices.index[130],
            config=config,
            price_df=prices,
            benchmark_df=prices,
        )
