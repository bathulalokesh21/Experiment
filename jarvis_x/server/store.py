"""Tiny JSON persistence. Atomic writes so a crash never corrupts a file."""
from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid

from . import config

_lock = threading.RLock()


def load(name: str, default):
    path = config.data(name)
    with _lock:
        if not path.exists():
            return copy.deepcopy(default)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            # keep the damaged file for inspection, start clean
            try:
                path.replace(path.with_suffix(path.suffix + f".broken-{int(time.time())}"))
            except OSError:
                pass
            return copy.deepcopy(default)


def save(name: str, obj) -> None:
    path = config.data(name)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:8]
