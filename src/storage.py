from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import tempfile
import threading
from collections.abc import Callable

from src.environment import get_environment


_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}


def _project_root():
    return Path(__file__).resolve().parent.parent


def _data_dir():
    path = _project_root() / "data" / get_environment()
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_path(filename):
    filename = str(filename)
    if not filename or Path(filename).name != filename:
        raise ValueError("Ugyldig datafilnavn")
    return _data_dir() / filename


def _thread_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _locked_path(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / f".{path.name}.lock"
    with _thread_lock(path):
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _atomic_write_json_unlocked(path: Path, data):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def atomic_write_json(path: str | Path, data) -> Path:
    resolved = Path(path)
    with _locked_path(resolved):
        _atomic_write_json_unlocked(resolved, data)
    return resolved


def _load_json_path(path: Path, default):
    if not path.exists():
        return deepcopy(default)
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def load_json(filename, default):
    path = data_path(filename)

    if not path.exists():
        with _locked_path(path):
            if not path.exists():
                _atomic_write_json_unlocked(path, default)

    return _load_json_path(path, default)


def save_json(filename, data):
    path = data_path(filename)
    return atomic_write_json(path, data)


def update_json(filename, updater: Callable, default):
    path = data_path(filename)
    with _locked_path(path):
        current = _load_json_path(path, default)
        updated = updater(deepcopy(current))
        _atomic_write_json_unlocked(path, updated)
    return updated


def load_portfolio(default=None):
    return load_json("portfolio.json", default or [])


def save_portfolio(portfolio):
    return save_json("portfolio.json", portfolio)
