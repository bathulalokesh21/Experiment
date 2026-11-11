"""Learning mode: flashcards with spaced repetition (SM-2), quizzed by voice."""
from __future__ import annotations

import time

from .. import bus, store
from .registry import tool

FILE = "flashcards.json"
DAY = 86400


def _load() -> list[dict]:
    return store.load(FILE, [])


def grade_card(card: dict, grade: int, now: float | None = None) -> dict:
    """SM-2. grade 0-5 (0-2 = forgot, 3 = hard, 4 = good, 5 = easy)."""
    now = now or time.time()
    grade = max(0, min(5, int(grade)))
    if grade < 3:
        card["reps"], card["interval"] = 0, 0
        card["due"] = now + 600  # see it again in ten minutes
    else:
        card["reps"] = card.get("reps", 0) + 1
        if card["reps"] == 1:
            card["interval"] = 1
        elif card["reps"] == 2:
            card["interval"] = 3
        else:
            card["interval"] = round(card.get("interval", 1) * card.get("ease", 2.5))
        card["due"] = now + card["interval"] * DAY
    card["ease"] = max(1.3, card.get("ease", 2.5) + 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
    card["last"] = now
    return card


def summary() -> dict:
    cards, now = _load(), time.time()
    decks: dict[str, dict] = {}
    for c in cards:
        d = decks.setdefault(c["deck"], {"total": 0, "due": 0})
        d["total"] += 1
        d["due"] += 1 if c["due"] <= now else 0
    return {"decks": decks, "total": len(cards), "due": sum(d["due"] for d in decks.values())}


def due_cards(deck: str = "", limit: int = 5) -> list[dict]:
    now = time.time()
    cards = [c for c in _load() if c["due"] <= now and (not deck or c["deck"].lower() == deck.lower())]
    return sorted(cards, key=lambda c: c["due"])[:limit]


def grade(card_id: str, value: int) -> dict | None:
    cards = _load()
    card = next((c for c in cards if c["id"] == card_id), None)
    if card:
        grade_card(card, value)
        store.save(FILE, cards)
        bus.publish("flashcards", summary=summary())
    return card


@tool("flashcards_create", "Create flashcards in a deck (from a topic, or from his file after search_knowledge). "
      "cards is a list of {\"q\": question, \"a\": answer}.", {"deck": "str: deck name", "cards": "list: [{q, a}]"},
      chip="Making flashcards", family="learn")
def flashcards_create(deck: str, cards: list):
    items, added = _load(), 0
    for c in (cards or [])[:60]:
        if isinstance(c, dict) and c.get("q") and c.get("a"):
            items.append({"id": store.new_id("k_"), "deck": deck.strip(), "q": str(c["q"]), "a": str(c["a"]),
                          "reps": 0, "interval": 0, "ease": 2.5, "due": time.time(), "last": 0})
            added += 1
    if not added:
        return "No valid cards. Each card needs q and a."
    store.save(FILE, items)
    bus.publish("flashcards", summary=summary())
    return f"Created {added} cards in '{deck}'. They're due now."


@tool("flashcards_due", "Get the next due flashcards to quiz him by voice. Ask ONE question at a time, wait for his "
      "answer, then grade it with flashcards_grade.", optional={"deck": "str: deck name", "limit": "int: default 5"},
      chip="Picking your cards", family="learn")
def flashcards_due(deck: str = "", limit: int = 5):
    cards = due_cards(deck, int(limit or 5))
    if not cards:
        return "No cards are due. " + (f"{summary()['total']} cards in total." if summary()["total"] else "No decks yet.")
    return "\n".join(f"id={c['id']} | deck={c['deck']} | Q: {c['q']} | A: {c['a']}" for c in cards)


def grade_text(card_id: str, grade: int) -> str:
    card = globals()["grade"](card_id, grade)
    if not card:
        return "I couldn't find that card."
    days = card["interval"]
    return f"Graded. Next review {'in ten minutes' if not days else f'in {days} day(s)'}."


tool("flashcards_grade", "Record how well he answered a card: 0-2 forgot, 3 hard, 4 good, 5 easy.",
     {"card_id": "str", "grade": "int: 0-5"}, family="learn")(grade_text)


@tool("flashcards_decks", "List flashcard decks with how many cards are due.", family="learn")
def flashcards_decks():
    s = summary()
    if not s["total"]:
        return "No flashcards yet."
    return "\n".join(f"- {name}: {d['total']} cards, {d['due']} due" for name, d in s["decks"].items())
