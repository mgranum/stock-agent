import unittest
from datetime import date

import pandas as pd

from src.alerts import (
    ALERT_NEAR_TRAILING_STOP,
    ALERT_PENDING_ORDER,
    ALERT_TRAILING_STOP_TRIGGERED,
)
from src.daily_briefing import (
    TOTAL_CONCRETE_ITEM_LIMIT,
    build_daily_briefing,
    format_daily_briefing,
    resolve_daily_briefing,
)
from src.sentiment import SENTIMENT_NEGATIVE
from src.watchlist_advisor import (
    ACTION_AVVENT_EARNINGS,
    ACTION_FJERN_FRA_WATCHLIST,
    ACTION_FOLG_MED,
    ACTION_VENT,
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


def _concrete_item_count(briefing):
    return sum(
        len(briefing.get(section) or [])
        for section in (
            "critical_items",
            "important_items",
            "watchlist_items",
            "candidate_items",
        )
    )


def _all_concrete_tickers(briefing):
    tickers = []
    for section in (
        "critical_items",
        "important_items",
        "watchlist_items",
        "candidate_items",
    ):
        for item in briefing.get(section) or []:
            tickers.append(item.get("ticker"))
    return tickers


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

    def test_earnings_owned_today_or_tomorrow_goes_to_critical(self):
        context = {
            "portfolio_report": pd.DataFrame(
                [
                    _portfolio_row(ticker="DNB.OL"),
                    _portfolio_row(ticker="EQNR.OL"),
                ]
            ),
            "earnings_summary": {
                "items": [
                    {
                        "ticker": "DNB.OL",
                        "days_until": 1,
                        "in_portfolio": True,
                    },
                    {
                        "ticker": "EQNR.OL",
                        "days_until": 0,
                        "in_portfolio": True,
                    },
                    {
                        "ticker": "AAPL",
                        "days_until": 0,
                        "in_portfolio": False,
                    },
                    {
                        "ticker": "MSFT",
                        "days_until": 3,
                        "in_portfolio": True,
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["critical_items"]), 2)
        self.assertEqual(briefing["critical_items"][0]["days_until"], 0)
        self.assertIn("i dag", briefing["critical_items"][0]["text"])
        self.assertEqual(briefing["critical_items"][1]["days_until"], 1)
        self.assertIn("i morgen", briefing["critical_items"][1]["text"])
        self.assertEqual(briefing["headline"], "Earnings-fokus i dag.")

    def test_vurder_kjop_goes_to_watchlist_on_quiet_day(self):
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
        watchlist_tickers = {item["ticker"] for item in briefing["watchlist_items"]}
        self.assertEqual(watchlist_tickers, {"NVDA", "MSFT"})
        self.assertEqual(briefing["important_items"], [])

    def test_candidate_items_from_opportunity_advisor_on_quiet_day(self):
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
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["candidate_items"]), 2)
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
            "portfolio_report": pd.DataFrame([_portfolio_row(ticker="DNB.OL")]),
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
            "portfolio_report": pd.DataFrame([_portfolio_row(ticker="DNB.OL")]),
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

    def test_reduser_critical_and_near_trailing_stop_important(self):
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
        critical_categories = {item["category"] for item in briefing["critical_items"]}
        important_rules = {item["rule"] for item in briefing["important_items"]}

        self.assertIn("reduser", critical_categories)
        self.assertNotIn("trailing_stop", critical_categories)
        self.assertIn("trailing_stop_near", important_rules)

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

    def test_negative_analyst_change_owned_goes_to_critical(self):
        context = {
            "portfolio_report": pd.DataFrame([_portfolio_row(ticker="NVDA")]),
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

    def test_max_five_concrete_items_total(self):
        context = {
            "portfolio_report": pd.DataFrame(
                [
                    _portfolio_row(ticker="NVDA", portefølje_råd="REDUSER / SELG"),
                    _portfolio_row(ticker="GOOGL", portefølje_råd="REDUSER / SELG"),
                    _portfolio_row(ticker="EQNR.OL", portefølje_råd="REDUSER / SELG"),
                    _portfolio_row(ticker="KOG.OL", portefølje_råd="REDUSER / SELG"),
                    _portfolio_row(ticker="KMAR.OL", portefølje_råd="REDUSER / SELG"),
                ]
            ),
            "alerts": [
                _alert(
                    ALERT_NEAR_TRAILING_STOP,
                    "AAPL",
                    title="Nær trailing stop",
                    message="Kursen er 1.9 % over stop.",
                ),
            ],
        }

        briefing = build_daily_briefing(context)

        self.assertLessEqual(len(briefing["critical_items"]), 3)
        self.assertLessEqual(_concrete_item_count(briefing), TOTAL_CONCRETE_ITEM_LIMIT)

    def test_ticker_not_in_multiple_sections(self):
        context = {
            "portfolio_report": pd.DataFrame(
                [
                    _portfolio_row(ticker="NVDA", portefølje_råd="REDUSER / SELG"),
                ]
            ),
            "alerts": [
                _alert(
                    ALERT_PENDING_ORDER,
                    "NVDA",
                    message="Salgsordre venter: 10 aksjer @ 120. Utfør, juster limit, eller kanseller.",
                ),
            ],
            "watchlist_advisor_output": {
                "items": [
                    {
                        "ticker": "NVDA",
                        "watchlist_action": ACTION_VURDER_KJOP,
                        "headline": "Sterk kandidat",
                        "priority": 1,
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)
        tickers = _all_concrete_tickers(briefing)

        self.assertEqual(tickers.count("NVDA"), 1)
        self.assertEqual(briefing["critical_items"][0]["rule"], "sell_order")

    def test_watchlist_filters_fjern_vent_folg_med(self):
        context = {
            "watchlist_advisor_output": {
                "items": [
                    {
                        "ticker": "AKRBP.OL",
                        "watchlist_action": ACTION_FJERN_FRA_WATCHLIST,
                        "headline": "Fjern fra watchlist",
                        "priority": 1,
                    },
                    {
                        "ticker": "AMZN",
                        "watchlist_action": ACTION_VENT,
                        "headline": "Vent",
                        "priority": 2,
                    },
                    {
                        "ticker": "FRO.OL",
                        "watchlist_action": ACTION_FOLG_MED,
                        "headline": "Følg med",
                        "priority": 2,
                    },
                    {
                        "ticker": "BRK-B",
                        "watchlist_action": ACTION_VURDER_KJOP,
                        "headline": "Vurder kjøp",
                        "priority": 3,
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["watchlist_items"]), 1)
        self.assertEqual(briefing["watchlist_items"][0]["ticker"], "BRK-B")

    def test_candidates_hidden_when_critical_exists(self):
        context = {
            "portfolio_report": pd.DataFrame(
                [_portfolio_row(ticker="NVDA", portefølje_råd="REDUSER / SELG")]
            ),
            "opportunity_advisor": {
                "items": [
                    {"ticker": "AVGO", "headline": "Sterk kandidat", "priority": 1},
                ],
            },
            "watchlist_advisor_output": {
                "items": [
                    {
                        "ticker": "BRK-B",
                        "watchlist_action": ACTION_VURDER_KJOP,
                        "headline": "Vurder kjøp",
                        "priority": 1,
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(briefing["candidate_items"], [])
        self.assertEqual(briefing["watchlist_items"], [])

    def test_avvent_watchlist_shown_when_critical_and_within_three_days(self):
        context = {
            "portfolio_report": pd.DataFrame(
                [_portfolio_row(ticker="NVDA", portefølje_råd="REDUSER / SELG")]
            ),
            "earnings_summary": {
                "items": [
                    {"ticker": "MSFT", "days_until": 2, "in_portfolio": False},
                ],
            },
            "watchlist_advisor_output": {
                "items": [
                    {
                        "ticker": "MSFT",
                        "watchlist_action": ACTION_AVVENT_EARNINGS,
                        "headline": "Avvent kvartalsrapport",
                        "priority": 1,
                    },
                    {
                        "ticker": "BRK-B",
                        "watchlist_action": ACTION_VURDER_KJOP,
                        "headline": "Vurder kjøp",
                        "priority": 2,
                    },
                ],
            },
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["watchlist_items"]), 1)
        self.assertEqual(briefing["watchlist_items"][0]["ticker"], "MSFT")
        self.assertEqual(briefing["watchlist_items"][0]["rule"], "avvent_earnings")

    def test_trailing_stop_triggered_goes_to_critical(self):
        context = {
            "alerts": [
                _alert(
                    ALERT_TRAILING_STOP_TRIGGERED,
                    "AAPL",
                    title="Trailing stop trigget",
                    message="Stop-nivå brutt.",
                ),
            ],
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["critical_items"]), 1)
        self.assertEqual(
            briefing["critical_items"][0]["rule"],
            "trailing_stop_triggered",
        )

    def test_summary_does_not_repeat_headline(self):
        context = {
            "portfolio_report": pd.DataFrame(
                [_portfolio_row(ticker="NVDA", portefølje_råd="REDUSER / SELG")]
            ),
        }

        briefing = build_daily_briefing(context)

        self.assertEqual(
            briefing["headline"],
            "Handlingspunkter krever oppmerksomhet i dag.",
        )
        summary_text = " ".join(item["text"] for item in briefing["summary"])
        self.assertNotIn("Handlingspunkter", summary_text)
        self.assertLessEqual(len(briefing["summary"]), 2)


class FormatDailyBriefingTests(unittest.TestCase):
    def test_format_daily_briefing_renders_sections(self):
        briefing = {
            "headline": "Handlingspunkter krever oppmerksomhet i dag.",
            "critical_items": [{"text": "NVDA: Reduser / selg"}],
            "important_items": [{"text": "MSFT: Rapport nær – avvent inngang"}],
            "watchlist_items": [{"text": "NVDA: sterk kandidat for videre vurdering"}],
            "candidate_items": [
                {"text": "AVGO: Sterk screener-kandidat"},
            ],
            "summary": [
                {"text": "Støttende signaler er verdt et raskt blikk"},
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

    def test_format_daily_briefing_hides_empty_sections(self):
        briefing = {
            "headline": "Rolig dag – ingen kritiske hendelser.",
            "critical_items": [],
            "important_items": [],
            "watchlist_items": [],
            "candidate_items": [],
            "summary": [],
        }

        formatted = format_daily_briefing(briefing)

        self.assertNotIn("Kritisk", formatted)
        self.assertNotIn("Viktig", formatted)
        self.assertNotIn("Watchlist", formatted)
        self.assertNotIn("Kandidater", formatted)
        self.assertNotIn("Oppsummering", formatted)


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
