import unittest
from unittest.mock import patch

import pandas as pd

from src.news import build_news_table
from src.sentiment import (
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    SENTIMENT_METHOD,
    SENTIMENT_NEGATIVE,
    SENTIMENT_NEUTRAL,
    SENTIMENT_POSITIVE,
    analyze_headline,
    build_sentiment_summary,
    merge_sentiment_into_news_summary,
)


class AnalyzeHeadlineTests(unittest.TestCase):
    def test_positive_beats_estimates(self):
        result = analyze_headline("Nvidia beats estimates on strong AI demand")

        self.assertEqual(result["sentiment"], SENTIMENT_POSITIVE)
        self.assertGreater(result["sentiment_score"], 0.25)
        self.assertEqual(result["sentiment_method"], SENTIMENT_METHOD)
        self.assertIn("beats estimates", result["sentiment_signals"])

    def test_positive_raises_guidance(self):
        result = analyze_headline("Apple raises guidance after record quarter")

        self.assertEqual(result["sentiment"], SENTIMENT_POSITIVE)
        self.assertIn("raises guidance", result["sentiment_signals"])

    def test_positive_upgrade(self):
        result = analyze_headline("Analyst upgraded to buy on growth outlook")

        self.assertEqual(result["sentiment"], SENTIMENT_POSITIVE)
        self.assertIn("upgrade", result["sentiment_signals"])

    def test_positive_price_target_raised(self):
        result = analyze_headline("Price target raised to $250 on margin expansion")

        self.assertEqual(result["sentiment"], SENTIMENT_POSITIVE)
        self.assertIn("price target raised", result["sentiment_signals"])

    def test_negative_misses_estimates(self):
        result = analyze_headline("Microsoft misses estimates as cloud growth slows")

        self.assertEqual(result["sentiment"], SENTIMENT_NEGATIVE)
        self.assertLess(result["sentiment_score"], -0.25)
        self.assertIn("misses estimates", result["sentiment_signals"])

    def test_negative_cuts_guidance(self):
        result = analyze_headline("Company cuts guidance amid weak demand")

        self.assertEqual(result["sentiment"], SENTIMENT_NEGATIVE)
        self.assertIn("cuts guidance", result["sentiment_signals"])

    def test_negative_downgrade(self):
        result = analyze_headline("Analyst downgrade hits shares")

        self.assertEqual(result["sentiment"], SENTIMENT_NEGATIVE)
        self.assertIn("downgrade", result["sentiment_signals"])

    def test_negative_lawsuit(self):
        result = analyze_headline("Firm faces lawsuit over accounting practices")

        self.assertEqual(result["sentiment"], SENTIMENT_NEGATIVE)
        self.assertIn("lawsuit", result["sentiment_signals"])

    def test_negative_investigation(self):
        result = analyze_headline("Regulators open investigation into sales practices")

        self.assertEqual(result["sentiment"], SENTIMENT_NEGATIVE)
        self.assertIn("investigation", result["sentiment_signals"])

    def test_neutral_headline(self):
        result = analyze_headline("Company schedules investor day for September")

        self.assertEqual(result["sentiment"], SENTIMENT_NEUTRAL)
        self.assertEqual(result["sentiment_score"], 0.0)
        self.assertEqual(result["sentiment_signals"], [])


class LiveFeedHeadlineTests(unittest.TestCase):
    """Headlines styled like typical Yahoo Finance / yfinance feed items."""

    def test_nvda_gains_on_solid_ai_demand(self):
        result = analyze_headline(
            "NVIDIA Corporation (NVDA) Gains As AI Demand Remains Solid: What Investors Need To Know"
        )

        self.assertEqual(result["sentiment"], SENTIMENT_POSITIVE)
        self.assertIn("gains", result["sentiment_signals"])

    def test_equinor_remains_solid(self):
        result = analyze_headline(
            "Equinor ASA (EQNR.OL) Remains Solid Amid Oil Price Volatility"
        )

        self.assertEqual(result["sentiment"], SENTIMENT_POSITIVE)
        self.assertIn("remains solid", result["sentiment_signals"])

    def test_analyst_upgrade_and_price_target_raised(self):
        result = analyze_headline(
            "BofA Upgrades Apple (AAPL), Raises Price Target on Resilient Services Growth"
        )

        self.assertEqual(result["sentiment"], SENTIMENT_POSITIVE)
        self.assertIn("upgrade", result["sentiment_signals"])

    def test_msft_beats_on_strong_demand(self):
        result = analyze_headline(
            "Microsoft (MSFT) Beats Q1 Earnings on Strong Demand for Cloud Products"
        )

        self.assertEqual(result["sentiment"], SENTIMENT_POSITIVE)
        self.assertIn("beats", result["sentiment_signals"])
        self.assertIn("strong demand", result["sentiment_signals"])

    def test_stock_drops_after_data_breach(self):
        result = analyze_headline(
            "CrowdStrike (CRWD) Stock Drops After Major Data Breach Hits Enterprise Clients"
        )

        self.assertEqual(result["sentiment"], SENTIMENT_NEGATIVE)
        self.assertIn("drops", result["sentiment_signals"])
        self.assertIn("data breach", result["sentiment_signals"])

    def test_cyberattack_and_investigation(self):
        result = analyze_headline(
            "Company Falls After Cyberattack Triggers Regulatory Investigation and Warning"
        )

        self.assertEqual(result["sentiment"], SENTIMENT_NEGATIVE)
        self.assertIn("cyberattack", result["sentiment_signals"])
        self.assertIn("investigation", result["sentiment_signals"])
        self.assertIn("warning", result["sentiment_signals"])

    def test_oracle_stock_sinks_in_red(self):
        result = analyze_headline("Oracle (ORCL) Stock Sinks After Earnings Miss, Shares in Red")

        self.assertEqual(result["sentiment"], SENTIMENT_NEGATIVE)
        self.assertIn("in red", result["sentiment_signals"])
        self.assertIn("sinks", result["sentiment_signals"])

    def test_downgrade_and_cuts(self):
        result = analyze_headline(
            "Analyst Downgrades Tesla (TSLA), Cuts Outlook After Weak Deliveries"
        )

        self.assertEqual(result["sentiment"], SENTIMENT_NEGATIVE)
        self.assertIn("downgrade", result["sentiment_signals"])
        self.assertIn("cuts", result["sentiment_signals"])

    def test_lawsuit_headline(self):
        result = analyze_headline(
            "Johnson & Johnson (JNJ) Falls on Lawsuit Over Product Safety Claims"
        )

        self.assertEqual(result["sentiment"], SENTIMENT_NEGATIVE)
        self.assertIn("lawsuit", result["sentiment_signals"])
        self.assertIn("falls", result["sentiment_signals"])

    def test_sector_roundup_stays_neutral(self):
        result = analyze_headline(
            "Market Talk: European Equities Mixed Ahead of Central Bank Decisions"
        )

        self.assertEqual(result["sentiment"], SENTIMENT_NEUTRAL)


class BuildSentimentSummaryTests(unittest.TestCase):
    def _news_item(self, **overrides):
        base = {
            "ticker": "NVDA",
            "headline": "Nvidia beats estimates",
            "publisher": "Reuters",
            "published_at": "2026-06-11T19:52:25+00:00",
            "url": "https://example.com/nvda-1",
            "publisher_score": 3,
            "relevance_score": 5,
            "in_portfolio": True,
        }
        base.update(overrides)
        return base

    def test_empty_news_summary(self):
        summary = build_sentiment_summary({})

        self.assertEqual(summary["items"], [])
        self.assertEqual(summary["articles"], [])
        self.assertEqual(summary["notable_positive"], [])
        self.assertEqual(summary["notable_negative"], [])
        self.assertEqual(summary["method"], SENTIMENT_METHOD)

    def test_builds_ticker_aggregate_from_filtered_news(self):
        news_summary = {
            "portfolio_news": [
                self._news_item(),
                self._news_item(
                    headline="Nvidia raises guidance",
                    url="https://example.com/nvda-2",
                ),
            ],
            "watchlist_news": [],
            "items": [],
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        summary = build_sentiment_summary(news_summary)

        self.assertEqual(len(summary["articles"]), 2)
        self.assertEqual(len(summary["items"]), 1)
        self.assertEqual(summary["items"][0]["ticker"], "NVDA")
        self.assertEqual(summary["items"][0]["sentiment"], SENTIMENT_POSITIVE)
        self.assertEqual(summary["items"][0]["article_count"], 2)
        self.assertEqual(summary["items"][0]["confidence"], CONFIDENCE_MEDIUM)
        self.assertIn("NVDA", summary["notable_positive"])

    def test_mixed_ticker_sentiment_has_low_confidence(self):
        news_summary = {
            "portfolio_news": [
                self._news_item(headline="Nvidia beats estimates"),
                self._news_item(
                    headline="Nvidia misses estimates",
                    url="https://example.com/nvda-miss",
                ),
            ],
            "watchlist_news": [],
            "items": [],
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        summary = build_sentiment_summary(news_summary)

        self.assertEqual(summary["items"][0]["positive_count"], 1)
        self.assertEqual(summary["items"][0]["negative_count"], 1)
        self.assertEqual(summary["items"][0]["confidence"], CONFIDENCE_LOW)

    def test_uses_only_filtered_news_not_raw_items(self):
        news_summary = {
            "portfolio_news": [
                self._news_item(headline="Nvidia beats estimates"),
            ],
            "watchlist_news": [],
            "items": [
                {
                    "ticker": "FAKE",
                    "headline": "Fake headline should not be analyzed",
                    "url": "https://example.com/fake",
                }
            ],
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        summary = build_sentiment_summary(news_summary)

        self.assertEqual(len(summary["articles"]), 1)
        self.assertEqual(summary["articles"][0]["ticker"], "NVDA")
        tickers = {item["ticker"] for item in summary["items"]}
        self.assertEqual(tickers, {"NVDA"})

    def test_splits_portfolio_and_watchlist_items(self):
        news_summary = {
            "portfolio_news": [
                self._news_item(ticker="AAPL", in_portfolio=True),
            ],
            "watchlist_news": [
                self._news_item(
                    ticker="MSFT",
                    headline="Microsoft misses estimates",
                    url="https://example.com/msft",
                    in_portfolio=False,
                ),
            ],
            "items": [],
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        summary = build_sentiment_summary(news_summary)

        self.assertEqual([item["ticker"] for item in summary["portfolio_items"]], ["AAPL"])
        self.assertEqual([item["ticker"] for item in summary["watchlist_items"]], ["MSFT"])
        self.assertIn("AAPL", summary["notable_positive"])
        self.assertIn("MSFT", summary["notable_negative"])


class MergeSentimentIntoNewsSummaryTests(unittest.TestCase):
    def test_merges_article_sentiment_into_dashboard_items(self):
        news_summary = {
            "items": [
                {
                    "ticker": "NVDA",
                    "headline": "Nvidia beats estimates",
                    "url": "https://example.com/nvda",
                }
            ],
            "portfolio_news": [
                {
                    "ticker": "NVDA",
                    "headline": "Nvidia beats estimates",
                    "url": "https://example.com/nvda",
                    "publisher_score": 3,
                    "in_portfolio": True,
                }
            ],
            "watchlist_news": [],
            "last_updated": "2026-06-12T08:00:00+00:00",
        }
        sentiment_summary = build_sentiment_summary(news_summary)

        merged = merge_sentiment_into_news_summary(news_summary, sentiment_summary)

        self.assertEqual(merged["items"][0]["sentiment"], SENTIMENT_POSITIVE)
        self.assertIn("beats estimates", merged["items"][0]["sentiment_signals"])


class BuildNewsTableSentimentTests(unittest.TestCase):
    def test_news_table_includes_sentiment_column(self):
        news_summary = {
            "items": [
                {
                    "ticker": "NVDA",
                    "headline": "Nvidia beats estimates",
                    "publisher": "Reuters",
                    "published_at": "2026-06-11T19:52:25+00:00",
                    "url": "https://example.com/nvda",
                    "sentiment": SENTIMENT_POSITIVE,
                }
            ]
        }

        table = build_news_table(news_summary)

        self.assertIn("Sentiment", table.columns)
        self.assertEqual(table.iloc[0]["Sentiment"], "Positiv")


class ContextIntegrationTests(unittest.TestCase):
    @patch("src.context.build_sentiment_summary")
    @patch("src.context.build_news_summary")
    @patch("src.context.build_earnings_summary", return_value={})
    @patch("src.context.build_dashboard", return_value={})
    @patch("src.context.build_alerts", return_value=[])
    @patch("src.context.build_daily_flow", return_value={})
    @patch("src.context.analyze_watchlist")
    def test_context_includes_sentiment_summary(
        self,
        mock_analyze_watchlist,
        _mock_daily_flow,
        _mock_alerts,
        _mock_dashboard,
        _mock_earnings,
        mock_news_summary,
        mock_sentiment_summary,
    ):
        from src.context import build_agent_context

        mock_analyze_watchlist.return_value = pd.DataFrame()
        mock_news_summary.return_value = {
            "items": [],
            "portfolio_news": [],
            "watchlist_news": [],
            "last_updated": "2026-06-12T08:00:00+00:00",
        }
        mock_sentiment_summary.return_value = {
            "items": [],
            "portfolio_items": [],
            "watchlist_items": [],
            "articles": [],
            "notable_positive": [],
            "notable_negative": [],
            "last_updated": "2026-06-12T08:00:00+00:00",
            "method": SENTIMENT_METHOD,
            "disclaimer": "Støttesignal basert på overskrifter. Påvirker ikke anbefaling.",
        }

        context = build_agent_context(
            watchlist=["AAPL"],
            portfolio=[],
            pause_seconds=0,
        )

        mock_sentiment_summary.assert_called_once()
        self.assertIn("sentiment_summary", context)
        self.assertIn("sentiment_summary", context["dashboard"])


if __name__ == "__main__":
    unittest.main()
