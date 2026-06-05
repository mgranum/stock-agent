import time
import pandas as pd

from src.analysis import analyze_stock


def analyze_portfolio(portfolio, pause_seconds=1):
    rows = []

    for i, position in enumerate(portfolio, start=1):
        symbol = position["ticker"]

        print(f"Analyserer portefølje: {symbol} ({i}/{len(portfolio)})...")

        try:
            result, df = analyze_stock(symbol)

            current_price = result["kurs"]
            buy_price = position["buy_price"]
            shares = position["shares"]

            gain_pct = ((current_price - buy_price) / buy_price) * 100
            market_value = current_price * shares
            cost_value = buy_price * shares
            profit_loss = market_value - cost_value

            trailing_stop_triggered = result.get(
                "trailing_stop_triggered",
                False
            )

            # -----------------------------
            # Porteføljelogikk
            # -----------------------------

            if result["trend_regime"] == "SVAK / NEGATIV TREND":
                portfolio_action = "REDUSER / SELG"
                portfolio_reason = "Trendregimet er svakt eller negativt"

            elif (
                trailing_stop_triggered
                and gain_pct > 15
                and result["trend_score"] >= 2
            ):
                portfolio_action = "VURDER GEVINSTSIKRING"
                portfolio_reason = (
                    "Trailing stop er trigget, men aksjen har fortsatt "
                    "akseptabel trend og posisjonen er tydelig i pluss"
                )

            elif (
                trailing_stop_triggered
                and gain_pct <= 0
            ):
                portfolio_action = "REDUSER / SELG"
                portfolio_reason = (
                    "Trailing stop er trigget og posisjonen er ikke i pluss"
                )

            elif (
                result["trend_regime"] == "STERK OPPTREND"
                and result["relative_strength_20d"] > 0
                and gain_pct > 0
            ):
                portfolio_action = "HOLD / LA VINNER LØPE"
                portfolio_reason = (
                    "Sterk trend, positiv relativ styrke og posisjonen er i pluss"
                )

            elif (
                result["trend_regime"] == "MODERAT OPPTREND"
                and result["relative_strength_20d"] > 0
                and gain_pct > 0
            ):
                portfolio_action = "HOLD"
                portfolio_reason = (
                    "Moderat opptrend, positiv relativ styrke og posisjonen er i pluss"
                )

            elif (
                result["trend_regime"] == "STERK OPPTREND"
            ):
                portfolio_action = "HOLD"
                portfolio_reason = "Sterk hovedtrend"

            elif (
                result["trend_regime"] == "MODERAT OPPTREND"
                and result["score"] >= 45
            ):
                portfolio_action = "HOLD / FØLG MED"
                portfolio_reason = (
                    "Moderat opptrend, men signalene er ikke sterke nok til å øke"
                )

            elif trailing_stop_triggered:
                portfolio_action = "VURDER REDUKSJON"
                portfolio_reason = (
                    "Trailing stop er trigget, men øvrige signaler gir ikke klart salg"
                )

            else:
                portfolio_action = "FØLG MED / IKKE ØK"
                portfolio_reason = (
                    "Signalene er svake eller uklare, men ikke nødvendigvis salg"
                )

            row = {
                "ticker": symbol,
                "shares": shares,
                "buy_price": round(buy_price, 2),
                "current_price": round(current_price, 2),
                "gain_pct": round(gain_pct, 2),
                "profit_loss": round(profit_loss, 2),
                "market_value": round(market_value, 2),
                "score": result["score"],
                "trend_score": result["trend_score"],
                "trend_regime": result["trend_regime"],
                "relative_strength_20d": result["relative_strength_20d"],
                "trailing_stop_triggered": trailing_stop_triggered,
                "portefølje_råd": portfolio_action,
                "begrunnelse": portfolio_reason,
                "kursmål": result["kursmål"],
                "stop_loss": result["stop_loss"],
                "atr_stop_loss": result["atr_stop_loss"],
                "trailing_stop_loss": result["trailing_stop_loss"],
                "tidshorisont": result["tidshorisont"],
            }

            rows.append(row)

        except Exception as e:
            rows.append({
                "ticker": symbol,
                "error": str(e)
            })

        if i < len(portfolio):
            time.sleep(pause_seconds)

    return pd.DataFrame(rows)