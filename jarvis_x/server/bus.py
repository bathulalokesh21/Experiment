"""Server -> dashboard event bus (delivered over SSE at /api/events)."""
from __future__ import annotations

import asyncio
import time
from collections import deque

_subscribers: set[asyncio.Queue] = set()
_backlog: deque = deque(maxlen=200)
_loop: asyncio.AbstractEventLoop | None = None
_seq = 0


def bind_loop(loop) -> None:
    global _loop
    _loop = loop


def _deliver(event: dict) -> None:
    for queue in list(_subscribers):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass


def publish(kind: str, **data) -> dict:
    """Safe to call from the event loop or from a worker thread."""
    global _seq
    _seq += 1
    event = {"type": kind, "seq": _seq, "t": time.time(), **data}
    _backlog.append(event)
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        _deliver(event)
    elif _loop is not None and not _loop.is_closed():
        _loop.call_soon_threadsafe(_deliver, event)
    return event


def subscribe() -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue) -> None:
    _subscribers.discard(queue)


def listeners() -> int:
    return len(_subscribers)


def recent(kind: str | None = None, limit: int = 50) -> list[dict]:
    items = [e for e in _backlog if kind is None or e["type"] == kind]
    return items[-limit:]


def reset() -> None:
    _backlog.clear()
    _subscribers.clear()
