"""Proactive JARVIS: speaks up on its own only when it matters. Rate-limited,
quiet hours, snooze, and every line is also a dismissible card."""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta

from . import bus, config, gmail, store, widgets
from .tools import daily, tasks

FILE = "proactive.json"
MIN_GAP = 20 * 60
OUTING = re.compile(r"\b(go|going|gym|walk|run|jog|market|shop|shopping|meet|outing|trip|travel|class|football|"
                    r"cricket|bus|flight|train|pick up|drop|visit|dinner out|movie)\b", re.I)


def _state() -> dict:
    s = store.load(FILE, {})
    s.setdefault("last", 0)
    s.setdefault("snooze_until", 0)
    s.setdefault("said", {})
    return s


def in_quiet_hours(now: datetime, start: str, end: str) -> bool:
    try:
        s = datetime.strptime(start, "%H:%M").time()
        e = datetime.strptime(end, "%H:%M").time()
    except ValueError:
        return False
    t = now.time()
    return (s <= t < e) if s < e else (t >= s or t < e)


def snooze(minutes: int = 60) -> float:
    s = _state()
    s["snooze_until"] = time.time() + minutes * 60
    store.save(FILE, s)
    return s["snooze_until"]


def candidates(now: datetime) -> list[dict]:
    """Real triggers only. Each has a key that is announced at most once per day."""
    out = []
    snap = tasks.snapshot()
    weather = widgets._state.get("weather") or {}
    # 1. rain before a planned outing
    if weather.get("ok"):
        wet = next((h for h in weather.get("hourly", [])[:6] if (h.get("pop") or 0) >= 60), None)
        soon = [r for r in snap["reminders"]
                if 0 <= (datetime.fromisoformat(r["due"]) - now).total_seconds() <= 4 * 3600 and OUTING.search(r["text"])]
        if wet and soon:
            out.append({"key": f"rain:{soon[0]['id']}", "kind": "rain",
                        "text": f"Heads up: rain is likely around {widgets._clock(wet['t'])} and you have "
                                f"'{soon[0]['text']}' coming up. Take an umbrella."})
    # 2. reminder conflict
    for a, b in tasks.conflicts():
        if 0 <= (datetime.fromisoformat(a["due"]) - now).total_seconds() <= 6 * 3600:
            out.append({"key": f"conflict:{a['id']}:{b['id']}", "kind": "conflict",
                        "text": f"Two things collide: '{a['text']}' and '{b['text']}' are both set for {a['when']}."})
    # 3. skipped guitar practice 3+ days
    g = daily.guitar_stats()
    if g["days_since"] is not None and g["days_since"] >= 3 and 10 <= now.hour <= 21:
        out.append({"key": "guitar", "kind": "habit",
                    "text": f"You haven't picked up the guitar in {g['days_since']} days. Ten minutes tonight keeps the calluses."})
    # 4. important unread email
    if gmail.connected():
        try:
            mail = gmail.search("is:unread is:important newer_than:1d", 1)
        except Exception:
            mail = []
        if mail:
            sender = mail[0]["from"].split("<")[0].strip().strip('"') or "someone"
            out.append({"key": f"mail:{mail[0]['id']}", "kind": "mail",
                        "text": f"An important email is waiting from {sender}: {mail[0]['subject']}."})
    return out


def check(now: datetime | None = None, publish: bool = True) -> dict | None:
    """Returns the one proactive item to say now, or None."""
    now = now or datetime.now()
    settings = config.settings()
    if not settings.get("proactive", True):
        return None
    if in_quiet_hours(now, settings.get("quiet_start", "23:00"), settings.get("quiet_end", "07:00")):
        return None
    s = _state()
    ts = now.timestamp()
    if ts < s["snooze_until"] or ts - s["last"] < MIN_GAP:
        return None
    today = now.strftime("%Y-%m-%d")
    s["said"] = {k: v for k, v in s["said"].items() if v == today}
    for item in candidates(now):
        if item["key"] in s["said"]:
            continue
        s["said"][item["key"]] = today
        s["last"] = ts
        store.save(FILE, s)
        item["id"] = store.new_id("p_")
        if publish:
            bus.publish("proactive", item=item)
        return item
    return None
