import unittest

import pandas as pd

from src.alerts import (
    ACTION_ADD_TO_WATCHLIST,
    ACTION_ARCHIVE_RESEARCH,
    ACTION_PREPARE_EARNINGS,
    ACTION_PREPARE_SELL_ORDER,
    ACTION_PROTECT_PROFIT,
    ACTION_REVIEW_ORDER,
    ACTION_REVIEW_SELL,
    ALERT_EARNINGS_TODAY,
    ALERT_EARNINGS_TOMORROW,
    ALERT_EARNINGS_WITHIN_14_DAYS,
    ALERT_EARNINGS_WITHIN_7_DAYS,
    ALERT_NEAR_TRAILING_STOP,
    ALERT_PORTFOLIO_SELL,
    ALERT_PROFIT_PROTECTION,
    ALERT_TRAILING_STOP_TRIGGERED,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    _dedupe_alerts,
    _make_alert,
    build_alerts,
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


class BuildAlertsV2Tests(unittest.TestCase):
    def test_alert_has_action_fields(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    portefølje_råd="REDUSER / SELG",
                    anbefaling="UNNGÅ / SELG",
                ),
            ]
        )

        alerts = build_alerts(portfolio_report, [], [])

        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert["alert_type"], ALERT_PORTFOLIO_SELL)
        self.assertEqual(alert["action"], ACTION_REVIEW_SELL)
        self.assertEqual(alert["action_label"], "Vurder salg")
        self.assertEqual(alert["priority"], 1)
        self.assertEqual(alert["dedupe_key"], f"{ALERT_PORTFOLIO_SELL}:AAPL")

    def test_existing_alert_actions(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="WIN",
                    portefølje_råd="VURDER GEVINSTSIKRING",
                    anbefaling="HOLD / OBSERVER",
                ),
                _portfolio_row(
                    ticker="NEAR",
                    current_price=103.0,
                    trailing_stop_loss=100.0,
                    trailing_stop_triggered=False,
                ),
            ]
        )
        pending_orders = [
            {
                "ticker": "ORD",
                "action": "BUY",
                "shares": 10,
                "limit_price": 50.0,
            },
        ]
        research_ideas = [
            {
                "ticker": "ADD",
                "status": "LEGG TIL WATCHLIST",
                "score": 75,
                "recommendation": "KJØP / ØK",
            },
            {
                "ticker": "DROP",
                "status": "ARKIVER",
                "score": 30,
                "recommendation": "UNNGÅ / SELG",
            },
        ]

        alerts = build_alerts(portfolio_report, pending_orders, research_ideas)
        actions = {alert["alert_type"]: alert["action"] for alert in alerts}
        action_labels = {
            alert["alert_type"]: alert["action_label"] for alert in alerts
        }

        self.assertEqual(actions["PROFIT_PROTECTION"], ACTION_PROTECT_PROFIT)
        self.assertEqual(actions["NEAR_TRAILING_STOP"], ACTION_PREPARE_SELL_ORDER)
        self.assertEqual(action_labels["NEAR_TRAILING_STOP"], "Følg stop-nivå")
        self.assertEqual(actions["PENDING_ORDER"], ACTION_REVIEW_ORDER)
        self.assertEqual(actions["RESEARCH_ADD"], ACTION_ADD_TO_WATCHLIST)
        self.assertEqual(actions["RESEARCH_ARCHIVE"], ACTION_ARCHIVE_RESEARCH)

    def test_trailing_stop_triggered_alert_is_created(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    current_price=240.0,
                    trailing_stop_loss=250.0,
                    trailing_stop_triggered=True,
                ),
            ]
        )

        alerts = build_alerts(portfolio_report, [], [])

        triggered = [
            alert
            for alert in alerts
            if alert["alert_type"] == ALERT_TRAILING_STOP_TRIGGERED
        ]
        self.assertEqual(len(triggered), 1)
        self.assertEqual(triggered[0]["action"], ACTION_REVIEW_SELL)
        self.assertEqual(triggered[0]["severity"], "HIGH")
        self.assertIn("brutt", triggered[0]["message"].lower())

    def test_duplicates_are_removed_by_dedupe_key(self):
        research_ideas = [
            {
                "ticker": "AAPL",
                "status": "LEGG TIL WATCHLIST",
                "score": 80,
                "recommendation": "KJØP / ØK",
            },
            {
                "ticker": "AAPL",
                "status": "LEGG TIL WATCHLIST",
                "score": 70,
                "recommendation": "KJØP / ØK",
            },
        ]

        alerts = build_alerts(pd.DataFrame(), [], research_ideas)

        watchlist_alerts = [
            alert for alert in alerts if alert["alert_type"] == "RESEARCH_ADD"
        ]
        self.assertEqual(len(watchlist_alerts), 1)
        self.assertEqual(watchlist_alerts[0]["dedupe_key"], "RESEARCH_ADD:AAPL")


class BuildAlertsV3Tests(unittest.TestCase):
    def test_merge_review_sell_prefers_portfolio_sell(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    portefølje_råd="REDUSER / SELG",
                    anbefaling="UNNGÅ / SELG",
                    trailing_stop_triggered=True,
                    current_price=240.0,
                    trailing_stop_loss=250.0,
                    unrealized_gain_pct=-4.1,
                ),
            ]
        )

        alerts = build_alerts(portfolio_report, [], [])
        review_sells = [
            alert for alert in alerts if alert["action"] == ACTION_REVIEW_SELL
        ]

        self.assertEqual(len(review_sells), 1)
        self.assertEqual(review_sells[0]["alert_type"], ALERT_PORTFOLIO_SELL)

    def test_profit_protection_suppresses_trailing_stop_triggered(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    portefølje_råd="VURDER GEVINSTSIKRING",
                    anbefaling="HOLD / OBSERVER",
                    trailing_stop_triggered=True,
                    current_price=240.0,
                    trailing_stop_loss=250.0,
                    unrealized_gain_pct=24.0,
                    begrunnelse=(
                        "Trailing stop er trigget, men aksjen har fortsatt "
                        "akseptabel trend og posisjonen er tydelig i pluss"
                    ),
                ),
            ]
        )

        alerts = build_alerts(portfolio_report, [], [])

        triggered = [
            alert
            for alert in alerts
            if alert["alert_type"] == ALERT_TRAILING_STOP_TRIGGERED
        ]
        profit = [
            alert
            for alert in alerts
            if alert["alert_type"] == ALERT_PROFIT_PROTECTION
        ]

        self.assertEqual(len(triggered), 0)
        self.assertEqual(len(profit), 1)

    def test_near_trailing_stop_suppressed_when_pending_sell_exists(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="AAPL",
                    current_price=103.0,
                    trailing_stop_loss=100.0,
                    trailing_stop_triggered=False,
                ),
            ]
        )
        pending_orders = [
            {
                "ticker": "AAPL",
                "action": "SELL",
                "shares": 5,
                "limit_price": 100.0,
            },
        ]

        alerts = build_alerts(portfolio_report, pending_orders, [])

        near_stop = [
            alert
            for alert in alerts
            if alert["alert_type"] == ALERT_NEAR_TRAILING_STOP
        ]
        self.assertEqual(len(near_stop), 0)

    def test_messages_include_relevant_numbers(self):
        portfolio_report = pd.DataFrame(
            [
                _portfolio_row(
                    ticker="SELL",
                    portefølje_råd="REDUSER / SELG",
                    anbefaling="UNNGÅ / SELG",
                    unrealized_gain_pct=-8.2,
                    score=38,
                    begrunnelse="Trendregimet er svakt eller negativt",
                ),
                _portfolio_row(
                    ticker="TRIG",
                    trailing_stop_triggered=True,
                    current_price=240.0,
                    trailing_stop_loss=250.0,
                    unrealized_gain_pct=-4.1,
                ),
                _portfolio_row(
                    ticker="NEAR",
                    current_price=103.0,
                    trailing_stop_loss=100.0,
                    unrealized_gain_pct=62.0,
                    trailing_stop_triggered=False,
                ),
                _portfolio_row(
                    ticker="WIN",
                    portefølje_råd="VURDER GEVINSTSIKRING",
                    anbefaling="HOLD / OBSERVER",
                    unrealized_gain_pct=24.0,
                    begrunnelse="Trailing stop er trigget, men trend OK",
                ),
            ]
        )
        pending_orders = [
            {
                "ticker": "ORD",
                "action": "SELL",
                "shares": 10,
                "limit_price": 250.0,
            },
        ]

        alerts = build_alerts(portfolio_report, pending_orders, [])
        messages = {alert["alert_type"]: alert["message"] for alert in alerts}

        self.assertIn("-8.2 %", messages[ALERT_PORTFOLIO_SELL])
        self.assertIn("score 38", messages[ALERT_PORTFOLIO_SELL])
        self.assertIn("250.00 brutt", messages[ALERT_TRAILING_STOP_TRIGGERED])
        self.assertIn("240.00", messages[ALERT_TRAILING_STOP_TRIGGERED])
        self.assertIn("-4.1 %", messages[ALERT_TRAILING_STOP_TRIGGERED])
        self.assertIn("Dagens kurs er 103.00", messages[ALERT_NEAR_TRAILING_STOP])
        self.assertIn("Stop loss er 100.00", messages[ALERT_NEAR_TRAILING_STOP])
        self.assertIn("2.9 % under dagens kurs", messages[ALERT_NEAR_TRAILING_STOP])
        self.assertIn("Behold posisjonen", messages[ALERT_NEAR_TRAILING_STOP])
        self.assertIn("+24.0 %", messages[ALERT_PROFIT_PROTECTION])
        self.assertIn("Salgsordre venter", messages["PENDING_ORDER"])
        self.assertIn("250.0", messages["PENDING_ORDER"])


def _earnings_summary(*items):
    return {
        "items": list(items),
        "upcoming_14_days": list(items),
        "unknown": [],
        "last_updated": "2026-06-12T08:00:00+00:00",
    }


def _earnings_item(ticker, days_until, in_portfolio=False):
    return {
        "ticker": ticker,
        "earnings_date": "2026-06-20",
        "days_until": days_until,
        "status": "confirmed",
        "source": "yfinance",
        "in_portfolio": in_portfolio,
        "last_updated": "2026-06-12T08:00:00+00:00",
    }


class EarningsAlertsTests(unittest.TestCase):
    def test_earnings_today_portfolio_is_high(self):
        alerts = build_alerts(
            pd.DataFrame(),
            [],
            [],
            earnings_summary=_earnings_summary(
                _earnings_item("AAPL", 0, in_portfolio=True),
            ),
        )

        earnings = [alert for alert in alerts if alert["alert_type"] == ALERT_EARNINGS_TODAY]
        self.assertEqual(len(earnings), 1)
        self.assertEqual(earnings[0]["severity"], SEVERITY_HIGH)
        self.assertEqual(earnings[0]["action"], ACTION_PREPARE_EARNINGS)
        self.assertEqual(earnings[0]["action_label"], "Forbered kvartalsrapport")
        self.assertEqual(earnings[0]["message"], "Kvartalsrapport i dag.")
        self.assertEqual(earnings[0]["priority"], 1)
        self.assertEqual(earnings[0]["dedupe_key"], "EARNINGS:AAPL")

    def test_earnings_today_watchlist_is_medium(self):
        alerts = build_alerts(
            pd.DataFrame(),
            [],
            [],
            earnings_summary=_earnings_summary(
                _earnings_item("MSFT", 0, in_portfolio=False),
            ),
        )

        earnings = [alert for alert in alerts if alert["alert_type"] == ALERT_EARNINGS_TODAY]
        self.assertEqual(earnings[0]["severity"], SEVERITY_MEDIUM)

    def test_earnings_tomorrow(self):
        alerts = build_alerts(
            pd.DataFrame(),
            [],
            [],
            earnings_summary=_earnings_summary(
                _earnings_item("NVDA", 1, in_portfolio=True),
            ),
        )

        earnings = [alert for alert in alerts if alert["alert_type"] == ALERT_EARNINGS_TOMORROW]
        self.assertEqual(len(earnings), 1)
        self.assertEqual(earnings[0]["message"], "Kvartalsrapport i morgen.")
        self.assertEqual(earnings[0]["priority"], 1)

    def test_earnings_within_7_days(self):
        alerts = build_alerts(
            pd.DataFrame(),
            [],
            [],
            earnings_summary=_earnings_summary(
                _earnings_item("EQNR.OL", 5, in_portfolio=True),
            ),
        )

        earnings = [
            alert
            for alert in alerts
            if alert["alert_type"] == ALERT_EARNINGS_WITHIN_7_DAYS
        ]
        self.assertEqual(len(earnings), 1)
        self.assertEqual(earnings[0]["severity"], SEVERITY_MEDIUM)
        self.assertEqual(earnings[0]["message"], "Kvartalsrapport om 5 dager.")
        self.assertEqual(earnings[0]["priority"], 2)

    def test_earnings_within_14_days(self):
        alerts = build_alerts(
            pd.DataFrame(),
            [],
            [],
            earnings_summary=_earnings_summary(
                _earnings_item("DNB.OL", 12, in_portfolio=False),
            ),
        )

        earnings = [
            alert
            for alert in alerts
            if alert["alert_type"] == ALERT_EARNINGS_WITHIN_14_DAYS
        ]
        self.assertEqual(len(earnings), 1)
        self.assertEqual(earnings[0]["severity"], SEVERITY_LOW)
        self.assertEqual(earnings[0]["message"], "Kvartalsrapport om 12 dager.")
        self.assertEqual(earnings[0]["priority"], 3)

    def test_earnings_dedup_keeps_most_severe_per_ticker(self):
        alerts = [
            _make_alert(
                ALERT_EARNINGS_WITHIN_14_DAYS,
                SEVERITY_LOW,
                "AAPL",
                "Kvartalsrapport innen 14 dager",
                "Kvartalsrapport om 12 dager.",
                "EARNINGS",
                "2026-06-12T08:00:00+00:00",
                action=ACTION_PREPARE_EARNINGS,
                priority=3,
                dedupe_key="EARNINGS:AAPL",
            ),
            _make_alert(
                ALERT_EARNINGS_TODAY,
                SEVERITY_HIGH,
                "AAPL",
                "Kvartalsrapport i dag",
                "Kvartalsrapport i dag.",
                "EARNINGS",
                "2026-06-12T08:00:00+00:00",
                action=ACTION_PREPARE_EARNINGS,
                priority=1,
                dedupe_key="EARNINGS:AAPL",
            ),
        ]

        deduped = _dedupe_alerts(alerts)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["alert_type"], ALERT_EARNINGS_TODAY)
        self.assertEqual(deduped[0]["priority"], 1)


if __name__ == "__main__":
    unittest.main()
