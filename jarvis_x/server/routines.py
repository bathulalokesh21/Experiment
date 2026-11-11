"""Routines: named multi-step sequences. Stored in data/routines.json."""
from __future__ import annotations

import re

from . import bus, store

FILE = "routines.json"
BUILTINS = [
    {"name": "Good morning", "trigger": "good morning", "builtin": True, "steps": [
        {"ui": "wake"}, {"tool": "light_on", "args": {}}, {"ask": "Give me my morning brief."}]},
    {"name": "Good night", "trigger": "good night", "builtin": True, "steps": [
        {"tool": "light_brightness", "args": {"percent": 10}},
        {"ask": "Tell me tomorrow's first task or reminder in one sentence, then say good night."},
        {"ui": "ambient"}]},
    {"name": "Focus mode", "trigger": "focus mode", "builtin": True, "steps": [
        {"tool": "light_scene", "args": {"scene": "focus"}}, {"ui": "focus_start", "value": "25"},
        {"say": "Focus mode on. Twenty five minutes. I'll keep quiet."}]},
    {"name": "Party", "trigger": "party time", "builtin": True, "steps": [
        {"tool": "light_scene", "args": {"scene": "party"}}, {"ui": "house_party"}]},
]


def all_routines() -> list[dict]:
    saved = store.load(FILE, [])
    names = {r["name"].lower() for r in saved}
    return saved + [dict(b) for b in BUILTINS if b["name"].lower() not in names]


def find(name: str) -> dict | None:
    key = name.strip().lower()
    items = all_routines()
    return next((r for r in items if r["name"].lower() == key), None) or \
        next((r for r in items if key in r["name"].lower() or r["trigger"].lower() == key), None)


def validate_steps(steps) -> list[dict]:
    if not isinstance(steps, list) or not steps:
        raise ValueError("a routine needs at least one step")
    clean = []
    for step in steps[:12]:
        if not isinstance(step, dict):
            raise ValueError("each step must be an object")
        if "say" in step:
            clean.append({"say": str(step["say"])[:400]})
        elif "ask" in step:
            clean.append({"ask": str(step["ask"])[:400]})
        elif "tool" in step:
            name = str(step["tool"])
            if name in ("whatsapp_draft", "call_draft", "gmail_draft", "plugin_propose", "routine_run", "routine_save"):
                raise ValueError(f"'{name}' can't run inside a routine (it needs your approval each time)")
            clean.append({"tool": name, "args": step.get("args") if isinstance(step.get("args"), dict) else {}})
        elif "ui" in step:
            clean.append({"ui": str(step["ui"]), "value": str(step.get("value", ""))})
        else:
            raise ValueError("each step needs one of: say, ask, tool, ui")
    return clean


def save(name: str, trigger: str, steps) -> dict:
    name = re.sub(r"\s+", " ", name).strip()[:60]
    if not name:
        raise ValueError("the routine needs a name")
    routine = {"name": name, "trigger": (trigger or name).strip().lower()[:80], "steps": validate_steps(steps)}
    saved = [r for r in store.load(FILE, []) if r["name"].lower() != name.lower()]
    saved.append(routine)
    store.save(FILE, saved)
    bus.publish("routines_changed")
    return routine


def delete(name: str) -> bool:
    saved = store.load(FILE, [])
    kept = [r for r in saved if r["name"].lower() != name.strip().lower()]
    if len(kept) == len(saved):
        return False
    store.save(FILE, kept)
    bus.publish("routines_changed")
    return True


def match(utterance: str) -> dict | None:
    """Does what he said start a routine? Whole-phrase match, so 'good night' inside a long sentence doesn't fire."""
    said = re.sub(r"[^a-z0-9 ]", "", utterance.lower()).strip()
    said = re.sub(r"^(hey |ok |okay )?(jarvis|friday|robin)\s+", "", said)
    for r in all_routines():
        trig = re.sub(r"[^a-z0-9 ]", "", r["trigger"].lower()).strip()
        if trig and (said == trig or said in (trig + " " + n for n in ("jarvis", "friday", "robin"))
                     or said == "run " + trig or said == r["name"].lower() + " routine"):
            return r
    return None


async def run(name: str) -> dict:
    """Server steps (tools) run here; say/ask/ui steps are handed to the dashboard in order."""
    from .tools import registry
    routine = find(name)
    if routine is None:
        return {"ok": False, "message": f"There's no routine called '{name}'."}
    client_steps, notes = [], []
    for step in routine["steps"]:
        if "tool" in step:
            result = await registry.call(step["tool"], step.get("args", {}))
            notes.append(f"{step['tool']}: {result}")
        else:
            client_steps.append(step)
    bus.publish("routine", name=routine["name"], steps=client_steps, notes=notes)
    return {"ok": True, "name": routine["name"], "steps": client_steps, "notes": notes,
            "message": f"Running '{routine['name']}'. " + " ".join(notes)}
