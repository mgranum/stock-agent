import unittest

import pandas as pd

from src.discovery import combine_discovery_candidates


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

    def test_invalid_or_empty_results_are_safe(self):
        self.assertTrue(combine_discovery_candidates(None).empty)
        self.assertTrue(
            combine_discovery_candidates(
                {"USA": pd.DataFrame(), "NORDEN": "invalid"}
            ).empty
        )


if __name__ == "__main__":
    unittest.main()
