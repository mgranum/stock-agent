import unittest

from src.cache_preserve import annotate_fetch_attempt


class CachePreserveTests(unittest.TestCase):
    def test_annotate_fetch_attempt_adds_metadata(self):
        result = annotate_fetch_attempt(
            {"earnings_date": "2026-07-30"},
            error="network down",
        )

        self.assertEqual(result["earnings_date"], "2026-07-30")
        self.assertEqual(result["fetch_error"], "network down")
        self.assertIn("last_attempted_at", result)
