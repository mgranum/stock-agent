import time
import pandas as pd

from src.analysis import analyze_stock

PORTFOLIO_METRIC_COLUMNS = (
    "market_value",
    "unrealized_gain_pct",
    "current_price",
    "cost_value",
)

PORTFOLIO_ACTION_FIELDS = (
    "portefølje_råd",
    "anbefaling",
    "trailing_stop_loss",
)


def analyze_portfolio(portfolio, pause_seconds=1):
    rows = []

    for i, position in enumerate(portfolio, start=1):
        symbol = position["ticker"]

        print(
            f"Analyserer porteføljeposisjon: "
            f"{symbol} ({i}/{len(portfolio)})..."
        )

        try:
            result, df = analyze_stock(symbol)

            current_price = float(result["kurs"])
            buy_price = float(position["buy_price"])
            shares = float(position["shares"])

            market_value = current_price * shares
            cost_value = buy_price * shares
            profit_loss = market_value - cost_value
            gain_pct = ((current_price - buy_price) / buy_price) * 100

            row = {
                "position_id": position.get("position_id"),
                "ticker": symbol,
                "shares": shares,
                "buy_price": round(buy_price, 2),
                "buy_datetime": position.get("buy_datetime"),
                "current_price": round(current_price, 2),
                "cost_value": round(cost_value, 2),
                "market_value": round(market_value, 2),
                "unrealized_profit_loss": round(profit_loss, 2),
                "unrealized_gain_pct": round(gain_pct, 2),

                "score": result["score"],
                "anbefaling": result["anbefaling"],
                "trend_score": result["trend_score"],
                "trend_regime": result["trend_regime"],
                "relative_strength_20d": result["relative_strength_20d"],
                "trailing_stop_triggered": result.get(
                    "trailing_stop_triggered",
                    False,
                ),

                "portefølje_råd": _portfolio_action(
                    result=result,
                    gain_pct=gain_pct,
                ),
                "begrunnelse": _portfolio_reason(
                    result=result,
                    gain_pct=gain_pct,
                ),

                "kursmål": result["kursmål"],
                "stop_loss": result["stop_loss"],
                "atr_stop_loss": result["atr_stop_loss"],
                "trailing_stop_loss": result["trailing_stop_loss"],
                "tidshorisont": result["tidshorisont"],
            }

            rows.append(row)

        except Exception as e:
            rows.append({
                "position_id": position.get("position_id"),
                "ticker": symbol,
                "error": str(e),
            })

        if i < len(portfolio):
            time.sleep(pause_seconds)

    return pd.DataFrame(rows)


def valid_portfolio_rows(portfolio_report):
    if portfolio_report is None or portfolio_report.empty:
        return pd.DataFrame()

    df = portfolio_report.copy()
    if "error" in df.columns:
        df = df[df["error"].isna()]

    if df.empty:
        return pd.DataFrame()

    required = list(PORTFOLIO_METRIC_COLUMNS) + list(PORTFOLIO_ACTION_FIELDS)
    missing = [column for column in required if column not in df.columns]
    if missing:
        return pd.DataFrame()

    for column in PORTFOLIO_METRIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    metric_mask = df[list(PORTFOLIO_METRIC_COLUMNS)].notna().all(axis=1)
    return df[metric_mask].copy()


def portfolio_report_is_analyzed(portfolio_report):
    return not valid_portfolio_rows(portfolio_report).empty


def ensure_portfolio_report(portfolio_report, portfolio):
    if not portfolio:
        return None

    if portfolio_report_is_analyzed(portfolio_report):
        return portfolio_report

    return analyze_portfolio(portfolio, pause_seconds=0)


def summarize_portfolio(portfolio_report):
    valid = valid_portfolio_rows(portfolio_report)

    if valid.empty:
        return {
            "total_cost_value": 0,
            "total_market_value": 0,
            "total_unrealized_profit_loss": 0,
            "total_unrealized_gain_pct": 0,
            "positions": 0,
        }

    total_cost = valid["cost_value"].sum()
    total_market = valid["market_value"].sum()
    total_pl = total_market - total_cost

    if total_cost > 0:
        total_gain_pct = (total_pl / total_cost) * 100
    else:
        total_gain_pct = 0

    return {
        "total_cost_value": round(total_cost, 2),
        "total_market_value": round(total_market, 2),
        "total_unrealized_profit_loss": round(total_pl, 2),
        "total_unrealized_gain_pct": round(total_gain_pct, 2),
        "positions": len(valid),
    }


def _portfolio_action(result, gain_pct):
    trailing_stop_triggered = result.get(
        "trailing_stop_triggered",
        False,
    )

    if result["trend_regime"] == "SVAK / NEGATIV TREND":
        return "REDUSER / SELG"

    if (
        trailing_stop_triggered
        and gain_pct > 15
        and result["trend_score"] >= 2
    ):
        return "VURDER GEVINSTSIKRING"

    if trailing_stop_triggered and gain_pct <= 0:
        return "REDUSER / SELG"

    if (
        result["trend_regime"] == "STERK OPPTREND"
        and result["relative_strength_20d"] > 0
        and gain_pct > 0
    ):
        return "HOLD / LA VINNER LØPE"

    if (
        result["trend_regime"] == "MODERAT OPPTREND"
        and result["relative_strength_20d"] > 0
        and gain_pct > 0
    ):
        return "HOLD"

    if result["trend_regime"] == "STERK OPPTREND":
        return "HOLD"

    if (
        result["trend_regime"] == "MODERAT OPPTREND"
        and result["score"] >= 45
    ):
        return "HOLD / FØLG MED"

    if trailing_stop_triggered:
        return "VURDER REDUKSJON"

    return "FØLG MED / IKKE ØK"


def _portfolio_reason(result, gain_pct):
    trailing_stop_triggered = result.get(
        "trailing_stop_triggered",
        False,
    )

    if result["trend_regime"] == "SVAK / NEGATIV TREND":
        return "Trendregimet er svakt eller negativt"

    if (
        trailing_stop_triggered
        and gain_pct > 15
        and result["trend_score"] >= 2
    ):
        return (
            "Trailing stop er trigget, men aksjen har fortsatt "
            "akseptabel trend og posisjonen er tydelig i pluss"
        )

    if trailing_stop_triggered and gain_pct <= 0:
        return (
            "Trailing stop er trigget og posisjonen er ikke i pluss"
        )

    if (
        result["trend_regime"] == "STERK OPPTREND"
        and result["relative_strength_20d"] > 0
        and gain_pct > 0
    ):
        return (
            "Sterk trend, positiv relativ styrke og posisjonen er i pluss"
        )

    if (
        result["trend_regime"] == "MODERAT OPPTREND"
        and result["relative_strength_20d"] > 0
        and gain_pct > 0
    ):
        return (
            "Moderat opptrend, positiv relativ styrke og posisjonen er i pluss"
        )

    if result["trend_regime"] == "STERK OPPTREND":
        return "Sterk hovedtrend"

    if (
        result["trend_regime"] == "MODERAT OPPTREND"
        and result["score"] >= 45
    ):
        return (
            "Moderat opptrend, men signalene er ikke sterke nok til å øke"
        )

    if trailing_stop_triggered:
        return (
            "Trailing stop er trigget, men øvrige signaler gir ikke klart salg"
        )

    return (
        "Signalene er svake eller uklare, men ikke nødvendigvis salg"
    )