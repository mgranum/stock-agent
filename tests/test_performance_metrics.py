import pandas as pd
import pytest

from src.performance_metrics import (
    build_equal_weight_curve,
    calculate_performance_metrics,
)


def test_performance_metrics_for_known_equity_curve():
    curve = pd.Series(
        [100, 110, 88, 121],
        index=pd.date_range("2024-01-01", periods=4),
    )
    trades = pd.DataFrame(
        [
            {
                "action": "SELL",
                "net_gain_pct": 10,
                "hold_days": 20,
            },
            {
                "action": "SELL",
                "net_gain_pct": -5,
                "hold_days": 10,
            },
        ]
    )

    metrics = calculate_performance_metrics(
        curve,
        initial_value=100,
        turnover_notional=200,
        trades_df=trades,
    )

    assert metrics["total_return_pct"] == 21
    assert metrics["max_drawdown_pct"] == 20
    assert metrics["turnover"] == pytest.approx(1.93, abs=0.01)
    assert metrics["closed_trades"] == 2
    assert metrics["win_rate_pct"] == 50
    assert metrics["gain_loss_ratio"] == 2
    assert metrics["avg_hold_days"] == 15


def test_empty_equity_curve_returns_unavailable_metrics():
    metrics = calculate_performance_metrics(pd.Series(dtype=float))

    assert metrics["total_return_pct"] is None
    assert metrics["max_drawdown_pct"] is None
    assert metrics["closed_trades"] == 0


def test_closed_trade_metrics_tolerate_missing_optional_columns():
    metrics = calculate_performance_metrics(
        pd.Series(
            [100, 101],
            index=pd.date_range("2024-01-01", periods=2),
        ),
        initial_value=100,
        trades_df=pd.DataFrame([{"action": "SELL"}]),
    )

    assert metrics["closed_trades"] == 0
    assert metrics["win_rate_pct"] is None


def test_equal_weight_curve_combines_complete_sleeves():
    dates = pd.date_range("2024-01-01", periods=3)
    frames = {
        "A": pd.DataFrame(
            {"portfolio_value": [100, 110, 120]},
            index=dates,
        ),
        "B": pd.DataFrame(
            {"portfolio_value": [100, 90, 80]},
            index=dates,
        ),
    }

    curve = build_equal_weight_curve(
        frames,
        "portfolio_value",
        initial_value=100,
    )

    assert curve.tolist() == [100, 100, 100]


def test_equal_weight_curve_requires_requested_column():
    curve = build_equal_weight_curve(
        {"A": pd.DataFrame({"other": [1]})},
        "portfolio_value",
        initial_value=100,
    )

    assert curve.empty
