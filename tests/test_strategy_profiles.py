import unittest

import pandas as pd

from src.agent import ask_agent
from src.strategy_profiles import (
    _UNKNOWN_TICKER_MESSAGE,
    build_strategy_profile,
    extract_strategy_profile_ticker,
    format_strategy_profile,
    format_strategy_profile_answer,
    is_strategy_profile_question,
)


def _brk_b_like(**overrides):
    base = {
        "ticker": "BRK-B",
        "trend_regime": "STERK OPPTREND",
        "trend_points": 40,
        "momentum_points": 30,
        "relative_strength_points": 10,
        "relative_strength_20d": 1.01,
        "fundamental_score": 50,
        "fundamental_history_score": 60,
    }
    base.update(overrides)
    return base


def _nvda_momentum_like(**overrides):
    base = {
        "ticker": "NVDA",
        "trend_regime": "STERK OPPTREND",
        "trend_points": 40,
        "momentum_points": 30,
        "relative_strength_points": 10,
        "relative_strength_20d": 8.5,
        "fundamental_score": 55,
        "fundamental_history_score": 60,
    }
    base.update(overrides)
    return base


def _nvda_quality_like(**overrides):
    base = {
        "ticker": "NVDA",
        "trend_regime": "SVAK / NEGATIV TREND",
        "trend_points": 0,
        "momentum_points": 15,
        "relative_strength_points": 0,
        "relative_strength_20d": -9.28,
        "fundamental_score": 80,
        "fundamental_history_score": 100,
    }
    base.update(overrides)
    return base


def _cyclical_stock(**overrides):
    base = {
        "ticker": "FRO",
        "sector": "Industrials",
        "industry": "Marine Shipping",
        "trend_points": 20,
        "momentum_points": 15,
        "relative_strength_points": 5,
        "relative_strength_20d": 2.0,
        "fundamental_score": 45,
        "fundamental_history_score": 40,
        "price_to_book": 1.1,
        "return_on_equity": 0.08,
        "debt_to_equity": 90,
        "profit_margin": 0.12,
    }
    base.update(overrides)
    return base


class StrategyProfileTests(unittest.TestCase):
    def test_brk_b_like_quality_primary_with_modest_rs(self):
        profile = build_strategy_profile(_brk_b_like())

        self.assertEqual(profile["primary_profile"], "quality")
        self.assertGreater(profile["profiles"]["quality"], profile["profiles"]["momentum"])
        self.assertLessEqual(profile["profiles"]["momentum"], 55)

    def test_nvda_like_strong_rs_momentum_primary(self):
        profile = build_strategy_profile(_nvda_momentum_like())

        self.assertEqual(profile["primary_profile"], "momentum")
        self.assertGreater(profile["profiles"]["momentum"], profile["profiles"]["quality"])
        self.assertGreaterEqual(profile["profiles"]["momentum"], 85)

    def test_low_rs_caps_momentum(self):
        profile = build_strategy_profile(
            _brk_b_like(
                relative_strength_20d=0.5,
                relative_strength_points=10,
            )
        )

        self.assertLessEqual(profile["profiles"]["momentum"], 55)

    def test_missing_value_fields_return_none(self):
        profile = build_strategy_profile(_brk_b_like())

        self.assertIsNone(profile["profiles"]["value"])
        formatted = format_strategy_profile(profile)
        self.assertIn("Value: ukjent", formatted)

    def test_cyclical_candidate_classified_correctly(self):
        profile = build_strategy_profile(_cyclical_stock())

        self.assertEqual(profile["primary_profile"], "cyclical")
        self.assertGreater(profile["profiles"]["cyclical"], profile["profiles"]["quality"])

    def test_primary_profile_ignores_unknown_value(self):
        profile = build_strategy_profile(
            {
                "ticker": "TEST",
                "trend_points": 10,
                "momentum_points": 10,
                "relative_strength_points": 0,
                "relative_strength_20d": 1.0,
                "fundamental_score": 80,
                "fundamental_history_score": 95,
            }
        )

        self.assertIsNone(profile["profiles"]["value"])
        self.assertEqual(profile["primary_profile"], "quality")

    def test_question_detection(self):
        self.assertTrue(is_strategy_profile_question("Hvilken strategi passer BRK-B?"))
        self.assertTrue(is_strategy_profile_question("Hva er profilen til NVDA?"))
        self.assertTrue(is_strategy_profile_question("Er FRO en syklisk aksje?"))
        self.assertTrue(is_strategy_profile_question("Vis strategi-profil for MSFT"))
        self.assertFalse(is_strategy_profile_question("Ranger watchlist"))


class AgentStrategyProfileTests(unittest.TestCase):
    def _context(self):
        return {
            "watchlist": ["BRK-B", "NVDA"],
            "watchlist_report": pd.DataFrame(
                [
                    _brk_b_like(),
                    _nvda_momentum_like(),
                ]
            ),
            "portfolio_report": None,
            "dashboard": {},
            "daily_flow": {},
        }

    def test_agent_answers_strategy_profile_question(self):
        answer = ask_agent("Vis strategi-profil for BRK-B", self._context())

        self.assertIn("BRK-B", answer)
        self.assertIn("Quality:", answer)
        self.assertIn("Primær profil:", answer)
        self.assertIn("Quality", answer.split("Primær profil:")[1])

    def test_unknown_ticker_returns_helpful_message(self):
        answer = format_strategy_profile_answer(
            {
                "watchlist": ["BRK-B"],
                "watchlist_report": pd.DataFrame([_brk_b_like()]),
                "portfolio_report": None,
            },
            "Vis strategi-profil for FRO",
        )

        self.assertEqual(
            answer,
            _UNKNOWN_TICKER_MESSAGE.format(ticker="FRO"),
        )

    def test_agent_unknown_ticker_message(self):
        answer = ask_agent("Er FRO en syklisk aksje?", self._context())

        self.assertIn("Jeg finner ikke FRO i aktiv analyse", answer)

    def test_agent_extracts_unknown_ticker_from_question(self):
        ticker = extract_strategy_profile_ticker(
            "Vis strategi-profil for FRO",
            {"watchlist": [], "watchlist_report": None, "portfolio_report": None},
        )

        self.assertEqual(ticker, "FRO")


if __name__ == "__main__":
    unittest.main()
