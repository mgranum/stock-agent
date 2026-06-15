from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def annotate_fetch_attempt(data, *, error=None):
    annotated = dict(data)
    annotated["last_attempted_at"] = utc_now_iso()
    if error is not None:
        annotated["fetch_error"] = str(error)
    else:
        annotated.pop("fetch_error", None)
    return annotated
