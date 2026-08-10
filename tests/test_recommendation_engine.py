import unittest

import pandas as pd

from src.agent import ask_agent
from src.alerts import (
    ACTION_REVIEW_SELL,
    ALERT_PORTFOLIO_SELL,
    build_alerts,
)
from src.advisor import CONFLICT_SELL_VS_ANALYST
from src.recommendation_engine import (
    CATEGORY_BUYING,
    CATEGORY_PORTFOLIO,
    CATEGORY_RISK,
    MAX_RECOMMENDATIONS,
    build_recommendations,
    format_recommendations,
    is_recommendation_question,
    limit_recommendations,
)
from src.recommendation_contract import RECOMMENDATION_CONTRACT_VERSION
from src.watchlist_advisor import ACTION_VURDER_KJOP


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
        "begrunnelse": "Weak trend.",
    }
    base.update(overrides)
    return base


def _daily_action(**overrides):
    base = {
        "priority": 2,
        "ticker": "AAPL",
        "action_label": "Vurder salg",
        "message": "Weak trend while score remains low.",
        "source": "PORTFOLIO",
        "dedupe_key": "PORTFOLIO_ACTION:AAPL:REDUSER / SELG",
    }
    base.update(overrides)
    return base


def _sample_context(**overrides):
    context = {
        "watchlist": ["AAPL", "SUBC"],
        "watchlist_report": pd.DataFrame(),
        "portfolio_report": None,
        "alerts": [],
        "daily_flow": {"daily_actions": []},
        "watchlist_advisor_output": {"items": []},
        "opportunity_advisor": {"items": []},
        "advisor_output": {"items": []},
        "earnings_summary": {"items": []},
        "analyst_summary": {"items": [], "material_changes": []},
        "sentiment_summary": {"items": []},
        "dashboard": {},
    }
    context.update(overrides)
    return context


class RecommendationQuestionTests(unittest.TestCase):
    def test_recommendation_question_matches_expected_phrases(self):
        self.assertTrue(is_recommendation_question("What should I do today?"))
        self.assertTrue(is_recommendation_question("What are today's recommendations?"))
        self.assertTrue(is_recommendation_question("Hva bør jeg gjøre i dag?"))
        self.assertTrue(is_recommendation_question("Hva er viktig i dag?"))
        self.assertTrue(is_recommendation_question("dagens råd"))

    def test_candidate_discovery_not_treated_as_recommendation(self):
        self.assertFalse(
            is_recommendation_question("Hvilke aksjer ser sterkest ut i dag?")
        )
        self.assertFalse(
            is_recommendation_question("Vis de beste kandidatene i dag")
        )

    def test_recommendation_question_does_not_match_overview_phrases(self):
        self.assertFalse(is_recommendation_question("Vis morning briefing i dag"))
        self.assertFalse(is_recommendation_question("dagens situasjon"))


class BuildRecommendationsTests(unittest.TestCase):
    def test_no_recommendations(self):
        result = build_recommendations(_sample_context())

        self.assertEqual(result["actions"], [])
        self.assertEqual(
            result["summary"],
            "Ingen viktige handlinger anbefales i dag.",
        )

    def test_one_recommendation(self):
        context = _sample_context(
            daily_flow={
                "daily_actions": [
                    _daily_action(
                        ticker="AKRBP",
                        action_label="Vurder reduksjon",
                        message="Weakening trend.",
                    ),
                ],
            },
        )

        result = build_recommendations(context)

        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["ticker"], "AKRBP")
        self.assertEqual(result["actions"][0]["category"], CATEGORY_PORTFOLIO)
        self.assertEqual(result["contract_version"], RECOMMENDATION_CONTRACT_VERSION)
        decision = result["actions"][0]["decision"]
        self.assertEqual(decision["action_code"], "reduce_or_exit")
        self.assertEqual(decision["scope"], "portfolio")
        self.assertEqual(decision["time_horizon"], "days_to_weeks")
        self.assertEqual(decision["reasons"], ["Weakening trend."])

    def test_contract_preserves_canonical_ticker_while_legacy_label_is_unchanged(self):
        result = build_recommendations(
            _sample_context(
                opportunity_advisor={
                    "items": [
                        {
                            "ticker": "KMAR.OL",
                            "headline": "Sterk kandidat",
                            "priority": 1,
                        }
                    ]
                }
            )
        )

        action = result["actions"][0]
        self.assertEqual(action["ticker"], "KMAR")
        self.assertEqual(action["decision"]["ticker"], "KMAR.OL")

    def test_multiple_recommendations(self):
        context = _sample_context(
            daily_flow={
                "daily_actions": [
                    _daily_action(ticker="AKRBP", priority=2),
                    _daily_action(
                        ticker="SUBC",
                        action_label="Følg med",
                        message="Monitor position.",
                    ),
                ],
            },
            watchlist_advisor_output={
                "items": [
                    {
                        "ticker": "MSFT",
                        "watchlist_action": ACTION_VURDER_KJOP,
                        "headline": "Strong candidate",
                        "takeaway": "Score and trend support a buy.",
                        "priority": 1,
                    },
                ],
            },
        )

        result = build_recommendations(context)

        self.assertGreaterEqual(len(result["actions"]), 3)
        tickers = {item["ticker"] for item in result["actions"]}
        self.assertIn("AKRBP", tickers)
        self.assertIn("SUBC", tickers)
        self.assertIn("MSFT", tickers)

    def test_priority_ordering(self):
        context = _sample_context(
            daily_flow={
                "daily_actions": [
                    _daily_action(
                        ticker="LOW",
                        priority=3,
                        action_label="Følg med",
                        message="Monitor position.",
                    ),
                    _daily_action(
                        ticker="HIGH",
                        priority=1,
                        action_label="Vurder salg",
                        message="Sell signal.",
                    ),
                ],
            },
        )

        result = build_recommendations(context)

        self.assertEqual(result["actions"][0]["ticker"], "HIGH")
        self.assertEqual(result["actions"][0]["priority"], 1)

    def test_duplicate_removal_for_same_ticker_and_intent(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="NVDA",
                    portefølje_råd="REDUSER / SELG",
                    anbefaling="UNNGÅ / SELG",
                ),
            ]
        )
        alerts = build_alerts(portfolio_report, [])
        context = _sample_context(
            portfolio_report=portfolio_report,
            alerts=alerts,
            daily_flow={
                "daily_actions": [
                    {
                        "priority": 1,
                        "ticker": "NVDA",
                        "action_label": "Vurder salg",
                        "message": "Model recommends reduction.",
                        "dedupe_key": f"{ALERT_PORTFOLIO_SELL}:NVDA",
                    },
                    {
                        "priority": 1,
                        "ticker": "NVDA",
                        "action_label": "Vurder reduksjon",
                        "message": "Portfolio review recommended.",
                        "dedupe_key": "PORTFOLIO_ACTION:NVDA:REDUSER / SELG",
                    },
                ],
            },
            advisor_output={
                "items": [
                    {
                        "ticker": "NVDA",
                        "conflict_id": CONFLICT_SELL_VS_ANALYST,
                        "headline": "Analysts positive, risk points to reduction",
                        "takeaway": "Prioritize risk management over price targets.",
                        "priority": 1,
                    },
                ],
            },
        )

        result = build_recommendations(context)
        nvda_actions = [
            item for item in result["actions"] if item["ticker"] == "NVDA"
        ]

        self.assertEqual(len(nvda_actions), 1)

    def test_maximum_five_items(self):
        actions = [
            _daily_action(
                ticker=f"T{i}",
                priority=1,
                action_label="Vurder salg",
                message=f"Action {i}",
            )
            for i in range(8)
        ]
        result = limit_recommendations(
            build_recommendations(
                _sample_context(daily_flow={"daily_actions": actions}),
            ),
        )

        self.assertLessEqual(len(result["actions"]), MAX_RECOMMENDATIONS)

    def test_portfolio_recommendation(self):
        portfolio_report = pd.DataFrame(
            [_portfolio_row(ticker="NVDA", trailing_stop_loss=250.0)]
        )
        result = build_recommendations(
            _sample_context(
                portfolio_report=portfolio_report,
                daily_flow={
                    "daily_actions": [
                        _daily_action(
                            ticker="NVDA",
                            action_label="Sikre gevinst",
                            message="Profit protection.",
                        ),
                    ],
                },
            ),
        )

        self.assertEqual(result["actions"][0]["category"], CATEGORY_PORTFOLIO)
        self.assertIn("NVDA", result["actions"][0]["action"])
        self.assertEqual(result["actions"][0]["decision"]["stop_level"], 250.0)

    def test_opportunity_recommendation(self):
        result = build_recommendations(
            _sample_context(
                opportunity_advisor={
                    "items": [
                        {
                            "ticker": "SUBC",
                            "headline": "Strong cyclical setup",
                            "takeaway": "Momentum and value align.",
                            "priority": 1,
                            "primary_profile": "cyclical",
                        },
                    ],
                },
            ),
        )

        self.assertEqual(result["actions"][0]["category"], CATEGORY_BUYING)
        self.assertIn("SUBC", result["actions"][0]["action"])

    def test_opportunity_recommendations_follow_rank_before_ticker(self):
        result = build_recommendations(
            _sample_context(
                opportunity_advisor={
                    "items": [
                        {
                            "ticker": "AORT",
                            "headline": "Candidate",
                            "priority": 1,
                            "rank": 4,
                        },
                        {
                            "ticker": "PLTR",
                            "headline": "Candidate",
                            "priority": 1,
                            "rank": 1,
                        },
                        {
                            "ticker": "WTS",
                            "headline": "Candidate",
                            "priority": 1,
                            "rank": 2,
                        },
                    ],
                },
            ),
        )

        opportunity_tickers = {
            item["ticker"]
            for item in result["actions"]
            if item["source"] == "opportunity_advisor"
        }
        self.assertEqual(opportunity_tickers, {"PLTR", "WTS"})

    def test_risk_recommendation(self):
        result = build_recommendations(
            _sample_context(
                daily_flow={
                    "daily_actions": [
                        {
                            "priority": 1,
                            "ticker": "AAPL",
                            "action_label": "Forbered kvartalsrapport",
                            "message": "Reports today.",
                        },
                    ],
                },
            ),
        )

        self.assertEqual(result["actions"][0]["category"], CATEGORY_RISK)
        self.assertIn("AAPL", result["actions"][0]["action"])


class FormatRecommendationsTests(unittest.TestCase):
    def test_formatting_with_actions(self):
        text = format_recommendations(
            {
                "actions": [
                    {
                        "action": "Gjennomgå AKRBP",
                        "reason": "Svakere trend mens analytikerkonsensus fortsatt er positivt.",
                        "confidence": "høy",
                    },
                ],
            },
        )

        self.assertIn("Dagens anbefalinger", text)
        self.assertIn("Gjennomgå AKRBP", text)
        self.assertIn("Begrunnelse", text)
        self.assertIn("Konfidans", text)
        self.assertIn("Høy", text)

    def test_formatting_without_actions(self):
        text = format_recommendations(build_recommendations(_sample_context()))

        self.assertIn("Dagens anbefalinger", text)
        self.assertIn("Ingen viktige handlinger anbefales i dag.", text)


class AgentRoutingTests(unittest.TestCase):
    def test_agent_routes_recommendation_question(self):
        answer = ask_agent(
            "What should I do today?",
            _sample_context(),
        )

        self.assertIn("Dagens anbefalinger", answer)
        self.assertIn("Ingen viktige handlinger anbefales i dag.", answer)

    def test_agent_does_not_route_comparison_to_recommendations(self):
        context = _sample_context(
            watchlist_report=pd.DataFrame(
                [
                    {
                        "ticker": "AAPL",
                        "score": 80,
                        "anbefaling": "KJØP / ØK",
                        "trend_regime": "STERK OPPTREND",
                        "relative_strength_20d": 5.0,
                        "fundamental_score": 70,
                        "fundamental_history_score": 65,
                    },
                    {
                        "ticker": "MSFT",
                        "score": 75,
                        "anbefaling": "KJØP / ØK",
                        "trend_regime": "OPPTREND",
                        "relative_strength_20d": 3.0,
                        "fundamental_score": 68,
                        "fundamental_history_score": 60,
                    },
                ]
            ),
        )

        answer = ask_agent("AAPL vs MSFT", context)

        self.assertNotIn("Dagens anbefalinger", answer)
        self.assertIn("Sammenligning", answer)
