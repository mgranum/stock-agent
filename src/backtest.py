import pandas as pd

from src.data import get_daily_prices
from src.indicators import add_indicators


def backtest_stock(
    symbol,
    initial_cash=10000,
    period="1y",
    atr_multiplier=4,
    min_hold_days=20,
):
    df = get_daily_prices(symbol, period=period, use_cache=False)
    df = add_indicators(df)

    cash = initial_cash
    shares = 0
    entry_price = None
    entry_date = None
    highest_close_since_entry = None

    trades = []

    for date, row in df.iterrows():
        price = row["close"]
        atr = row["atr14"]

        if (
            pd.isna(row["sma20"])
            or pd.isna(row["sma50"])
            or pd.isna(row["sma100"])
            or pd.isna(atr)
        ):
            continue

        trend_score = 0

        if price > row["sma20"]:
            trend_score += 1

        if row["sma20"] > row["sma50"]:
            trend_score += 1

        if price > row["sma50"]:
            trend_score += 1

        buy_signal = (
            shares == 0
            and row["sma20"] > row["sma50"]
            and price > row["sma50"]
        )

        if shares > 0:
            highest_close_since_entry = max(
                highest_close_since_entry,
                price
            )

            trailing_stop = (
                highest_close_since_entry
                - (atr_multiplier * atr)
            )

            hold_days = (date - entry_date).days

            sell_signal = (
                hold_days >= min_hold_days
                and (
                    price < row["sma100"]
                    or price < trailing_stop
                )
            )
        else:
            trailing_stop = None
            hold_days = 0
            sell_signal = False

        if buy_signal:
            shares = cash // price
            entry_price = price
            entry_date = date
            highest_close_since_entry = price
            cash -= shares * price

            trades.append({
                "date": date,
                "action": "BUY",
                "price": round(price, 2),
                "shares": shares,
                "cash": round(cash, 2),
                "portfolio_value": round(cash + shares * price, 2),
                "reason": "Trend-following inngang",
                "trend_score": trend_score,
                "sma20": round(row["sma20"], 2),
                "sma50": round(row["sma50"], 2),
                "sma100": round(row["sma100"], 2),
                "trailing_stop": None,
                "gain_pct": None,
            })

        elif sell_signal:
            cash += shares * price

            gain_pct = (
                (price - entry_price)
                / entry_price
            ) * 100

            sell_reason = []

            if price < row["sma100"]:
                sell_reason.append("Kurs under SMA100")

            if price < trailing_stop:
                sell_reason.append(
                    f"Trailing stop brutt ({atr_multiplier} × ATR)"
                )

            trades.append({
                "date": date,
                "action": "SELL",
                "price": round(price, 2),
                "shares": shares,
                "cash": round(cash, 2),
                "portfolio_value": round(cash, 2),
                "reason": ", ".join(sell_reason),
                "trend_score": trend_score,
                "sma20": round(row["sma20"], 2),
                "sma50": round(row["sma50"], 2),
                "sma100": round(row["sma100"], 2),
                "trailing_stop": round(trailing_stop, 2),
                "gain_pct": round(gain_pct, 2),
            })

            shares = 0
            entry_price = None
            entry_date = None
            highest_close_since_entry = None

    final_price = df.iloc[-1]["close"]
    final_value = cash + shares * final_price

    total_return_pct = (
        (final_value - initial_cash)
        / initial_cash
    ) * 100

    buy_and_hold_return_pct = (
        (final_price - df.iloc[0]["close"])
        / df.iloc[0]["close"]
    ) * 100

    trades_df = pd.DataFrame(trades)

    summary = {
        "ticker": symbol,
        "initial_cash": round(initial_cash, 2),
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return_pct, 2),
        "buy_and_hold_return_pct": round(buy_and_hold_return_pct, 2),
        "open_position": shares > 0,
        "shares": shares,
        "last_price": round(final_price, 2),
        "number_of_trades": len(trades_df),
        "atr_multiplier": atr_multiplier,
        "min_hold_days": min_hold_days,
        "strategy": "trend_following_sma50_entry_sma100_exit",
    }

    return summary, trades_df, df

def backtest_watchlist(
    watchlist,
    initial_cash=10000,
    period="1y",
    atr_multiplier=4,
    min_hold_days=20,
):
    results = []

    for symbol in watchlist:
        print(f"Backtester {symbol}...")

        try:
            summary, trades, df = backtest_stock(
                symbol=symbol,
                initial_cash=initial_cash,
                period=period,
                atr_multiplier=atr_multiplier,
                min_hold_days=min_hold_days,
            )

            strategy_return = summary["total_return_pct"]
            buy_hold_return = summary["buy_and_hold_return_pct"]

            results.append({
                "ticker": symbol,
                "strategy_return_pct": strategy_return,
                "buy_and_hold_return_pct": buy_hold_return,
                "difference_pct": round(
                    strategy_return - buy_hold_return,
                    2
                ),
                "number_of_trades": summary["number_of_trades"],
                "open_position": summary["open_position"],
                "final_value": summary["final_value"],
                "last_price": summary["last_price"],
            })

        except Exception as e:
            results.append({
                "ticker": symbol,
                "error": str(e),
            })

    return pd.DataFrame(results)