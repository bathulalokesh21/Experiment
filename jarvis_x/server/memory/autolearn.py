"""Auto-learning: after each exchange a cheap background pass (Haiku) pulls out
durable facts he stated, dedupes them, and updates facts that changed."""
from __future__ import annotations

import json
import re

from . import facts

FIRST_PERSON = re.compile(
    r"\b(i|i'm|im|i've|i'll|my|mine|me|we|we're|our)\b", re.I)
SIGNAL = re.compile(
    r"\b(am|i'm|im|was|will|going to|plan|planning|moved?|moving|live|living|join|joined|joining|"
    r"accept|accepted|start|started|starting|prefer|like|love|hate|favou?rite|bought|got|birthday|"
    r"born|name is|called|friend|brother|sister|mom|mother|dad|father|girlfriend|wife|roommate|"
    r"working on|decided|learning|practi[sc]e|allergic|remember that|note that|from now on|always|never)\b", re.I)
FORGET_ALL = re.compile(r"\bforget (?:everything|anything|all)(?: you know)? about (.+?)[.!?]*$", re.I)
FORGET_THAT = re.compile(r"\b(forget that|forget it|forget what i (just )?said|don'?t remember that|scratch that)\b", re.I)
FORGET_X = re.compile(r"\bforget (?:that |about )?(?:my |the )?(.{3,60}?)[.!?]*$", re.I)

EXTRACT_PROMPT = """You maintain a personal assistant's long-term memory about its user, Nikesh.
From the exchange below, extract only DURABLE facts that Nikesh himself stated about his own life:
plans, people, preferences, projects, decisions, dates, places. Ignore questions, small talk,
one-off requests, and anything the assistant said.
NEVER store: health or medical details, financial account/card/ID numbers, passwords, PINs, OTPs.

Existing facts (id: text):
{existing}

Reply with ONLY a JSON array (no prose). Each item is one of:
  {{"op": "add", "text": "<fact in third person, e.g. 'Accepted the Deloitte offer'>", "category": "<career|people|preferences|plans|projects|places|hobbies|general>"}}
  {{"op": "update", "id": "<existing id that is now outdated>", "text": "<the new fact>"}}
If there is nothing durable and new, reply [].

Nikesh said: {user}
Assistant replied: {assistant}"""


def worth_checking(user_text: str) -> bool:
    """Cheap gate so we don't spend a model call on 'what's the weather'."""
    text = user_text.strip()
    if len(text) < 12 or len(text.split()) < 4:
        return False
    if text.endswith("?") and not re.search(r"\b(i'm|i am|my)\b", text, re.I):
        return False
    return bool(FIRST_PERSON.search(text) and SIGNAL.search(text))


def handle_forget(user_text: str) -> dict | None:
    """Voice 'forget that' / 'forget everything about X'. Returns a result dict or None."""
    text = user_text.strip()
    m = FORGET_ALL.search(text)
    if m:
        removed = facts.forget(m.group(1))
        return {"forgot": [f["text"] for f in removed], "about": m.group(1)}
    if FORGET_THAT.search(text):
        last = facts.forget_last()
        return {"forgot": [last["text"]] if last else [], "about": "that"}
    m = FORGET_X.search(text)
    if m and re.match(r"^\s*(please\s+)?(jarvis|friday|robin)?[, ]*(please\s+)?forget\b", text, re.I):
        removed = facts.forget(m.group(1))
        if removed:
            return {"forgot": [f["text"] for f in removed], "about": m.group(1)}
    return None


def parse_ops(raw: str) -> list[dict]:
    match = re.search(r"\[.*\]", raw or "", re.S)
    if not match:
        return []
    try:
        ops = json.loads(match.group(0))
    except ValueError:
        return []
    return [op for op in ops if isinstance(op, dict) and op.get("op") in ("add", "update")]


def apply_ops(ops: list[dict]) -> list[dict]:
    """Apply extractor output through the same safety rules as everything else."""
    results = []
    for op in ops[:5]:
        text = str(op.get("text", "")).strip()
        if not text:
            continue
        if op["op"] == "update" and op.get("id"):
            res = facts.update(str(op["id"]), text)
            if res["status"] == "missing":
                res = facts.add(text, op.get("category", "general"), source="learned")
        else:
            # a changed fact that the extractor did not link: replace a near-duplicate subject
            res = facts.add(text, op.get("category", "general"), source="learned")
        results.append(res)
    return results


async def learn(user_text: str, assistant_text: str, extractor=None) -> list[dict]:
    """extractor: async (prompt) -> str. Defaults to a one-shot Haiku call via the Agent SDK."""
    if not worth_checking(user_text):
        return []
    if facts.sensitive_reason(user_text) and len(user_text) < 160:
        return []
    existing = "\n".join(f"{f['id']}: {f['text']}" for f in facts.search(user_text, 12)) or "(none)"
    prompt = EXTRACT_PROMPT.format(existing=existing, user=user_text[:1500], assistant=assistant_text[:600])
    if extractor is None:
        from ..crew import one_shot
        extractor = lambda p: one_shot(p, model="haiku")  # noqa: E731
    try:
        raw = await extractor(prompt)
    except Exception:
        return []
    return apply_ops(parse_ops(raw))
