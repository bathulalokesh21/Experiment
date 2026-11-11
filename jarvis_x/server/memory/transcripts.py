"""Conversation history: one JSONL file per day, searchable."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from .. import config


def _path(day: str):
    return config.data("transcripts", f"{day}.jsonl")


def log(who: str, text: str, persona: str = "", when: datetime | None = None) -> None:
    text = (text or "").strip()
    if not text:
        return
    when = when or datetime.now()
    path = _path(when.strftime("%Y-%m-%d"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": when.strftime("%H:%M:%S"), "who": who, "persona": persona,
                             "text": text}, ensure_ascii=False) + "\n")


def read_day(day: str | None = None) -> list[dict]:
    day = day or datetime.now().strftime("%Y-%m-%d")
    path = _path(day)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
            item["day"] = day
            out.append(item)
        except ValueError:
            continue
    return out


def search(query: str, days: int = 30, who: str = "", limit: int = 8) -> list[dict]:
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    today = datetime.now().date()
    hits = []
    for back in range(max(1, days)):
        day = (today - timedelta(days=back)).strftime("%Y-%m-%d")
        for item in read_day(day):
            if who and who.lower() not in (item.get("who", "") + " " + item.get("persona", "")).lower():
                continue
            low = item["text"].lower()
            score = sum(1 for w in words if w in low)
            if score and (score >= max(1, len(words) // 2)):
                hits.append((score, day, item))
    hits.sort(key=lambda h: (-h[0], h[1]), reverse=False)
    hits.sort(key=lambda h: (-h[0], -int(h[1].replace("-", ""))))
    return [h[2] for h in hits[:limit]]


def recent(limit: int = 30) -> list[dict]:
    return read_day()[-limit:]


def days_with_data() -> list[str]:
    root = config.data("transcripts")
    return sorted((p.stem for p in root.glob("*.jsonl")), reverse=True) if root.exists() else []
