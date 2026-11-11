"""Persistent tasks and reminders (data/tasks.json). Survive restarts."""
from __future__ import annotations

import time
from datetime import datetime

from .. import bus, store, timeparse
from .registry import tool

FILE = "tasks.json"


def _load() -> dict:
    data = store.load(FILE, {"tasks": [], "reminders": []})
    data.setdefault("tasks", [])
    data.setdefault("reminders", [])
    return data


def _save(data: dict) -> None:
    store.save(FILE, data)
    bus.publish("tasks_changed")


def snapshot() -> dict:
    data = _load()
    now = datetime.now()
    reminders = sorted((r for r in data["reminders"] if not r.get("done")), key=lambda r: r["due"])
    for r in reminders:
        r["when"] = timeparse.friendly(datetime.fromisoformat(r["due"]), now)
    return {"tasks": [t for t in data["tasks"] if not t.get("done")],
            "done_today": [t for t in data["tasks"] if t.get("done") and
                           datetime.fromtimestamp(t.get("done_at", 0)).date() == now.date()],
            "reminders": reminders}


def create_reminder(text: str, when: str, repeat: str = "", now: datetime | None = None) -> dict | None:
    now = now or datetime.now()
    due, parsed_repeat = timeparse.parse_when(when, now)
    if due is None:
        due, parsed_repeat2 = timeparse.parse_when(text, now)
        parsed_repeat = parsed_repeat or parsed_repeat2
    if due is None:
        return None
    rep = (repeat or "").strip().lower() or parsed_repeat or ""
    if rep and rep not in ("daily", "weekly", "weekdays", "hourly") and not rep.startswith("every:"):
        rep = timeparse.parse_repeat(rep) or ""
    data = _load()
    item = {"id": store.new_id("r_"), "text": text.strip(), "due": due.isoformat(timespec="seconds"),
            "repeat": rep, "done": False, "created": time.time()}
    data["reminders"].append(item)
    _save(data)
    return item


def pop_due(now: datetime | None = None) -> list[dict]:
    """Reminders that are due now. One-offs are marked done; recurring ones roll forward."""
    now = now or datetime.now()
    data = _load()
    fired = []
    for r in data["reminders"]:
        if r.get("done"):
            continue
        due = datetime.fromisoformat(r["due"])
        if due <= now:
            fired.append(dict(r, late_minutes=int((now - due).total_seconds() // 60)))
            if r.get("repeat"):
                r["due"] = timeparse.next_occurrence(due, r["repeat"], now).isoformat(timespec="seconds")
            else:
                r["done"] = True
                r["fired_at"] = time.time()
    if fired:
        _save(data)
    return fired


def conflicts(window_minutes: int = 10) -> list[tuple[dict, dict]]:
    items = snapshot()["reminders"]
    out = []
    for a, b in zip(items, items[1:]):
        gap = (datetime.fromisoformat(b["due"]) - datetime.fromisoformat(a["due"])).total_seconds()
        if 0 <= gap <= window_minutes * 60:
            out.append((a, b))
    return out


def add_task_item(text: str) -> dict:
    data = _load()
    item = {"id": store.new_id("t_"), "text": text.strip(), "done": False, "created": time.time()}
    data["tasks"].append(item)
    _save(data)
    return item


def _match(items: list[dict], which: str) -> dict | None:
    which = which.strip().lower()
    live = [i for i in items if not i.get("done")]
    for i in live:
        if i["id"] == which:
            return i
    if which.isdigit() and 1 <= int(which) <= len(live):
        return live[int(which) - 1]
    words = set(which.split())
    best = max(live, key=lambda i: len(words & set(i["text"].lower().split())), default=None)
    if best and (which in best["text"].lower() or len(words & set(best["text"].lower().split())) >= max(1, len(words) // 2)):
        return best
    return None


def set_task_done(which: str, done: bool = True) -> dict | None:
    data = _load()
    item = _match(data["tasks"], which)
    if item:
        item["done"] = done
        item["done_at"] = time.time()
        _save(data)
    return item


def remove(kind: str, which: str) -> dict | None:
    data = _load()
    item = _match(data[kind], which)
    if item:
        data[kind] = [i for i in data[kind] if i["id"] != item["id"]]
        _save(data)
    return item


@tool("add_reminder", "Set a reminder that will be spoken and shown when due. 'when' is natural language "
      "('in 2 minutes', 'tomorrow at 9', 'friday 6pm', 'every day at 7 am') or ISO 'YYYY-MM-DD HH:MM'.",
      {"text": "str: what to remind him about", "when": "str: when, in his words"},
      {"repeat": "str: '', daily, weekdays, weekly or hourly"}, chip="Setting a reminder", family="tasks")
def add_reminder(text: str, when: str, repeat: str = ""):
    item = create_reminder(text, when, repeat)
    if item is None:
        return f"I couldn't work out a time from '{when}'. Ask him for a clearer time."
    extra = f", repeating {item['repeat']}" if item["repeat"] else ""
    return f"Reminder set: '{item['text']}' {timeparse.friendly(datetime.fromisoformat(item['due']))}{extra}."


@tool("list_reminders", "List his upcoming reminders.", family="tasks")
def list_reminders():
    items = snapshot()["reminders"]
    if not items:
        return "No reminders set."
    return "\n".join(f"{i + 1}. {r['text']} ({r['when']}{', ' + r['repeat'] if r['repeat'] else ''})"
                     for i, r in enumerate(items))


@tool("cancel_reminder", "Cancel a reminder by its number in the list or by words from its text.",
      {"which": "str: number or words"}, family="tasks")
def cancel_reminder(which: str):
    item = remove("reminders", which)
    return f"Cancelled the reminder '{item['text']}'." if item else "I couldn't find that reminder."


@tool("add_task", "Add an item to his to-do list.", {"text": "str: the task"}, chip="Adding to your list",
      family="tasks")
def add_task(text: str):
    add_task_item(text)
    return f"Added to the list: {text.strip()}."


@tool("list_tasks", "Show his open to-do items.", family="tasks")
def list_tasks():
    items = snapshot()["tasks"]
    return "\n".join(f"{i + 1}. {t['text']}" for i, t in enumerate(items)) if items else "The to-do list is empty."


@tool("complete_task", "Mark a to-do item done (by number or words).", {"which": "str: number or words"},
      family="tasks")
def complete_task(which: str):
    item = set_task_done(which)
    return f"Ticked off: {item['text']}." if item else "I couldn't find that task."


@tool("delete_task", "Remove a to-do item without completing it.", {"which": "str: number or words"},
      family="tasks")
def delete_task(which: str):
    item = remove("tasks", which)
    return f"Removed: {item['text']}." if item else "I couldn't find that task."
