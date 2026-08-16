import math
from hashlib import sha256
import json

import pandas as pd

from src.config import load_backtest_validation_config
from src.indicators import add_indicators
from src.performance_metrics import calculate_performance_metrics
from src.signal_backtest import (
    _get_exit_reason,
    _get_price_data,
    _market_regime_at,
    _technical_result_at,
)
from src.technicals import get_benchmark_for_symbol


NORDIC_SUFFIXES = (".OL", ".ST", ".CO", ".HE")
TECHNICAL_BASELINE_VERSION = "technical_only_v1"
TECHNICAL_REFERENCE_VERSION = "trend_momentum_v1"
TECHNICAL_BASELINE_REQUIRED_TREND = "STERK OPPTREND"
REQUIRED_PRICE_COLUMNS = {
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
}


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def technical_baseline_buy_signal(technical, market_regime, strategy_config):
    """Apply the frozen technical-only entry rule to signal-time inputs."""
    technical_score = _finite_number(technical.get("technical_score"))
    relative_strength = _finite_number(technical.get("relative_strength_20d"))
    trend_regime = str(technical.get("trend_regime") or "").strip()
    if technical_score is None or relative_strength is None or not trend_regime:
        raise ValueError("Teknisk referanse mangler signaldata.")

    risk_on_ok = (
        market_regime == "RISK_ON"
        or not bool(strategy_config["require_risk_on"])
    )
    return (
        risk_on_ok
        and technical_score >= float(strategy_config["min_technical_score"])
        and trend_regime == TECHNICAL_BASELINE_REQUIRED_TREND
        and relative_strength
        >= float(strategy_config["min_buy_relative_strength"])
    )


def trend_momentum_reference_signal(technical, min_relative_strength=0.0):
    """Apply the deliberately simple prospective trend/momentum rule."""
    relative_strength = _finite_number(technical.get("relative_strength_20d"))
    trend_regime = str(technical.get("trend_regime") or "").strip()
    if relative_strength is None or not trend_regime:
        raise ValueError("Trend-/momentumreferansen mangler signaldata.")
    return (
        trend_regime == TECHNICAL_BASELINE_REQUIRED_TREND
        and relative_strength >= float(min_relative_strength)
    )


def build_trend_momentum_reference_snapshot(
    technical,
    *,
    config=None,
):
    """Freeze the simple technical reference decision at signal time."""
    config = config or load_backtest_validation_config()
    strategy_config = config.get("strategy") or {}
    try:
        rule = {
            "required_trend_regime": TECHNICAL_BASELINE_REQUIRED_TREND,
            "min_relative_strength_20d": float(
                strategy_config["min_buy_relative_strength"]
            ),
        }
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "version": TECHNICAL_REFERENCE_VERSION,
            "status": "unavailable",
            "reason": f"Ugyldig teknisk referansekonfigurasjon: {exc}",
        }

    encoded_rule = json.dumps(
        rule,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    technical = technical if hasattr(technical, "get") else {}
    inputs = {
        "trend_regime": str(technical.get("trend_regime") or "").strip() or None,
        "relative_strength_20d": _finite_number(
            technical.get("relative_strength_20d")
        ),
    }
    if any(
        inputs[key] is None
        for key in (
            "trend_regime",
            "relative_strength_20d",
        )
    ):
        return {
            "version": TECHNICAL_REFERENCE_VERSION,
            "status": "unavailable",
            "reason": "Signalgrunnlaget mangler tekniske referanseverdier.",
            "rule_fingerprint": sha256(encoded_rule).hexdigest()[:16],
            "rule": rule,
            "inputs": inputs,
        }

    buy = trend_momentum_reference_signal(
        inputs,
        rule["min_relative_strength_20d"],
    )
    return {
        "version": TECHNICAL_REFERENCE_VERSION,
        "status": "complete",
        "action": "buy" if buy else "cash",
        "rule_fingerprint": sha256(encoded_rule).hexdigest()[:16],
        "rule": rule,
        "inputs": inputs,
    }


def validate_chronological_datasets(datasets):
    if not isinstance(datasets, dict) or not datasets:
        raise ValueError("Datasettkonfigurasjonen kan ikke være tom.")

    parsed = []
    for name, bounds in datasets.items():
        if not isinstance(bounds, dict):
            raise ValueError(f"Datasettet '{name}' må ha start og end.")

        try:
            start = pd.Timestamp(bounds["start"])
            end = pd.Timestamp(bounds["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Datasettet '{name}' har ugyldig start eller end."
            ) from exc

        if start > end:
            raise ValueError(
                f"Datasettet '{name}' starter etter sluttdatoen."
            )
        parsed.append((name, start, end))

    parsed.sort(key=lambda item: item[1])
    for previous, current in zip(parsed, parsed[1:]):
        if current[1] <= previous[2]:
            raise ValueError(
                f"Datasettene '{previous[0]}' og '{current[0]}' overlapper."
            )

    return {
        name: {
            "start": start,
            "end": end,
        }
        for name, start, end in parsed
    }


def _adjust_ohlc_prices(df):
    missing = REQUIRED_PRICE_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(
            "Prisdata mangler kolonner: " + ", ".join(sorted(missing))
        )

    adjusted = df.copy()
    valid_close = adjusted["close"].where(adjusted["close"] != 0)
    adjustment_factor = adjusted["adjusted_close"] / valid_close

    if adjustment_factor.isna().all():
        raise ValueError("Prisdata mangler gyldig justeringsfaktor.")

    adjustment_factor = adjustment_factor.ffill().bfill()
    for column in ("open", "high", "low", "close"):
        adjusted[column] = adjusted[column] * adjustment_factor

    return adjusted


def _prepare_prices(df, use_adjusted_prices):
    if df is None or df.empty:
        raise ValueError("Prisdata kan ikke være tom.")

    prepared = (
        _adjust_ohlc_prices(df)
        if use_adjusted_prices
        else df.copy()
    )
    return add_indicators(prepared)


def _cost_profile(symbol, costs):
    market = (
        "nordics"
        if symbol.upper().endswith(NORDIC_SUFFIXES)
        else "usa"
    )
    profile = costs.get(market)
    if not isinstance(profile, dict):
        raise ValueError(f"Mangler kostnadsprofil for '{market}'.")

    values = {
        "market": market,
        "commission_pct": float(profile.get("commission_pct", 0)),
        "minimum_commission": float(
            profile.get("minimum_commission", 0)
        ),
        "spread_pct_per_side": float(
            costs.get("spread_pct_per_side", 0)
        ),
        "fx_pct_per_side": float(profile.get("fx_pct_per_side", 0)),
    }

    if any(value < 0 for key, value in values.items() if key != "market"):
        raise ValueError("Kostnadsantakelser kan ikke være negative.")
    return values


def region_for_symbol(symbol):
    upper = symbol.upper()
    if upper.endswith(".OL"):
        return "norway"
    if upper.endswith((".ST", ".CO", ".HE")):
        return "other_nordics"
    return "usa"


def _execution(symbol, side, raw_price, shares, costs):
    if side not in {"BUY", "SELL"}:
        raise ValueError("Handelssiden må være BUY eller SELL.")
    if shares <= 0 or not math.isfinite(raw_price) or raw_price <= 0:
        raise ValueError("Handelen krever positiv pris og antall aksjer.")

    profile = _cost_profile(symbol, costs)
    direction = 1 if side == "BUY" else -1
    price_impact_pct = (
        profile["spread_pct_per_side"]
        + profile["fx_pct_per_side"]
    )
    execution_price = raw_price * (1 + direction * price_impact_pct)
    notional = execution_price * shares
    commission = max(
        notional * profile["commission_pct"],
        profile["minimum_commission"],
    )
    cash_change = (
        -(notional + commission)
        if side == "BUY"
        else notional - commission
    )

    return {
        **profile,
        "raw_price": raw_price,
        "execution_price": execution_price,
        "notional": notional,
        "commission": commission,
        "cash_change": cash_change,
        "total_cost": (
            abs(execution_price - raw_price) * shares + commission
        ),
    }


def _affordable_shares(symbol, cash, raw_price, costs):
    profile = _cost_profile(symbol, costs)
    price_impact_pct = (
        profile["spread_pct_per_side"]
        + profile["fx_pct_per_side"]
    )
    execution_price = raw_price * (1 + price_impact_pct)
    estimate = math.floor(
        (cash - profile["minimum_commission"])
        / (
            execution_price
            * (1 + profile["commission_pct"])
        )
    )

    shares = max(0, estimate)
    while shares > 0:
        trade = _execution(symbol, "BUY", raw_price, shares, costs)
        if cash + trade["cash_change"] >= -1e-9:
            return shares
        shares -= 1
    return 0


def _liquidation_value(symbol, cash, shares, raw_price, costs):
    if shares <= 0:
        return cash
    return cash + _execution(
        symbol,
        "SELL",
        raw_price,
        shares,
        costs,
    )["cash_change"]


def _buy_and_hold_curve(
    symbol,
    initial_cash,
    prices,
    eligible_indices,
    costs,
):
    first_i = eligible_indices[0]
    shares = _affordable_shares(
        symbol,
        initial_cash,
        prices.iloc[first_i]["open"],
        costs,
    )
    if shares == 0:
        return pd.Series(
            initial_cash,
            index=prices.index[eligible_indices],
            dtype=float,
        )

    buy = _execution(
        symbol,
        "BUY",
        prices.iloc[first_i]["open"],
        shares,
        costs,
    )
    cash = initial_cash + buy["cash_change"]
    return pd.Series(
        {
            prices.index[i]: _liquidation_value(
                symbol,
                cash,
                shares,
                prices.iloc[i]["close"],
                costs,
            )
            for i in eligible_indices
        },
        dtype=float,
    )


def backtest_technical_baseline(
    symbol,
    start_date,
    end_date,
    config=None,
    price_df=None,
    benchmark_df=None,
):
    config = config or load_backtest_validation_config()
    execution_config = config["execution"]
    strategy_config = config["strategy"]
    costs = config["costs"]

    if execution_config.get("signal_price") != "close":
        raise ValueError("Baselinen støtter bare signal på close.")
    if execution_config.get("execution_price") != "next_open":
        raise ValueError("Baselinen støtter bare utførelse på neste open.")

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if start > end:
        raise ValueError("Startdato kan ikke være etter sluttdato.")

    raw_prices = (
        _get_price_data(symbol, "max")
        if price_df is None
        else price_df
    )
    benchmark_symbol = get_benchmark_for_symbol(symbol)
    raw_benchmark = (
        _get_price_data(benchmark_symbol, "max")
        if benchmark_df is None
        else benchmark_df
    )
    prices = _prepare_prices(
        raw_prices,
        execution_config.get("use_adjusted_prices", True),
    )
    benchmark = _prepare_prices(
        raw_benchmark,
        execution_config.get("use_adjusted_prices", True),
    )

    eligible_indices = [
        i
        for i in range(121, len(prices))
        if start <= prices.index[i] <= end
        and prices.index[i - 1] >= start
    ]
    if not eligible_indices:
        raise ValueError(
            f"Ingen evaluerbare handelsdager for {symbol} i perioden."
        )

    initial_cash = float(execution_config["initial_cash"])
    if not math.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("Startkapital må være et positivt tall.")
    cash = initial_cash
    shares = 0
    entry_price = None
    entry_date = None
    entry_cash_outflow = None
    trades = []
    total_costs = 0.0
    turnover_notional = 0.0
    equity_values = {}

    for execution_i in eligible_indices:
        signal_i = execution_i - 1
        signal_row = prices.iloc[signal_i]
        execution_row = prices.iloc[execution_i]
        signal_date = prices.index[signal_i]
        execution_date = prices.index[execution_i]
        raw_execution_price = execution_row["open"]

        if (
            pd.isna(signal_row["sma100"])
            or pd.isna(signal_row["atr14"])
            or pd.isna(raw_execution_price)
        ):
            continue

        technical = _technical_result_at(
            prices,
            benchmark,
            benchmark_symbol,
            signal_i,
        )
        market_regime = _market_regime_at(
            benchmark,
            signal_date,
        )["market_regime"]
        buy_signal = (
            shares == 0
            and technical_baseline_buy_signal(
                technical,
                market_regime,
                strategy_config,
            )
        )

        if shares > 0:
            hold_days = (signal_date - entry_date).days
            exit_reason = _get_exit_reason(
                price=signal_row["close"],
                recommendation="HOLD / OBSERVER",
                trend_regime=technical["trend_regime"],
                hard_stop=entry_price
                * (1 - strategy_config["stop_loss_pct"]),
                trailing_stop=signal_row[
                    strategy_config["trailing_sma"]
                ],
                hold_days=hold_days,
                min_hold_days=strategy_config["min_hold_days"],
            )
        else:
            hold_days = 0
            exit_reason = None

        if buy_signal:
            trade_shares = _affordable_shares(
                symbol,
                cash,
                raw_execution_price,
                costs,
            )
            if trade_shares == 0:
                continue

            execution = _execution(
                symbol,
                "BUY",
                raw_execution_price,
                trade_shares,
                costs,
            )
            cash += execution["cash_change"]
            shares = trade_shares
            entry_price = execution["execution_price"]
            entry_date = execution_date
            entry_cash_outflow = abs(execution["cash_change"])
            total_costs += execution["total_cost"]
            turnover_notional += execution["notional"]
            trades.append(
                _trade_row(
                    signal_date,
                    execution_date,
                    "BUY",
                    shares,
                    cash,
                    technical,
                    market_regime,
                    "Teknisk score + sterk trend",
                    execution,
                    0,
                )
            )
        elif shares > 0 and exit_reason:
            execution = _execution(
                symbol,
                "SELL",
                raw_execution_price,
                shares,
                costs,
            )
            gain_pct = (
                (execution["execution_price"] - entry_price)
                / entry_price
            ) * 100
            net_gain_pct = (
                (
                    execution["cash_change"] - entry_cash_outflow
                )
                / entry_cash_outflow
            ) * 100
            cash += execution["cash_change"]
            total_costs += execution["total_cost"]
            turnover_notional += execution["notional"]
            trades.append(
                _trade_row(
                    signal_date,
                    execution_date,
                    "SELL",
                    shares,
                    cash,
                    technical,
                    market_regime,
                    exit_reason,
                    execution,
                    hold_days,
                    gain_pct,
                    net_gain_pct,
                )
            )
            shares = 0
            entry_price = None
            entry_date = None
            entry_cash_outflow = None

        equity_values[execution_date] = _liquidation_value(
            symbol,
            cash,
            shares,
            execution_row["close"],
            costs,
        )

    first_i = eligible_indices[0]
    last_i = eligible_indices[-1]
    final_close = prices.iloc[last_i]["close"]
    equity_curve = pd.Series(equity_values, dtype=float).sort_index()
    if equity_curve.empty:
        raise ValueError(
            f"Ingen gyldige verdsettelsesdager for {symbol} i perioden."
        )
    buy_and_hold_curve = _buy_and_hold_curve(
        symbol,
        initial_cash,
        prices,
        eligible_indices,
        costs,
    )
    final_value = float(equity_curve.iloc[-1])
    benchmark_value = float(buy_and_hold_curve.iloc[-1])
    strategy_return_pct = (final_value / initial_cash - 1) * 100
    benchmark_return_pct = (benchmark_value / initial_cash - 1) * 100
    profile = _cost_profile(symbol, costs)
    trades_df = pd.DataFrame(trades)
    metrics = calculate_performance_metrics(
        equity_curve,
        initial_value=initial_cash,
        turnover_notional=turnover_notional,
        trades_df=trades_df,
    )
    benchmark_metrics = calculate_performance_metrics(
        buy_and_hold_curve,
        initial_value=initial_cash,
    )
    estimated_exit_cost = (
        _execution(
            symbol,
            "SELL",
            final_close,
            shares,
            costs,
        )["total_cost"]
        if shares > 0
        else 0
    )

    summary = {
        "ticker": symbol,
        "baseline": TECHNICAL_BASELINE_VERSION,
        "start_date": prices.index[first_i].date().isoformat(),
        "end_date": prices.index[last_i].date().isoformat(),
        "signal_timing": "close_t",
        "execution_timing": "open_t_plus_1",
        "prices_adjusted": bool(
            execution_config.get("use_adjusted_prices", True)
        ),
        "initial_cash": round(initial_cash, 2),
        "final_value": round(final_value, 2),
        "strategy_return_pct": round(strategy_return_pct, 2),
        "buy_and_hold_return_pct": round(benchmark_return_pct, 2),
        "difference_pct": round(
            strategy_return_pct - benchmark_return_pct,
            2,
        ),
        "number_of_trades": len(trades),
        "open_position": shares > 0,
        "total_realized_costs": round(total_costs, 2),
        "estimated_open_position_exit_cost": round(
            estimated_exit_cost,
            2,
        ),
        "cagr_pct": metrics["cagr_pct"],
        "max_drawdown_pct": metrics["max_drawdown_pct"],
        "sharpe": metrics["sharpe"],
        "sortino": metrics["sortino"],
        "turnover": metrics["turnover"],
        "closed_trades": metrics["closed_trades"],
        "win_rate_pct": metrics["win_rate_pct"],
        "gain_loss_ratio": metrics["gain_loss_ratio"],
        "avg_hold_days": metrics["avg_hold_days"],
        "buy_and_hold_cagr_pct": benchmark_metrics["cagr_pct"],
        "buy_and_hold_max_drawdown_pct": benchmark_metrics[
            "max_drawdown_pct"
        ],
        "buy_and_hold_sharpe": benchmark_metrics["sharpe"],
        "buy_and_hold_sortino": benchmark_metrics["sortino"],
        "region": region_for_symbol(symbol),
        **profile,
    }
    analysis_frame = prices.loc[start:end].copy()
    analysis_frame["portfolio_value"] = equity_curve
    analysis_frame["buy_and_hold_value"] = buy_and_hold_curve
    return summary, trades_df, analysis_frame


def _trade_row(
    signal_date,
    execution_date,
    action,
    shares,
    cash,
    technical,
    market_regime,
    reason,
    execution,
    hold_days,
    gain_pct=None,
    net_gain_pct=None,
):
    return {
        "signal_date": signal_date,
        "execution_date": execution_date,
        "action": action,
        "shares": shares,
        "raw_price": round(execution["raw_price"], 4),
        "execution_price": round(execution["execution_price"], 4),
        "commission": round(execution["commission"], 2),
        "total_cost": round(execution["total_cost"], 2),
        "notional": round(execution["notional"], 2),
        "cash": round(cash, 2),
        "technical_score": technical["technical_score"],
        "trend_regime": technical["trend_regime"],
        "relative_strength_20d": technical["relative_strength_20d"],
        "market_regime": market_regime,
        "reason": reason,
        "hold_days": hold_days,
        "gain_pct": None if gain_pct is None else round(gain_pct, 2),
        "net_gain_pct": (
            None
            if net_gain_pct is None
            else round(net_gain_pct, 2)
        ),
    }


def backtest_technical_baseline_watchlist(
    symbols,
    dataset_name="historical_test",
    config=None,
):
    config = config or load_backtest_validation_config()
    datasets = validate_chronological_datasets(config["datasets"])
    if dataset_name not in datasets:
        raise ValueError(f"Ukjent datasett: '{dataset_name}'.")

    bounds = datasets[dataset_name]
    rows = []
    for symbol in symbols:
        try:
            summary, _, _ = backtest_technical_baseline(
                symbol,
                bounds["start"],
                bounds["end"],
                config=config,
            )
            summary["dataset"] = dataset_name
            rows.append(summary)
        except Exception as exc:
            rows.append(
                {
                    "ticker": symbol,
                    "dataset": dataset_name,
                    "error": str(exc),
                }
            )
    return pd.DataFrame(rows)
