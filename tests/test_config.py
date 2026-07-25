import unittest
from unittest.mock import patch

from src.config import load_discovery_config


class DiscoveryConfigTests(unittest.TestCase):
    @patch("src.config.load_json_config")
    def test_merges_new_defaults_into_existing_config(self, mock_load):
        mock_load.return_value = {
            "coarse_filter": {
                "enabled": True,
                "min_history_days": 90,
            }
        }

        config = load_discovery_config()

        self.assertEqual(config["coarse_filter"]["min_history_days"], 90)
        self.assertEqual(config["coarse_filter"]["max_full_analysis"], 40)
        self.assertEqual(config["coarse_filter"]["liquidity_top_slots"], 15)
        self.assertEqual(config["coarse_filter"]["mid_liquidity_slots"], 10)
        self.assertIn("min_average_traded_value_20d", config["coarse_filter"])
