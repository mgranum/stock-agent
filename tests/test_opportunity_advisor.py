import unittest
from unittest.mock import ANY, patch

import pandas as pd

from src.opportunity_advisor import (
    build_opportunity_advisor,
    build_opportunity_advisor_item,
    enrich_support_summaries_for_screener,
)
from src.sentiment import SENTIMENT_NEGATIVE


def _screen_row(**overrides):
    row = {
        "ticker": "NVDA",
        "in_watchlist": "Nei",
        "score": 85,
        "recommendation": "KJØP / ØK",
        "trend_regime": "STERK OPPTREND",
        "relative_strength_20d": 12.0,
        "fundamental_score": 78,
        "fundamental_history_score": 80,
    }
    row.update(overrides)
    return row


def _analyst_item(**overrides):
    item = {
        "ticker": "NVDA",
        "recommendation_key": "buy",
        "recommendation_mean": 1.8,
        "upside_pct": 15.0,
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


class StrongCandidateTests(unittest.TestCase):
    def test_strong_candidate_gets_why_interesting(self):
        item = build_opportunity_advisor_item(
            _screen_row(),
            analyst_item=_analyst_item(),
        )

        self.assertIn("Høy score (85)", item["why_interesting"])
        self.assertIn("Sterk trend", item["why_interesting"])
        self.assertIn("Sterk relativ styrke (12.0%)", item["why_interesting"])
        self.assertNotIn("Positiv relativ styrke (12.0%)", item["why_interesting"])
        self.assertEqual(item["headline"], "Sterk screener-kandidat")
        self.assertEqual(item["priority"], 1)


class WatchOutTests(unittest.TestCase):
    def test_earnings_within_7_days_in_watch_out_for(self):
        item = build_opportunity_advisor_item(
            _screen_row(),
            earnings_item=_earnings_item(days_until=5),
        )

        self.assertTrue(
            any("Kvartalsrapport om 5 dager" in line for line in item["watch_out_for"])
        )

    def test_negative_sentiment_in_watch_out_for(self):
        item = build_opportunity_advisor_item(
            _screen_row(),
            sentiment_item=_sentiment_item(sentiment=SENTIMENT_NEGATIVE),
        )

        self.assertIn("Negativ nyhetstone", item["watch_out_for"])

    def test_weak_analyst_consensus_in_watch_out_for(self):
        item = build_opportunity_advisor_item(
            _screen_row(),
            analyst_item=_analyst_item(
                recommendation_key="sell",
                recommendation_mean=4.2,
                upside_pct=-8.0,
            ),
        )

        self.assertTrue(
            any(
                "Svak eller negativ analytikerkonsensus" in line
                for line in item["watch_out_for"]
            )
        )


class AnalystConsensusInterpretationTests(unittest.TestCase):
    def _analyst_watch_out(self, **analyst_overrides):
        item = build_opportunity_advisor_item(
            _screen_row(),
            analyst_item=_analyst_item(**analyst_overrides),
        )
        return [
            line
            for line in item["watch_out_for"]
            if "analytikerkonsensus" in line
        ]

    def test_strong_buy_does_not_add_watch_out(self):
        self.assertEqual(
            self._analyst_watch_out(
                recommendation_key="strong_buy",
                recommendation_mean=1.2,
                upside_pct=-5.0,
            ),
            [],
        )

    def test_buy_does_not_add_watch_out(self):
        self.assertEqual(
            self._analyst_watch_out(
                recommendation_key="buy",
                recommendation_mean=2.0,
                upside_pct=-3.0,
            ),
            [],
        )

    def test_hold_does_not_add_watch_out(self):
        self.assertEqual(
            self._analyst_watch_out(
                recommendation_key="hold",
                recommendation_mean=3.0,
                upside_pct=-10.0,
            ),
            [],
        )

    def test_sell_adds_watch_out(self):
        watch_out = self._analyst_watch_out(
            recommendation_key="sell",
            recommendation_mean=4.5,
        )
        self.assertEqual(len(watch_out), 1)
        self.assertIn("Selg", watch_out[0])

    def test_strong_sell_adds_watch_out(self):
        watch_out = self._analyst_watch_out(
            recommendation_key="strong_sell",
            recommendation_mean=4.8,
        )
        self.assertEqual(len(watch_out), 1)
        self.assertIn("Sterk selg", watch_out[0])

    def test_missing_key_uses_recommendation_mean(self):
        watch_out = self._analyst_watch_out(
            recommendation_key=None,
            recommendation_mean=4.2,
        )
        self.assertEqual(len(watch_out), 1)

        no_watch_out = self._analyst_watch_out(
            recommendation_key=None,
            recommendation_mean=3.2,
        )
        self.assertEqual(no_watch_out, [])


class TakeawayInterpretationTests(unittest.TestCase):
    def test_strong_score_and_relative_strength_gives_advisory_takeaway(self):
        item = build_opportunity_advisor_item(
            _screen_row(
                score=85,
                trend_regime="MODERAT OPPTREND",
                relative_strength_20d=8.5,
                fundamental_score=60,
                fundamental_history_score=62,
            ),
            analyst_item={
                "ticker": "NVDA",
                "recommendation_mean": 2.0,
                "analyst_count": 10,
            },
        )

        self.assertIn("modellen både liker totalbildet og kursutviklingen", item["takeaway"])

    def test_strong_score_and_positive_analyst_gives_consensus_takeaway(self):
        item = build_opportunity_advisor_item(
            _screen_row(score=85),
            analyst_item=_analyst_item(recommendation_key="buy"),
        )

        self.assertIn(
            "modellen og analytikerkonsensus i positiv retning",
            item["takeaway"],
        )

    def test_strong_score_and_neutral_analyst_gives_skeptical_takeaway(self):
        item = build_opportunity_advisor_item(
            _screen_row(score=85),
            analyst_item=_analyst_item(recommendation_key="hold"),
        )

        self.assertIn("Modellen er mer positiv enn analytikerne", item["takeaway"])

    def test_strong_score_and_near_earnings_gives_cautious_takeaway(self):
        item = build_opportunity_advisor_item(
            _screen_row(score=85),
            analyst_item=_analyst_item(),
            earnings_item=_earnings_item(days_until=4),
        )

        self.assertIn("rapportdato nærmer seg", item["takeaway"])

    def test_why_interesting_has_no_duplicate_relative_strength_signal(self):
        item = build_opportunity_advisor_item(_screen_row(relative_strength_20d=12.0))

        rs_lines = [
            line
            for line in item["why_interesting"]
            if "relativ styrke" in line.lower()
        ]
        self.assertEqual(len(rs_lines), 1)
        self.assertIn("Sterk relativ styrke (12.0%)", rs_lines)

    def test_jpm_like_case_without_watch_out(self):
        item = build_opportunity_advisor_item(
            _screen_row(
                ticker="JPM",
                score=100,
                trend_regime="MODERAT OPPTREND",
                relative_strength_20d=8.5,
                fundamental_score=72,
                fundamental_history_score=74,
            ),
            analyst_item={
                "ticker": "JPM",
                "recommendation_mean": 2.0,
                "analyst_count": 20,
            },
            earnings_item=_earnings_item(ticker="JPM", days_until=20),
        )

        self.assertEqual(item["watch_out_for"], [])
        self.assertIn(
            "modellen både liker totalbildet og kursutviklingen",
            item["takeaway"],
        )
        self.assertIn("Siden det ikke er tydelige forbehold", item["takeaway"])


class ResilienceTests(unittest.TestCase):
    def test_missing_analyst_data_in_watch_out_for(self):
        item = build_opportunity_advisor_item(
            _screen_row(),
            analyst_item=None,
        )

        self.assertIn("Manglende analytikerdata", item["watch_out_for"])

    def test_empty_support_data_does_not_crash(self):
        item = build_opportunity_advisor_item(
            _screen_row(score=60, trend_regime="SVAK / NEGATIV TREND"),
            analyst_item=None,
            sentiment_item=None,
            earnings_item=None,
        )

        self.assertEqual(item["ticker"], "NVDA")
        self.assertIsInstance(item["why_interesting"], list)
        self.assertIsInstance(item["watch_out_for"], list)

    def test_empty_screener_results(self):
        output = build_opportunity_advisor(pd.DataFrame())

        self.assertEqual(output["items"], [])

    def test_build_opportunity_advisor_limits_to_top_n(self):
        df = pd.DataFrame(
            [
                _screen_row(ticker="AAA", score=90),
                _screen_row(ticker="BBB", score=88),
                _screen_row(ticker="CCC", score=86),
            ]
        )

        output = build_opportunity_advisor(df, limit=2)

        self.assertEqual(len(output["items"]), 2)


class QualityAndMomentumTests(unittest.TestCase):
    def test_quality_candidate_why(self):
        item = build_opportunity_advisor_item(
            _screen_row(
                score=70,
                trend_regime="MODERAT OPPTREND",
                relative_strength_20d=2.0,
                fundamental_score=80,
                fundamental_history_score=78,
            ),
            analyst_item=_analyst_item(),
        )

        self.assertIn("Sterk fundamental kvalitet", item["why_interesting"])
        self.assertIn("Sterk fundamental utvikling", item["why_interesting"])
        self.assertEqual(item["headline"], "Kvalitetskandidat")

    def test_momentum_candidate_why(self):
        item = build_opportunity_advisor_item(
            _screen_row(
                score=72,
                trend_regime="MODERAT OPPTREND",
                relative_strength_20d=11.5,
                fundamental_score=60,
                fundamental_history_score=62,
            ),
            analyst_item=_analyst_item(),
        )

        self.assertIn("Sterk relativ styrke (11.5%)", item["why_interesting"])
        self.assertIn("Positiv kursutvikling", item["why_interesting"])
        self.assertEqual(item["headline"], "Momentumkandidat")


class SupportDataEnrichmentTests(unittest.TestCase):
    @patch("src.opportunity_advisor.get_news")
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_screener_ticker_outside_context_gets_analyst_data(
        self,
        mock_get_analyst,
        mock_get_earnings,
        mock_get_news,
    ):
        mock_get_analyst.return_value = {
            "ticker": "JPM",
            "recommendation_key": "buy",
            "recommendation_mean": 2.0,
            "upside_pct": 12.0,
            "analyst_count": 20,
        }
        mock_get_earnings.return_value = {
            "ticker": "JPM",
            "days_until": 20,
        }
        mock_get_news.return_value = []

        screener = pd.DataFrame([_screen_row(ticker="JPM")])

        output = build_opportunity_advisor(
            screener,
            analyst_summary={"items": [_analyst_item(ticker="NVDA")]},
            sentiment_summary={"items": []},
            earnings_summary={"items": []},
            news_summary={"items": []},
        )

        jpm = next(item for item in output["items"] if item["ticker"] == "JPM")
        self.assertNotIn("Manglende analytikerdata", jpm["watch_out_for"])
        mock_get_analyst.assert_called_once_with(
            "JPM",
            use_cache=True,
            today=ANY,
        )

    @patch("src.opportunity_advisor.get_news")
    @patch("src.opportunity_advisor.get_earnings")
    @patch("src.opportunity_advisor.get_analyst")
    def test_missing_support_data_still_handled_safely(
        self,
        mock_get_analyst,
        mock_get_earnings,
        mock_get_news,
    ):
        mock_get_analyst.return_value = {"ticker": "JPM"}
        mock_get_earnings.return_value = {"ticker": "JPM"}
        mock_get_news.return_value = []

        output = build_opportunity_advisor(
            pd.DataFrame([_screen_row(ticker="JPM")]),
            analyst_summary={"items": []},
            sentiment_summary={"items": []},
            earnings_summary={"items": []},
            news_summary={"items": []},
        )

        jpm = output["items"][0]
        self.assertIn("Manglende analytikerdata", jpm["watch_out_for"])

    @patch("src.opportunity_advisor._build_support_for_tickers")
    def test_only_top_five_are_enriched(self, mock_build_support):
        mock_build_support.return_value = {
            "analyst_summary": {"items": []},
            "earnings_summary": {"items": []},
            "news_summary": {"items": []},
            "sentiment_summary": {"items": []},
        }

        screener = pd.DataFrame(
            [
                _screen_row(ticker=f"T{i}", score=90 - i)
                for i in range(8)
            ]
        )

        enrich_support_summaries_for_screener(
            screener,
            analyst_summary={"items": []},
            sentiment_summary={"items": []},
            earnings_summary={"items": []},
            news_summary={"items": []},
            limit=5,
        )

        called_tickers = mock_build_support.call_args[0][0]
        self.assertEqual(len(called_tickers), 5)
        self.assertEqual(called_tickers, ["T0", "T1", "T2", "T3", "T4"])

    @patch("src.opportunity_advisor._build_support_for_tickers")
    def test_existing_context_tickers_are_not_refetched(self, mock_build_support):
        mock_build_support.return_value = {
            "analyst_summary": {"items": []},
            "earnings_summary": {"items": []},
            "news_summary": {"items": []},
            "sentiment_summary": {"items": []},
        }

        screener = pd.DataFrame(
            [
                _screen_row(ticker="AAPL", score=90),
                _screen_row(ticker="JPM", score=85),
            ]
        )

        enrich_support_summaries_for_screener(
            screener,
            analyst_summary={"items": [_analyst_item(ticker="AAPL")]},
            sentiment_summary={"items": [_sentiment_item(ticker="AAPL")]},
            earnings_summary={"items": [_earnings_item(ticker="AAPL")]},
            news_summary={"items": [{"ticker": "AAPL", "headline": "News"}]},
        )

        called_tickers = mock_build_support.call_args[0][0]
        self.assertEqual(called_tickers, ["JPM"])


if __name__ == "__main__":
    unittest.main()
