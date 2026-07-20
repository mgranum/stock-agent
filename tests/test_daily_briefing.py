import unittest
from datetime import date

import pandas as pd

from src.alerts import (
    ALERT_NEAR_TRAILING_STOP,
    ALERT_PENDING_ORDER,
    ALERT_TRAILING_STOP_TRIGGERED,
)
from src.daily_briefing import (
    CHANGE_ITEM_LIMIT,
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


def _snapshot_change_row(**overrides):
    base = {
        "ticker": "AAPL",
        "previous_score": 50,
        "current_score": 65,
        "score_change": 15,
        "previous_recommendation": "HOLD / OBSERVER",
        "current_recommendation": "KJØP / ØK",
    }
    base.update(overrides)
    return base


def _changes_context(
    recommendation_rows=None,
    score_rows=None,
    *,
    new_buy_rows=None,
    include_changes=True,
):
    context = {}
    if include_changes:
        context["dashboard"] = {
            "changes_since_last_snapshot": {
                "recommendation_changed": pd.DataFrame(
                    recommendation_rows or [],
                ),
                "large_score_changes": pd.DataFrame(score_rows or []),
            },
        }
    daily_flow = {}
    if new_buy_rows is not None:
        daily_flow["key_opportunities"] = {
            "new_buy_candidates": pd.DataFrame(new_buy_rows),
        }
    if daily_flow:
        context["daily_flow"] = daily_flow
    return context


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
        self.assertEqual(briefing["change_items"], [])
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


class BuildDailyBriefingChangeTests(unittest.TestCase):
    def test_change_items_shown_from_snapshot_diff(self):
        context = _changes_context(
            recommendation_rows=[
                _snapshot_change_row(
                    ticker="BRK-B",
                    previous_recommendation="HOLD / OBSERVER",
                    current_recommendation="KJØP / ØK",
                ),
            ],
            score_rows=[
                _snapshot_change_row(
                    ticker="DNB.OL",
                    previous_score=71,
                    current_score=83,
                    score_change=12,
                    previous_recommendation="HOLD / OBSERVER",
                    current_recommendation="HOLD / OBSERVER",
                ),
            ],
            new_buy_rows=[
                {
                    "ticker": "AVGO",
                    "anbefaling": "KJØP / ØK",
                    "score": 78,
                },
            ],
        )

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["change_items"]), 3)
        self.assertEqual(
            briefing["change_items"][0]["text"],
            "BRK-B oppgradert til KJØP / ØK",
        )
        self.assertEqual(
            briefing["change_items"][1]["text"],
            "DNB score økt fra 71 til 83",
        )
        self.assertEqual(
            briefing["change_items"][2]["text"],
            "AVGO ny kjøpskandidat",
        )
        self.assertIn("Endret siden sist", format_daily_briefing(briefing))

    def test_change_items_limited_to_three(self):
        recommendation_rows = [
            _snapshot_change_row(ticker=f"REC{i}")
            for i in range(4)
        ]
        context = _changes_context(recommendation_rows=recommendation_rows)

        briefing = build_daily_briefing(context)

        self.assertEqual(len(briefing["change_items"]), CHANGE_ITEM_LIMIT)

    def test_change_items_deduped_against_watchlist_and_candidates(self):
        context = _changes_context(
            recommendation_rows=[
                _snapshot_change_row(
                    ticker="BRK-B",
                    previous_recommendation="HOLD / OBSERVER",
                    current_recommendation="KJØP / ØK",
                ),
            ],
        )
        context["watchlist_advisor_output"] = {
            "items": [
                {
                    "ticker": "BRK-B",
                    "watchlist_action": ACTION_VURDER_KJOP,
                    "headline": "Sterk kandidat for videre vurdering",
                    "priority": 1,
                },
                {
                    "ticker": "MSFT",
                    "watchlist_action": ACTION_VURDER_KJOP,
                    "headline": "Vurder kjøp",
                    "priority": 2,
                },
            ],
        }
        context["opportunity_advisor"] = {
            "items": [
                {
                    "ticker": "BRK-B",
                    "headline": "Sterk screener-kandidat",
                    "priority": 1,
                },
                {
                    "ticker": "AVGO",
                    "headline": "Momentum og sterk score",
                    "priority": 2,
                },
            ],
        }

        briefing = build_daily_briefing(context)

        watchlist_tickers = {item["ticker"] for item in briefing["watchlist_items"]}
        candidate_tickers = {item["ticker"] for item in briefing["candidate_items"]}
        change_tickers = {item["ticker"] for item in briefing["change_items"]}

        self.assertIn("BRK-B", change_tickers)
        self.assertNotIn("BRK-B", watchlist_tickers)
        self.assertNotIn("BRK-B", candidate_tickers)

    def test_headline_quiet_day_with_changes(self):
        context = _changes_context(
            score_rows=[
                _snapshot_change_row(
                    ticker="DNB.OL",
                    previous_score=71,
                    current_score=83,
                    score_change=12,
                    previous_recommendation="HOLD / OBSERVER",
                    current_recommendation="HOLD / OBSERVER",
                ),
            ],
        )

        briefing = build_daily_briefing(context)

        self.assertEqual(
            briefing["headline"],
            "Flere nye signaler siden sist oppdatering.",
        )

    def test_no_change_section_when_no_snapshot_changes(self):
        briefing = build_daily_briefing({})

        self.assertEqual(briefing["change_items"], [])
        formatted = format_daily_briefing(briefing)
        self.assertNotIn("Endret siden sist", formatted)

    def test_no_change_section_when_snapshot_empty(self):
        context = _changes_context()

        briefing = build_daily_briefing(context)

        self.assertEqual(briefing["change_items"], [])
        self.assertNotIn(
            "Endret siden sist",
            format_daily_briefing(briefing),
        )

    def test_summary_reflects_changes(self):
        context = _changes_context(
            recommendation_rows=[
                _snapshot_change_row(ticker="BRK-B"),
            ],
        )
        context["sentiment_summary"] = {
            "items": [
                {
                    "ticker": "TSLA",
                    "sentiment": SENTIMENT_NEGATIVE,
                    "score": -0.75,
                    "in_portfolio": True,
                },
            ],
        }

        briefing = build_daily_briefing(context)

        summary_rules = {item["rule"] for item in briefing["summary"]}
        summary_text = " ".join(item["text"] for item in briefing["summary"])

        self.assertIn("snapshot_changes", summary_rules)
        self.assertIn("siden forrige snapshot", summary_text)
        self.assertNotIn("Støttende signaler er verdt et raskt blikk", summary_text)

    def test_v21_caps_still_apply_with_changes(self):
        context = _changes_context(
            recommendation_rows=[
                _snapshot_change_row(ticker="BRK-B"),
            ],
        )
        context["portfolio_report"] = pd.DataFrame(
            [
                _portfolio_row(ticker="NVDA", portefølje_råd="REDUSER / SELG"),
                _portfolio_row(ticker="GOOGL", portefølje_råd="REDUSER / SELG"),
                _portfolio_row(ticker="EQNR.OL", portefølje_råd="REDUSER / SELG"),
                _portfolio_row(ticker="KOG.OL", portefølje_råd="REDUSER / SELG"),
                _portfolio_row(ticker="KMAR.OL", portefølje_råd="REDUSER / SELG"),
            ]
        )
        context["alerts"] = [
            _alert(
                ALERT_NEAR_TRAILING_STOP,
                "AAPL",
                title="Nær trailing stop",
                message="Kursen er 1.9 % over stop.",
            ),
        ]

        briefing = build_daily_briefing(context)

        self.assertLessEqual(len(briefing["critical_items"]), 3)
        self.assertLessEqual(_concrete_item_count(briefing), TOTAL_CONCRETE_ITEM_LIMIT)
        self.assertEqual(len(briefing["change_items"]), 1)


class FormatDailyBriefingTests(unittest.TestCase):
    def test_format_daily_briefing_renders_sections(self):
        briefing = {
            "headline": "Handlingspunkter krever oppmerksomhet i dag.",
            "critical_items": [{"text": "NVDA: Reduser / selg"}],
            "change_items": [{"text": "BRK-B oppgradert til KJØP / ØK"}],
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
        kritisk_pos = formatted.index("Kritisk")
        endret_pos = formatted.index("Endret siden sist")
        viktig_pos = formatted.index("Viktig")
        self.assertLess(kritisk_pos, endret_pos)
        self.assertLess(endret_pos, viktig_pos)
        self.assertIn("Endret siden sist", formatted)
        self.assertIn("• BRK-B oppgradert til KJØP / ØK", formatted)
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
            "change_items": [],
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

    def test_briefing_includes_recommendation_engine_output(self):
        from src.recommendation_engine import build_recommendations

        context = {
            "portfolio_report": pd.DataFrame(
                [_portfolio_row(ticker="NVDA", portefølje_råd="REDUSER / SELG")],
            ),
        }
        recommendations = build_recommendations(context)
        briefing = build_daily_briefing(context, recommendations=recommendations)

        self.assertEqual(briefing["recommendations"], recommendations)
        self.assertEqual(len(briefing["critical_items"]), 1)
