"""The crew's side of self-upgrading: it can only PROPOSE."""
from __future__ import annotations

from .. import plugins
from .registry import tool

GUIDE = ("Plugin rules: plain Python, imports only from " + ", ".join(sorted(plugins.ALLOWED_IMPORTS)) +
         ". No open(), no network, no shell, no names starting with underscore, no getattr/type. Persist data only "
         "with storage.load(default) / storage.save(obj) (JSON). Define functions that take keyword arguments and "
         "return a string, then TOOLS = [{\"name\": \"snake_case\", \"description\": \"...\", \"schema\": "
         "{\"arg\": \"str: meaning\"}, \"fn\": function}]. Also define test() with asserts that exercise the tools.")


@tool("plugin_propose", "Propose a NEW ability for yourself as a sandboxed plugin when he wishes you could do something "
      "you have no tool for. This only creates an approval card showing a plain-English summary and the code; it is "
      "installed only if HE approves and its tests pass. " + GUIDE,
      {"name": "str: snake_case plugin name", "summary": "str: plain-English description for him", "code": "str: the Python code"},
      chip="Designing a new ability", family="plugins")
def plugin_propose(name: str, summary: str, code: str):
    try:
        plugins.propose(name, summary, code)
    except plugins.PluginError as exc:
        return f"The plugin was rejected by the sandbox check: {exc}. Fix it and propose again."
    except Exception as exc:
        return f"The plugin failed to load ({type(exc).__name__}: {exc}). Fix it and propose again."
    return "The new ability is on an approval card with its code. It is NOT installed until he approves."


@tool("plugin_list", "List installed plugins (abilities added after approval).", family="plugins")
def plugin_list():
    items = plugins.index()
    return "\n".join(f"- {p['name']} ({'on' if p['enabled'] else 'off'}): {p['summary']}" for p in items) or "No plugins installed."
