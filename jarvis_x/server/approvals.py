"""The ONLY place actions get approved.

The crew can *prepare* an action (create a card). Nothing here is exposed to the
model as a tool: approve()/cancel() are reachable only from the dashboard routes,
which are triggered by his click, his voice ("send it") or his thumbs-up gesture.
"""
from __future__ import annotations

import inspect
import time

from . import bus, store

FILE = "approvals.json"
_executors: dict[str, tuple] = {}


def register_executor(kind: str, on_approve, on_cancel=None) -> None:
    _executors[kind] = (on_approve, on_cancel)


def _load() -> list[dict]:
    return store.load(FILE, [])


def _save(cards: list[dict]) -> None:
    store.save(FILE, cards[-100:])


def public(card: dict) -> dict:
    """What the dashboard sees: everything except the raw payload."""
    return {k: v for k, v in card.items() if k != "payload"}


def create(kind: str, title: str, fields: list[dict], payload: dict, warning: str = "") -> dict:
    """fields: [{"label": "To", "value": "Mom (+91 ••••• ••123)"}, ...] shown on the card."""
    cards = _load()
    card = {
        "id": store.new_id("ap_"), "kind": kind, "title": title, "fields": fields,
        "warning": warning, "payload": payload, "status": "pending", "created": time.time(),
        "result": "",
    }
    cards.append(card)
    _save(cards)
    bus.publish("approval", card=public(card))
    return card


def pending() -> list[dict]:
    return [c for c in _load() if c["status"] == "pending"]


def get(card_id: str) -> dict | None:
    return next((c for c in _load() if c["id"] == card_id), None)


def latest_pending() -> dict | None:
    items = pending()
    return items[-1] if items else None


async def _finish(card_id: str, action: str, via: str) -> dict:
    cards = _load()
    card = next((c for c in cards if c["id"] == card_id), None)
    if card is None:
        return {"ok": False, "message": "That card no longer exists."}
    if card["status"] != "pending":
        return {"ok": False, "message": f"Already {card['status']}.", "card": public(card)}
    on_approve, on_cancel = _executors.get(card["kind"], (None, None))
    handler = on_approve if action == "approve" else on_cancel
    # mark first so a double click / double gesture can never run the action twice
    card["status"] = "working" if action == "approve" else "cancelled"
    card["via"] = via
    _save(cards)
    ok, message = True, ("Cancelled." if action == "cancel" else "Done.")
    if handler is not None:
        try:
            out = handler(card["payload"])
            if inspect.isawaitable(out):
                out = await out
            if isinstance(out, tuple):
                ok, message = bool(out[0]), str(out[1])
            elif out:
                message = str(out)
        except Exception as exc:  # the action failed: say so plainly
            ok, message = False, f"{type(exc).__name__}: {exc}"
    elif action == "approve":
        ok, message = False, f"No executor is registered for '{card['kind']}'."
    cards = _load()
    card = next(c for c in cards if c["id"] == card_id)
    if action == "approve":
        # a failed action keeps the draft: the card returns to pending so he can retry or cancel
        card["status"] = "done" if ok else "pending"
        card["attempts"] = card.get("attempts", 0) + (0 if ok else 1)
    card["result"] = message
    card["finished"] = time.time()
    _save(cards)
    bus.publish("approval_done", card=public(card), ok=ok, message=message)
    return {"ok": ok, "message": message, "card": public(card)}


async def approve(card_id: str, via: str = "click") -> dict:
    return await _finish(card_id, "approve", via)


async def cancel(card_id: str, via: str = "click") -> dict:
    return await _finish(card_id, "cancel", via)
