import unittest
from datetime import date

import pandas as pd

from src.alerts import (
    ALERT_NEAR_TRAILING_STOP,
    ALERT_PENDING_ORDER,
)
from src.daily_briefing import (
    build_daily_briefing,
    format_daily_briefing,
    resolve_daily_briefing,
)
from src.sentiment import SENTIMENT_NEGATIVE
from src.watchlist_advisor import (
    ACTION_AVVENT_EARNINGS,
    ACTION_VURDER_KJOP,
)


def _portfolio_row(**overrides):
    base = {
        "ticker": "AAPL",
        "market_value": 2905.5,
        "unrealized_gain_pct": 62.32,
        "current_price": 290.55,
        "cost_value": 1790.0,
        "portefølje_råd": "HOLD",
        "anbefaling": "HOLD / OBSERVER",
        "trailing_stop_loss": 250.0,
        "trailing_stop_triggered": False,
    }
    base.update(overrides)
    return base


def _alert(alert_type, ticker, *, title="", message="", action=""):
    return {
        "alert_type": alert_type,
        "ticker": ticker,
        "title": title,
        "message": message,
        "action": action,
    }


class BuildDailyBriefingTests(unittest.TestCase):
    def test_empty_briefing_handled(self):
        briefing = build_daily_briefing({})

        self.assertEqual(briefing["critical_items"], [])
        self.assertEqual(briefing["important_items"], [])
        self.assertEqual(briefing["watchlist_items"], [])
        self.assertEqual(briefing["candidate_items"], [])
        self.assertEqual(briefing["summary"], [])
        self.assertEqual(
            briefing["headline"],
            "Rolig dag – ingen kritiske hendelser.",
        )
        self.assertIn(
            "Rolig dag – ingen kritiske hendelser.",
            format_daily_briefing(briefing),
        )

    def test_earnings_within_three_days_goes_to_critical(self):
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

        self.assertEqual(len(briefing["critical_items"]), 2)
        self.assertEqual(briefing["critical_items"][0]["days_until"], 0)
        self.assertIn("i dag", briefing["critical_items"][0]["text"])
        self.assertEqual(briefing["critical_items"][1]["days_until"], 3)
        self.assertIn("om 3 dager", briefing["critical_items"][1]["text"])
        self.assertEqual(briefing["headline"], "Earnings-fokus i dag.")

    def test_vurder_kjop_goes_to_watchlist(self):
        context = {
            "watchlist_advisor_output": {
                "items": [
                    {
                        "ticker": "NVDA",
                        "watchlist_action": ACTION_VURDER_KJOP,
                        "headline": "Sterk kandidat for videre vurdering",
                        "priority": 1,
                    },
                    {
                        "ticker": "MSFT",
                        "watchlist_action": ACTION_AVVENT_EARNINGS,
                        "headline": "Rapport nær – avvent inngang",
                        "priority": 1,
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["watchlist_items"]), 2)
        vurder_kjop_items = [
            item
            for item in briefing["watchlist_items"]
            if item.get("watchlist_action") == ACTION_VURDER_KJOP
        ]
        self.assertEqual(len(vurder_kjop_items), 1)
        self.assertEqual(vurder_kjop_items[0]["ticker"], "NVDA")
        self.assertNotIn(
            ACTION_VURDER_KJOP,
            {
                item.get("watchlist_action")
                for item in briefing["important_items"]
            },
        )

    def test_candidate_items_from_opportunity_advisor(self):
        context = {
            "opportunity_advisor": {
                "items": [
                    {
                        "ticker": "AVGO",
                        "headline": "Sterk screener-kandidat",
                        "priority": 1,
                    },
                    {
                        "ticker": "JPM",
                        "headline": "Momentum og sterk score",
                        "priority": 2,
                    },
                    {
                        "ticker": "MSFT",
                        "headline": "Solid kandidat",
                        "priority": 2,
                    },
                    {
                        "ticker": "AAPL",
                        "headline": "Interessant oppside",
                        "priority": 3,
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["candidate_items"]), 3)
        self.assertEqual(
            briefing["candidate_items"][0]["text"],
            "AVGO: Sterk screener-kandidat",
        )
        self.assertEqual(
            briefing["candidate_items"][1]["text"],
            "JPM: Momentum og sterk score",
        )

    def test_headline_quiet_day(self):
        briefing = build_daily_briefing({})
        self.assertEqual(
            briefing["headline"],
            "Rolig dag – ingen kritiske hendelser.",
        )

    def test_headline_earnings_focus(self):
        context = {
            "earnings_summary": {
                "items": [
                    {"ticker": "DNB.OL", "days_until": 1, "in_portfolio": True},
                ],
            },
        }

        briefing = build_daily_briefing(context)
        self.assertEqual(briefing["headline"], "Earnings-fokus i dag.")

    def test_headline_candidates_with_reporting_risk(self):
        context = {
            "earnings_summary": {
                "items": [
                    {"ticker": "DNB.OL", "days_until": 2, "in_portfolio": True},
                ],
            },
            "opportunity_advisor": {
                "items": [
                    {"ticker": "AVGO", "headline": "Sterk kandidat", "priority": 1},
                    {"ticker": "JPM", "headline": "Sterk kandidat", "priority": 1},
                ],
            },
        }

        briefing = build_daily_briefing(context)
        self.assertEqual(
            briefing["headline"],
            "Flere sterke kandidater, men rapporteringsrisiko nærmer seg.",
        )

    def test_critical_reduser_and_trailing_stop(self):
        context = {
            "portfolio_report": pd.DataFrame(
                [
                    _portfolio_row(
                        ticker="NVDA",
                        portefølje_råd="REDUSER / SELG",
                    ),
                ]
            ),
            "alerts": [
                _alert(
                    ALERT_NEAR_TRAILING_STOP,
                    "EQNR.OL",
                    title="Nær trailing stop",
                    message="Kursen er 2.1 % over stop-nivå.",
                ),
            ],
        }

        briefing = build_daily_briefing(context)
        categories = {item["category"] for item in briefing["critical_items"]}

        self.assertIn("reduser", categories)
        self.assertIn("trailing_stop", categories)

    def test_critical_sell_order(self):
        context = {
            "alerts": [
                _alert(
                    ALERT_PENDING_ORDER,
                    "NVDA",
                    message="Salgsordre venter: 10 aksjer @ 120. Utfør, juster limit, eller kanseller.",
                ),
            ],
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["critical_items"]), 1)
        self.assertEqual(briefing["critical_items"][0]["category"], "sell")

    def test_negative_analyst_change_goes_to_critical(self):
        context = {
            "analyst_summary": {
                "material_changes": [
                    {
                        "ticker": "NVDA",
                        "change_type": "target_mean",
                        "Endring": "Kursmål ned (-6.0%)",
                    },
                    {
                        "ticker": "AAPL",
                        "change_type": "target_mean",
                        "Endring": "Kursmål opp (+5.5%)",
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["critical_items"]), 1)
        self.assertIn("Kursmål ned", briefing["critical_items"][0]["text"])
        self.assertEqual(len(briefing["important_items"]), 1)
        self.assertIn("Kursmål opp", briefing["important_items"][0]["text"])

    def test_avvent_earnings_goes_to_important(self):
        context = {
            "watchlist_advisor_output": {
                "items": [
                    {
                        "ticker": "MSFT",
                        "watchlist_action": ACTION_AVVENT_EARNINGS,
                        "headline": "Rapport nær – avvent inngang",
                        "priority": 1,
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["important_items"]), 1)
        self.assertEqual(briefing["important_items"][0]["rule"], "avvent_earnings")

    def test_strong_negative_sentiment_goes_to_important(self):
        context = {
            "sentiment_summary": {
                "items": [
                    {
                        "ticker": "TSLA",
                        "sentiment": SENTIMENT_NEGATIVE,
                        "score": -0.75,
                        "in_portfolio": True,
                    },
                    {
                        "ticker": "MSFT",
                        "sentiment": SENTIMENT_NEGATIVE,
                        "score": -0.30,
                        "in_portfolio": False,
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["important_items"]), 1)
        self.assertEqual(briefing["important_items"][0]["ticker"], "TSLA")


class FormatDailyBriefingTests(unittest.TestCase):
    def test_format_daily_briefing_renders_sections(self):
        briefing = {
            "headline": "Handlingspunkter krever oppmerksomhet i dag.",
            "critical_items": [{"text": "NVDA: Reduser / selg"}],
            "important_items": [{"text": "MSFT: Rapport nær – avvent inngang"}],
            "watchlist_items": [{"text": "NVDA: sterk kandidat for videre vurdering"}],
            "candidate_items": [
                {"text": "AVGO: Sterk screener-kandidat"},
                {"text": "JPM: Momentum og sterk score"},
            ],
            "summary": [
                {"text": "Markedet tilbyr flere interessante kandidater"},
            ],
        }

        formatted = format_daily_briefing(briefing)

        self.assertIn("Dagens briefing", formatted)
        self.assertIn("Handlingspunkter krever oppmerksomhet i dag.", formatted)
        self.assertIn("Kritisk", formatted)
        self.assertIn("• NVDA: Reduser / selg", formatted)
        self.assertIn("Viktig", formatted)
        self.assertIn("Watchlist", formatted)
        self.assertIn("Kandidater", formatted)
        self.assertIn("• AVGO: Sterk screener-kandidat", formatted)
        self.assertIn("Oppsummering", formatted)


class ResolveDailyBriefingTests(unittest.TestCase):
    def test_uses_existing_daily_briefing_from_context(self):
        existing = {
            "generated_at": "2026-06-12T08:00:00+00:00",
            "headline": "Rolig dag – ingen kritiske hendelser.",
            "critical_items": [],
            "important_items": [],
            "watchlist_items": [],
            "candidate_items": [],
            "summary": [],
        }
        context = {"daily_briefing": existing}

        briefing = resolve_daily_briefing(context)

        self.assertIs(briefing, existing)

    def test_builds_briefing_when_context_missing_field(self):
        context = {
            "portfolio_report": pd.DataFrame(
                [
                    _portfolio_row(
                        ticker="NVDA",
                        portefølje_råd="REDUSER / SELG",
                    ),
                ]
            ),
        }

        briefing = resolve_daily_briefing(context)

        self.assertNotIn("daily_briefing", context)
        self.assertEqual(len(briefing["critical_items"]), 1)
        self.assertIn("Reduser / selg", briefing["critical_items"][0]["text"])
