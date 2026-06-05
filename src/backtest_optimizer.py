import pandas as pd

from src.signal_backtest import backtest_signal_watchlist


def optimize_signal_backtest(
    symbols,
    period="2y",
    initial_cash=10000,
):
    rows = []

    min_hold_days_options = [20, 30, 45, 60]
    stop_loss_pct_options = [0.10, 0.12, 0.15]
    trailing_sma_options = ["sma50", "sma100"]

    for min_hold_days in min_hold_days_options:
        for stop_loss_pct in stop_loss_pct_options:
            for trailing_sma in trailing_sma_options:
                print(
                    f"Tester min_hold_days={min_hold_days}, "
                    f"stop_loss_pct={stop_loss_pct}, "
                    f"trailing_sma={trailing_sma}"
                )

                result = backtest_signal_watchlist(
                    symbols=symbols,
                    period=period,
                    initial_cash=initial_cash,
                    min_hold_days=min_hold_days,
                    stop_loss_pct=stop_loss_pct,
                    trailing_sma=trailing_sma,
                )

                valid = result[result.get("error").isna()] if "error" in result.columns else result

                rows.append({
                    "min_hold_days": min_hold_days,
                    "stop_loss_pct": stop_loss_pct,
                    "trailing_sma": trailing_sma,
                    "avg_strategy_return_pct": round(
                        valid["strategy_return_pct"].mean(),
                        2,
                    ),
                    "avg_buy_hold_return_pct": round(
                        valid["buy_and_hold_return_pct"].mean(),
                        2,
                    ),
                    "avg_difference_pct": round(
                        valid["difference_pct"].mean(),
                        2,
                    ),
                    "avg_trades": round(
                        valid["number_of_trades"].mean(),
                        2,
                    ),
                    "beat_buy_hold_count": int(
                        (valid["difference_pct"] > 0).sum()
                    ),
                    "tested_symbols": len(valid),
                })

    return pd.DataFrame(rows).sort_values(
        by=[
            "avg_difference_pct",
            "avg_strategy_return_pct",
        ],
        ascending=[False, False],
    ).reset_index(drop=True)