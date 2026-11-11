"""Memory, notes, knowledge files, transcripts, drills."""
from __future__ import annotations

import time
from datetime import datetime

from .. import config, store
from ..memory import facts, search, transcripts
from .registry import tool


@tool("remember", "Save a durable fact about him to long-term memory (he asked you to remember it, or it is "
      "clearly worth keeping). Never health details, account numbers, passwords or OTPs.",
      {"fact": "str: the fact, third person"}, {"category": "str: career|people|preferences|plans|projects|places|hobbies|general"},
      chip="Updating memory", family="memory")
def remember(fact: str, category: str = "general"):
    res = facts.add(fact, category, source="told")
    if res["status"] == "refused":
        return f"I don't store {res['reason']}. Tell him that plainly."
    if res["status"] == "duplicate":
        return "Already in memory."
    return "Saved to memory." if res["status"] == "added" else "Nothing to save."


@tool("recall", "Search what you have learned about him (long-term memory facts).",
      {"query": "str: what to look for"}, chip="Checking memory", family="memory")
def recall(query: str):
    hits = facts.search(query, 8)
    return "\n".join(f"- {f['text']}" for f in hits) if hits else "Nothing in memory about that."


@tool("forget", "Delete everything in long-term memory that mentions a subject (he asked you to forget it).",
      {"subject": "str: what to forget"}, chip="Forgetting", family="memory")
def forget(subject: str):
    removed = facts.forget(subject)
    return f"Forgot {len(removed)} item(s) about {subject}." if removed else f"There was nothing stored about {subject}."


@tool("search_knowledge", "Search his own files (PDF, DOCX, PPTX, CSV, TXT, MD in the knowledge folder). "
      "Returns the best passages with file names. Use for anything about his CV, projects, notes, documents.",
      {"query": "str: what to find"}, chip="Reading your files", family="memory")
def search_knowledge(query: str):
    hits = search.search(query, 4)
    if not hits:
        return "No matching passages in his files."
    return "\n\n".join(f"[{h['file']}]\n{h['text']}" for h in hits)


@tool("list_knowledge", "List the files in his knowledge folder.", family="memory")
def list_knowledge():
    names = [p.name for p in search.files()]
    return "\n".join(names) if names else "The knowledge folder is empty. He can drag files onto the dashboard."


@tool("save_note", "Append a note to his notes file.", {"text": "str: the note"}, chip="Writing a note",
      family="memory")
def save_note(text: str):
    path = config.data("notes.txt")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {text.strip()}\n")
    return "Noted."


@tool("read_notes", "Read his most recent notes.", optional={"count": "int: how many (default 10)"},
      family="memory")
def read_notes(count: int = 10):
    path = config.data("notes.txt")
    if not path.exists():
        return "No notes yet."
    lines = [ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    return "\n".join(lines[-max(1, int(count)):]) or "No notes yet."


@tool("save_link", "Save a web link with a short label to his second brain.",
      {"url": "str: the link", "label": "str: what it is"}, chip="Saving the link", family="memory")
def save_link(url: str, label: str):
    links = store.load("links.json", [])
    links.append({"url": url.strip(), "label": label.strip(), "saved": time.time()})
    store.save("links.json", links)
    with config.data("knowledge", "saved_links.md").open("a", encoding="utf-8") as fh:
        fh.write(f"- {label.strip()}: {url.strip()} (saved {datetime.now().strftime('%Y-%m-%d')})\n")
    return "Link saved."


@tool("search_conversations", "Search past conversations with the crew (transcripts are saved per day).",
      {"query": "str: words to find"}, {"days": "int: how far back (default 30)", "who": "str: jarvis|friday|robin|nikesh"},
      chip="Searching our conversations", family="memory")
def search_conversations(query: str, days: int = 30, who: str = ""):
    hits = transcripts.search(query, int(days or 30), who or "")
    if not hits:
        return "Nothing found in the saved conversations."
    return "\n".join(f"{h['day']} {h['t']} {h.get('persona') or h['who']}: {h['text'][:300]}" for h in hits)


@tool("log_drill", "Log an interview-drill result (type, question, score out of 10, feedback).",
      {"kind": "str: cv|guesstimate|case|hr", "question": "str", "score": "int: 0-10", "feedback": "str"},
      chip="Logging the drill", family="memory")
def log_drill(kind: str, question: str, score: int, feedback: str):
    drills = store.load("memory/drills.json", [])
    drills.append({"t": time.time(), "kind": kind, "question": question, "score": int(score), "feedback": feedback})
    store.save("memory/drills.json", drills)
    return "Drill logged."


@tool("drill_history", "Recent interview-drill results and average score.", family="memory")
def drill_history():
    drills = store.load("memory/drills.json", [])
    if not drills:
        return "No drills logged yet."
    avg = sum(d["score"] for d in drills) / len(drills)
    last = "\n".join(f"- {d['kind']}: {d['score']}/10, {d['feedback'][:120]}" for d in drills[-5:])
    return f"{len(drills)} drills, average {avg:.1f}/10.\n{last}"
