import pandas as pd

from src.config import load_backtest_config
from src.signal_backtest import backtest_signal_watchlist


def rolling_walk_forward(
    symbols,
    train_periods=None,
    test_periods=None,
    configs=None,
):
    if train_periods is None:
        train_periods = ["1y", "18mo"]

    if test_periods is None:
        test_periods = ["6mo", "1y"]

    if configs is None:
        configs = _default_configs()

    rows = []

    for train_period in train_periods:
        print(f"\nTRAIN: {train_period}")

        train_rows = []

        for config in configs:
            print(f"  Train config: {config['name']}")

            train_config = {
                **config,
                "period": train_period,
            }

            result = backtest_signal_watchlist(
                symbols=symbols,
                **_config_kwargs(train_config),
            )

            valid = _valid_rows(result)

            if valid.empty:
                continue

            train_rows.append(
                summarize_result(
                    config_name=config["name"],
                    period=train_period,
                    result=valid,
                )
            )

        if not train_rows:
            continue

        train_df = pd.DataFrame(train_rows).sort_values(
            by=["avg_difference_pct", "avg_strategy_return_pct"],
            ascending=[False, False],
        )

        best_name = train_df.iloc[0]["config_name"]

        best_config = next(
            config for config in configs
            if config["name"] == best_name
        )

        print(f"BEST TRAIN CONFIG: {best_name}")

        for test_period in test_periods:
            print(f"  TEST: {test_period}")

            test_config = {
                **best_config,
                "period": test_period,
            }

            result = backtest_signal_watchlist(
                symbols=symbols,
                **_config_kwargs(test_config),
            )

            valid = _valid_rows(result)

            if valid.empty:
                continue

            test_summary = summarize_result(
                config_name=best_name,
                period=test_period,
                result=valid,
            )

            rows.append({
                "train_period": train_period,
                "test_period": test_period,
                "selected_config": best_name,
                "train_avg_difference_pct": train_df.iloc[0]["avg_difference_pct"],
                "test_avg_strategy_return_pct": test_summary["avg_strategy_return_pct"],
                "test_avg_buy_hold_return_pct": test_summary["avg_buy_hold_return_pct"],
                "test_avg_difference_pct": test_summary["avg_difference_pct"],
                "test_avg_trades": test_summary["avg_trades"],
                "test_beat_buy_hold_count": test_summary["beat_buy_hold_count"],
                "tested_symbols": test_summary["tested_symbols"],
            })

    return pd.DataFrame(rows).sort_values(
        by=["test_avg_difference_pct", "test_avg_strategy_return_pct"],
        ascending=[False, False],
    ).reset_index(drop=True)


def summarize_result(config_name, period, result):
    return {
        "config_name": config_name,
        "period": period,
        "avg_strategy_return_pct": round(result["strategy_return_pct"].mean(), 2),
        "avg_buy_hold_return_pct": round(result["buy_and_hold_return_pct"].mean(), 2),
        "avg_difference_pct": round(result["difference_pct"].mean(), 2),
        "avg_trades": round(result["number_of_trades"].mean(), 2),
        "beat_buy_hold_count": int((result["difference_pct"] > 0).sum()),
        "tested_symbols": len(result),
    }


def _default_configs():
    config = load_backtest_config()
    base = config["baseline"]

    return [
        {**base, "name": "baseline"},
        {**base, "name": "stricter_buy", "min_buy_score": 80},
        {**base, "name": "stronger_rs", "min_buy_relative_strength": 3},
        {**base, "name": "risk_on", "require_risk_on": True},
    ]


def _config_kwargs(config):
    return {
        key: value
        for key, value in config.items()
        if key != "name"
    }


def _valid_rows(result):
    if result.empty:
        return result

    if "error" in result.columns:
        result = result[result["error"].isna()]

    return result.dropna(
        subset=[
            "strategy_return_pct",
            "buy_and_hold_return_pct",
            "difference_pct",
        ]
    )