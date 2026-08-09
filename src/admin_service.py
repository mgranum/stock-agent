from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import re
import threading
from uuid import uuid4

from src.company_detail_query import normalize_ticker
from src.config import DEFAULT_WATCHLISTS
from src.environment import get_environment
from src.storage import atomic_write_json, data_path, load_json, save_json
from src.write_ownership import claim_writer


_BACKUP_PATTERN = re.compile(r"^\d{8}T\d{6}Z-[a-f0-9]{8}$")
_MUTATION_LOCK = threading.RLock()


class AdminWritesDisabled(RuntimeError):
    pass


class AdminMutationService:
    """Single guarded writer for portfolio and watchlist user data."""

    def is_writable(self) -> bool:
        environment = get_environment()
        return environment == "test" or (
            environment == "prod"
            and os.getenv("STOCK_AGENT_ENABLE_PROD_WRITES") == "1"
        )

    def _assert_writable(self):
        if not self.is_writable():
            raise AdminWritesDisabled(
                "Skriveoperasjoner er deaktivert. PROD krever "
                "STOCK_AGENT_ENABLE_PROD_WRITES=1."
            )

    def _raw_watchlists(self):
        return load_json("watchlists.json", DEFAULT_WATCHLISTS)

    def _writer_owner_snapshot(self) -> dict:
        path = data_path("writer_owner.json")
        if not path.exists():
            return {"exists": False, "value": None}
        with open(path, "r", encoding="utf-8") as stream:
            return {"exists": True, "value": json.load(stream)}

    def _restore_writer_owner(self, snapshot: dict):
        path = data_path("writer_owner.json")
        if snapshot.get("exists"):
            atomic_write_json(path, snapshot.get("value") or {})
        else:
            path.unlink(missing_ok=True)

    def _backup(self, portfolio, watchlists, writer_owner) -> str:
        backup_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid4().hex[:8]
        )
        backup_dir = data_path("backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            backup_dir / f"{backup_id}.json",
            {
                "backup_id": backup_id,
                "environment": get_environment(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "portfolio": portfolio,
                "watchlists": watchlists,
                "writer_owner": writer_owner,
            },
        )
        return backup_id

    def update_stock(
        self,
        ticker: str,
        *,
        owned: bool,
        average_cost: float | None,
        watchlists: list[str],
    ) -> dict:
        self._assert_writable()
        symbol = normalize_ticker(ticker)
        if owned and (average_cost is None or average_cost <= 0):
            raise ValueError("GAV må være større enn 0 for en eid aksje.")

        with _MUTATION_LOCK:
            portfolio = load_json("portfolio.json", [])
            current_watchlists = self._raw_watchlists()
            writer_owner = self._writer_owner_snapshot()
            editable = set(current_watchlists)
            requested = {str(name).strip() for name in watchlists}
            unknown = requested - editable
            if unknown:
                raise ValueError(
                    "Ukjent watchlist: " + ", ".join(sorted(unknown))
                )
            backup_id = self._backup(
                portfolio, current_watchlists, writer_owner
            )
            updated_portfolio = []
            existing = None
            for position in portfolio:
                if str(position.get("ticker", "")).upper() == symbol:
                    existing = deepcopy(position)
                else:
                    updated_portfolio.append(position)
            if owned:
                position = existing or {
                    "position_id": str(uuid4()),
                    "ticker": symbol,
                    # Quantity is retained for compatibility with the existing
                    # risk model, but is not exposed as portfolio value in UI.
                    "shares": 1.0,
                    "buy_datetime": datetime.now(timezone.utc).isoformat(),
                    "source": "react_admin",
                }
                position["ticker"] = symbol
                position["buy_price"] = round(float(average_cost), 4)
                updated_portfolio.append(position)

            updated_watchlists = deepcopy(current_watchlists)
            for name, symbols in updated_watchlists.items():
                normalized = [str(item).upper() for item in symbols]
                if name in requested and symbol not in normalized:
                    normalized.append(symbol)
                if name not in requested:
                    normalized = [item for item in normalized if item != symbol]
                updated_watchlists[name] = normalized

            try:
                claim_writer("react")
                save_json("portfolio.json", updated_portfolio)
                save_json("watchlists.json", updated_watchlists)
            except Exception:
                save_json("portfolio.json", portfolio)
                save_json("watchlists.json", current_watchlists)
                self._restore_writer_owner(writer_owner)
                raise

        return {
            "ticker": symbol,
            "owned": owned,
            "average_cost": round(float(average_cost), 4) if owned else None,
            "watchlists": sorted(requested),
            "backup_id": backup_id,
        }

    def rollback(self, backup_id: str) -> dict:
        self._assert_writable()
        if not _BACKUP_PATTERN.fullmatch(str(backup_id)):
            raise ValueError("Ugyldig backup-id.")
        backup_path = data_path("backups") / f"{backup_id}.json"
        if not backup_path.exists():
            raise FileNotFoundError("Backup finnes ikke.")

        with _MUTATION_LOCK:
            with open(backup_path, "r", encoding="utf-8") as stream:
                backup = json.load(stream)
            if backup.get("environment") != get_environment():
                raise ValueError("Backup tilhører et annet miljø.")
            save_json("portfolio.json", backup.get("portfolio") or [])
            save_json("watchlists.json", backup.get("watchlists") or {})
            self._restore_writer_owner(
                backup.get("writer_owner")
                or {"exists": False, "value": None}
            )
        return {"backup_id": backup_id, "restored": True}
