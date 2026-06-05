import pandas as pd

from src.signal_backtest import backtest_signal_watchlist


def optimize_obx(symbols):
    configs = [
        {
            "name": "baseline",
            "min_hold_days": 60,
            "stop_loss_pct": 0.12,
            "trailing_sma": "sma100",
            "min_buy_score": 70,
            "min_buy_relative_strength": 0,
            "require_risk_on": False,
        },
        {
            "name": "tighter_stop",
            "min_hold_days": 60,
            "stop_loss_pct": 0.08,
            "trailing_sma": "sma100",
            "min_buy_score": 70,
            "min_buy_relative_strength": 0,
            "require_risk_on": False,
        },
        {
            "name": "shorter_hold",
            "min_hold_days": 30,
            "stop_loss_pct": 0.12,
            "trailing_sma": "sma100",
            "min_buy_score": 70,
            "min_buy_relative_strength": 0,
            "require_risk_on": False,
        },
        {
            "name": "stronger_rs",
            "min_hold_days": 60,
            "stop_loss_pct": 0.12,
            "trailing_sma": "sma100",
            "min_buy_score": 70,
            "min_buy_relative_strength": 3,
            "require_risk_on": False,
        },
        {
            "name": "sma50_exit",
            "min_hold_days": 60,
            "stop_loss_pct": 0.12,
            "trailing_sma": "sma50",
            "min_buy_score": 70,
            "min_buy_relative_strength": 0,
            "require_risk_on": False,
        },
        {
            "name": "stricter_buy",
            "min_hold_days": 60,
            "stop_loss_pct": 0.12,
            "trailing_sma": "sma100",
            "min_buy_score": 80,
            "min_buy_relative_strength": 0,
            "require_risk_on": False,
        },
    ]

    rows = []

    for config in configs:
        print(f"Tester OBX-konfig: {config['name']}")

        result = backtest_signal_watchlist(
            symbols=symbols,
            period="2y",
            initial_cash=10000,
            min_hold_days=config["min_hold_days"],
            stop_loss_pct=config["stop_loss_pct"],
            trailing_sma=config["trailing_sma"],
            min_buy_score=config["min_buy_score"],
            min_buy_relative_strength=config["min_buy_relative_strength"],
            require_risk_on=config["require_risk_on"],
        )

        valid = (
            result[result["error"].isna()]
            if "error" in result.columns
            else result
        )

        rows.append({
            **config,
            "avg_strategy_return_pct": round(valid["strategy_return_pct"].mean(), 2),
            "avg_buy_hold_return_pct": round(valid["buy_and_hold_return_pct"].mean(), 2),
            "avg_difference_pct": round(valid["difference_pct"].mean(), 2),
            "avg_trades": round(valid["number_of_trades"].mean(), 2),
            "beat_buy_hold_count": int((valid["difference_pct"] > 0).sum()),
            "tested_symbols": len(valid),
        })

    return pd.DataFrame(rows).sort_values(
        by=["avg_difference_pct", "avg_strategy_return_pct"],
        ascending=[False, False],
    ).reset_index(drop=True)