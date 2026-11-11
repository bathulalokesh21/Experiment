"""Self-upgrading, approval-gated. The crew can PROPOSE a new tool as a plugin file;
it is installed only when he approves the card, after its own tests pass.

A plugin is restricted Python: a short import allowlist, no file/network/shell access,
no dunder tricks. Its only persistence is `storage` (one JSON file under data/plugins/)."""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import textwrap

from . import approvals, bus, config, store
from .tools import registry

ALLOWED_IMPORTS = {"json", "re", "math", "datetime", "statistics", "random", "collections", "itertools",
                   "functools", "textwrap", "string", "decimal", "fractions", "time", "calendar"}
FORBIDDEN_NAMES = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "input",
                   "breakpoint", "getattr", "setattr", "delattr", "memoryview", "exit", "quit", "help", "dir",
                   "type", "object", "super", "classmethod", "staticmethod", "property"}
SAFE_BUILTINS = ["abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "format", "frozenset", "int",
                 "isinstance", "len", "list", "map", "max", "min", "print", "range", "repr", "reversed", "round",
                 "set", "sorted", "str", "sum", "tuple", "zip", "Exception", "ValueError", "KeyError", "TypeError",
                 "IndexError", "ZeroDivisionError", "True", "False", "None", "AssertionError", "divmod", "pow",
                 "chr", "ord", "hasattr", "iter", "next", "slice", "bytes", "callable"]
INDEX = "plugins/plugins.json"


class PluginError(Exception):
    pass


def validate(code: str) -> None:
    """Static sandbox check. Raises PluginError with a plain-English reason."""
    if len(code) > 20000:
        raise PluginError("the plugin is too long")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise PluginError(f"syntax error on line {exc.lineno}: {exc.msg}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    raise PluginError(f"import of '{alias.name}' is not allowed (no shell, files or network)")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS or node.level:
                raise PluginError(f"import from '{node.module}' is not allowed")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise PluginError(f"'{node.id}' is not allowed in plugins")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise PluginError(f"access to '{node.attr}' is not allowed in plugins")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            raise PluginError("global/nonlocal are not allowed in plugins")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            raise PluginError("double-underscore strings are not allowed in plugins")


class Storage:
    """The plugin's only persistence: data/plugins/<name>.data.json"""

    def __init__(self, name: str):
        self._file = f"plugins/{name}.data.json"

    def load(self, default=None):
        return store.load(self._file, {} if default is None else default)

    def save(self, obj) -> None:
        json.dumps(obj)  # must be plain data
        store.save(self._file, obj)


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name.split(".")[0] not in ALLOWED_IMPORTS:
        raise ImportError(f"import of '{name}' is not allowed in plugins")
    return __import__(name, globals, locals, fromlist, level)


def execute(name: str, code: str, storage=None) -> dict:
    """Run plugin code in a restricted namespace and return it."""
    import builtins
    validate(code)
    safe = {k: getattr(builtins, k) for k in SAFE_BUILTINS if hasattr(builtins, k)}
    safe["__import__"] = _restricted_import
    namespace = {"__builtins__": safe, "__name__": f"plugin_{name}", "storage": storage or Storage(name)}
    exec(compile(code, f"<plugin {name}>", "exec"), namespace)  # noqa: S102 - validated + restricted above
    tools = namespace.get("TOOLS")
    if not isinstance(tools, list) or not tools:
        raise PluginError("the plugin must define TOOLS = [{name, description, schema, fn}, ...]")
    for t in tools:
        if not (isinstance(t, dict) and re.match(r"^[a-z][a-z0-9_]{2,40}$", str(t.get("name", ""))) and callable(t.get("fn"))
                and t.get("description")):
            raise PluginError("each tool needs a snake_case name, a description and a function")
    return namespace


RUNNER = textwrap.dedent('''
    import json, sys
    sys.path.insert(0, {root!r})
    from server import config, plugins
    config.set_data_dir({data!r})
    class Mem:
        def __init__(self): self.v = None
        def load(self, default=None): return self.v if self.v is not None else ({{}} if default is None else default)
        def save(self, obj): json.dumps(obj); self.v = obj
    code = open({code!r}, encoding="utf-8").read()
    ns = plugins.execute({name!r}, code, storage=Mem())
    test = ns.get("test")
    if callable(test):
        test()
    print("PLUGIN_TESTS_OK", len(ns["TOOLS"]))
''')


def run_tests(name: str, code: str) -> tuple[bool, str]:
    """Run the plugin's own test() in a separate process with a timeout and in-memory storage."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        code_file = f"{tmp}/plugin.py"
        with open(code_file, "w", encoding="utf-8") as fh:
            fh.write(code)
        script = RUNNER.format(root=str(config.ROOT), data=tmp, code=code_file, name=name)
        try:
            out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return False, "the plugin's tests took longer than 20 seconds"
    if "PLUGIN_TESTS_OK" in out.stdout:
        return True, "tests passed"
    lines = (out.stderr or out.stdout).strip().splitlines()
    return False, (lines[-1] if lines else "the tests failed")[:300]


def index() -> list[dict]:
    return store.load(INDEX, [])


def propose(name: str, summary: str, code: str) -> dict:
    name = re.sub(r"[^a-z0-9_]", "_", name.strip().lower())[:40]
    if not re.match(r"^[a-z][a-z0-9_]{2,}$", name):
        raise PluginError("the plugin name must be snake_case, at least 3 letters")
    validate(code)
    ns = execute(name, code, storage=_NullStorage())
    clash = [t["name"] for t in ns["TOOLS"] if registry.get(t["name"]) and registry.get(t["name"]).plugin != name]
    if clash:
        raise PluginError(f"tool name already exists: {', '.join(clash)}")
    has_test = callable(ns.get("test"))
    card = approvals.create(
        "plugin", f"New ability: {name}",
        [{"label": "What it does", "value": summary},
         {"label": "Tools it adds", "value": ", ".join(t["name"] for t in ns["TOOLS"])},
         {"label": "Safety", "value": "Sandboxed: no shell, no files outside data/, no network. "
                                      + ("Its tests run before install." if has_test else "It has NO tests.")},
         {"label": "Code", "value": code, "code": True}],
        {"name": name, "summary": summary, "code": code})
    return card


class _NullStorage:
    def load(self, default=None):
        return {} if default is None else default

    def save(self, obj):
        pass


def install(payload: dict):
    name, code = payload["name"], payload["code"]
    try:
        validate(code)
    except PluginError as exc:
        return False, f"Not installed: {exc}."
    ok, message = run_tests(name, code)
    if not ok:
        return False, f"Not installed: {message}."
    config.data("plugins", f"{name}.py").write_text(code, encoding="utf-8")
    items = [p for p in index() if p["name"] != name]
    items.append({"name": name, "summary": payload.get("summary", ""), "enabled": True})
    store.save(INDEX, items)
    count = load_one(name)
    bus.publish("plugins_changed")
    return True, f"Installed '{name}' ({count} new tool{'s' if count != 1 else ''}, tests passed). It's ready to use."


def load_one(name: str) -> int:
    path = config.data("plugins", f"{name}.py")
    registry.unregister_plugin(name)
    ns = execute(name, path.read_text(encoding="utf-8"))
    for t in ns["TOOLS"]:
        schema = t.get("schema") if isinstance(t.get("schema"), dict) and "properties" in t.get("schema", {}) \
            else registry.schema(t.get("schema") or {})
        registry.register(registry.Tool(t["name"], str(t["description"]), schema, t["fn"],
                                        chip=f"Using {name}", family="plugin", plugin=name))
    return len(ns["TOOLS"])


def load_enabled() -> list[str]:
    loaded = []
    for entry in index():
        if entry.get("enabled"):
            try:
                load_one(entry["name"])
                loaded.append(entry["name"])
            except Exception as exc:  # a broken plugin never stops the app
                entry["error"] = f"{type(exc).__name__}: {exc}"
    return loaded


def set_enabled(name: str, enabled: bool) -> bool:
    items = index()
    entry = next((p for p in items if p["name"] == name), None)
    if not entry:
        return False
    entry["enabled"] = bool(enabled)
    store.save(INDEX, items)
    if enabled:
        load_one(name)
    else:
        registry.unregister_plugin(name)
    bus.publish("plugins_changed")
    return True


def remove(name: str) -> bool:
    items = index()
    if not any(p["name"] == name for p in items):
        return False
    registry.unregister_plugin(name)
    store.save(INDEX, [p for p in items if p["name"] != name])
    for suffix in (".py",):
        path = config.data("plugins", name + suffix)
        if path.exists():
            path.unlink()
    bus.publish("plugins_changed")
    return True


approvals.register_executor("plugin", install)
