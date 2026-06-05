def combine_scores(
    technical_result,
    fundamental_result,
    fundamental_history_result=None,
):
    fundamental_history_result = fundamental_history_result or {}

    technical_score = technical_result["technical_score"]
    trend_score = technical_result["trend_score"]
    relative_strength_20d = technical_result["relative_strength_20d"]

    fundamental_score = fundamental_result.get("fundamental_score", 0)
    fundamental_history_score = fundamental_history_result.get(
        "fundamental_history_score",
        0
    )

    technical_points = technical_score
    fundamental_points = round(fundamental_score * 0.20)
    fundamental_history_points = round(fundamental_history_score * 0.20)

    score = (
        technical_points
        + fundamental_points
        + fundamental_history_points
    )

    score = max(0, min(score, 100))

    score_reasons = []

    if fundamental_score >= 70:
        score_reasons.append("Sterk fundamental kvalitet")
    elif fundamental_score >= 45:
        score_reasons.append("Akseptabel fundamental kvalitet")
    else:
        score_reasons.append("Svak eller uklar fundamental kvalitet")

    if fundamental_history_score >= 80:
        score_reasons.append("Sterk historisk fundamental utvikling")
    elif fundamental_history_score >= 60:
        score_reasons.append("God historisk fundamental utvikling")
    elif fundamental_history_score > 0:
        score_reasons.append("Blandet historisk fundamental utvikling")
    else:
        score_reasons.append("Mangler historisk fundamental score")

    buy_setup_ok = (
        technical_score >= 50
        and trend_score == 3
        and relative_strength_20d > 0
    )

    if score >= 70 and buy_setup_ok:
        anbefaling = "KJØP / ØK"
    elif score >= 45:
        anbefaling = "HOLD / OBSERVER"
    else:
        anbefaling = "UNNGÅ / SELG"

    if score >= 70 and not buy_setup_ok:
        score_reasons.append(
            "Sterke fundamentals, men teknisk setup er ikke sterkt nok for ny kjøpskandidat"
        )

    return {
        "score": score,
        "anbefaling": anbefaling,
        "technical_points": technical_points,
        "fundamental_points": fundamental_points,
        "fundamental_history_points": fundamental_history_points,
        "score_reasons": score_reasons,
    }


def calculate_stop_levels(df):
    latest = df.iloc[-1]

    price = latest["close"]
    atr = latest["atr14"]
    sma50 = latest["sma50"]

    stop_loss = price * 0.92
    atr_stop_loss = price - (3 * atr)
    trailing_stop_loss = sma50

    trailing_stop_triggered = price < trailing_stop_loss

    kursmål = price * 1.12

    return {
        "kursmål": round(kursmål, 2),
        "stop_loss": round(stop_loss, 2),
        "atr_stop_loss": round(atr_stop_loss, 2),
        "trailing_stop_loss": round(trailing_stop_loss, 2),
        "trailing_stop_triggered": bool(trailing_stop_triggered),
    }