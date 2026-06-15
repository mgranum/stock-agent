import unittest
from unittest.mock import patch

import pandas as pd

from src.sentiment import SENTIMENT_NEGATIVE
from src.watchlist_advisor import (
    ACTION_AVVENT_EARNINGS,
    ACTION_FJERN_FRA_WATCHLIST,
    ACTION_FLYTT_TIL_RESEARCH,
    ACTION_FOLG_MED,
    ACTION_VENT,
    ACTION_VURDER_KJOP,
    build_watchlist_advisor,
    build_watchlist_advisor_table,
    format_watchlist_advisor_detail,
    format_watchlist_action_label,
    format_watchlist_priority_label,
    _build_watchlist_advisor_item,
)


def _watchlist_row(**overrides):
    row = {
        "ticker": "NVDA",
        "score": 85,
        "anbefaling": "KJØP / ØK",
        "trend_regime": "STERK OPPTREND",
        "relative_strength_20d": 12.0,
    }
    row.update(overrides)
    return row


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
    }
    row.update(overrides)
    return row


def _analyst_item(**overrides):
    item = {
        "ticker": "NVDA",
        "recommendation_key": "buy",
        "recommendation_mean": 1.8,
        "analyst_count": 40,
    }
    item.update(overrides)
    return item


def _sentiment_item(**overrides):
    item = {
        "ticker": "NVDA",
        "sentiment": "NEUTRAL",
    }
    item.update(overrides)
    return item


def _earnings_item(**overrides):
    item = {
        "ticker": "NVDA",
        "days_until": 30,
    }
    item.update(overrides)
    return item


class VurderKjopTests(unittest.TestCase):
    def test_vurder_kjop_on_strong_buy_candidate(self):
        item = _build_watchlist_advisor_item(
            pd.Series(_watchlist_row()),
            analyst_item=_analyst_item(),
            earnings_item=_earnings_item(days_until=30),
        )

        self.assertEqual(item["watchlist_action"], ACTION_VURDER_KJOP)
        self.assertEqual(item["priority"], 1)
        self.assertIn("Modellanbefaling: KJØP / ØK", item["why"])


class AvventEarningsTests(unittest.TestCase):
    def test_avvent_earnings_when_buy_and_report_near(self):
        item = _build_watchlist_advisor_item(
            pd.Series(_watchlist_row()),
            earnings_item=_earnings_item(days_until=5),
        )

        self.assertEqual(item["watchlist_action"], ACTION_AVVENT_EARNINGS)
        self.assertIn("Kvartalsrapport om 5 dager", item["watch_out_for"])


class FjernFraWatchlistTests(unittest.TestCase):
    def test_fjern_requires_all_weak_signals(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="WEAK",
                    anbefaling="UNNGÅ / SELG",
                    trend_regime="SVAK / NEGATIV TREND",
                    relative_strength_20d=-8.0,
                    score=30,
                )
            ),
        )

        self.assertEqual(item["watchlist_action"], ACTION_FJERN_FRA_WATCHLIST)

    def test_fjern_not_triggered_with_only_two_weak_signals(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="WEAKRS",
                    anbefaling="UNNGÅ / SELG",
                    trend_regime="MODERAT OPPTREND",
                    relative_strength_20d=-6.0,
                    score=35,
                )
            ),
        )

        self.assertEqual(item["watchlist_action"], ACTION_FLYTT_TIL_RESEARCH)

    def test_fjern_not_triggered_when_score_is_not_low_enough(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="SCORE",
                    anbefaling="UNNGÅ / SELG",
                    trend_regime="SVAK / NEGATIV TREND",
                    relative_strength_20d=-8.0,
                    score=42,
                )
            ),
        )

        self.assertEqual(item["watchlist_action"], ACTION_FLYTT_TIL_RESEARCH)


class AvoidPartialWeakSignalTests(unittest.TestCase):
    def test_avoid_with_one_weak_signal_uses_vent(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="ONE",
                    anbefaling="UNNGÅ / SELG",
                    trend_regime="MODERAT OPPTREND",
                    relative_strength_20d=-2.0,
                    score=55,
                )
            ),
        )

        self.assertEqual(item["watchlist_action"], ACTION_VENT)

    def test_avoid_with_two_weak_signals_uses_flytt(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="TWO",
                    anbefaling="UNNGÅ / SELG",
                    trend_regime="SVAK / NEGATIV TREND",
                    relative_strength_20d=2.0,
                    score=35,
                )
            ),
        )

        self.assertEqual(item["watchlist_action"], ACTION_FLYTT_TIL_RESEARCH)


class FlyttTilResearchTests(unittest.TestCase):
    def test_flytt_on_recommendation_downgrade(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="DOWN",
                    anbefaling="HOLD / OBSERVER",
                    trend_regime="MODERAT OPPTREND",
                    score=60,
                )
            ),
            snapshot_info={"recommendation_downgraded": True},
        )

        self.assertEqual(item["watchlist_action"], ACTION_FLYTT_TIL_RESEARCH)
        self.assertIn("Nylig nedgradering siden snapshot", item["watch_out_for"])

    def test_flytt_on_score_fall(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="FALL",
                    anbefaling="HOLD / OBSERVER",
                    trend_regime="MODERAT OPPTREND",
                    score=55,
                )
            ),
            snapshot_info={"score_fall": True},
        )

        self.assertEqual(item["watchlist_action"], ACTION_FLYTT_TIL_RESEARCH)

    def test_flytt_on_avoid_without_weak_enough_signal(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="AVOID",
                    anbefaling="UNNGÅ / SELG",
                    trend_regime="MODERAT OPPTREND",
                    relative_strength_20d=1.0,
                    score=48,
                )
            ),
        )

        self.assertEqual(item["watchlist_action"], ACTION_FLYTT_TIL_RESEARCH)


class FolgMedTests(unittest.TestCase):
    def test_folg_med_on_hold_with_positive_trend(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="HOLD",
                    anbefaling="HOLD / OBSERVER",
                    trend_regime="MODERAT OPPTREND",
                    relative_strength_20d=3.0,
                    score=62,
                )
            ),
        )

        self.assertEqual(item["watchlist_action"], ACTION_FOLG_MED)
        self.assertEqual(item["priority"], 2)

    def test_folg_med_with_strong_score_and_negative_sentiment(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="CHECK",
                    anbefaling="HOLD / OBSERVER",
                    trend_regime="MODERAT OPPTREND",
                    score=72,
                )
            ),
            sentiment_item=_sentiment_item(sentiment=SENTIMENT_NEGATIVE),
        )

        self.assertEqual(item["watchlist_action"], ACTION_FOLG_MED)
        self.assertIn("dobbeltsjekk", item["takeaway"])


class VentTests(unittest.TestCase):
    def test_vent_on_hold_and_weak_trend(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="WAIT",
                    anbefaling="HOLD / OBSERVER",
                    trend_regime="SVAK / NEGATIV TREND",
                    relative_strength_20d=-2.0,
                    score=50,
                )
            ),
        )

        self.assertEqual(item["watchlist_action"], ACTION_VENT)

    def test_vent_on_low_score(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="LOW",
                    anbefaling="KJØP / ØK",
                    trend_regime="SVAK / NEGATIV TREND",
                    relative_strength_20d=-1.0,
                    score=40,
                )
            ),
        )

        self.assertEqual(item["watchlist_action"], ACTION_VENT)


class PriorityResolutionTests(unittest.TestCase):
    def test_priority_one_wins_over_priority_two(self):
        item = _build_watchlist_advisor_item(
            pd.Series(_watchlist_row()),
            earnings_item=_earnings_item(days_until=3),
            snapshot_info={"score_fall": True},
        )

        self.assertEqual(item["watchlist_action"], ACTION_AVVENT_EARNINGS)

    def test_fjern_wins_over_flytt_for_weak_avoid(self):
        item = _build_watchlist_advisor_item(
            pd.Series(
                _watchlist_row(
                    ticker="DROP",
                    anbefaling="UNNGÅ / SELG",
                    trend_regime="SVAK / NEGATIV TREND",
                    relative_strength_20d=-7.0,
                    score=30,
                )
            ),
            snapshot_info={"score_fall": True},
        )

        self.assertEqual(item["watchlist_action"], ACTION_FJERN_FRA_WATCHLIST)


class OwnedTickerExclusionTests(unittest.TestCase):
    def test_owned_tickers_are_excluded(self):
        output = build_watchlist_advisor(
            watchlist_report=pd.DataFrame(
                [
                    _watchlist_row(ticker="NVDA"),
                    _watchlist_row(ticker="AAPL", score=70),
                ]
            ),
            portfolio_report=pd.DataFrame([_portfolio_row(ticker="AAPL")]),
        )

        tickers = [item["ticker"] for item in output["items"]]
        self.assertEqual(tickers, ["NVDA"])


class EmptyAndMissingDataTests(unittest.TestCase):
    def test_empty_watchlist_returns_empty_items(self):
        output = build_watchlist_advisor(
            watchlist_report=pd.DataFrame(),
        )

        self.assertEqual(output["items"], [])
        self.assertEqual(output["method"], "rule_v1")
        self.assertIn("Tolkningslag for watchlist", output["disclaimer"])

    def test_missing_support_data_does_not_crash(self):
        output = build_watchlist_advisor(
            watchlist_report=pd.DataFrame([_watchlist_row()]),
            analyst_summary=None,
            sentiment_summary=None,
            earnings_summary=None,
            snapshot_changes=None,
        )

        self.assertEqual(len(output["items"]), 1)
        self.assertIn("Manglende analytikerdata", output["items"][0]["watch_out_for"])


class BuildWatchlistAdvisorTests(unittest.TestCase):
    def test_sorts_by_priority_then_ticker(self):
        output = build_watchlist_advisor(
            watchlist_report=pd.DataFrame(
                [
                    _watchlist_row(
                        ticker="ZZZ",
                        anbefaling="HOLD / OBSERVER",
                        trend_regime="SVAK / NEGATIV TREND",
                        score=50,
                    ),
                    _watchlist_row(ticker="AAA"),
                    _watchlist_row(
                        ticker="BBB",
                        anbefaling="HOLD / OBSERVER",
                        trend_regime="MODERAT OPPTREND",
                        score=72,
                    ),
                ]
            ),
        )

        actions = [item["watchlist_action"] for item in output["items"]]
        priorities = [item["priority"] for item in output["items"]]
        self.assertEqual(actions[0], ACTION_VURDER_KJOP)
        self.assertEqual(actions[1], ACTION_FOLG_MED)
        self.assertEqual(actions[2], ACTION_VENT)
        self.assertEqual(priorities[:2], [1, 2])


class ContextIntegrationTests(unittest.TestCase):
    @patch("src.context.build_daily_briefing", return_value={})
    @patch("src.context.build_advisor_details", return_value={})
    @patch("src.context.build_advisor_output", return_value={"items": []})
    @patch("src.context.build_analyst_summary", return_value={})
    @patch("src.context.build_earnings_summary", return_value={})
    @patch("src.context.build_alerts", return_value=[])
    @patch("src.context.build_daily_flow", return_value={})
    @patch("src.context.build_sentiment_summary", return_value={"items": []})
    @patch("src.context.build_news_summary", return_value={"items": []})
    @patch("src.context.analyze_watchlist")
    def test_build_agent_context_includes_watchlist_advisor_output(
        self,
        mock_analyze_watchlist,
        _mock_news,
        _mock_sentiment,
        _mock_daily_flow,
        _mock_alerts,
        _mock_earnings,
        _mock_analyst,
        _mock_advisor_output,
        _mock_advisor_details,
        _mock_daily_briefing,
    ):
        from src.context import build_agent_context

        mock_analyze_watchlist.return_value = pd.DataFrame(
            [_watchlist_row(ticker="NVDA")]
        )

        with patch("src.context.build_dashboard") as mock_dashboard:
            mock_dashboard.return_value = {
                "changes_since_last_snapshot": {
                    "recommendation_changed": pd.DataFrame(),
                    "large_score_changes": pd.DataFrame(),
                },
            }

            context = build_agent_context(
                watchlist=["NVDA"],
                portfolio=[],
                pause_seconds=0,
            )

        self.assertIn("watchlist_advisor_output", context)
        self.assertEqual(context["watchlist_advisor_output"]["method"], "rule_v1")
        self.assertEqual(len(context["watchlist_advisor_output"]["items"]), 1)
        self.assertEqual(
            context["watchlist_advisor_output"]["items"][0]["ticker"],
            "NVDA",
        )


class WatchlistAdvisorUiFormatterTests(unittest.TestCase):
    def _sample_output(self):
        return {
            "items": [
                {
                    "ticker": "NVDA",
                    "watchlist_action": ACTION_VURDER_KJOP,
                    "headline": "Vurder kjøp",
                    "why": ["Modellanbefaling: KJØP / ØK"],
                    "watch_out_for": ["Kvartalsrapport om 5 dager"],
                    "takeaway": "Sterk kandidat.",
                    "priority": 1,
                }
            ],
            "disclaimer": "Tolkningslag for watchlist.",
        }

    def test_build_watchlist_advisor_table_from_output(self):
        table = build_watchlist_advisor_table(self._sample_output())

        self.assertEqual(len(table), 1)
        self.assertEqual(table.iloc[0]["Ticker"], "NVDA")
        self.assertEqual(table.iloc[0]["Handling"], "Vurder kjøp")
        self.assertEqual(table.iloc[0]["Headline"], "Vurder kjøp")
        self.assertEqual(table.iloc[0]["Tolkning"], "Sterk kandidat.")
        self.assertEqual(table.iloc[0]["Prioritet"], "Høy")

    def test_empty_output_returns_empty_table(self):
        table = build_watchlist_advisor_table({"items": []})

        self.assertTrue(table.empty)
        self.assertEqual(
            list(table.columns),
            ["Ticker", "Handling", "Headline", "Tolkning", "Prioritet"],
        )

    def test_format_watchlist_advisor_detail_handles_missing_sections(self):
        detail = format_watchlist_advisor_detail(
            {
                "ticker": "MSFT",
                "takeaway": "Vent litt.",
            }
        )

        self.assertEqual(detail["why"], [])
        self.assertEqual(detail["watch_out_for"], [])
        self.assertEqual(detail["takeaway"], "Vent litt.")

    def test_format_watchlist_advisor_detail_returns_none_for_empty_item(self):
        self.assertIsNone(format_watchlist_advisor_detail(None))
        self.assertIsNone(format_watchlist_advisor_detail({}))

    def test_action_and_priority_labels(self):
        self.assertEqual(
            format_watchlist_action_label(ACTION_AVVENT_EARNINGS),
            "Avvent earnings",
        )
        self.assertEqual(format_watchlist_priority_label(2), "Medium")
        self.assertEqual(format_watchlist_priority_label(99), "Lav")


if __name__ == "__main__":
    unittest.main()
