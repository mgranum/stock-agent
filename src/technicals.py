from src.benchmarks import local_benchmark_for_symbol


def get_benchmark_for_symbol(symbol):
    return local_benchmark_for_symbol(symbol)


def relative_strength(df_stock, df_benchmark, days=20):
    stock_return = df_stock["close"].iloc[-1] / df_stock["close"].iloc[-days] - 1
    benchmark_return = df_benchmark["close"].iloc[-1] / df_benchmark["close"].iloc[-days] - 1
    return stock_return - benchmark_return


def analyze_technicals(df, benchmark_df, benchmark_symbol):
    latest = df.iloc[-1]
    price = latest["close"]
    rsi = latest["rsi"]

    score = 0
    reasons = []

    trend_points = 0
    momentum_points = 0
    volume_points = 0
    relative_strength_points = 0

    trend_score = 0

    if price > latest["sma20"]:
        trend_score += 1
        trend_points += 15
        score += 15
        reasons.append("Kurs over SMA20")

    if latest["sma20"] > latest["sma50"]:
        trend_score += 1
        trend_points += 15
        score += 15
        reasons.append("SMA20 over SMA50")

    if price > latest["sma50"]:
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

    if latest["macd"] > latest["macd_signal"]:
        momentum_points += 15
        score += 15
        reasons.append("MACD positiv")

    if latest["volume"] > latest["volume_avg20"]:
        volume_points += 10
        score += 10
        reasons.append("Volum over 20-dagers snitt")

    rs_20d = relative_strength(df, benchmark_df, days=20)

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
