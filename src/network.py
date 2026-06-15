from __future__ import annotations

import socket

YAHOO_FINANCE_HOST = "query1.finance.yahoo.com"
DEFAULT_NETWORK_TIMEOUT = 5.0


def check_network_ready(
    host: str = YAHOO_FINANCE_HOST,
    *,
    timeout: float = DEFAULT_NETWORK_TIMEOUT,
) -> tuple[bool, str | None]:
    address = (host, 443)

    try:
        with socket.create_connection(address, timeout=timeout):
            pass
    except socket.gaierror as exc:
        return False, f"Could not resolve host: {host} ({exc})"
    except OSError as exc:
        return False, f"Network check failed for {host}: {exc}"

    return True, None
