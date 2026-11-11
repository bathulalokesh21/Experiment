"""Daily life: morning brief, day recap, guitar, comic studio, expenses, journal,
work co-pilot frameworks, routines."""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta

from .. import bus, gmail, routines, store, widgets
from ..memory import transcripts
from . import tasks
from .registry import tool

# ------------------------------------------------------------------ brief / recap

LEARN_TODAY = [
    "The Pyramid Principle: lead with the answer, then group supporting arguments in threes.",
    "Pentatonic box 1 in A minor: the backbone of Gilmour-style solos. Five minutes of bends on the G string.",
    "MECE test: can any item be moved to another bucket? If yes, the buckets overlap.",
    "Palm muting: rest the side of your picking hand on the bridge; it's what gives rock rhythm its chug.",
    "Kotter's 8 steps start with urgency, not vision. Most change programmes skip step one.",
    "A good comic page ends on a question so the reader has to turn it.",
    "The 'so what?' test: every slide title should survive being asked 'so what?' twice.",
    "Power chords use only root and fifth, which is why they stay clean under distortion.",
    "In OCM, resistance is data: map who loses what before you write the comms plan.",
    "Worldbuilding rule: decide what your world's scarcest resource is; plots grow from scarcity.",
    "Alternate picking with a metronome at 60 bpm beats sloppy playing at 120.",
    "RACI gotcha: exactly one 'A' per row. Two accountable people means nobody is.",
    "Issue trees beat frameworks: start from the client's question, not from Porter.",
    "Thumbnail your comic pages at stamp size first; composition problems show up early.",
]


def learn_today(day: datetime | None = None) -> str:
    day = day or datetime.now()
    return LEARN_TODAY[day.timetuple().tm_yday % len(LEARN_TODAY)]


async def brief_data() -> dict:
    snap = tasks.snapshot()
    today = datetime.now().date()
    todays = [r for r in snap["reminders"] if datetime.fromisoformat(r["due"]).date() == today]
    weather = await widgets.weather()
    news = await widgets.headlines_mix(per_topic=1)
    mail = []
    if gmail.connected():
        try:
            mail = gmail.search("is:unread is:important newer_than:2d", 3)
        except Exception:
            mail = []
    return {"date": datetime.now().strftime("%A, %d %B"), "weather": weather, "reminders": todays,
            "tasks": snap["tasks"][:6], "mail": mail, "headlines": news["items"][:3], "learn": learn_today(),
            "chord": chord_today()}


def brief_text(d: dict) -> str:
    w = d["weather"]
    lines = [f"Date: {d['date']}"]
    lines.append(f"Weather: {w['city']} {w['temp']}°C, {w['desc']}. {w['rain']}" if w.get("ok")
                 else "Weather: unavailable right now.")
    lines.append("Reminders today: " + ("; ".join(f"{r['text']} ({r['when']})" for r in d["reminders"]) or "none"))
    lines.append("Open tasks: " + ("; ".join(t["text"] for t in d["tasks"]) or "none"))
    if d["mail"]:
        lines.append("Important unread mail: " + "; ".join(f"{m['from'].split('<')[0].strip()}: {m['subject']}" for m in d["mail"]))
    lines.append("Headlines: " + ("; ".join(h["title"] for h in d["headlines"]) or "unavailable"))
    lines.append("One thing to learn today: " + d["learn"])
    lines.append(f"Guitar chord of the day: {d['chord']['name']}")
    return "\n".join(lines)


@tool("morning_brief", "Everything for his morning brief: weather + rain advice, today's reminders and tasks, important "
      "unread mail, 3 headlines, one thing to learn. Then deliver it in your own voice, short.",
      chip="Preparing your brief", family="daily")
async def morning_brief():
    return brief_text(await brief_data())


def recap_data() -> dict:
    snap = tasks.snapshot()
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    lines = transcripts.read_day()
    asked = [ln["text"] for ln in lines if ln["who"] == "nikesh"]
    practice = [p for p in store.load("guitar.json", {"sessions": []})["sessions"]
                if datetime.fromtimestamp(p["t"]).date() == today]
    spent = [e for e in store.load("expenses.json", []) if datetime.fromtimestamp(e["t"]).date() == today]
    focus = [f for f in store.load("focus.json", []) if datetime.fromtimestamp(f["t"]).date() == today]
    return {"done": [t["text"] for t in snap["done_today"]], "pending": [t["text"] for t in snap["tasks"]],
            "tomorrow": [r for r in snap["reminders"] if datetime.fromisoformat(r["due"]).date() == tomorrow],
            "asked": asked[-12:], "exchanges": len(asked), "guitar_minutes": sum(p["minutes"] for p in practice),
            "spent": sum(e["amount"] for e in spent), "focus_minutes": sum(f["minutes"] for f in focus)}


@tool("day_recap", "Data for an end-of-day recap ('how was my day?'): what he did, what's pending, what's tomorrow.",
      chip="Looking back at your day", family="daily")
def day_recap():
    d = recap_data()
    return "\n".join([
        "Completed today: " + ("; ".join(d["done"]) or "nothing ticked off"),
        "Still pending: " + ("; ".join(d["pending"]) or "nothing"),
        "Tomorrow: " + ("; ".join(f"{r['text']} ({r['when']})" for r in d["tomorrow"]) or "nothing scheduled"),
        f"Focus time: {d['focus_minutes']} min. Guitar: {d['guitar_minutes']} min. Spent: ₹{d['spent']:.0f}.",
        f"He talked to the crew {d['exchanges']} times. Recent topics: " + ("; ".join(a[:70] for a in d["asked"][-6:]) or "none"),
    ])


# ------------------------------------------------------------------ guitar

CHORDS = [
    {"name": "E minor", "frets": "022000", "tip": "Two fingers. Strum all six strings; the darkest open chord."},
    {"name": "A minor", "frets": "x02210", "tip": "Skip the low E. Same shape as E major moved one string down."},
    {"name": "G major", "frets": "320003", "tip": "The 'Wish You Were Here' home chord. Keep the ring finger anchored."},
    {"name": "C major", "frets": "x32010", "tip": "Arch your fingers so the open G and high E ring."},
    {"name": "D major", "frets": "xx0232", "tip": "Strum only the top four strings."},
    {"name": "E major", "frets": "022100", "tip": "Add one finger to E minor. The base shape for barre chords."},
    {"name": "A major", "frets": "x02220", "tip": "Three fingers in one fret; try barring with one finger."},
    {"name": "D minor", "frets": "xx0231", "tip": "Sad cousin of D. Top four strings only."},
    {"name": "E5 power chord", "frets": "022xxx", "tip": "Root + fifth. Palm mute it and you have rock rhythm."},
    {"name": "A5 power chord", "frets": "x022xx", "tip": "Move the E5 shape down a string. Try E5 → A5 with a metronome at 80."},
    {"name": "F major (barre)", "frets": "133211", "tip": "The wall every guitarist hits. Roll the index finger slightly onto its edge."},
    {"name": "Em7", "frets": "022033", "tip": "The 'Wish You Were Here' intro voicing: keep fingers 3 and 4 planted."},
    {"name": "A7sus4", "frets": "x02030", "tip": "Also from 'Wish You Were Here'. Tiny move from Em7."},
    {"name": "Dsus2", "frets": "xx0230", "tip": "Lift a finger off D. Great for Audioslave-style open riffs."},
    {"name": "B minor (barre)", "frets": "x24432", "tip": "A minor shape with a barre on fret 2."},
    {"name": "Cadd9", "frets": "x32033", "tip": "Pairs with G and Em7 without moving fingers 3 and 4."},
]


def chord_today(day: datetime | None = None) -> dict:
    day = day or datetime.now()
    return CHORDS[day.timetuple().tm_yday % len(CHORDS)]


def guitar_stats() -> dict:
    sessions = store.load("guitar.json", {"sessions": []})["sessions"]
    now = datetime.now()
    week = [s for s in sessions if now.timestamp() - s["t"] < 7 * 86400]
    days = {datetime.fromtimestamp(s["t"]).date() for s in sessions}
    streak, day = 0, now.date()
    if day not in days:
        day -= timedelta(days=1)
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    last = max((s["t"] for s in sessions), default=0)
    return {"sessions": len(sessions), "week_minutes": sum(s["minutes"] for s in week), "streak": streak,
            "days_since": int((now.timestamp() - last) // 86400) if last else None, "last": last}


def log_guitar(minutes: float, notes: str = "") -> dict:
    data = store.load("guitar.json", {"sessions": []})
    data["sessions"].append({"t": time.time(), "minutes": round(float(minutes), 1), "notes": notes})
    store.save("guitar.json", data)
    bus.publish("guitar", stats=guitar_stats())
    return guitar_stats()


@tool("chord_of_the_day", "Today's guitar chord with fingering (low E to high E) and a practice tip.", family="guitar")
def chord_of_the_day():
    c = chord_today()
    return f"{c['name']}: frets {c['frets']} (low E to high E, x = don't play). {c['tip']}"


@tool("log_practice", "Log a guitar practice session.", {"minutes": "float: how long"}, {"notes": "str: what he worked on"},
      chip="Logging practice", family="guitar")
def log_practice(minutes: float, notes: str = ""):
    s = log_guitar(minutes, notes)
    return f"Logged {minutes} minutes. This week: {s['week_minutes']:.0f} minutes, streak {s['streak']} day(s)."


@tool("practice_stats", "His guitar practice stats: this week's minutes, streak, days since last session.", family="guitar")
def practice_stats():
    s = guitar_stats()
    if not s["sessions"]:
        return "No practice logged yet."
    return f"{s['week_minutes']:.0f} minutes this week, {s['streak']}-day streak, last session {s['days_since']} day(s) ago."


# ------------------------------------------------------------------ comic studio

COMIC_SECTIONS = ["world", "characters", "timeline", "scripts", "ideas"]


def comic_bible() -> dict:
    bible = store.load("comic/bible.json", {})
    for section in COMIC_SECTIONS:
        bible.setdefault(section, [])
    bible.setdefault("title", "Untitled post-apocalyptic comic")
    return bible


@tool("comic_read", "Read the story bible of his original post-apocalyptic sci-fi comic. section: all, world, "
      "characters, timeline, scripts, ideas. ALWAYS read before adding, so the canon stays consistent.",
      optional={"section": "str: default all"}, chip="Opening the story bible", family="comic")
def comic_read(section: str = "all"):
    bible = comic_bible()
    wanted = COMIC_SECTIONS if section in ("", "all") else [s for s in COMIC_SECTIONS if s.startswith(section.lower()[:4])]
    out = [f"# {bible['title']}"]
    for sec in wanted:
        out.append(f"\n## {sec.title()}")
        out.extend(f"- [{e['id']}] {e['title']}: {e['text']}" for e in bible[sec]) if bible[sec] else out.append("(empty)")
    return "\n".join(out)


@tool("comic_write", "Add or update an entry in the comic story bible. Pass entry_id to update an existing entry. "
      "If the new entry contradicts canon, tell him instead of silently overwriting.",
      {"section": "str: world|characters|timeline|scripts|ideas", "title": "str: entry name", "text": "str: the content"},
      {"entry_id": "str: id to update", "comic_title": "str: set the comic's title"}, chip="Writing to the story bible",
      family="comic")
def comic_write(section: str, title: str, text: str, entry_id: str = "", comic_title: str = ""):
    bible = comic_bible()
    sec = next((s for s in COMIC_SECTIONS if s.startswith(section.lower()[:4])), None)
    if not sec:
        return "Sections are: " + ", ".join(COMIC_SECTIONS)
    if comic_title:
        bible["title"] = comic_title
    entry = next((e for e in bible[sec] if e["id"] == entry_id), None) if entry_id else \
        next((e for e in bible[sec] if e["title"].lower() == title.lower()), None)
    if entry:
        entry.update(title=title, text=text, updated=time.time())
        verb = "Updated"
    else:
        bible[sec].append({"id": store.new_id("c_"), "title": title, "text": text, "updated": time.time()})
        verb = "Added"
    store.save("comic/bible.json", bible)
    bus.publish("comic", counts={s: len(bible[s]) for s in COMIC_SECTIONS}, title=bible["title"])
    return f"{verb} '{title}' in {sec}."


# ------------------------------------------------------------------ expenses

CATEGORIES = {
    "food": "lunch dinner breakfast snack snacks food coffee tea chai maggi biryani pizza swiggy zomato canteen mess restaurant cafe momos",
    "travel": "cab uber ola auto bus train flight taxi fuel petrol metro rapido ticket travel",
    "shopping": "clothes shirt shoes amazon flipkart myntra shopping headphones gadget",
    "music": "guitar strings string pick picks capo amp pedal",
    "study": "book books course udemy printout print stationery exam certification",
    "bills": "recharge wifi rent electricity bill subscription netflix spotify",
    "fun": "movie game party outing trip anime manga comic",
    "health": "gym protein pharmacy",
}


def categorise(text: str) -> str:
    words = set(re.findall(r"[a-z]+", text.lower()))
    for cat, keys in CATEGORIES.items():
        if words & set(keys.split()):
            return cat
    return "other"


def parse_expense(text: str):
    """'200 on lunch', 'spent 1,250 for guitar strings', 'lunch 180' -> (amount, what)."""
    m = re.search(r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?\b", text, re.I)
    if not m:
        return None
    amount = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
    rest = (text[:m.start()] + " " + text[m.end():]).strip()
    rest = re.sub(r"^\s*(i\s+)?(spent|paid|log|add|bought)\b", "", rest, flags=re.I)
    rest = re.sub(r"\b(rupees|rs|bucks|on|for|at|spent|paid)\b", " ", rest, flags=re.I)
    what = re.sub(r"\s+", " ", rest).strip(" .,") or "something"
    return amount, what


def expense_summary_data(month: str | None = None) -> dict:
    month = month or datetime.now().strftime("%Y-%m")
    items = [e for e in store.load("expenses.json", []) if datetime.fromtimestamp(e["t"]).strftime("%Y-%m") == month]
    cats: dict[str, float] = {}
    for e in items:
        cats[e["category"]] = cats.get(e["category"], 0) + e["amount"]
    today = datetime.now().date()
    return {"month": month, "total": sum(e["amount"] for e in items), "count": len(items),
            "categories": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
            "today": sum(e["amount"] for e in items if datetime.fromtimestamp(e["t"]).date() == today),
            "recent": items[-5:][::-1]}


def add_expense(amount: float, what: str, category: str = "") -> dict:
    items = store.load("expenses.json", [])
    entry = {"id": store.new_id("e_"), "t": time.time(), "amount": round(float(amount), 2), "what": what.strip(),
             "category": (category or categorise(what)).lower()}
    items.append(entry)
    store.save("expenses.json", items)
    bus.publish("expenses", summary=expense_summary_data())
    return entry


@tool("expense_add", "Log money he spent ('200 on lunch'). Local only.", {"amount": "float: rupees", "what": "str: on what"},
      {"category": "str: food|travel|shopping|music|study|bills|fun|health|other"}, chip="Logging the expense",
      family="expenses")
def expense_add(amount: float, what: str, category: str = ""):
    e = add_expense(amount, what, category)
    s = expense_summary_data()
    return f"Logged ₹{e['amount']:.0f} on {e['what']} ({e['category']}). This month so far: ₹{s['total']:.0f}."


@tool("expense_summary", "Spending summary for a month (default this month) by category.",
      optional={"month": "str: YYYY-MM"}, family="expenses")
def expense_summary(month: str = ""):
    s = expense_summary_data(month or None)
    if not s["count"]:
        return f"No expenses logged for {s['month']}."
    cats = ", ".join(f"{c} ₹{v:.0f}" for c, v in s["categories"].items())
    return f"{s['month']}: ₹{s['total']:.0f} across {s['count']} entries. {cats}. Today: ₹{s['today']:.0f}."


@tool("expense_undo", "Remove the most recent expense entry (logged by mistake).", family="expenses")
def expense_undo():
    items = store.load("expenses.json", [])
    if not items:
        return "There's nothing to undo."
    last = items.pop()
    store.save("expenses.json", items)
    bus.publish("expenses", summary=expense_summary_data())
    return f"Removed ₹{last['amount']:.0f} on {last['what']}."


# ------------------------------------------------------------------ work co-pilot

FRAMEWORKS = {
    "pyramid principle": "Answer first → 3 supporting arguments (MECE) → evidence under each. Title every slide with the 'so what'.",
    "issue tree": "Key question → 2-4 MECE sub-questions → hypotheses → analyses needed → data sources. Prioritise by impact x ease.",
    "profitability": "Profit = Revenue (price x volume, by segment/product/channel) - Cost (fixed vs variable). Find which branch moved, then why (internal vs market).",
    "market entry": "Market (size, growth, profit pools) → Customer → Competition → Company capabilities → Entry mode (build/buy/partner) → Risks → Financial case.",
    "3c": "Company, Customers, Competitors. Add Collaborators and Context for 5C.",
    "4p": "Product, Price, Place, Promotion.",
    "porter five forces": "Rivalry, new entrants, substitutes, supplier power, buyer power → industry attractiveness.",
    "swot": "Strengths/Weaknesses (internal), Opportunities/Threats (external). Finish with 'so what' actions, not a list.",
    "ansoff": "Existing/new products x existing/new markets: penetration, product development, market development, diversification.",
    "ge mckinsey": "Industry attractiveness x competitive strength, 3x3: invest/grow, selective, harvest/divest.",
    "raci": "Responsible, Accountable (exactly one), Consulted, Informed, per deliverable.",
    "adkar": "Change at the individual level: Awareness, Desire, Knowledge, Ability, Reinforcement. Diagnose the first weak link.",
    "kotter": "Urgency → coalition → vision → communicate → remove obstacles → short-term wins → build on change → anchor in culture.",
    "stakeholder map": "Power x interest grid: manage closely, keep satisfied, keep informed, monitor. Add current vs desired stance.",
    "star": "Situation, Task, Action, Result. Spend 60% on Action, quantify the Result.",
    "meeting prep": "Purpose (decision needed?) → attendees and what each wants → 3 key messages → likely objections + answers → the ask → next steps.",
    "status update": "Headline (RAG status) → done since last update → next up → risks/blockers with owner → decisions needed.",
    "first 90 days": "Days 1-30 learn (people, process, tools, expectations); 31-60 contribute (one visible quick win); 61-90 own (a workstream). Weekly: what I learned, who I met, what I'd do differently.",
    "bcg matrix": "Market growth x relative share: stars, cash cows, question marks, dogs.",
    "mece": "Mutually exclusive, collectively exhaustive. Test: no overlaps, no gaps.",
    "rice": "Reach x Impact x Confidence / Effort, for prioritising product work.",
    "brd": "Background → objectives → scope (in/out) → stakeholders → current vs future process → functional and non-functional requirements → assumptions → acceptance criteria.",
}


@tool("framework", "Fetch a consulting/PM framework scaffold by name (pyramid principle, issue tree, profitability, market "
      "entry, ADKAR, Kotter, RACI, stakeholder map, meeting prep, status update, first 90 days, RICE, BRD ...). "
      "Call with 'list' to see all.", {"name": "str"}, family="copilot")
def framework(name: str):
    key = name.strip().lower()
    if key in ("list", "all", ""):
        return "Frameworks: " + ", ".join(sorted(FRAMEWORKS))
    hit = FRAMEWORKS.get(key) or next((v for k, v in FRAMEWORKS.items() if key in k or k in key), None)
    return hit or ("Not in the library. Available: " + ", ".join(sorted(FRAMEWORKS)))


@tool("journal_add", "Add an entry to his work/learning journal ('what I learned today', first-90-days notes).",
      {"text": "str: the entry"}, {"tag": "str: learned|met|win|idea|note"}, chip="Writing your journal", family="copilot")
def journal_add(text: str, tag: str = "learned"):
    items = store.load("journal.json", [])
    items.append({"t": time.time(), "text": text.strip(), "tag": (tag or "learned").lower()})
    store.save("journal.json", items)
    return "Added to your journal."


@tool("journal_review", "Read journal entries from the last N days for a weekly reflection.",
      optional={"days": "int: default 7"}, chip="Reading your journal", family="copilot")
def journal_review(days: int = 7):
    cutoff = time.time() - int(days or 7) * 86400
    items = [j for j in store.load("journal.json", []) if j["t"] >= cutoff]
    if not items:
        return "No journal entries in that period."
    return "\n".join(f"{datetime.fromtimestamp(j['t']).strftime('%a %d %b')} [{j['tag']}] {j['text']}" for j in items)


# ------------------------------------------------------------------ routines

@tool("routine_save", "Create or replace a named routine he defines ('when I say good night: ...'). steps is a list of "
      "objects, each ONE of: {\"say\": \"text to speak\"}, {\"ask\": \"a request for the crew to answer aloud\"}, "
      "{\"tool\": \"tool_name\", \"args\": {...}}, {\"ui\": \"dashboard action\", \"value\": \"...\"}.",
      {"name": "str: routine name", "trigger": "str: the phrase that starts it", "steps": "list: the steps"},
      chip="Saving the routine", family="routines")
def routine_save(name: str, trigger: str, steps: list):
    try:
        r = routines.save(name, trigger, steps)
    except ValueError as exc:
        return f"Not saved: {exc}"
    return f"Routine '{r['name']}' saved with {len(r['steps'])} steps. Trigger: '{r['trigger']}'."


@tool("routine_run", "Run one of his routines by name (Good morning, Good night, Focus mode, Party, or his own).",
      {"name": "str"}, chip="Running the routine", family="routines")
async def routine_run(name: str):
    res = await routines.run(name)
    return res["message"]


@tool("routine_list", "List his routines and their trigger phrases.", family="routines")
def routine_list():
    return "\n".join(f"- {r['name']} (say: '{r['trigger']}', {len(r['steps'])} steps)" for r in routines.all_routines())


@tool("routine_delete", "Delete one of his own routines.", {"name": "str"}, family="routines")
def routine_delete(name: str):
    return "Deleted." if routines.delete(name) else "No routine with that name (built-ins can't be deleted, only edited)."
