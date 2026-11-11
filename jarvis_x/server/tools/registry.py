"""Tool registry. Every tool: typed schema, clear description, returns plain
text, and never throws to the model (errors come back as a sentence)."""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field

from .. import bus


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    fn: object
    chip: str = ""
    family: str = "core"
    plugin: str = ""
    meta: dict = field(default_factory=dict)


_tools: dict[str, Tool] = {}

TYPES = {"str": "string", "int": "integer", "float": "number", "bool": "boolean", "list": "array",
         "dict": "object"}


def schema(required: dict | None = None, optional: dict | None = None) -> dict:
    """schema({"text": "str: what to save"}, {"n": "int: how many"}) -> JSON Schema."""
    props, req = {}, []
    for group, is_required in ((required or {}, True), (optional or {}, False)):
        for name, spec in group.items():
            if isinstance(spec, dict):
                props[name] = spec
            else:
                kind, _, desc = spec.partition(":")
                prop = {"type": TYPES.get(kind.strip(), "string")}
                if desc.strip():
                    prop["description"] = desc.strip()
                if prop["type"] == "array":
                    prop["items"] = {}
                props[name] = prop
            if is_required:
                req.append(name)
    return {"type": "object", "properties": props, "required": req}


def tool(name: str, description: str, required: dict | None = None, optional: dict | None = None,
         chip: str = "", family: str = "core"):
    def wrap(fn):
        _tools[name] = Tool(name, description, schema(required, optional), fn, chip, family)
        return fn
    return wrap


def register(t: Tool) -> None:
    _tools[t.name] = t


def unregister_plugin(plugin: str) -> None:
    for name in [n for n, t in _tools.items() if t.plugin == plugin]:
        del _tools[name]


def all_tools() -> list[Tool]:
    return list(_tools.values())


def get(name: str) -> Tool | None:
    return _tools.get(name)


async def call(name: str, args: dict | None = None) -> str:
    """Run a tool. Always returns text."""
    t = _tools.get(name)
    if t is None:
        return f"There is no tool called '{name}'."
    args = dict(args or {})
    for key in t.schema.get("required", []):
        if args.get(key) in (None, ""):
            return f"I need '{key}' to do that."
    if t.chip:
        bus.publish("chip", text=t.chip, tool=name)
    try:
        allowed = set(t.schema.get("properties", {}))
        out = t.fn(**{k: v for k, v in args.items() if k in allowed})
        if inspect.isawaitable(out):
            out = await out
    except Exception as exc:
        return f"That didn't work ({type(exc).__name__}: {exc})."
    if out is None:
        return "Done."
    return out if isinstance(out, str) else str(out)


def load_all() -> None:
    """Import every tool family so their @tool decorators run."""
    from . import (comms, daily, gmail_tools, home, learn, memory_tools, plugins_tools,  # noqa: F401
                   system, tasks, widgets_tools)
