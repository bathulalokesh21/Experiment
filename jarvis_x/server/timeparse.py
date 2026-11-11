"""Natural-language times for reminders: "in 2 minutes", "tomorrow at 9",
"every day at 7 am", "on friday 6pm", "2026-11-20 14:30"."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "forty five": 45, "forty-five": 45, "half an": 0.5, "sixty": 60, "ninety": 90,
}
UNIT_SECONDS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600,
                "day": 86400, "week": 604800}
PART_OF_DAY = {"morning": 9, "afternoon": 15, "evening": 18, "tonight": 21, "night": 21, "noon": 12,
               "midnight": 0}


def _clock(text: str):
    """Find a clock time. Returns (hour, minute) or None."""
    m = re.search(r"\b(\d{1,2})[:.](\d{2})\s*(am|pm|a\.m\.|p\.m\.)?", text)
    if m:
        hour, minute, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").replace(".", "")
    else:
        m = re.search(r"\b(\d{1,2})\s*(am|pm|a\.m\.|p\.m\.)", text) or \
            re.search(r"\bat\s+(\d{1,2})\b(?!\s*(?:min|hour|sec|day))", text)
        if not m:
            return None
        hour, minute = int(m.group(1)), 0
        ap = (m.group(2) if m.lastindex and m.lastindex >= 2 else "") or ""
        ap = ap.replace(".", "")
    if ap == "pm" and hour < 12:
        hour += 12
    if ap == "am" and hour == 12:
        hour = 0
    if not ap and 1 <= hour <= 6 and re.search(r"evening|afternoon|tonight|night", text):
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def parse_repeat(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\bevery\s+(week\s?day|working day)", t) or "on weekdays" in t:
        return "weekdays"
    if re.search(r"\b(every\s?day|daily|each day|every (morning|evening|night))\b", t):
        return "daily"
    if re.search(r"\b(every week|weekly)\b", t):
        return "weekly"
    if re.search(r"\b(every hour|hourly)\b", t):
        return "hourly"
    for day in WEEKDAYS:
        if re.search(rf"\bevery {day}\b", t):
            return "weekly"
    m = re.search(r"\bevery (\d+) (minute|min|hour)s?\b", t)
    if m:
        return f"every:{int(m.group(1)) * (60 if m.group(2).startswith('h') else 1)}"
    return None


def parse_when(text: str, now: datetime | None = None):
    """Returns (datetime | None, repeat | None). datetime is naive local time."""
    now = now or datetime.now()
    t = " " + text.lower().strip() + " "
    repeat = parse_repeat(t)

    # ISO / explicit numeric date
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:[t ](\d{1,2}):(\d{2}))?", t)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            int(m.group(4) or 9), int(m.group(5) or 0)), repeat
        except ValueError:
            return None, repeat

    # relative: "in 2 minutes", "in half an hour", "after 10 mins", "in an hour and a half"
    m = re.search(r"\b(?:in|after)\s+(\d+(?:\.\d+)?|half an|forty[- ]five|[a-z]+)\s*"
                  r"(second|sec|minute|min|hour|hr|day|week)s?\b", t)
    if m:
        raw = m.group(1)
        qty = float(raw) if re.match(r"\d", raw) else NUMBER_WORDS.get(raw)
        if qty is not None:
            delta = timedelta(seconds=qty * UNIT_SECONDS[m.group(2)])
            if "and a half" in t:
                delta += timedelta(seconds=0.5 * UNIT_SECONDS[m.group(2)])
            return (now + delta).replace(microsecond=0), repeat

    clock = _clock(t)
    base = None
    if "day after tomorrow" in t:
        base = now + timedelta(days=2)
    elif "tomorrow" in t:
        base = now + timedelta(days=1)
    elif "today" in t or "tonight" in t or "this evening" in t or "this afternoon" in t:
        base = now
    else:
        for i, day in enumerate(WEEKDAYS):
            if re.search(rf"\b{day}\b", t):
                ahead = (i - now.weekday()) % 7
                if ahead == 0 and (clock is None or (clock[0], clock[1]) <= (now.hour, now.minute)):
                    ahead = 7
                if "next " + day in t and ahead < 7 and ahead <= 1:
                    ahead += 7
                base = now + timedelta(days=ahead)
                break
    if base is None:
        m = re.search(r"\bnext week\b", t)
        if m:
            base = now + timedelta(days=7)

    if clock is None:
        for word, hour in PART_OF_DAY.items():
            if re.search(rf"\b{word}\b", t):
                clock = (hour, 0)
                break

    if base is None and clock is None:
        return None, repeat
    if base is None:
        base = now
        candidate = base.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate, repeat
    if clock is None:
        clock = (9, 0)
    return base.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0), repeat


def next_occurrence(due: datetime, repeat: str, now: datetime) -> datetime:
    step = {"daily": timedelta(days=1), "weekly": timedelta(days=7), "hourly": timedelta(hours=1),
            "weekdays": timedelta(days=1)}.get(repeat)
    if repeat.startswith("every:"):
        step = timedelta(minutes=max(1, int(repeat.split(":")[1])))
    if step is None:
        return due
    nxt = due + step
    while nxt <= now or (repeat == "weekdays" and nxt.weekday() >= 5):
        nxt += step
    return nxt


def friendly(dt: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now()
    days = (dt.date() - now.date()).days
    clock = dt.strftime("%I:%M %p").lstrip("0")
    if days == 0:
        return f"today at {clock}"
    if days == 1:
        return f"tomorrow at {clock}"
    if 1 < days < 7:
        return f"{dt.strftime('%A')} at {clock}"
    return f"{dt.strftime('%d %b')} at {clock}"
