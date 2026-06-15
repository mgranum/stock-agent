import socket
import unittest
from unittest.mock import patch

from src.network import YAHOO_FINANCE_HOST, check_network_ready


class CheckNetworkReadyTests(unittest.TestCase):
    @patch("src.network.socket.create_connection")
    def test_returns_true_when_tcp_succeeds(self, mock_connect):
        ready, error = check_network_ready()

        self.assertTrue(ready)
        self.assertIsNone(error)
        mock_connect.assert_called_once_with(
            (YAHOO_FINANCE_HOST, 443),
            timeout=5.0,
        )

    @patch("src.network.socket.create_connection")
    def test_returns_false_when_dns_fails(self, mock_connect):
        mock_connect.side_effect = socket.gaierror("Name or service not known")

        ready, error = check_network_ready()

        self.assertFalse(ready)
        self.assertIn("Could not resolve host", error or "")
        mock_connect.assert_called_once_with(
            (YAHOO_FINANCE_HOST, 443),
            timeout=5.0,
        )

    @patch("src.network.socket.create_connection")
    def test_returns_false_when_tcp_connect_fails(self, mock_connect):
        mock_connect.side_effect = TimeoutError("timed out")

        ready, error = check_network_ready()

        self.assertFalse(ready)
        self.assertIn("Network check failed", error or "")
        mock_connect.assert_called_once_with(
            (YAHOO_FINANCE_HOST, 443),
            timeout=5.0,
        )

    @patch("src.daily_refresh.check_network_ready", return_value=(True, None))
    def test_dry_run_does_not_crash(self, _mock_network):
        from src.daily_refresh import execute_daily_refresh

        result = execute_daily_refresh(dry_run=True)

        self.assertTrue(result["dry_run"])
        self.assertTrue(result["network_ready"])
