import pandas as pd

from src.config import load_backtest_validation_config
from src.performance_metrics import (
    build_equal_weight_curve,
    calculate_performance_metrics,
)
from src.signal_backtest import _get_price_data
from src.technical_baseline import (
    backtest_technical_baseline,
    region_for_symbol,
)
from src.technicals import get_benchmark_for_symbol


def build_walk_forward_folds(walk_forward_config):
    try:
        overall_start = pd.Timestamp(walk_forward_config["start"])
        overall_end = pd.Timestamp(walk_forward_config["end"])
        train_years = int(walk_forward_config["train_years"])
        test_months = int(walk_forward_config["test_months"])
        step_months = int(walk_forward_config["step_months"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Ugyldig walk-forward-konfigurasjon.") from exc

    if overall_start > overall_end:
        raise ValueError("Walk-forward-start kan ikke være etter sluttdato.")
    if train_years <= 0 or test_months <= 0 or step_months <= 0:
        raise ValueError("Walk-forward-vinduer må være positive.")

    folds = []
    train_start = overall_start
    fold_number = 1

    while True:
        train_end = (
            train_start + pd.DateOffset(years=train_years)
            - pd.Timedelta(days=1)
        )
        test_start = train_end + pd.Timedelta(days=1)
        test_end = (
            test_start + pd.DateOffset(months=test_months)
            - pd.Timedelta(days=1)
        )
        if test_end > overall_end:
            break

        folds.append(
            {
                "fold": fold_number,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
            }
        )
        fold_number += 1
        train_start += pd.DateOffset(months=step_months)

    if not folds:
        raise ValueError(
            "Walk-forward-perioden er for kort for valgte vinduer."
        )
    return folds


def rolling_walk_forward(
    symbols,
    config=None,
    folds=None,
    price_loader=None,
    baseline_runner=None,
    **legacy_options,
):
    if legacy_options:
        unsupported = ", ".join(sorted(legacy_options))
        raise ValueError(
            "Den validerte walk-forward støtter ikke gamle valg: "
            f"{unsupported}."
        )

    config = config or load_backtest_validation_config()
    selected_folds = (
        build_walk_forward_folds(config["walk_forward"])
        if folds is None
        else list(folds)
    )
    if not selected_folds:
        return pd.DataFrame()

    load_prices = price_loader or _get_price_data
    run_baseline = baseline_runner or backtest_technical_baseline
    price_cache = {}
    benchmark_cache = {}
    results_by_fold = {
        fold["fold"]: {
            "train": [],
            "test": [],
            "train_frames": {},
            "test_frames": {},
            "errors": [],
        }
        for fold in selected_folds
    }

    for symbol in symbols:
        benchmark_symbol = get_benchmark_for_symbol(symbol)
        try:
            if symbol not in price_cache:
                price_cache[symbol] = load_prices(symbol, "max")
            if benchmark_symbol not in benchmark_cache:
                benchmark_cache[benchmark_symbol] = load_prices(
                    benchmark_symbol,
                    "max",
                )
        except Exception as exc:
            for fold in selected_folds:
                results_by_fold[fold["fold"]]["errors"].append(
                    f"{symbol}: {exc}"
                )
            continue

        for fold in selected_folds:
            fold_result = results_by_fold[fold["fold"]]
            for phase in ("train", "test"):
                try:
                    summary, _, analysis_frame = run_baseline(
                        symbol,
                        fold[f"{phase}_start"],
                        fold[f"{phase}_end"],
                        config=config,
                        price_df=price_cache[symbol],
                        benchmark_df=benchmark_cache[benchmark_symbol],
                    )
                    summary.setdefault(
                        "region",
                        region_for_symbol(symbol),
                    )
                    fold_result[phase].append(summary)
                    fold_result[f"{phase}_frames"][symbol] = (
                        analysis_frame
                    )
                except Exception as exc:
                    fold_result["errors"].append(
                        f"{symbol} {phase}: {exc}"
                    )

    rows = []
    for fold in selected_folds:
        fold_result = results_by_fold[fold["fold"]]
        train = _valid_rows(pd.DataFrame(fold_result["train"]))
        test = _valid_rows(pd.DataFrame(fold_result["test"]))
        if train.empty or test.empty:
            continue

        train_summary = summarize_result(train)
        test_summary = summarize_result(test)
        portfolio_summary = _portfolio_summary(
            fold_result["test_frames"],
            config["execution"]["initial_cash"],
        )
        rows.append(
            {
                "fold": fold["fold"],
                "baseline": "technical_only_v1",
                "selection": "fixed_no_tuning",
                "train_start": fold["train_start"].date().isoformat(),
                "train_end": fold["train_end"].date().isoformat(),
                "test_start": fold["test_start"].date().isoformat(),
                "test_end": fold["test_end"].date().isoformat(),
                "train_avg_strategy_return_pct": train_summary[
                    "avg_strategy_return_pct"
                ],
                "train_avg_buy_hold_return_pct": train_summary[
                    "avg_buy_hold_return_pct"
                ],
                "train_avg_difference_pct": train_summary[
                    "avg_difference_pct"
                ],
                "test_avg_strategy_return_pct": test_summary[
                    "avg_strategy_return_pct"
                ],
                "test_avg_buy_hold_return_pct": test_summary[
                    "avg_buy_hold_return_pct"
                ],
                "test_avg_difference_pct": test_summary[
                    "avg_difference_pct"
                ],
                "test_avg_trades": test_summary["avg_trades"],
                "test_avg_max_drawdown_pct": test_summary[
                    "avg_max_drawdown_pct"
                ],
                "test_avg_buy_hold_max_drawdown_pct": test_summary[
                    "avg_buy_hold_max_drawdown_pct"
                ],
                "test_avg_sharpe": test_summary["avg_sharpe"],
                "test_avg_buy_hold_sharpe": test_summary[
                    "avg_buy_hold_sharpe"
                ],
                "test_avg_sortino": test_summary["avg_sortino"],
                "test_avg_turnover": test_summary["avg_turnover"],
                "test_avg_hold_days": test_summary[
                    "avg_hold_days"
                ],
                "test_avg_win_rate_pct": test_summary[
                    "avg_win_rate_pct"
                ],
                "test_avg_gain_loss_ratio": test_summary[
                    "avg_gain_loss_ratio"
                ],
                "test_beat_buy_hold_count": test_summary[
                    "beat_buy_hold_count"
                ],
                "tested_symbols": test_summary["tested_symbols"],
                "error_count": len(fold_result["errors"]),
                **_regional_columns(test),
                **portfolio_summary,
            }
        )

    return pd.DataFrame(rows).sort_values(
        by="fold",
    ).reset_index(drop=True) if rows else pd.DataFrame()


def rolling_walk_forward_strategy_specific(symbols, **kwargs):
    return rolling_walk_forward(symbols, **kwargs)


def summarize_result(result):
    valid = _valid_rows(result)
    if valid.empty:
        return {
            "avg_strategy_return_pct": 0,
            "avg_buy_hold_return_pct": 0,
            "avg_difference_pct": 0,
            "avg_trades": 0,
            "avg_max_drawdown_pct": None,
            "avg_buy_hold_max_drawdown_pct": None,
            "avg_sharpe": None,
            "avg_buy_hold_sharpe": None,
            "avg_sortino": None,
            "avg_turnover": None,
            "avg_hold_days": None,
            "avg_win_rate_pct": None,
            "avg_gain_loss_ratio": None,
            "beat_buy_hold_count": 0,
            "tested_symbols": 0,
        }

    return {
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
        "avg_trades": round(valid["number_of_trades"].mean(), 2),
        "avg_max_drawdown_pct": _mean(valid, "max_drawdown_pct"),
        "avg_buy_hold_max_drawdown_pct": _mean(
            valid,
            "buy_and_hold_max_drawdown_pct",
        ),
        "avg_sharpe": _mean(valid, "sharpe"),
        "avg_buy_hold_sharpe": _mean(
            valid,
            "buy_and_hold_sharpe",
        ),
        "avg_sortino": _mean(valid, "sortino"),
        "avg_turnover": _mean(valid, "turnover"),
        "avg_hold_days": _mean(valid, "avg_hold_days"),
        "avg_win_rate_pct": _mean(valid, "win_rate_pct"),
        "avg_gain_loss_ratio": _mean(valid, "gain_loss_ratio"),
        "beat_buy_hold_count": int((valid["difference_pct"] > 0).sum()),
        "tested_symbols": len(valid),
    }


def _regional_columns(result):
    columns = {}
    for region in ("usa", "norway", "other_nordics"):
        region_rows = result[result["region"] == region]
        columns[f"{region}_tested_symbols"] = len(region_rows)
        columns[f"{region}_test_avg_difference_pct"] = _mean(
            region_rows,
            "difference_pct",
        )
        columns[f"{region}_test_avg_strategy_return_pct"] = _mean(
            region_rows,
            "strategy_return_pct",
        )
        columns[f"{region}_test_avg_buy_hold_return_pct"] = _mean(
            region_rows,
            "buy_and_hold_return_pct",
        )
    return columns


def _portfolio_summary(analysis_frames, initial_cash):
    strategy_curve = build_equal_weight_curve(
        analysis_frames,
        "portfolio_value",
        initial_cash,
    )
    benchmark_curve = build_equal_weight_curve(
        analysis_frames,
        "buy_and_hold_value",
        initial_cash,
    )
    if strategy_curve.empty or benchmark_curve.empty:
        return {
            "test_portfolio_return_pct": None,
            "test_portfolio_buy_hold_return_pct": None,
            "test_portfolio_difference_pct": None,
            "test_portfolio_max_drawdown_pct": None,
            "test_portfolio_buy_hold_max_drawdown_pct": None,
            "test_portfolio_sharpe": None,
            "test_portfolio_buy_hold_sharpe": None,
            "test_portfolio_sortino": None,
            "test_portfolio_buy_hold_sortino": None,
        }

    strategy = calculate_performance_metrics(
        strategy_curve,
        initial_value=initial_cash,
    )
    benchmark = calculate_performance_metrics(
        benchmark_curve,
        initial_value=initial_cash,
    )
    return {
        "test_portfolio_return_pct": strategy["total_return_pct"],
        "test_portfolio_buy_hold_return_pct": benchmark[
            "total_return_pct"
        ],
        "test_portfolio_difference_pct": round(
            strategy["total_return_pct"]
            - benchmark["total_return_pct"],
            2,
        ),
        "test_portfolio_max_drawdown_pct": strategy[
            "max_drawdown_pct"
        ],
        "test_portfolio_buy_hold_max_drawdown_pct": benchmark[
            "max_drawdown_pct"
        ],
        "test_portfolio_sharpe": strategy["sharpe"],
        "test_portfolio_buy_hold_sharpe": benchmark["sharpe"],
        "test_portfolio_sortino": strategy["sortino"],
        "test_portfolio_buy_hold_sortino": benchmark["sortino"],
    }


def _mean(result, column):
    if result is None or result.empty or column not in result.columns:
        return None
    values = pd.to_numeric(result[column], errors="coerce").dropna()
    if values.empty:
        return None
    return round(float(values.mean()), 2)


def _valid_rows(result):
    required_columns = [
        "strategy_return_pct",
        "buy_and_hold_return_pct",
        "difference_pct",
        "number_of_trades",
    ]
    if result is None or result.empty:
        return pd.DataFrame()

    valid = result.copy()
    if "error" in valid.columns:
        valid = valid[valid["error"].isna()]
    if not all(column in valid.columns for column in required_columns):
        return pd.DataFrame()
    return valid.dropna(subset=required_columns)
