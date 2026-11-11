"""profile/me.md + profile/preferences.md: his own description of himself."""
from __future__ import annotations

from .. import config
from . import facts


def read(name: str) -> str:
    path = config.PROFILE / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def me() -> str:
    # unfilled "[FILL]" lines carry no information; don't waste the model's attention on them
    lines = [ln for ln in read("me.md").splitlines() if "[FILL]" not in ln]
    return "\n".join(lines).strip()


def preferences() -> str:
    return read("preferences.md").strip()


def learned_block(limit: int = 25) -> str:
    items = facts.relevant(limit)
    if not items:
        return "(nothing learned yet)"
    return "\n".join(f"- {f['text']}" for f in items)


def context_block() -> str:
    return (
        "## About him (his own profile)\n" + (me() or "(profile/me.md is empty)") +
        "\n\n## How he likes answers\n" + (preferences() or "(no preferences file)") +
        "\n\n## Things you have learned about him so far\n" + learned_block()
    )
