import pandas as pd

from src.data import get_daily_prices
from src.indicators import add_indicators
from src.technicals import get_benchmark_for_symbol, relative_strength
from src.fundamentals import analyze_fundamentals
from src.fundamental_history import analyze_fundamental_history
from src.scoring import combine_scores
from src.regime import analyze_market_regime
from src.strategy_classification import classify_stock
from src.strategy_profiles import get_strategy_profile


def _technical_result_at(df, benchmark_df, benchmark_symbol, i):
    row = df.iloc[i]
    price = row["close"]

    score = 0
    reasons = []

    trend_points = 0
    momentum_points = 0
    volume_points = 0
    relative_strength_points = 0
    trend_score = 0

    if price > row["sma20"]:
        trend_score += 1
        trend_points += 15
        score += 15
        reasons.append("Kurs over SMA20")

    if row["sma20"] > row["sma50"]:
        trend_score += 1
        trend_points += 15
        score += 15
        reasons.append("SMA20 over SMA50")

    if price > row["sma50"]:
        trend_score += 1
        trend_points += 10
        score += 10
        reasons.append("Kurs over SMA50")

    if trend_score == 3:
        trend_regime = "STERK OPPTREND"
    elif trend_score == 2:
        trend_regime = "MODERAT OPPTREND"
    else:
        trend_regime = "SVAK / NEGATIV TREND"

    rsi = row["rsi"]

    if 50 <= rsi <= 70:
        momentum_points += 15
        score += 15
        reasons.append("RSI i positivt område")
    elif rsi > 70:
        momentum_points += 8
        score += 8
        reasons.append("RSI sterk, men mulig overkjøpt")
    elif rsi < 40:
        reasons.append("RSI svakt")

    if row["macd"] > row["macd_signal"]:
        momentum_points += 15
        score += 15
        reasons.append("MACD positiv")

    if row["volume"] > row["volume_avg20"]:
        volume_points += 10
        score += 10
        reasons.append("Volum over 20-dagers snitt")

    stock_window = df.iloc[: i + 1]
    benchmark_window = benchmark_df[
        benchmark_df.index <= row.name
    ]

    rs_20d = relative_strength(
        stock_window,
        benchmark_window,
        days=20,
    )

    if rs_20d > 0:
        relative_strength_points += 10
        score += 10
        reasons.append(f"Sterkere enn benchmark {benchmark_symbol}")
    else:
        reasons.append(f"Svakere enn benchmark {benchmark_symbol}")

    return {
        "technical_score": score,
        "trend_score": trend_score,
        "trend_regime": trend_regime,
        "trend_points": trend_points,
        "momentum_points": momentum_points,
        "volume_points": volume_points,
        "relative_strength_points": relative_strength_points,
        "relative_strength_20d": round(rs_20d * 100, 2),
        "technical_reasons": reasons,
    }


def _market_regime_at(benchmark_df, date):
    benchmark_window = benchmark_df[
        benchmark_df.index <= date
    ]

    if len(benchmark_window) < 100:
        return {
            "market_regime": "UNKNOWN",
            "market_regime_score": 0,
            "market_regime_reasons": [],
        }

    return analyze_market_regime(benchmark_window)


def _get_price_data(symbol, period):
    try:
        return get_daily_prices(
            symbol,
            period=period,
            use_cache=False,
        )
    except Exception:
        return get_daily_prices(
            symbol,
            period=period,
            use_cache=True,
        )


def _get_exit_reason(
    price,
    recommendation,
    trend_regime,
    hard_stop,
    trailing_stop,
    hold_days,
    min_hold_days,
):
    # Hard stop skal gjelde umiddelbart.
    if price < hard_stop:
        return "Hard stop-loss"

    # Trend-/trailing-exit skal først gjelde etter minimum holdetid.
    if hold_days < min_hold_days:
        return None

    if (
        price < trailing_stop
        and trend_regime == "SVAK / NEGATIV TREND"
    ):
        return "Trailing stop + svak trend"

    if recommendation == "UNNGÅ / SELG":
        return "Modell ga UNNGÅ / SELG"

    return None


def _resolve_position_exit_params(
    strategy_specific,
    symbol,
    score,
    recommendation,
    trend_regime,
    relative_strength_20d,
    fundamental_result,
    fundamental_history_result,
    default_min_hold_days,
    default_stop_loss_pct,
    default_trailing_sma,
):
    if not strategy_specific:
        return (
            None,
            default_min_hold_days,
            default_stop_loss_pct,
            default_trailing_sma,
        )

    classification_row = {
        "ticker": symbol,
        "score": score,
        "anbefaling": recommendation,
        "trend_regime": trend_regime,
        "relative_strength_20d": relative_strength_20d,
        "fundamental_score": fundamental_result.get("fundamental_score", 0),
        "fundamental_history_score": fundamental_history_result.get(
            "fundamental_history_score",
            0,
        ),
    }

    strategy_type = classify_stock(classification_row)
    profile = get_strategy_profile(strategy_type)

    return (
        strategy_type,
        profile.get("preferred_hold_days", default_min_hold_days),
        profile.get("preferred_stop_loss_pct", default_stop_loss_pct),
        profile.get("preferred_trailing_sma", default_trailing_sma),
    )


def _strategy_trade_fields(
    strategy_specific,
    strategy_type,
    effective_min_hold_days,
    effective_stop_loss_pct,
    effective_trailing_sma,
):
    if not strategy_specific:
        return {}

    return {
        "strategy_type": strategy_type,
        "effective_min_hold_days": effective_min_hold_days,
        "effective_stop_loss_pct": effective_stop_loss_pct,
        "effective_trailing_sma": effective_trailing_sma,
    }


def backtest_signal_model(
    symbol,
    period="2y",
    initial_cash=10000,
    min_hold_days=60,
    stop_loss_pct=0.12,
    trailing_sma="sma100",
    min_buy_score=70,
    min_buy_relative_strength=0,
    require_risk_on=False,
    strategy_specific=False,
):
    df = _get_price_data(symbol, period)
    df = add_indicators(df)

    benchmark_symbol = get_benchmark_for_symbol(symbol)
    benchmark_df = _get_price_data(benchmark_symbol, period)
    benchmark_df = add_indicators(benchmark_df)

    fundamental_result = analyze_fundamentals(symbol)
    fundamental_history_result = analyze_fundamental_history(symbol)

    cash = initial_cash
    shares = 0
    entry_price = None
    entry_date = None
    position_strategy_type = None
    position_min_hold_days = min_hold_days
    position_stop_loss_pct = stop_loss_pct
    position_trailing_sma = trailing_sma

    trades = []
    start_i = 120

    for i in range(start_i, len(df)):
        row = df.iloc[i]
        date = df.index[i]
        price = row["close"]

        if pd.isna(row["sma100"]) or pd.isna(row["atr14"]):
            continue

        market_regime_result = _market_regime_at(
            benchmark_df,
            date,
        )

        market_regime = market_regime_result["market_regime"]

        technical_result = _technical_result_at(
            df,
            benchmark_df,
            benchmark_symbol,
            i,
        )

        scoring_result = combine_scores(
            technical_result,
            fundamental_result,
            fundamental_history_result,
        )

        recommendation = scoring_result["anbefaling"]
        trend_regime = technical_result["trend_regime"]
        relative_strength_20d = technical_result["relative_strength_20d"]
        score = scoring_result["score"]

        risk_on_ok = (
            market_regime == "RISK_ON"
            or not require_risk_on
        )

        buy_signal = (
            shares == 0
            and risk_on_ok
            and recommendation == "KJØP / ØK"
            and score >= min_buy_score
            and trend_regime == "STERK OPPTREND"
            and relative_strength_20d >= min_buy_relative_strength
        )

        if shares > 0:
            hold_days = (date - entry_date).days
            hard_stop = entry_price * (1 - position_stop_loss_pct)
            trailing_stop = row[position_trailing_sma]

            exit_reason = _get_exit_reason(
                price=price,
                recommendation=recommendation,
                trend_regime=trend_regime,
                hard_stop=hard_stop,
                trailing_stop=trailing_stop,
                hold_days=hold_days,
                min_hold_days=position_min_hold_days,
            )

            sell_signal = exit_reason is not None
        else:
            hold_days = 0
            exit_reason = None
            sell_signal = False

        if buy_signal:
            (
                position_strategy_type,
                position_min_hold_days,
                position_stop_loss_pct,
                position_trailing_sma,
            ) = _resolve_position_exit_params(
                strategy_specific=strategy_specific,
                symbol=symbol,
                score=score,
                recommendation=recommendation,
                trend_regime=trend_regime,
                relative_strength_20d=relative_strength_20d,
                fundamental_result=fundamental_result,
                fundamental_history_result=fundamental_history_result,
                default_min_hold_days=min_hold_days,
                default_stop_loss_pct=stop_loss_pct,
                default_trailing_sma=trailing_sma,
            )

            shares = cash // price
            entry_price = price
            entry_date = date
            cash -= shares * price

            trades.append({
                "date": date,
                "action": "BUY",
                "price": round(price, 2),
                "shares": shares,
                "cash": round(cash, 2),
                "score": score,
                "recommendation": recommendation,
                "trend_regime": trend_regime,
                "relative_strength_20d": relative_strength_20d,
                "market_regime": market_regime,
                "reason": "KJØP / ØK + sterk trend",
                "gain_pct": None,
                "hold_days": 0,
                **_strategy_trade_fields(
                    strategy_specific,
                    position_strategy_type,
                    position_min_hold_days,
                    position_stop_loss_pct,
                    position_trailing_sma,
                ),
            })

        elif sell_signal:
            cash += shares * price
            gain_pct = ((price - entry_price) / entry_price) * 100

            trades.append({
                "date": date,
                "action": "SELL",
                "price": round(price, 2),
                "shares": shares,
                "cash": round(cash, 2),
                "score": score,
                "recommendation": recommendation,
                "trend_regime": trend_regime,
                "relative_strength_20d": relative_strength_20d,
                "market_regime": market_regime,
                "reason": exit_reason,
                "gain_pct": round(gain_pct, 2),
                "hold_days": hold_days,
                **_strategy_trade_fields(
                    strategy_specific,
                    position_strategy_type,
                    position_min_hold_days,
                    position_stop_loss_pct,
                    position_trailing_sma,
                ),
            })

            shares = 0
            entry_price = None
            entry_date = None
            position_strategy_type = None
            position_min_hold_days = min_hold_days
            position_stop_loss_pct = stop_loss_pct
            position_trailing_sma = trailing_sma

    final_price = df.iloc[-1]["close"]
    final_value = cash + shares * final_price

    strategy_return_pct = (
        (final_value - initial_cash)
        / initial_cash
    ) * 100

    buy_and_hold_return_pct = (
        (final_price - df.iloc[start_i]["close"])
        / df.iloc[start_i]["close"]
    ) * 100

    summary = {
        "ticker": symbol,
        "initial_cash": round(initial_cash, 2),
        "final_value": round(final_value, 2),
        "strategy_return_pct": round(strategy_return_pct, 2),
        "buy_and_hold_return_pct": round(buy_and_hold_return_pct, 2),
        "difference_pct": round(
            strategy_return_pct - buy_and_hold_return_pct,
            2,
        ),
        "open_position": shares > 0,
        "number_of_trades": len(trades),
        "last_price": round(final_price, 2),
        "min_hold_days": min_hold_days,
        "stop_loss_pct": stop_loss_pct,
        "trailing_sma": trailing_sma,
        "min_buy_score": min_buy_score,
        "min_buy_relative_strength": min_buy_relative_strength,
        "require_risk_on": require_risk_on,
        "strategy_specific": strategy_specific,
    }

    return summary, pd.DataFrame(trades), df


def backtest_signal_watchlist(
    symbols,
    period="2y",
    initial_cash=10000,
    min_hold_days=60,
    stop_loss_pct=0.12,
    trailing_sma="sma100",
    min_buy_score=70,
    min_buy_relative_strength=0,
    require_risk_on=False,
    strategy_specific=False,
):
    rows = []

    for symbol in symbols:
        print(f"Backtester signalmodell: {symbol}")

        try:
            summary, trades, df = backtest_signal_model(
                symbol=symbol,
                period=period,
                initial_cash=initial_cash,
                min_hold_days=min_hold_days,
                stop_loss_pct=stop_loss_pct,
                trailing_sma=trailing_sma,
                min_buy_score=min_buy_score,
                min_buy_relative_strength=min_buy_relative_strength,
                require_risk_on=require_risk_on,
                strategy_specific=strategy_specific,
            )

            rows.append(summary)

        except Exception as e:
            rows.append({
                "ticker": symbol,
                "error": str(e),
            })

    return pd.DataFrame(rows)


def backtest_strategy_specific_watchlist(
    symbols,
    period="2y",
    initial_cash=10000,
    min_hold_days=60,
    stop_loss_pct=0.12,
    trailing_sma="sma100",
    min_buy_score=70,
    min_buy_relative_strength=0,
    require_risk_on=False,
):
    return backtest_signal_watchlist(
        symbols=symbols,
        period=period,
        initial_cash=initial_cash,
        min_hold_days=min_hold_days,
        stop_loss_pct=stop_loss_pct,
        trailing_sma=trailing_sma,
        min_buy_score=min_buy_score,
        min_buy_relative_strength=min_buy_relative_strength,
        require_risk_on=require_risk_on,
        strategy_specific=True,
    )