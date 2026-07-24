import math

import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def calculate_performance_metrics(
    equity_curve,
    initial_value=None,
    turnover_notional=0,
    trades_df=None,
):
    equity = pd.to_numeric(
        pd.Series(equity_curve, copy=True),
        errors="coerce",
    ).dropna()
    equity = equity[equity > 0]
    if equity.empty:
        return _empty_metrics()

    start_value = (
        float(initial_value)
        if initial_value is not None
        else float(equity.iloc[0])
    )
    if (
        initial_value is not None
        and isinstance(equity.index, pd.DatetimeIndex)
    ):
        anchor_date = equity.index[0] - pd.Timedelta(days=1)
        equity.loc[anchor_date] = start_value
        equity = equity.sort_index()
    end_value = float(equity.iloc[-1])
    total_return_pct = (end_value / start_value - 1) * 100

    elapsed_days = (
        (equity.index[-1] - equity.index[0]).days
        if isinstance(equity.index, pd.DatetimeIndex)
        else 0
    )
    cagr_pct = None
    if elapsed_days > 0 and start_value > 0:
        cagr_pct = (
            (end_value / start_value) ** (365.25 / elapsed_days) - 1
        ) * 100

    running_peak = equity.cummax()
    drawdown = equity / running_peak - 1
    max_drawdown_pct = abs(float(drawdown.min())) * 100

    daily_returns = equity.pct_change().dropna()
    sharpe = _annualized_sharpe(daily_returns)
    sortino = _annualized_sortino(daily_returns)
    average_equity = float(equity.mean())
    turnover = (
        float(turnover_notional) / average_equity
        if average_equity > 0
        else None
    )
    trade_metrics = _closed_trade_metrics(trades_df)

    return {
        "total_return_pct": _rounded(total_return_pct),
        "cagr_pct": _rounded(cagr_pct),
        "max_drawdown_pct": _rounded(max_drawdown_pct),
        "sharpe": _rounded(sharpe),
        "sortino": _rounded(sortino),
        "turnover": _rounded(turnover),
        **trade_metrics,
    }


def build_equal_weight_curve(
    analysis_frames,
    value_column,
    initial_value,
):
    series = []
    for symbol, frame in analysis_frames.items():
        if frame is None or value_column not in frame.columns:
            continue
        values = pd.to_numeric(
            frame[value_column],
            errors="coerce",
        ).dropna()
        if values.empty:
            continue
        series.append((values / float(initial_value)).rename(symbol))

    if not series:
        return pd.Series(dtype=float)

    aligned = pd.concat(series, axis=1).sort_index().ffill()
    aligned = aligned.dropna(how="any")
    if aligned.empty:
        return pd.Series(dtype=float)
    return aligned.mean(axis=1) * float(initial_value)


def _annualized_sharpe(daily_returns):
    if len(daily_returns) < 2:
        return None
    volatility = float(daily_returns.std(ddof=1))
    if not math.isfinite(volatility) or volatility == 0:
        return None
    return (
        float(daily_returns.mean())
        / volatility
        * math.sqrt(TRADING_DAYS_PER_YEAR)
    )


def _annualized_sortino(daily_returns):
    if len(daily_returns) < 2:
        return None
    downside = daily_returns[daily_returns < 0]
    if downside.empty:
        return None
    downside_deviation = math.sqrt(float((downside ** 2).mean()))
    if not math.isfinite(downside_deviation) or downside_deviation == 0:
        return None
    return (
        float(daily_returns.mean())
        / downside_deviation
        * math.sqrt(TRADING_DAYS_PER_YEAR)
    )


def _closed_trade_metrics(trades_df):
    if (
        trades_df is None
        or trades_df.empty
        or "action" not in trades_df.columns
    ):
        return {
            "closed_trades": 0,
            "win_rate_pct": None,
            "gain_loss_ratio": None,
            "avg_hold_days": None,
        }

    sells = trades_df[trades_df["action"] == "SELL"].copy()
    if sells.empty:
        return {
            "closed_trades": 0,
            "win_rate_pct": None,
            "gain_loss_ratio": None,
            "avg_hold_days": None,
        }

    gains = pd.to_numeric(
        (
            sells["net_gain_pct"]
            if "net_gain_pct" in sells.columns
            else pd.Series(dtype=float)
        ),
        errors="coerce",
    ).dropna()
    holds = pd.to_numeric(
        (
            sells["hold_days"]
            if "hold_days" in sells.columns
            else pd.Series(dtype=float)
        ),
        errors="coerce",
    ).dropna()
    winners = gains[gains > 0]
    losers = gains[gains < 0]
    gain_loss_ratio = None
    if not winners.empty and not losers.empty:
        gain_loss_ratio = float(winners.mean() / abs(losers.mean()))

    return {
        "closed_trades": len(gains),
        "win_rate_pct": (
            _rounded((gains > 0).mean() * 100)
            if not gains.empty
            else None
        ),
        "gain_loss_ratio": _rounded(gain_loss_ratio),
        "avg_hold_days": (
            _rounded(float(holds.mean()))
            if not holds.empty
            else None
        ),
    }


def _empty_metrics():
    return {
        "total_return_pct": None,
        "cagr_pct": None,
        "max_drawdown_pct": None,
        "sharpe": None,
        "sortino": None,
        "turnover": None,
        "closed_trades": 0,
        "win_rate_pct": None,
        "gain_loss_ratio": None,
        "avg_hold_days": None,
    }


def _rounded(value):
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), 2)
