import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.news import (
    DEFAULT_MAX_ITEMS,
    MAX_NEWS_AGE_DAYS,
    PUBLISHER_SCORE_HIGH,
    PUBLISHER_SCORE_LOW,
    PUBLISHER_SCORE_MEDIUM,
    _write_news_cache,
    build_news_summary,
    compute_content_relevance_score,
    compute_publisher_score,
    compute_relevance_score,
    dedupe_news_items,
    filter_news_by_scope,
    filter_recent_news,
    filter_relevant_news,
    get_news,
    is_generic_market_headline,
    is_low_quality_publisher,
    is_recent_news,
    normalize_news_item,
    normalize_published_at,
    sort_news_items,
)


class NormalizePublishedAtTests(unittest.TestCase):
    def test_normalizes_iso_string(self):
        self.assertEqual(
            normalize_published_at("2026-06-12T08:17:28Z"),
            "2026-06-12T08:17:28+00:00",
        )

    def test_normalizes_unix_timestamp(self):
        self.assertEqual(
            normalize_published_at(1718179200),
            "2024-06-12T08:00:00+00:00",
        )

    def test_returns_none_for_empty_value(self):
        self.assertIsNone(normalize_published_at(None))
        self.assertIsNone(normalize_published_at(""))


class NormalizeNewsItemTests(unittest.TestCase):
    def test_normalizes_nested_yfinance_item(self):
        raw = {
            "id": "abc",
            "content": {
                "title": "Apple launches new product",
                "pubDate": "2026-06-11T19:52:25Z",
                "provider": {"displayName": "Yahoo Finance"},
                "canonicalUrl": {
                    "url": "https://finance.yahoo.com/news/apple-launches.html",
                },
            },
        }

        item = normalize_news_item(raw, "AAPL")

        self.assertEqual(
            item,
            {
                "ticker": "AAPL",
                "headline": "Apple launches new product",
                "publisher": "Yahoo Finance",
                "published_at": "2026-06-11T19:52:25+00:00",
                "url": "https://finance.yahoo.com/news/apple-launches.html",
            },
        )

    def test_normalizes_legacy_flat_item(self):
        raw = {
            "title": "Legacy headline",
            "publisher": "Reuters",
            "link": "https://example.com/story",
            "providerPublishTime": 1718179200,
        }

        item = normalize_news_item(raw, "msft")

        self.assertEqual(item["ticker"], "MSFT")
        self.assertEqual(item["headline"], "Legacy headline")
        self.assertEqual(item["publisher"], "Reuters")
        self.assertEqual(item["url"], "https://example.com/story")
        self.assertEqual(item["published_at"], "2024-06-12T08:00:00+00:00")

    def test_returns_none_when_headline_missing(self):
        self.assertIsNone(
            normalize_news_item({"content": {"pubDate": "2026-06-11T19:52:25Z"}}, "AAPL")
        )


class RelevanceScoreTests(unittest.TestCase):
    def test_rewards_ticker_and_quality_publisher(self):
        item = {
            "ticker": "AAPL",
            "headline": "AAPL beats earnings expectations",
            "publisher": "Reuters",
        }
        score = compute_relevance_score(
            item,
            company_name="Apple Inc.",
            universe_tickers=["AAPL", "MSFT"],
        )
        self.assertEqual(score, 6)
        self.assertEqual(compute_publisher_score("Reuters"), PUBLISHER_SCORE_HIGH)

    def test_penalizes_other_ticker_and_low_quality_source(self):
        item = {
            "ticker": "MSFT",
            "headline": "Oracle (ORCL) stock sinks after earnings",
            "publisher": "Simply Wall St.",
        }
        score = compute_relevance_score(
            item,
            company_name="Microsoft Corporation",
            universe_tickers=["MSFT", "ORCL"],
        )
        self.assertEqual(score, -6)

    def test_penalizes_generic_market_roundup(self):
        item = {
            "ticker": "VWS.CO",
            "headline": "Buy These Renewable Energy & Battery Stocks Amid Global Energy Crisis",
            "publisher": "Zacks",
        }
        self.assertTrue(is_generic_market_headline(item["headline"], "VWS.CO"))
        self.assertFalse(is_low_quality_publisher("Zacks"))
        self.assertEqual(compute_publisher_score("Zacks"), PUBLISHER_SCORE_MEDIUM)
        score = compute_relevance_score(
            item,
            company_name="Vestas Wind Systems A/S",
            universe_tickers=["VWS.CO"],
        )
        self.assertEqual(score, -1)


class PublisherQualityTests(unittest.TestCase):
    def test_reuters_ranks_before_insider_monkey(self):
        items = [
            {
                "ticker": "AAPL",
                "headline": "AAPL outlook from Apple Inc. according to analysts",
                "publisher": "Insider Monkey",
                "published_at": "2026-06-12T12:00:00+00:00",
                "url": "https://example.com/aapl-monkey",
            },
            {
                "ticker": "AAPL",
                "headline": "Reuters reports on AAPL earnings",
                "publisher": "Reuters",
                "published_at": "2026-06-12T10:00:00+00:00",
                "url": "https://example.com/aapl-reuters",
            },
        ]

        filtered = filter_relevant_news(
            items,
            company_names={"AAPL": "Apple Inc."},
            universe_tickers=["AAPL"],
        )

        self.assertEqual(filtered[0]["publisher"], "Reuters")
        self.assertEqual(filtered[1]["publisher"], "Insider Monkey")

    def test_wsj_ranks_before_motley_fool(self):
        items = [
            {
                "ticker": "MSFT",
                "headline": "Motley Fool view on MSFT and Microsoft Corporation cloud",
                "publisher": "Motley Fool",
                "published_at": "2026-06-12T12:00:00+00:00",
                "url": "https://example.com/msft-fool",
            },
            {
                "ticker": "MSFT",
                "headline": "Microsoft Corporation expands cloud platform",
                "publisher": "The Wall Street Journal",
                "published_at": "2026-06-12T10:00:00+00:00",
                "url": "https://example.com/msft-wsj",
            },
        ]

        filtered = filter_relevant_news(
            items,
            company_names={"MSFT": "Microsoft Corporation"},
            universe_tickers=["MSFT"],
        )

        self.assertEqual(filtered[0]["publisher"], "The Wall Street Journal")
        self.assertEqual(filtered[1]["publisher"], "Motley Fool")

    def test_publisher_score_affects_total_score(self):
        item = {
            "ticker": "AAPL",
            "headline": "AAPL beats earnings expectations",
            "publisher": "Reuters",
        }
        content_score = compute_content_relevance_score(
            item,
            company_name="Apple Inc.",
            universe_tickers=["AAPL"],
        )
        publisher_score = compute_publisher_score("Reuters")

        self.assertEqual(content_score, 3)
        self.assertEqual(publisher_score, PUBLISHER_SCORE_HIGH)
        self.assertEqual(
            compute_relevance_score(
                item,
                company_name="Apple Inc.",
                universe_tickers=["AAPL"],
            ),
            content_score + publisher_score,
        )

    def test_max_eight_news_returned(self):
        tickers = [f"T{i}" for i in range(10)]

        with patch("src.news.get_company_name") as mock_company_name, patch(
            "src.news.get_news"
        ) as mock_get_news:
            mock_company_name.side_effect = lambda ticker: f"Company {ticker}"

            def side_effect(ticker, use_cache=True, today=None):
                return [
                    {
                        "ticker": ticker,
                        "headline": f"{ticker} reports strong quarter",
                        "publisher": "Reuters",
                        "published_at": "2026-06-12T10:00:00+00:00",
                        "url": f"https://example.com/{ticker}-1",
                        "source": "yfinance",
                        "last_updated": "2026-06-12T08:00:00+00:00",
                    },
                    {
                        "ticker": ticker,
                        "headline": f"{ticker} expands operations",
                        "publisher": "Bloomberg",
                        "published_at": "2026-06-11T10:00:00+00:00",
                        "url": f"https://example.com/{ticker}-2",
                        "source": "yfinance",
                        "last_updated": "2026-06-12T08:00:00+00:00",
                    },
                ]

            mock_get_news.side_effect = side_effect

            summary = build_news_summary(
                portfolio=[{"ticker": ticker} for ticker in tickers],
                watchlist=[],
                use_cache=False,
                today=date(2026, 6, 12),
            )

        self.assertEqual(len(summary["items"]), DEFAULT_MAX_ITEMS)
        self.assertEqual(DEFAULT_MAX_ITEMS, 8)

    def test_max_two_per_ticker_returned(self):
        items = [
            {
                "ticker": "AAPL",
                "headline": f"AAPL update {index}",
                "publisher": "Reuters",
                "published_at": f"2026-06-{index:02d}T10:00:00+00:00",
                "url": f"https://example.com/aapl-{index}",
            }
            for index in range(1, 6)
        ]

        filtered = filter_relevant_news(
            items,
            company_names={"AAPL": "Apple Inc."},
            universe_tickers=["AAPL"],
        )

        self.assertEqual(len(filtered), 2)


class DedupeNewsItemsTests(unittest.TestCase):
    def test_dedupes_on_url_and_headline(self):
        items = [
            {
                "ticker": "AAPL",
                "headline": "Apple launches product",
                "url": "https://example.com/a",
            },
            {
                "ticker": "AAPL",
                "headline": "Apple launches product",
                "url": "https://example.com/b",
            },
            {
                "ticker": "AAPL",
                "headline": "Different headline",
                "url": "https://example.com/a",
            },
        ]

        deduped = dedupe_news_items(items)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["headline"], "Apple launches product")


class FilterRelevantNewsTests(unittest.TestCase):
    def test_filters_low_score_and_limits_per_ticker(self):
        items = [
            {
                "ticker": "AAPL",
                "headline": "AAPL raises guidance",
                "publisher": "Reuters",
                "published_at": "2026-06-12T10:00:00+00:00",
                "url": "https://example.com/aapl-1",
            },
            {
                "ticker": "AAPL",
                "headline": "Apple unveils new MacBook",
                "publisher": "Bloomberg",
                "published_at": "2026-06-11T10:00:00+00:00",
                "url": "https://example.com/aapl-2",
            },
            {
                "ticker": "AAPL",
                "headline": "Apple mentioned in sector roundup",
                "publisher": "Zacks",
                "published_at": "2026-06-10T10:00:00+00:00",
                "url": "https://example.com/aapl-3",
            },
            {
                "ticker": "MSFT",
                "headline": "Oracle (ORCL) stock sinks",
                "publisher": "Reuters",
                "published_at": "2026-06-12T09:00:00+00:00",
                "url": "https://example.com/msft-noise",
            },
        ]

        filtered = filter_relevant_news(
            items,
            company_names={
                "AAPL": "Apple Inc.",
                "MSFT": "Microsoft Corporation",
            },
            universe_tickers=["AAPL", "MSFT"],
        )

        self.assertEqual(len(filtered), 2)
        self.assertEqual({item["ticker"] for item in filtered}, {"AAPL"})
        self.assertEqual(
            [item["headline"] for item in filtered],
            ["AAPL raises guidance", "Apple unveils new MacBook"],
        )


class SortNewsItemsTests(unittest.TestCase):
    def test_sorts_by_relevance_score_then_published_at(self):
        items = [
            {
                "ticker": "MSFT",
                "relevance_score": 5,
                "published_at": "2026-06-10T10:00:00+00:00",
            },
            {
                "ticker": "AAPL",
                "relevance_score": 8,
                "published_at": "2026-06-11T10:00:00+00:00",
            },
            {
                "ticker": "AAPL",
                "relevance_score": 8,
                "published_at": "2026-06-09T10:00:00+00:00",
            },
        ]

        sorted_items = sort_news_items(items)

        self.assertEqual(
            [item["published_at"] for item in sorted_items],
            [
                "2026-06-11T10:00:00+00:00",
                "2026-06-09T10:00:00+00:00",
                "2026-06-10T10:00:00+00:00",
            ],
        )


class FilterNewsByScopeTests(unittest.TestCase):
    def test_splits_portfolio_and_watchlist_news(self):
        items = [
            {"ticker": "AAPL", "headline": "Apple news"},
            {"ticker": "MSFT", "headline": "Microsoft news"},
            {"ticker": "NVDA", "headline": "Nvidia news"},
        ]

        portfolio_news, watchlist_news = filter_news_by_scope(
            items,
            portfolio_tickers={"AAPL", "NVDA"},
        )

        self.assertEqual([item["ticker"] for item in portfolio_news], ["AAPL", "NVDA"])
        self.assertEqual([item["ticker"] for item in watchlist_news], ["MSFT"])


class NewsCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cache_root = Path(self.temp_dir.name)

        self.temp_dir_patcher = patch(
            "src.news._cache_dir",
            return_value=self.cache_root,
        )
        self.temp_dir_patcher.start()
        self.addCleanup(self.temp_dir_patcher.stop)

    @patch("src.news._fetch_yfinance_news")
    def test_get_news_writes_and_reads_cache(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "ticker": "AAPL",
                "headline": "Apple headline",
                "publisher": "Yahoo Finance",
                "published_at": "2026-06-11T19:52:25+00:00",
                "url": "https://finance.yahoo.com/news/apple.html",
                "source": "yfinance",
                "last_updated": "2026-06-12T08:00:00+00:00",
            }
        ]

        first = get_news("AAPL", use_cache=True, today=date(2026, 6, 12))
        second = get_news("AAPL", use_cache=True, today=date(2026, 6, 12))

        mock_fetch.assert_called_once()
        self.assertEqual(first[0]["headline"], "Apple headline")
        self.assertEqual(second[0]["headline"], "Apple headline")

        cache_file = self.cache_root / "AAPL_news.json"
        self.assertTrue(cache_file.exists())
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        self.assertEqual(cached["date"], "2026-06-12")
        self.assertEqual(cached["data"][0]["publisher"], "Yahoo Finance")

    def test_cache_refresh_on_new_day(self):
        cache_file = self.cache_root / "MSFT_news.json"
        _write_news_cache(
            cache_file,
            "MSFT",
            [
                {
                    "ticker": "MSFT",
                    "headline": "Old headline",
                    "publisher": "Reuters",
                    "published_at": "2026-06-10T10:00:00+00:00",
                    "url": "https://example.com/old",
                    "source": "yfinance",
                    "last_updated": "2026-06-11T08:00:00+00:00",
                }
            ],
            today=date(2026, 6, 11),
        )

        with patch("src.news._fetch_yfinance_news") as mock_fetch:
            mock_fetch.return_value = [
                {
                    "ticker": "MSFT",
                    "headline": "Fresh headline",
                    "publisher": "Bloomberg",
                    "published_at": "2026-06-12T10:00:00+00:00",
                    "url": "https://example.com/new",
                    "source": "yfinance",
                    "last_updated": "2026-06-12T08:00:00+00:00",
                }
            ]
            result = get_news("MSFT", use_cache=True, today=date(2026, 6, 12))

        mock_fetch.assert_called_once()
        self.assertEqual(result[0]["headline"], "Fresh headline")


class BuildNewsSummaryTests(unittest.TestCase):
    @patch("src.news.get_company_name")
    @patch("src.news.get_news")
    def test_builds_summary_with_sorting_and_limit(self, mock_get_news, mock_company_name):
        mock_company_name.side_effect = lambda ticker: {
            "AAPL": "Apple Inc.",
            "MSFT": "Microsoft Corporation",
        }.get(ticker, "")

        def side_effect(ticker, use_cache=True, today=None):
            data = {
                "AAPL": [
                    {
                        "ticker": "AAPL",
                        "headline": "Older AAPL outlook from Apple Inc.",
                        "publisher": "Insider Monkey",
                        "published_at": "2026-06-10T10:00:00+00:00",
                        "url": "https://example.com/apple-old",
                        "source": "yfinance",
                        "last_updated": "2026-06-12T08:00:00+00:00",
                    },
                    {
                        "ticker": "AAPL",
                        "headline": "Newer AAPL beats estimates",
                        "publisher": "Reuters",
                        "published_at": "2026-06-12T10:00:00+00:00",
                        "url": "https://example.com/apple-new",
                        "source": "yfinance",
                        "last_updated": "2026-06-12T08:00:00+00:00",
                    },
                ],
                "MSFT": [
                    {
                        "ticker": "MSFT",
                        "headline": "Microsoft Corporation expands cloud platform",
                        "publisher": "Bloomberg",
                        "published_at": "2026-06-11T10:00:00+00:00",
                        "url": "https://example.com/msft",
                        "source": "yfinance",
                        "last_updated": "2026-06-12T08:00:00+00:00",
                    }
                ],
            }
            return data[ticker]

        mock_get_news.side_effect = side_effect

        summary = build_news_summary(
            portfolio=[{"ticker": "AAPL"}],
            watchlist=["MSFT"],
            use_cache=False,
            today=date(2026, 6, 12),
            max_items=2,
        )

        self.assertEqual(len(summary["items"]), 2)
        self.assertEqual(summary["items"][0]["ticker"], "AAPL")
        self.assertEqual(summary["items"][0]["headline"], "Newer AAPL beats estimates")
        self.assertEqual(len(summary["portfolio_news"]), 2)
        self.assertEqual(len(summary["watchlist_news"]), 1)
        self.assertEqual(summary["watchlist_news"][0]["ticker"], "MSFT")
        self.assertEqual(summary["last_updated"], "2026-06-12T08:00:00+00:00")

    @patch("src.news.get_company_name", return_value="Apple Inc.")
    @patch("src.news.get_news")
    def test_limits_to_two_per_ticker(self, mock_get_news, _mock_company_name):
        mock_get_news.return_value = [
            {
                "ticker": "AAPL",
                "headline": f"AAPL update {index}",
                "publisher": "Reuters",
                "published_at": f"2026-06-{index:02d}T10:00:00+00:00",
                "url": f"https://example.com/{index}",
                "source": "yfinance",
                "last_updated": "2026-06-12T08:00:00+00:00",
            }
            for index in range(1, 20)
        ]

        summary = build_news_summary(
            portfolio=[{"ticker": "AAPL"}],
            watchlist=[],
            use_cache=False,
            today=date(2026, 6, 12),
        )

        self.assertEqual(len(summary["portfolio_news"]), 2)
        self.assertEqual(len(summary["items"]), 2)

    @patch("src.news.get_company_name")
    @patch("src.news.get_news")
    def test_respects_default_max_items(self, mock_get_news, mock_company_name):
        tickers = [f"T{i}" for i in range(10)]

        def company_name(ticker):
            return f"Company {ticker}"

        mock_company_name.side_effect = company_name

        def side_effect(ticker, use_cache=True, today=None):
            return [
                {
                    "ticker": ticker,
                    "headline": f"{ticker} reports strong quarter",
                    "publisher": "Reuters",
                    "published_at": "2026-06-12T10:00:00+00:00",
                    "url": f"https://example.com/{ticker}-1",
                    "source": "yfinance",
                    "last_updated": "2026-06-12T08:00:00+00:00",
                },
                {
                    "ticker": ticker,
                    "headline": f"{ticker} expands operations",
                    "publisher": "Bloomberg",
                    "published_at": "2026-06-11T10:00:00+00:00",
                    "url": f"https://example.com/{ticker}-2",
                    "source": "yfinance",
                    "last_updated": "2026-06-12T08:00:00+00:00",
                },
            ]

        mock_get_news.side_effect = side_effect

        summary = build_news_summary(
            portfolio=[{"ticker": ticker} for ticker in tickers],
            watchlist=[],
            use_cache=False,
            today=date(2026, 6, 12),
        )

        self.assertEqual(len(summary["items"]), DEFAULT_MAX_ITEMS)
        self.assertEqual(len(summary["portfolio_news"]), 20)


class RecencyFilterTests(unittest.TestCase):
    def test_filters_out_old_news(self):
        items = [
            {
                "ticker": "AAPL",
                "headline": "AAPL old story",
                "publisher": "Reuters",
                "published_at": "2026-05-01T10:00:00+00:00",
            },
            {
                "ticker": "AAPL",
                "headline": "AAPL fresh story",
                "publisher": "Reuters",
                "published_at": "2026-06-12T10:00:00+00:00",
            },
        ]

        filtered = filter_recent_news(items, today=date(2026, 6, 12))

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["headline"], "AAPL fresh story")

    def test_filters_out_missing_published_at(self):
        items = [
            {
                "ticker": "AAPL",
                "headline": "AAPL no date",
                "publisher": "Reuters",
                "published_at": None,
            },
            {
                "ticker": "AAPL",
                "headline": "AAPL fresh story",
                "publisher": "Reuters",
                "published_at": "2026-06-12T10:00:00+00:00",
            },
        ]

        filtered = filter_recent_news(items, today=date(2026, 6, 12))

        self.assertEqual(len(filtered), 1)
        self.assertFalse(is_recent_news(items[0], today=date(2026, 6, 12)))

    def test_max_eight_applies_after_recency_filter(self):
        tickers = [f"T{i}" for i in range(10)]
        today = date(2026, 6, 12)

        with patch("src.news.get_company_name") as mock_company_name, patch(
            "src.news.get_news"
        ) as mock_get_news:
            mock_company_name.side_effect = lambda ticker: f"Company {ticker}"

            def side_effect(ticker, use_cache=True, today=None):
                return [
                    {
                        "ticker": ticker,
                        "headline": f"{ticker} fresh headline",
                        "publisher": "Reuters",
                        "published_at": "2026-06-12T10:00:00+00:00",
                        "url": f"https://example.com/{ticker}-fresh",
                        "source": "yfinance",
                        "last_updated": "2026-06-12T08:00:00+00:00",
                    },
                    {
                        "ticker": ticker,
                        "headline": f"{ticker} stale headline",
                        "publisher": "Reuters",
                        "published_at": "2026-05-01T10:00:00+00:00",
                        "url": f"https://example.com/{ticker}-old",
                        "source": "yfinance",
                        "last_updated": "2026-06-12T08:00:00+00:00",
                    },
                ]

            mock_get_news.side_effect = side_effect

            summary = build_news_summary(
                portfolio=[{"ticker": ticker} for ticker in tickers],
                watchlist=[],
                use_cache=False,
                today=today,
            )

        self.assertEqual(len(summary["items"]), DEFAULT_MAX_ITEMS)
        self.assertEqual(len(summary["portfolio_news"]), 10)
        self.assertTrue(
            all(
                is_recent_news(item, today=today, max_age_days=MAX_NEWS_AGE_DAYS)
                for item in summary["items"]
            )
        )
        self.assertTrue(
            all("fresh headline" in item["headline"] for item in summary["items"])
        )


if __name__ == "__main__":
    unittest.main()
