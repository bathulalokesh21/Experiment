"""Long-term fact store: what the crew has learned about him.

Rules baked in here (not left to the model): no health details, no financial
account numbers, no passwords / OTPs. Changed facts replace the old one."""
from __future__ import annotations

import re
import time

from .. import bus, store

FILE = "memory/facts.json"
STOP = set("a an the is are was were be been am i me my mine you your he she it we they to of in on at "
           "for with and or but that this have has had do does did will would can could should "
           "from by as about into than then so not no yes just like really very also".split())

SENSITIVE = [
    (r"\b(password|passcode|passphrase|pin code|otp|one[- ]time (password|code)|cvv|security code)\b", "passwords/OTPs"),
    (r"\b(pin|upi pin|atm pin)\s*(is|:|=)\s*\d{3,}", "passwords/OTPs"),
    (r"\b\d{9,18}\b", "account/card numbers"),
    (r"\b(?:\d[ -]?){13,19}\b", "account/card numbers"),
    (r"\b(account (number|no)|a/c no|ifsc|card number|aadhaar|aadhar|pan (number|card)|ssn)\b", "account/ID numbers"),
    (r"\b(diagnos\w+|medication|prescri\w+|blood pressure|diabet\w+|depress\w+|anxiety|therap(y|ist)|"
     r"illness|disease|surgery|hiv|cancer|asthma|mental health|medical (report|condition|history)|"
     r"blood (test|sugar|report)|symptom\w*|antibiotic\w*|allerg\w+|sick with|suffer\w* from)\b", "health details"),
]


def sensitive_reason(text: str) -> str | None:
    low = text.lower()
    for pattern, reason in SENSITIVE:
        if re.search(pattern, low):
            return reason
    return None


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in STOP and len(w) > 1]


def similarity(a: str, b: str) -> float:
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def all_facts() -> list[dict]:
    return store.load(FILE, [])


def _save(facts: list[dict]) -> None:
    store.save(FILE, facts)


def add(text: str, category: str = "general", source: str = "told") -> dict:
    """Returns {"status": "added"|"duplicate"|"refused"|"empty", "fact": ..., "reason": ...}."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) < 3:
        return {"status": "empty"}
    reason = sensitive_reason(text)
    if reason:
        return {"status": "refused", "reason": reason}
    facts = all_facts()
    for fact in facts:
        if similarity(fact["text"], text) >= 0.8:
            return {"status": "duplicate", "fact": fact}
    fact = {"id": store.new_id("f_"), "text": text[:400], "category": category or "general",
            "source": source, "created": time.time(), "updated": time.time()}
    facts.append(fact)
    _save(facts)
    bus.publish("memory", action="added", fact=fact, text=f"Memory updated: {fact['text']}")
    return {"status": "added", "fact": fact}


def update(fact_id: str, text: str, category: str | None = None) -> dict:
    text = re.sub(r"\s+", " ", text or "").strip()
    reason = sensitive_reason(text)
    if reason:
        return {"status": "refused", "reason": reason}
    facts = all_facts()
    for fact in facts:
        if fact["id"] == fact_id:
            fact["text"] = text[:400]
            if category:
                fact["category"] = category
            fact["updated"] = time.time()
            _save(facts)
            bus.publish("memory", action="updated", fact=fact, text=f"Memory updated: {fact['text']}")
            return {"status": "updated", "fact": fact}
    return {"status": "missing"}


def delete(fact_id: str) -> bool:
    facts = all_facts()
    kept = [f for f in facts if f["id"] != fact_id]
    if len(kept) == len(facts):
        return False
    _save(kept)
    bus.publish("memory", action="deleted", id=fact_id, text="Memory: forgotten.")
    return True


def search(query: str, limit: int = 8) -> list[dict]:
    q = set(tokens(query))
    if not q:
        return sorted(all_facts(), key=lambda f: -f.get("updated", 0))[:limit]
    scored = []
    for fact in all_facts():
        ft = set(tokens(fact["text"] + " " + fact.get("category", "")))
        hit = len(q & ft)
        if not hit and query.lower() in fact["text"].lower():
            hit = 1
        if hit:
            scored.append((hit / (len(q) ** 0.5), fact.get("updated", 0), fact))
    scored.sort(key=lambda s: (-s[0], -s[1]))
    return [s[2] for s in scored[:limit]]


def forget(query: str) -> list[dict]:
    """Delete every fact that mentions the query. Returns what was removed."""
    q = [w for w in tokens(query)]
    if not q:
        return []
    facts = all_facts()
    removed, kept = [], []
    for fact in facts:
        ft = set(tokens(fact["text"]))
        if all(w in ft for w in q) or query.lower().strip() in fact["text"].lower():
            removed.append(fact)
        else:
            kept.append(fact)
    if removed:
        _save(kept)
        bus.publish("memory", action="forgot", count=len(removed),
                    text=f"Memory: forgot {len(removed)} thing{'s' if len(removed) != 1 else ''} about {query}.")
    return removed


def forget_last() -> dict | None:
    facts = all_facts()
    learned = [f for f in facts if f.get("source") in ("learned", "told")]
    if not learned:
        return None
    last = max(learned, key=lambda f: f.get("updated", 0))
    delete(last["id"])
    return last


def relevant(limit: int = 25) -> list[dict]:
    """The facts injected into each assistant at startup: newest first, capped."""
    return sorted(all_facts(), key=lambda f: -f.get("updated", 0))[:limit]


def stats() -> dict:
    facts = all_facts()
    cats: dict[str, int] = {}
    for fact in facts:
        cats[fact.get("category", "general")] = cats.get(fact.get("category", "general"), 0) + 1
    return {"facts": len(facts), "categories": cats,
            "latest": max((f.get("updated", 0) for f in facts), default=0)}
