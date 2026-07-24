from copy import deepcopy

import pandas as pd
import pytest

from src.config import DEFAULT_BACKTEST_VALIDATION_CONFIG
from src.walk_forward import (
    build_walk_forward_folds,
    rolling_walk_forward,
)
from src.walk_forward_report import summarize_rolling_walk_forward


def test_folds_are_chronological_and_non_overlapping():
    folds = build_walk_forward_folds(
        {
            "start": "2020-01-01",
            "end": "2022-12-31",
            "train_years": 1,
            "test_months": 6,
            "step_months": 6,
        }
    )

    assert len(folds) == 4
    for fold in folds:
        assert fold["train_end"] < fold["test_start"]
    assert folds[0]["test_end"] < folds[1]["test_end"]


def test_invalid_or_too_short_walk_forward_config_is_rejected():
    with pytest.raises(ValueError, match="må være positive"):
        build_walk_forward_folds(
            {
                "start": "2020-01-01",
                "end": "2022-12-31",
                "train_years": 0,
                "test_months": 6,
                "step_months": 6,
            }
        )

    with pytest.raises(ValueError, match="for kort"):
        build_walk_forward_folds(
            {
                "start": "2020-01-01",
                "end": "2020-06-30",
                "train_years": 1,
                "test_months": 6,
                "step_months": 6,
            }
        )


def test_walk_forward_uses_fixed_baseline_and_loads_data_once():
    config = deepcopy(DEFAULT_BACKTEST_VALIDATION_CONFIG)
    config["walk_forward"] = {
        "start": "2020-01-01",
        "end": "2021-12-31",
        "train_years": 1,
        "test_months": 6,
        "step_months": 6,
    }
    load_calls = []

    def price_loader(symbol, period):
        load_calls.append((symbol, period))
        return pd.DataFrame({"marker": [1]})

    def baseline_runner(
        symbol,
        start_date,
        end_date,
        config,
        price_df,
        benchmark_df,
    ):
        is_test_window = (
            pd.Timestamp(end_date) - pd.Timestamp(start_date)
        ).days < 300
        difference = 2 if is_test_window else 1
        summary = {
            "ticker": symbol,
            "strategy_return_pct": 7,
            "buy_and_hold_return_pct": 7 - difference,
            "difference_pct": difference,
            "number_of_trades": 4,
        }
        return summary, pd.DataFrame(), price_df

    result = rolling_walk_forward(
        ["AAPL", "MSFT"],
        config=config,
        price_loader=price_loader,
        baseline_runner=baseline_runner,
    )

    assert len(result) == 2
    assert result.iloc[0]["selection"] == "fixed_no_tuning"
    assert result.iloc[0]["test_avg_difference_pct"] == 2
    assert result.iloc[0]["test_beat_buy_hold_count"] == 2
    assert result.iloc[0]["tested_symbols"] == 2
    assert sorted(load_calls) == [
        ("AAPL", "max"),
        ("MSFT", "max"),
        ("SPY", "max"),
    ]


def test_walk_forward_handles_empty_symbols():
    result = rolling_walk_forward(
        [],
        config=deepcopy(DEFAULT_BACKTEST_VALIDATION_CONFIG),
    )

    assert result.empty


def test_walk_forward_report_is_honest_about_historical_folds():
    result = pd.DataFrame(
        [
            {
                "fold": 1,
                "test_avg_strategy_return_pct": 5,
                "test_avg_buy_hold_return_pct": 6,
                "test_avg_difference_pct": -1,
                "test_beat_buy_hold_count": 1,
                "tested_symbols": 3,
            }
        ]
    )

    report = summarize_rolling_walk_forward(result)

    assert "ingen tuning per fold" in report
    assert "ikke den reserverte fremoverskuende OOS-perioden" in report
    assert "ikke stabil positiv relativ avkastning" in report


def test_walk_forward_builds_equal_weight_portfolio_and_regions():
    config = deepcopy(DEFAULT_BACKTEST_VALIDATION_CONFIG)
    config["execution"]["initial_cash"] = 100
    folds = [
        {
            "fold": 1,
            "train_start": pd.Timestamp("2020-01-01"),
            "train_end": pd.Timestamp("2020-12-31"),
            "test_start": pd.Timestamp("2021-01-01"),
            "test_end": pd.Timestamp("2021-06-30"),
        }
    ]
    dates = pd.date_range("2021-01-04", periods=3)

    def price_loader(symbol, period):
        return pd.DataFrame({"marker": [1]})

    def baseline_runner(
        symbol,
        start_date,
        end_date,
        config,
        price_df,
        benchmark_df,
    ):
        is_norway = symbol.endswith(".OL")
        end_value = 110 if is_norway else 90
        summary = {
            "ticker": symbol,
            "strategy_return_pct": end_value - 100,
            "buy_and_hold_return_pct": 0,
            "difference_pct": end_value - 100,
            "number_of_trades": 2,
            "max_drawdown_pct": 10 if not is_norway else 0,
            "buy_and_hold_max_drawdown_pct": 0,
            "sharpe": 1 if is_norway else -1,
            "buy_and_hold_sharpe": 0,
            "sortino": 1 if is_norway else -1,
            "turnover": 1,
            "avg_hold_days": 20,
            "win_rate_pct": 50,
            "gain_loss_ratio": 1,
        }
        analysis = pd.DataFrame(
            {
                "portfolio_value": [100, 100, end_value],
                "buy_and_hold_value": [100, 100, 100],
            },
            index=dates,
        )
        return summary, pd.DataFrame(), analysis

    result = rolling_walk_forward(
        ["AAPL", "DNB.OL"],
        config=config,
        folds=folds,
        price_loader=price_loader,
        baseline_runner=baseline_runner,
    )

    row = result.iloc[0]
    assert row["test_portfolio_return_pct"] == 0
    assert row["test_portfolio_difference_pct"] == 0
    assert row["usa_test_avg_difference_pct"] == -10
    assert row["norway_test_avg_difference_pct"] == 10
    assert pd.isna(row["other_nordics_test_avg_difference_pct"])
