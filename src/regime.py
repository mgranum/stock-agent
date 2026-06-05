def analyze_market_regime(benchmark_df):
    latest = benchmark_df.iloc[-1]

    score = 0
    reasons = []

    if latest["close"] > latest["sma100"]:
        score += 1
        reasons.append("Benchmark over SMA100")

    if latest["sma20"] > latest["sma50"]:
        score += 1
        reasons.append("SMA20 over SMA50")

    if latest["macd"] > latest["macd_signal"]:
        score += 1
        reasons.append("MACD positiv")

    if score >= 2:
        regime = "RISK_ON"
    else:
        regime = "RISK_OFF"

    return {
        "market_regime_score": score,
        "market_regime": regime,
        "market_regime_reasons": reasons,
    }