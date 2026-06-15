import unittest

import pandas as pd

from src.agent import ask_agent
from src.score_explainability import (
    build_score_explanation,
    extract_score_explanation_ticker,
    format_score_explanation,
    is_score_explanation_question,
)


def _sample_stock(**overrides):
    base = {
        "ticker": "BRK-B",
        "score": 100,
        "technical_score": 70,
        "trend_points": 40,
        "momentum_points": 30,
        "volume_points": 0,
        "relative_strength_points": 0,
        "trend_regime": "STERK OPPTREND",
        "fundamental_score": 50,
        "fundamental_history_score": 60,
        "fundamental_reasons": ["Sterk inntjeningsvekst"],
        "fundamental_history_reasons": ["Marginene har forbedret seg"],
        "begrunnelse": [
            "SMA20 over SMA50",
            "Kurs over SMA50",
            "RSI i positivt område",
            "MACD positiv",
            "Svakere enn benchmark SPY",
            "Sterk fundamental kvalitet",
            "God historisk fundamental utvikling",
        ],
    }
    base.update(overrides)
    return base


class ScoreExplainabilityTests(unittest.TestCase):
    def test_build_score_explanation(self):
        explanation = build_score_explanation(_sample_stock())

        self.assertEqual(explanation["ticker"], "BRK-B")
        self.assertEqual(explanation["score"], 100)
        self.assertEqual(explanation["technical"]["total"], 70)
        self.assertEqual(explanation["technical"]["trend_points"], 40)
        self.assertEqual(explanation["fundamental"]["snapshot_score"], 50)
        self.assertEqual(explanation["fundamental"]["history_score"], 60)
        self.assertIn("SMA20 over SMA50", explanation["explanations"])
        self.assertIn("Sterk inntjeningsvekst", explanation["explanations"])
        self.assertIn("Marginene har forbedret seg", explanation["explanations"])

    def test_empty_explanation_does_not_crash(self):
        explanation = build_score_explanation({})
        formatted = format_score_explanation(explanation)

        self.assertEqual(explanation["ticker"], "Ukjent")
        self.assertEqual(explanation["score"], 0)
        self.assertEqual(explanation["explanations"], [])
        self.assertIn("Ingen detaljerte forklaringer tilgjengelig", formatted)

    def test_fundamental_reasons_are_included(self):
        explanation = build_score_explanation(
            _sample_stock(
                fundamental_reasons=["Sterk omsetningsvekst"],
                fundamental_history_reasons=["Sterk EPS-vekst"],
            )
        )

        self.assertIn("Sterk omsetningsvekst", explanation["explanations"])
        self.assertIn("Sterk EPS-vekst", explanation["explanations"])

    def test_formatting(self):
        formatted = format_score_explanation(build_score_explanation(_sample_stock()))

        self.assertIn("BRK-B", formatted)
        self.assertIn("Total score: 100", formatted)
        self.assertIn("Trend: 40", formatted)
        self.assertIn("Momentum: 30", formatted)
        self.assertIn("Snapshot: 50", formatted)
        self.assertIn("Historikk: 60", formatted)
        self.assertIn("Viktigste forklaringer:", formatted)

    def test_question_detection(self):
        self.assertTrue(is_score_explanation_question("Hvorfor scorer BRK-B 100?"))
        self.assertTrue(is_score_explanation_question("Forklar scoren til NVDA"))
        self.assertTrue(is_score_explanation_question("Hvordan er BRK-B satt sammen?"))
        self.assertTrue(is_score_explanation_question("Vis score-forklaring for MSFT"))
        self.assertFalse(is_score_explanation_question("Ranger watchlist"))


class AgentScoreExplainabilityTests(unittest.TestCase):
    def _context(self):
        return {
            "watchlist": ["BRK-B", "NVDA"],
            "watchlist_report": pd.DataFrame([_sample_stock()]),
            "portfolio_report": None,
            "dashboard": {},
            "daily_flow": {},
        }

    def test_agent_recognizes_score_explanation_question(self):
        answer = ask_agent("Hvorfor scorer BRK-B 100?", self._context())

        self.assertIn("BRK-B", answer)
        self.assertIn("Total score: 100", answer)
        self.assertIn("Trend: 40", answer)
        self.assertIn("Sterk inntjeningsvekst", answer)

    def test_agent_extracts_ticker_from_score_question(self):
        ticker = extract_score_explanation_ticker(
            "Forklar scoren til BRK-B",
            self._context(),
        )

        self.assertEqual(ticker, "BRK-B")
