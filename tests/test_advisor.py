import unittest

import pandas as pd

from src.advisor import (
    CONFLICT_BUY_NEAR_EARNINGS,
    CONFLICT_GAIN_VS_STOP,
    CONFLICT_NEGATIVE_NEWS_STRONG_TREND,
    CONFLICT_SELL_VS_ANALYST,
    advisor_detail_tickers,
    build_advisor_detail,
    build_advisor_details,
    build_advisor_output,
    format_advisor_cell,
    format_advisor_detail_answer,
    format_advisor_detail_markdown,
)
from src.sentiment import SENTIMENT_NEGATIVE


def _portfolio_row(**overrides):
    row = {
        "ticker": "AAPL",
        "shares": 10,
        "buy_price": 100.0,
        "current_price": 150.0,
        "cost_value": 1000.0,
        "market_value": 1500.0,
        "unrealized_profit_loss": 500.0,
        "unrealized_gain_pct": 50.0,
        "score": 75,
        "anbefaling": "HOLD / OBSERVER",
        "trend_regime": "MODERAT OPPTREND",
        "relative_strength_20d": 2.0,
        "portefølje_råd": "HOLD",
        "trailing_stop_loss": 120.0,
        "trailing_stop_triggered": False,
    }
    row.update(overrides)
    return row


def _analyst_item(**overrides):
    item = {
        "ticker": "AAPL",
        "recommendation_key": "hold",
        "upside_pct": 5.0,
    }
    item.update(overrides)
    return item


def _sentiment_item(**overrides):
    item = {
        "ticker": "AAPL",
        "sentiment": "NEUTRAL",
    }
    item.update(overrides)
    return item


def _earnings_item(**overrides):
    item = {
        "ticker": "AAPL",
        "days_until": 30,
        "status": "estimated",
    }
    item.update(overrides)
    return item


class SellVsAnalystRuleTests(unittest.TestCase):
    def test_triggers_on_sell_action_and_bullish_analyst(self):
        output = build_advisor_output(
            portfolio_report=pd.DataFrame(
                [_portfolio_row(portefølje_råd="REDUSER / SELG")]
            ),
            analyst_summary={"items": [_analyst_item(recommendation_key="buy")]},
        )

        self.assertEqual(len(output["items"]), 1)
        self.assertEqual(output["items"][0]["conflict_id"], CONFLICT_SELL_VS_ANALYST)


class BuyNearEarningsRuleTests(unittest.TestCase):
    def test_triggers_on_buy_recommendation_and_near_earnings(self):
        output = build_advisor_output(
            portfolio_report=pd.DataFrame(
                [_portfolio_row(anbefaling="KJØP / ØK", portefølje_råd="HOLD")]
            ),
            earnings_summary={"items": [_earnings_item(days_until=5)]},
        )

        self.assertEqual(len(output["items"]), 1)
        self.assertEqual(output["items"][0]["conflict_id"], CONFLICT_BUY_NEAR_EARNINGS)


class GainVsStopRuleTests(unittest.TestCase):
    def test_triggers_on_large_gain_and_near_trailing_stop(self):
        output = build_advisor_output(
            portfolio_report=pd.DataFrame(
                [
                    _portfolio_row(
                        unrealized_gain_pct=20.0,
                        current_price=103.0,
                        trailing_stop_loss=100.0,
                        portefølje_råd="VURDER GEVINSTSIKRING",
                    )
                ]
            ),
        )

        self.assertEqual(len(output["items"]), 1)
        self.assertEqual(output["items"][0]["conflict_id"], CONFLICT_GAIN_VS_STOP)

    def test_triggers_when_trailing_stop_is_triggered(self):
        output = build_advisor_output(
            portfolio_report=pd.DataFrame(
                [
                    _portfolio_row(
                        unrealized_gain_pct=18.0,
                        trailing_stop_triggered=True,
                        portefølje_råd="VURDER GEVINSTSIKRING",
                    )
                ]
            ),
        )

        self.assertEqual(output["items"][0]["conflict_id"], CONFLICT_GAIN_VS_STOP)


class NegativeNewsStrongTrendRuleTests(unittest.TestCase):
    def test_triggers_on_negative_sentiment_and_strong_trend(self):
        output = build_advisor_output(
            portfolio_report=pd.DataFrame(
                [
                    _portfolio_row(
                        trend_regime="STERK OPPTREND",
                        score=65,
                    )
                ]
            ),
            sentiment_summary={
                "items": [_sentiment_item(sentiment=SENTIMENT_NEGATIVE)]
            },
        )

        self.assertEqual(len(output["items"]), 1)
        self.assertEqual(
            output["items"][0]["conflict_id"],
            CONFLICT_NEGATIVE_NEWS_STRONG_TREND,
        )

    def test_triggers_on_negative_sentiment_and_high_score(self):
        output = build_advisor_output(
            portfolio_report=pd.DataFrame([_portfolio_row(score=72)]),
            sentiment_summary={
                "items": [_sentiment_item(sentiment=SENTIMENT_NEGATIVE)]
            },
        )

        self.assertEqual(
            output["items"][0]["conflict_id"],
            CONFLICT_NEGATIVE_NEWS_STRONG_TREND,
        )


class AdvisorOutputTests(unittest.TestCase):
    def test_no_output_when_no_conflict(self):
        output = build_advisor_output(
            portfolio_report=pd.DataFrame([_portfolio_row()]),
        )

        self.assertEqual(output["items"], [])
        self.assertEqual(output["secondary_items"], [])

    def test_dedupes_multiple_rules_for_same_ticker(self):
        output = build_advisor_output(
            portfolio_report=pd.DataFrame(
                [
                    _portfolio_row(
                        portefølje_råd="REDUSER / SELG",
                        anbefaling="KJØP / ØK",
                        unrealized_gain_pct=20.0,
                        current_price=103.0,
                        trailing_stop_loss=100.0,
                    )
                ]
            ),
            analyst_summary={"items": [_analyst_item(recommendation_key="buy")]},
            earnings_summary={"items": [_earnings_item(days_until=3)]},
        )

        self.assertEqual(len(output["items"]), 1)
        self.assertGreater(len(output["secondary_items"]), 0)
        self.assertEqual(output["items"][0]["priority"], 1)

        tickers = {item["ticker"] for item in output["items"]}
        self.assertEqual(len(tickers), 1)

    def test_missing_support_data_does_not_crash(self):
        output = build_advisor_output(
            portfolio_report=pd.DataFrame(
                [_portfolio_row(portefølje_råd="REDUSER / SELG")]
            ),
            analyst_summary=None,
            sentiment_summary={"items": []},
            earnings_summary={"items": []},
        )

        self.assertEqual(output["items"], [])

    def test_empty_portfolio_returns_empty_output(self):
        output = build_advisor_output(portfolio_report=pd.DataFrame())

        self.assertEqual(output["items"], [])
        self.assertIn("disclaimer", output)

    def test_format_advisor_cell(self):
        text = format_advisor_cell(
            {
                "headline": "Kjøpssignal, rapport nær",
                "takeaway": "Vurder rapport-risiko.",
            }
        )

        self.assertEqual(text, "Kjøpssignal, rapport nær: Vurder rapport-risiko.")
        self.assertEqual(format_advisor_cell(None), "")


class AdvisorDetailTests(unittest.TestCase):
    def test_builds_detail_for_ticker_with_conflict(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="NVDA",
                    portefølje_råd="REDUSER / SELG",
                    trend_regime="SVAK / NEGATIV TREND",
                    unrealized_gain_pct=22.0,
                    current_price=103.0,
                    trailing_stop_loss=100.0,
                )
            ]
        )
        advisor_output = build_advisor_output(
            portfolio_report=portfolio_report,
            analyst_summary={
                "items": [
                    _analyst_item(
                        ticker="NVDA",
                        recommendation_key="buy",
                        upside_pct=15.0,
                    )
                ]
            },
        )
        advisor_item = advisor_output["items"][0]

        detail = build_advisor_detail(
            "NVDA",
            advisor_item,
            portfolio_report=portfolio_report,
            analyst_summary={
                "items": [
                    _analyst_item(
                        ticker="NVDA",
                        recommendation_key="buy",
                        upside_pct=15.0,
                    )
                ]
            },
            alerts=[
                {
                    "ticker": "NVDA",
                    "title": "Reduser / selg",
                }
            ],
        )

        self.assertEqual(detail["ticker"], "NVDA")
        self.assertIn("Analytikere er positive", detail["hold_signals"][0])
        self.assertIn("Svak / negativ trend", detail["caution_signals"])
        self.assertIn("Reduser / selg", detail["caution_signals"])
        self.assertTrue(detail["practical_interpretation"])

    def test_missing_support_data_does_not_crash_for_detail(self):
        detail = build_advisor_detail(
            "AAPL",
            {
                "ticker": "AAPL",
                "conflict_id": CONFLICT_GAIN_VS_STOP,
                "headline": "Gevinst høy, stop nær",
                "takeaway": "Test takeaway.",
                "priority": 1,
            },
            portfolio_report=pd.DataFrame([_portfolio_row()]),
            analyst_summary=None,
            sentiment_summary={"items": []},
            earnings_summary={"items": []},
            alerts=None,
        )

        self.assertEqual(detail["advisor"]["takeaway"], "Test takeaway.")
        self.assertIsInstance(detail["caution_signals"], list)
        self.assertIsInstance(detail["hold_signals"], list)

    def test_ticker_without_advisor_is_excluded(self):
        advisor_output = build_advisor_output(
            portfolio_report=pd.DataFrame([_portfolio_row(ticker="MSFT")]),
        )

        self.assertEqual(advisor_detail_tickers(advisor_output), [])
        self.assertEqual(build_advisor_details(advisor_output, pd.DataFrame()), {})
        self.assertIsNone(
            build_advisor_detail(
                "MSFT",
                None,
                portfolio_report=pd.DataFrame([_portfolio_row(ticker="MSFT")]),
            )
        )

    def test_build_advisor_details_indexes_conflicts(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="NVDA",
                    portefølje_råd="REDUSER / SELG",
                )
            ]
        )
        advisor_output = build_advisor_output(
            portfolio_report=portfolio_report,
            analyst_summary={
                "items": [_analyst_item(ticker="NVDA", recommendation_key="buy")]
            },
        )

        details = build_advisor_details(
            advisor_output,
            portfolio_report,
            analyst_summary={
                "items": [_analyst_item(ticker="NVDA", recommendation_key="buy")]
            },
        )

        self.assertIn("NVDA", details)
        self.assertEqual(advisor_detail_tickers(advisor_output), ["NVDA"])

    def test_format_advisor_detail_markdown(self):
        markdown = format_advisor_detail_markdown(
            {
                "advisor": {"takeaway": "Analytikere er positive, men trend peker ned."},
                "caution_signals": ["Svak / negativ trend"],
                "hold_signals": ["Kursmål viser 12.0% oppside"],
                "practical_interpretation": "Følg stop-nivå tettere enn kursmål.",
            }
        )

        self.assertIn("**Advisor**", markdown)
        self.assertIn("**Taler for varsomhet**", markdown)
        self.assertIn("**Taler for å holde/vente**", markdown)
        self.assertIn("**Praktisk tolkning**", markdown)

    def test_format_advisor_detail_answer(self):
        answer = format_advisor_detail_answer(
            {
                "ticker": "NVDA",
                "advisor": {"takeaway": "Analytikere er positive, men trend peker ned."},
                "caution_signals": ["Svak / negativ trend"],
                "hold_signals": ["Kursmål viser 12.0% oppside"],
                "practical_interpretation": "Følg stop-nivå tettere enn kursmål.",
            }
        )

        self.assertIn("NVDA", answer)
        self.assertIn("Kort oppsummering:", answer)
        self.assertIn("Taler for varsomhet:", answer)
        self.assertIn("Praktisk tolkning:", answer)


if __name__ == "__main__":
    unittest.main()
