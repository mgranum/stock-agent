import unittest

import pandas as pd

from src.alerts import (
    ALERT_EARNINGS_TODAY,
    ALERT_EARNINGS_WITHIN_14_DAYS,
    build_alerts,
)
from src.daily_flow import (
    DAILY_AGENDA_DISPLAY_LIMIT,
    WHATS_NEW_SUMMARY_LIMIT,
    _large_drawdown_positions,
    _positions_near_trailing_stop,
    build_daily_actions,
    build_daily_agenda_table,
    build_daily_flow,
    build_order_actions,
    build_portfolio_actions,
    build_whats_new_table,
    daily_agenda_from_alerts,
    daily_agenda_items,
    explain_snapshot_change_begrunnelse,
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
    }
    base.update(overrides)
    return base


class DailyFlowPortfolioAlertTests(unittest.TestCase):
    def test_nan_unrealized_gain_pct_does_not_trigger_drawdown_alert(self):
        df = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="NVDA",
                    unrealized_gain_pct=float("nan"),
                    current_price=float("nan"),
                    market_value=float("nan"),
                ),
            ]
        )

        alerts = _large_drawdown_positions(df)

        self.assertTrue(alerts.empty)

    def test_nan_current_price_does_not_trigger_near_trailing_stop_alert(self):
        df = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="NVDA",
                    current_price=float("nan"),
                    market_value=float("nan"),
                    unrealized_gain_pct=float("nan"),
                    trailing_stop_loss=200.0,
                ),
            ]
        )

        alerts = _positions_near_trailing_stop(df)

        self.assertTrue(alerts.empty)


def _watchlist_row(**overrides):
    base = {
        "ticker": "MSFT",
        "anbefaling": "KJØP / ØK",
        "score": 75,
        "relative_strength_20d": 4.0,
        "fundamental_score": 70,
        "fundamental_history_score": 72,
        "trend_regime": "STERK OPPTREND",
        "trend_score": 80,
    }
    base.update(overrides)
    return base


class DailyFlowAgendaTests(unittest.TestCase):
    def test_daily_actions_built_from_alerts(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    portefølje_råd="REDUSER / SELG",
                    anbefaling="UNNGÅ / SELG",
                ),
            ]
        )
        alerts = build_alerts(portfolio_report, [], [])

        daily_flow = build_daily_flow(
            watchlist_report=pd.DataFrame(),
            portfolio_report=portfolio_report,
            dashboard={},
            alerts=alerts,
        )

        self.assertIn("daily_actions", daily_flow)
        self.assertEqual(len(daily_flow["daily_actions"]), 1)
        self.assertEqual(
            daily_flow["daily_actions"][0]["action_label"],
            "Vurder salg",
        )

    def test_daily_agenda_items_limited_to_display_limit(self):
        alerts = []
        for index in range(7):
            alerts.append({
                "priority": 1,
                "source": "PORTFOLIO",
                "ticker": f"T{index}",
                "action_label": "Vurder salg",
                "message": f"Melding {index}",
            })

        daily_flow = build_daily_flow(
            watchlist_report=pd.DataFrame(),
            portfolio_report=pd.DataFrame(),
            dashboard={},
            alerts=alerts,
        )

        agenda = daily_agenda_items(daily_flow)

        self.assertEqual(len(agenda), DAILY_AGENDA_DISPLAY_LIMIT)
        self.assertEqual(len(daily_flow["daily_actions"]), 7)

    def test_daily_agenda_from_alerts_matches_build_alerts(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    portefølje_råd="REDUSER / SELG",
                    anbefaling="UNNGÅ / SELG",
                ),
            ]
        )
        alerts = build_alerts(portfolio_report, [], [])

        agenda = daily_agenda_from_alerts(alerts)

        self.assertEqual(len(agenda), 1)
        self.assertEqual(agenda[0]["ticker"], "AAPL")
        self.assertEqual(agenda[0]["action_label"], "Vurder salg")
        self.assertTrue(agenda[0]["message"])


def _mock_key_opportunities_context():
    """Mock watchlist/portfolio der AAPL er eid og MSFT er ny KJØP / ØK-kandidat."""
    watchlist_report = pd.DataFrame(
        [
            _watchlist_row(ticker="AAPL", score=85),
            _watchlist_row(ticker="MSFT", score=75),
        ]
    )
    portfolio_report = pd.DataFrame(
        [
            _portfolio_row(
                ticker="AAPL",
                anbefaling="KJØP / ØK",
            ),
        ]
    )
    dashboard = {
        "top_buy_candidates": watchlist_report.sort_values(
            by="score",
            ascending=False,
        ),
    }
    portfolio = [{"ticker": "AAPL", "shares": 10, "buy_price": 100.0}]

    daily_flow = build_daily_flow(
        watchlist_report=watchlist_report,
        portfolio_report=portfolio_report,
        dashboard=dashboard,
        alerts=[],
        portfolio=portfolio,
    )
    return daily_flow["key_opportunities"]


class DailyFlowKeyOpportunitiesTests(unittest.TestCase):
    def test_unowned_buy_candidate_goes_to_new_buy_candidates(self):
        opportunities = _mock_key_opportunities_context()
        new_buys = opportunities["new_buy_candidates"]

        self.assertFalse(new_buys.empty)
        self.assertEqual(new_buys["ticker"].tolist(), ["MSFT"])
        self.assertEqual(new_buys.iloc[0]["anbefaling"], "KJØP / ØK")

    def test_owned_buy_candidate_goes_to_existing_positions_to_increase(self):
        opportunities = _mock_key_opportunities_context()
        increase_buys = opportunities["existing_positions_to_increase"]

        self.assertFalse(increase_buys.empty)
        self.assertEqual(increase_buys["ticker"].tolist(), ["AAPL"])
        self.assertEqual(increase_buys.iloc[0]["anbefaling"], "KJØP / ØK")

    def test_owned_ticker_not_in_new_buy_candidates(self):
        opportunities = _mock_key_opportunities_context()
        new_buys = opportunities["new_buy_candidates"]

        self.assertNotIn("AAPL", new_buys["ticker"].tolist())


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


def _mock_whats_new_dashboard(
    recommendation_rows=None,
    score_rows=None,
    include_changes=True,
):
    dashboard = {}
    if include_changes:
        dashboard["changes_since_last_snapshot"] = {
            "recommendation_changed": pd.DataFrame(
                recommendation_rows or [],
            ),
            "large_score_changes": pd.DataFrame(score_rows or []),
        }
    return dashboard


class DailyFlowWhatsNewTodayTests(unittest.TestCase):
    def test_not_available_when_snapshot_changes_missing(self):
        daily_flow = build_daily_flow(
            watchlist_report=pd.DataFrame(),
            portfolio_report=pd.DataFrame(),
            dashboard={},
            alerts=[],
        )
        whats_new = daily_flow["whats_new_today"]

        self.assertFalse(whats_new["available"])
        self.assertFalse(whats_new["has_changes"])
        self.assertEqual(whats_new["summary_items"], [])

    def test_summary_items_prioritize_recommendation_changes(self):
        dashboard = _mock_whats_new_dashboard(
            recommendation_rows=[
                _snapshot_change_row(ticker="AAPL"),
                _snapshot_change_row(ticker="MSFT"),
            ],
            score_rows=[
                _snapshot_change_row(
                    ticker="NVDA",
                    previous_score=61,
                    current_score=72,
                    score_change=11,
                    previous_recommendation="HOLD / OBSERVER",
                    current_recommendation="HOLD / OBSERVER",
                ),
            ],
        )

        daily_flow = build_daily_flow(
            watchlist_report=pd.DataFrame(),
            portfolio_report=pd.DataFrame(),
            dashboard=dashboard,
            alerts=[],
        )
        items = daily_flow["whats_new_today"]["summary_items"]

        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["change_type"], "recommendation")
        self.assertEqual(items[1]["change_type"], "recommendation")
        self.assertEqual(items[2]["change_type"], "score")
        self.assertEqual(items[2]["ticker"], "NVDA")
        self.assertEqual(items[2]["fra"], "HOLD")
        self.assertEqual(items[2]["til"], "HOLD")
        self.assertEqual(
            items[2]["begrunnelse"],
            "Score +11 poeng siden sist snapshot",
        )

    def test_summary_items_limited_to_five(self):
        recommendation_rows = [
            _snapshot_change_row(ticker=f"REC{i}")
            for i in range(6)
        ]
        score_rows = [
            _snapshot_change_row(
                ticker=f"SCORE{i}",
                previous_score=50,
                current_score=65,
                score_change=15,
                previous_recommendation="HOLD / OBSERVER",
                current_recommendation="HOLD / OBSERVER",
            )
            for i in range(4)
        ]
        dashboard = _mock_whats_new_dashboard(
            recommendation_rows=recommendation_rows,
            score_rows=score_rows,
        )

        daily_flow = build_daily_flow(
            watchlist_report=pd.DataFrame(),
            portfolio_report=pd.DataFrame(),
            dashboard=dashboard,
            alerts=[],
        )
        items = daily_flow["whats_new_today"]["summary_items"]

        self.assertEqual(len(items), WHATS_NEW_SUMMARY_LIMIT)
        self.assertTrue(
            all(item["change_type"] == "recommendation" for item in items)
        )


class DailyFlowOrderActionsTests(unittest.TestCase):
    def test_build_order_actions_prioritizes_sell_before_buy(self):
        pending_orders = [
            {
                "ticker": "AAPL",
                "action": "BUY",
                "shares": 5,
                "limit_price": 180.0,
            },
            {
                "ticker": "NVDA",
                "action": "SELL",
                "shares": 10,
                "limit_price": 205.0,
            },
        ]

        order_actions = build_order_actions(pending_orders)

        self.assertEqual(len(order_actions), 2)
        self.assertEqual(order_actions[0]["ticker"], "NVDA")
        self.assertEqual(order_actions[0]["priority"], 1)
        self.assertEqual(order_actions[1]["ticker"], "AAPL")
        self.assertEqual(order_actions[1]["priority"], 2)

    def test_order_action_fields_and_message(self):
        pending_orders = [
            {
                "ticker": "NVDA",
                "action": "SELL",
                "shares": 10,
                "limit_price": 205.0,
            },
        ]

        order_actions = build_order_actions(pending_orders)
        action = order_actions[0]

        self.assertEqual(action["action_label"], "Gjennomgå ordre")
        self.assertIn("Salgsordre venter: 10 aksjer @ 205.0", action["message"])
        self.assertIn("Utfør, juster limit, eller kanseller.", action["message"])

    def test_daily_actions_includes_orders_not_covered_by_alerts(self):
        pending_orders = [
            {
                "ticker": "NVDA",
                "action": "SELL",
                "shares": 10,
                "limit_price": 205.0,
            },
        ]

        actions = build_daily_actions([], pending_orders)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["ticker"], "NVDA")
        self.assertEqual(actions[0]["action_label"], "Gjennomgå ordre")

    def test_daily_actions_does_not_duplicate_order_alerts(self):
        pending_orders = [
            {
                "ticker": "NVDA",
                "action": "SELL",
                "shares": 10,
                "limit_price": 205.0,
            },
        ]
        alerts = build_alerts(pd.DataFrame(), pending_orders, [])

        actions = build_daily_actions(alerts, pending_orders)
        order_actions = [
            action
            for action in actions
            if action["action_label"] == "Gjennomgå ordre"
            and action["ticker"] == "NVDA"
        ]

        self.assertEqual(len(order_actions), 1)

    def test_build_daily_flow_exposes_order_actions(self):
        pending_orders = [
            {
                "ticker": "NVDA",
                "action": "SELL",
                "shares": 10,
                "limit_price": 205.0,
            },
        ]

        daily_flow = build_daily_flow(
            watchlist_report=pd.DataFrame(),
            portfolio_report=pd.DataFrame(),
            dashboard={
                "pending_orders": pd.DataFrame(
                    [
                        {
                            "ticker": "NVDA",
                            "action": "SELL",
                            "shares": 10,
                            "limit_price": 205.0,
                        },
                    ]
                ),
            },
            pending_orders=pending_orders,
            alerts=[],
        )

        self.assertEqual(len(daily_flow["order_actions"]), 1)
        self.assertEqual(daily_flow["daily_actions"][0]["ticker"], "NVDA")


class DailyFlowPortfolioActionsTests(unittest.TestCase):
    def test_vurder_reduksjon_in_agenda(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="TRIG",
                    portefølje_råd="VURDER REDUKSJON",
                    begrunnelse="Trailing stop er trigget, men øvrige signaler gir ikke klart salg",
                    trailing_stop_triggered=True,
                ),
            ]
        )

        actions = build_daily_actions([], [], portfolio_report)
        matches = [
            action
            for action in actions
            if action["ticker"] == "TRIG"
            and action["action_label"] == "Vurder reduksjon"
        ]

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["source"], "PORTFOLIO")

    def test_følg_med_ikke_øk_in_agenda(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="MSFT",
                    portefølje_råd="FØLG MED / IKKE ØK",
                    begrunnelse="Signalene er svake eller uklare, men ikke nødvendigvis salg",
                ),
            ]
        )

        actions = build_daily_actions([], [], portfolio_report)
        matches = [
            action
            for action in actions
            if action["ticker"] == "MSFT"
            and action["action_label"] == "Følg med"
        ]

        self.assertEqual(len(matches), 1)

    def test_hold_not_in_portfolio_actions(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="AAPL",
                    portefølje_råd="HOLD",
                ),
                _portfolio_row(
                    ticker="MSFT",
                    portefølje_råd="HOLD / FØLG MED",
                ),
                _portfolio_row(
                    ticker="NVDA",
                    portefølje_råd="HOLD / LA VINNER LØPE",
                ),
            ]
        )

        actions = build_portfolio_actions(portfolio_report)

        self.assertEqual(actions, [])

    def test_reduser_selg_not_duplicated_when_review_sell_alert_exists(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="AAPL",
                    portefølje_råd="REDUSER / SELG",
                    anbefaling="UNNGÅ / SELG",
                ),
            ]
        )
        alerts = build_alerts(portfolio_report, [], [])

        actions = build_daily_actions(alerts, [], portfolio_report)
        portfolio_matches = [
            action
            for action in actions
            if action.get("source") == "PORTFOLIO"
            and action["ticker"] == "AAPL"
            and action["action_label"] == "Vurder salg"
        ]
        alert_matches = [
            action
            for action in actions
            if action["ticker"] == "AAPL"
            and action["action_label"] == "Vurder salg"
        ]

        self.assertEqual(len(portfolio_matches), 0)
        self.assertEqual(len(alert_matches), 1)

    def test_gevinstsikring_not_duplicated_when_profit_alert_exists(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="WIN",
                    portefølje_råd="VURDER GEVINSTSIKRING",
                    anbefaling="HOLD / OBSERVER",
                    unrealized_gain_pct=24.0,
                    trailing_stop_triggered=True,
                ),
            ]
        )
        alerts = build_alerts(portfolio_report, [], [])

        actions = build_daily_actions(alerts, [], portfolio_report)
        portfolio_matches = [
            action
            for action in actions
            if action.get("source") == "PORTFOLIO"
            and action["ticker"] == "WIN"
        ]

        self.assertEqual(len(portfolio_matches), 0)
        self.assertEqual(
            sum(
                1
                for action in actions
                if action["ticker"] == "WIN"
                and action["action_label"] == "Sikre gevinst"
            ),
            1,
        )


class DailyFlowPresentationTests(unittest.TestCase):
    def test_explain_snapshot_change_begrunnelse_prioritizes_score(self):
        row = _snapshot_change_row(score_change=-14)
        self.assertEqual(
            explain_snapshot_change_begrunnelse(row),
            "Score -14 poeng siden sist snapshot",
        )

        row = _snapshot_change_row(score_change=11)
        self.assertEqual(
            explain_snapshot_change_begrunnelse(row),
            "Score +11 poeng siden sist snapshot",
        )

    def test_explain_snapshot_change_begrunnelse_uses_recommendation_fallback(self):
        row = _snapshot_change_row(
            previous_recommendation="HOLD / OBSERVER",
            current_recommendation="UNNGÅ / SELG",
            score_change=0,
        )
        self.assertEqual(
            explain_snapshot_change_begrunnelse(row),
            "Anbefaling nedgradert etter svakere total score",
        )

    def test_build_daily_agenda_table_columns(self):
        actions = [
            {
                "priority": 1,
                "ticker": "AAPL",
                "action_label": "Vurder salg",
                "message": "Svak trend",
            },
        ]

        table = build_daily_agenda_table(actions)

        self.assertEqual(
            table.columns.tolist(),
            ["Prioritet", "Ticker", "Handling"],
        )
        self.assertEqual(table.iloc[0]["Prioritet"], "Høy")
        self.assertEqual(table.iloc[0]["Ticker"], "AAPL")
        self.assertEqual(table.iloc[0]["Handling"], "Vurder salg")

    def test_build_whats_new_table_columns_and_begrunnelse(self):
        dashboard = _mock_whats_new_dashboard(
            recommendation_rows=[
                _snapshot_change_row(
                    ticker="VOLV-B.ST",
                    previous_recommendation="HOLD / OBSERVER",
                    current_recommendation="UNNGÅ / SELG",
                    score_change=-14,
                ),
                _snapshot_change_row(
                    ticker="AAPL",
                    previous_recommendation="KJØP / ØK",
                    current_recommendation="HOLD / OBSERVER",
                    score_change=-8,
                ),
            ],
        )
        daily_flow = build_daily_flow(
            watchlist_report=pd.DataFrame(),
            portfolio_report=pd.DataFrame(),
            dashboard=dashboard,
            alerts=[],
        )

        table = build_whats_new_table(daily_flow)

        self.assertEqual(
            table.columns.tolist(),
            ["Ticker", "Fra", "Til", "Begrunnelse"],
        )
        self.assertEqual(table.iloc[0]["Ticker"], "VOLV-B.ST")
        self.assertEqual(table.iloc[0]["Fra"], "HOLD")
        self.assertEqual(table.iloc[0]["Til"], "UNNGÅ/SELG")
        self.assertEqual(
            table.iloc[0]["Begrunnelse"],
            "Score -14 poeng siden sist snapshot",
        )
        self.assertEqual(table.iloc[1]["Ticker"], "AAPL")
        self.assertEqual(table.iloc[1]["Fra"], "KJØP/ØK")
        self.assertEqual(table.iloc[1]["Til"], "HOLD")
        self.assertEqual(
            table.iloc[1]["Begrunnelse"],
            "Score -8 poeng siden sist snapshot",
        )


class EarningsDailyActionsTests(unittest.TestCase):
    def test_earnings_agenda_prioritization(self):
        earnings_summary = {
            "items": [],
            "upcoming_14_days": [
                {
                    "ticker": "FAR",
                    "days_until": 12,
                    "in_portfolio": False,
                },
                {
                    "ticker": "SOON",
                    "days_until": 1,
                    "in_portfolio": True,
                },
                {
                    "ticker": "TODAY",
                    "days_until": 0,
                    "in_portfolio": True,
                },
            ],
            "unknown": [],
            "last_updated": "2026-06-12T08:00:00+00:00",
        }

        alerts = build_alerts(
            pd.DataFrame(),
            [],
            [],
            earnings_summary=earnings_summary,
        )
        actions = build_daily_actions(alerts)

        earnings_actions = [
            action
            for action in actions
            if action["action_label"] == "Forbered kvartalsrapport"
        ]
        self.assertEqual(len(earnings_actions), 3)
        self.assertEqual(earnings_actions[0]["ticker"], "TODAY")
        self.assertEqual(earnings_actions[0]["priority"], 1)
        self.assertEqual(earnings_actions[1]["ticker"], "SOON")
        self.assertEqual(earnings_actions[1]["priority"], 1)
        self.assertEqual(earnings_actions[2]["ticker"], "FAR")
        self.assertEqual(earnings_actions[2]["priority"], 3)

        alert_types = {alert["ticker"]: alert["alert_type"] for alert in alerts}
        self.assertEqual(alert_types["TODAY"], ALERT_EARNINGS_TODAY)
        self.assertEqual(alert_types["FAR"], ALERT_EARNINGS_WITHIN_14_DAYS)


if __name__ == "__main__":
    unittest.main()
