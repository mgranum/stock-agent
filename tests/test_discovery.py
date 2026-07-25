import unittest

import pandas as pd

from src.discovery import (
    build_discovery_coverage,
    combine_discovery_candidates,
    format_discovery_coverage,
    summarize_discovery_rejections,
)


class CombineDiscoveryCandidatesTests(unittest.TestCase):
    def test_combines_regions_deduplicates_and_ranks(self):
        results = {
            "USA": pd.DataFrame(
                [
                    {"ticker": "AAA", "score": 70},
                    {"ticker": "BBB", "score": 90},
                ]
            ),
            "NORDEN": pd.DataFrame([{"ticker": "EQNR.OL", "score": 80}]),
            "OBX": pd.DataFrame([{"ticker": "EQNR.OL", "score": 80}]),
        }

        candidates = combine_discovery_candidates(results)

        self.assertEqual(candidates["ticker"].tolist(), ["BBB", "EQNR.OL", "AAA"])
        self.assertEqual(candidates["ticker"].nunique(), 3)

    def test_watchlist_marks_but_does_not_filter_candidates(self):
        results = {
            "USA": pd.DataFrame([{"ticker": "AAA", "score": 70}]),
            "NORDEN": pd.DataFrame([{"ticker": "BBB.ST", "score": 80}]),
        }

        candidates = combine_discovery_candidates(results, watchlist=["aaa"])

        self.assertEqual(set(candidates["ticker"]), {"AAA", "BBB.ST"})
        flags = candidates.set_index("ticker")["in_watchlist"].to_dict()
        self.assertEqual(flags, {"BBB.ST": False, "AAA": True})
        self.assertEqual(candidates.iloc[0]["ticker"], "BBB.ST")

    def test_invalid_or_empty_results_are_safe(self):
        self.assertTrue(combine_discovery_candidates(None).empty)
        self.assertTrue(
            combine_discovery_candidates(
                {"USA": pd.DataFrame(), "NORDEN": "invalid"}
            ).empty
        )

    def test_builds_region_coverage_from_screening_meta(self):
        coverage = build_discovery_coverage(
            {
                "meta": {
                    "USA": {
                        "universe_size": 500,
                        "analyzed": 490,
                        "failed": 10,
                        "passed_filters": 45,
                    },
                    "NORDEN": {
                        "universe_size": 300,
                        "analyzed": 280,
                        "failed": 20,
                        "passed_filters": 30,
                    },
                },
                "universe_snapshot": "snapshot.json",
            }
        )

        self.assertEqual(coverage["regions"]["USA"]["universe_size"], 500)
        self.assertEqual(coverage["regions"]["NORDEN"]["failed"], 20)
        self.assertEqual(coverage["candidates"], 75)
        self.assertEqual(coverage["snapshot"], "snapshot.json")

    def test_formats_legacy_coverage_without_selected_count(self):
        text = format_discovery_coverage(
            {
                "regions": {
                    "USA": {
                        "universe_size": 50,
                        "coarse_passed": 50,
                        "analyzed": 50,
                        "passed_filters": 16,
                        "failed": 0,
                    }
                }
            }
        )

        self.assertIn("50 valgt for fullanalyse", text)
        self.assertIn("16 kvalifiserte", text)

    def test_summarizes_rejections_by_stage(self):
        summary = summarize_discovery_rejections(
            {
                "regions": {
                    "USA": {
                        "rejected": [
                            {"stage": "capacity_limit"},
                            {"stage": "capacity_limit"},
                            {"stage": "coarse_filter"},
                        ]
                    },
                    "NORDEN": {
                        "rejected": [{"stage": "full_analysis"}]
                    },
                }
            }
        )

        self.assertEqual(
            summary,
            {"capacity_limit": 2, "coarse_filter": 1, "full_analysis": 1},
        )


if __name__ == "__main__":
    unittest.main()
