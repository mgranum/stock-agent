import unittest
from datetime import date

import pandas as pd

from src.advisor import CONFLICT_GAIN_VS_STOP, CONFLICT_SELL_VS_ANALYST
from src.daily_briefing import (
    build_daily_briefing,
    format_daily_briefing,
    resolve_daily_briefing,
)
from src.sentiment import SENTIMENT_NEGATIVE, SENTIMENT_POSITIVE


def _advisor_item(ticker, conflict_id, headline, priority=1):
    return {
        "ticker": ticker,
        "conflict_id": conflict_id,
        "headline": headline,
        "takeaway": "Test takeaway",
        "priority": priority,
    }


class BuildDailyBriefingTests(unittest.TestCase):
    def test_empty_briefing_handled(self):
        briefing = build_daily_briefing({})

        self.assertEqual(briefing["portfolio_items"], [])
        self.assertEqual(briefing["earnings_items"], [])
        self.assertEqual(briefing["analyst_items"], [])
        self.assertEqual(briefing["candidate_items"], [])
        self.assertEqual(briefing["news_items"], [])
        self.assertEqual(briefing["summary_items"], [])
        self.assertEqual(format_daily_briefing(briefing), "Dagens briefing")

    def test_advisor_items_sorted_by_priority(self):
        context = {
            "advisor_output": {
                "items": [
                    _advisor_item(
                        "EQNR.OL",
                        CONFLICT_SELL_VS_ANALYST,
                        "Analytikere positive, risiko peker mot reduksjon",
                        priority=1,
                    ),
                    _advisor_item(
                        "NVDA",
                        CONFLICT_GAIN_VS_STOP,
                        "Gevinst høy, stop nær",
                        priority=1,
                    ),
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["portfolio_items"]), 2)
        self.assertEqual(briefing["portfolio_items"][0]["ticker"], "EQNR")
        self.assertIn("analytikere positive", briefing["portfolio_items"][0]["text"])
        self.assertEqual(briefing["portfolio_items"][1]["ticker"], "NVDA")
        self.assertIn("gevinst høy", briefing["portfolio_items"][1]["text"])

    def test_earnings_items_within_seven_days(self):
        context = {
            "earnings_summary": {
                "items": [
                    {
                        "ticker": "DNB.OL",
                        "days_until": 3,
                        "in_portfolio": True,
                    },
                    {
                        "ticker": "AAPL",
                        "days_until": 0,
                        "in_portfolio": False,
                    },
                    {
                        "ticker": "MSFT",
                        "days_until": 10,
                        "in_portfolio": False,
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["earnings_items"]), 2)
        self.assertEqual(briefing["earnings_items"][0]["days_until"], 0)
        self.assertIn("i dag", briefing["earnings_items"][0]["text"])
        self.assertEqual(briefing["earnings_items"][1]["days_until"], 3)
        self.assertIn("om 3 dager", briefing["earnings_items"][1]["text"])

    def test_analyst_material_changes_included(self):
        context = {
            "analyst_summary": {
                "material_changes": [
                    {
                        "ticker": "NVDA",
                        "change_type": "target_mean",
                        "Endring": "Kursmål opp (+5.5%)",
                    },
                    {
                        "ticker": "AAPL",
                        "change_type": "recommendation_key",
                        "Endring": "Konsensus endret til Hold",
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["analyst_items"]), 2)
        self.assertEqual(
            briefing["analyst_items"][0]["text"],
            "NVDA: Kursmål opp (+5.5%)",
        )

    def test_candidate_items_from_screener_and_opportunity_advisor(self):
        context = {
            "screener_results": pd.DataFrame(
                [
                    {"ticker": "AVGO", "score": 96},
                    {"ticker": "JPM", "score": 92},
                    {"ticker": "MSFT", "score": 88},
                    {"ticker": "AAPL", "score": 85},
                ]
            ),
            "opportunity_advisor": {
                "items": [
                    {
                        "ticker": "AVGO",
                        "headline": "Sterk screener-kandidat",
                        "priority": 1,
                    }
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["candidate_items"]), 3)
        self.assertEqual(
            briefing["candidate_items"][0]["text"],
            "AVGO: Sterk screener-kandidat",
        )
        self.assertEqual(briefing["candidate_items"][1]["text"], "JPM score 92")

    def test_news_items_only_clear_sentiment(self):
        context = {
            "sentiment_summary": {
                "items": [
                    {
                        "ticker": "NVDA",
                        "sentiment": SENTIMENT_POSITIVE,
                        "score": 0.8,
                        "in_portfolio": True,
                    },
                    {
                        "ticker": "TSLA",
                        "sentiment": SENTIMENT_NEGATIVE,
                        "score": -0.7,
                        "in_portfolio": False,
                    },
                    {
                        "ticker": "MSFT",
                        "sentiment": "NEUTRAL",
                        "score": 0.0,
                        "in_portfolio": False,
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["news_items"]), 2)
        self.assertEqual(briefing["news_items"][0]["ticker"], "NVDA")
        self.assertIn("Positiv", briefing["news_items"][0]["text"])
        self.assertEqual(briefing["news_items"][1]["ticker"], "TSLA")
        self.assertIn("Negativ", briefing["news_items"][1]["text"])

    def test_summary_rules(self):
        context = {
            "advisor_output": {
                "items": [
                    _advisor_item(
                        "NVDA",
                        CONFLICT_GAIN_VS_STOP,
                        "Gevinst høy, stop nær",
                    )
                ],
            },
            "earnings_summary": {
                "items": [
                    {"ticker": "DNB.OL", "days_until": 0, "in_portfolio": True},
                ],
            },
            "screener_results": pd.DataFrame(
                [
                    {"ticker": "AVGO", "score": 96},
                    {"ticker": "JPM", "score": 92},
                ]
            ),
        }

        briefing = build_daily_briefing(context, today=date(2026, 6, 14))
        rules = {item["rule"] for item in briefing["summary_items"]}

        self.assertEqual(
            rules,
            {"earnings_today", "advisor_conflicts", "strong_candidates"},
        )


class FormatDailyBriefingTests(unittest.TestCase):
    def test_format_daily_briefing_renders_sections(self):
        briefing = {
            "portfolio_items": [{"text": "NVDA: gevinst høy, stop nær"}],
            "earnings_items": [{"text": "DNB rapporterer om 3 dager"}],
            "candidate_items": [
                {"text": "AVGO score 96"},
                {"text": "JPM score 92"},
            ],
            "summary_items": [
                {"text": "Markedet tilbyr flere interessante kandidater"},
            ],
        }

        formatted = format_daily_briefing(briefing)

        self.assertIn("Dagens briefing", formatted)
        self.assertIn("Portefølje", formatted)
        self.assertIn("• NVDA: gevinst høy, stop nær", formatted)
        self.assertIn("Earnings", formatted)
        self.assertIn("• DNB rapporterer om 3 dager", formatted)
        self.assertIn("Kandidater", formatted)
        self.assertIn("• AVGO score 96", formatted)
        self.assertIn("Oppsummering", formatted)


class ResolveDailyBriefingTests(unittest.TestCase):
    def test_uses_existing_daily_briefing_from_context(self):
        existing = {
            "generated_at": "2026-06-12T08:00:00+00:00",
            "portfolio_items": [{"text": "NVDA: cached briefing"}],
            "earnings_items": [],
            "analyst_items": [],
            "candidate_items": [],
            "news_items": [],
            "summary_items": [],
        }
        context = {"daily_briefing": existing}

        briefing = resolve_daily_briefing(context)

        self.assertIs(briefing, existing)

    def test_builds_briefing_when_context_missing_field(self):
        context = {
            "advisor_output": {
                "items": [
                    _advisor_item(
                        "NVDA",
                        CONFLICT_GAIN_VS_STOP,
                        "Gevinst høy, stop nær",
                    )
                ],
            },
        }

        briefing = resolve_daily_briefing(context)

        self.assertNotIn("daily_briefing", context)
        self.assertEqual(len(briefing["portfolio_items"]), 1)
        self.assertIn("gevinst høy", briefing["portfolio_items"][0]["text"])
