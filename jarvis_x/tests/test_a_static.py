"""QA A: static checks. Every route the UI calls exists, every element the scripts use exists."""
import ast
import re
from pathlib import Path

from server import app as app_module

ROOT = Path(__file__).resolve().parent.parent
PY = [p for p in ROOT.rglob("*.py") if "venv" not in p.parts and "data" not in p.relative_to(ROOT).parts[:1]]
JS = sorted((ROOT / "web" / "src").rglob("*.js"))


def test_every_python_file_compiles():
    assert len(PY) > 30
    for path in PY:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_no_forbidden_things():
    assert not list(ROOT.rglob("*.bat")), "no .bat files: he can't open them"
    code = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in PY + JS if "tests" not in p.parts
                     and p.name != "migrate_v15.py")
    low = code.lower()
    assert "moodle" not in low
    assert "pythonw" not in low and "schtasks" not in low and "startup folder" not in low   # no background / auto-start
    assert "ja-jp" not in low and "nanami" not in low                                        # Japanese mode is gone
    assert 'os.environ["anthropic_api_key"] =' not in low                                    # never set an API key


def test_requirements_are_pinned():
    lines = [ln.strip() for ln in (ROOT / "requirements.txt").read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    assert len(lines) >= 15
    assert all(re.match(r"^[A-Za-z0-9_.\-]+==\d", ln) for ln in lines), lines


def routes():
    out = set()
    for r in app_module.app.routes:
        for method in getattr(r, "methods", None) or []:
            out.add((method, re.sub(r"\{[^}]+\}", "{}", r.path)))
    return out


# The route inventory. A route silently disappearing in an edit (the v15 weather/news bug) fails here.
EXPECTED = {
    ("GET", "/"), ("GET", "/m"), ("GET", "/favicon.ico"), ("GET", "/api/state"), ("GET", "/api/boot"), ("GET", "/api/events"),
    ("POST", "/api/chat"), ("POST", "/api/stop"), ("POST", "/api/log"), ("GET", "/api/tts"), ("GET", "/api/weather"), ("GET", "/api/news"),
    ("GET", "/api/approvals"), ("POST", "/api/approvals/{}/{}"), ("GET", "/api/memory/facts"), ("POST", "/api/memory/facts"),
    ("PUT", "/api/memory/facts/{}"), ("DELETE", "/api/memory/facts/{}"), ("POST", "/api/knowledge/upload"), ("GET", "/api/transcripts"),
    ("GET", "/api/settings"), ("PUT", "/api/settings"), ("GET", "/api/tasks"), ("POST", "/api/tasks"), ("POST", "/api/tasks/{}/done"),
    ("DELETE", "/api/tasks/{}"), ("POST", "/api/reminders"), ("DELETE", "/api/reminders/{}"), ("POST", "/api/focus/log"),
    ("GET", "/api/routines"), ("POST", "/api/routines"), ("DELETE", "/api/routines/{}"), ("POST", "/api/routines/run"),
    ("GET", "/api/brief"), ("POST", "/api/brief/seen"), ("GET", "/api/recap"), ("POST", "/api/proactive/snooze"),
    ("POST", "/api/proactive/check"), ("GET", "/api/daily"), ("POST", "/api/guitar/log"), ("POST", "/api/expenses"),
    ("GET", "/api/flashcards/due"), ("POST", "/api/flashcards/{}/grade"), ("GET", "/api/comic"), ("POST", "/api/plugins/{}/toggle"),
    ("DELETE", "/api/plugins/{}"), ("GET", "/api/lights"), ("POST", "/api/lights"), ("POST", "/api/lights/devices"),
    ("DELETE", "/api/lights/devices/{}"), ("POST", "/api/vision/context"), ("POST", "/api/vision/snapshot"), ("POST", "/api/tool"),
    ("GET", "/api/companion"), ("POST", "/api/pair"), ("GET", "/models/{}"),
}


def test_route_inventory_is_complete():
    missing = EXPECTED - routes()
    assert not missing, f"routes disappeared: {sorted(missing)}"


def test_every_route_the_ui_calls_exists():
    have = {re.sub(r"\{\}", "X", path) for _, path in routes()}
    patterns = [re.compile("^" + re.sub(r"\\\{\\\}", "[^/]+", re.escape(path)) + "$") for _, path in routes()]
    used = set()
    for path in JS + [ROOT / "web" / "m.html", ROOT / "web" / "index.html"]:
        for m in re.finditer(r"[`'\"](/(?:api|models|vendor|src|css)/[^`'\"\s?]*)", path.read_text(encoding="utf-8")):
            used.add(re.sub(r"\$\{[^}]+\}", "X", m.group(1)).split("${")[0])
    assert len(used) > 30
    for url in sorted(used):
        if url.startswith(("/vendor/", "/src/", "/css/")):
            assert (ROOT / "web" / url.lstrip("/")).exists(), f"static file missing: {url}"
            continue
        assert any(p.match(url) for p in patterns), f"the UI calls {url} but no route serves it ({len(have)} routes)"


def test_every_element_the_scripts_reference_exists():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    assert len(ids) == len(re.findall(r'id="([^"]+)"', html)), "duplicate ids in index.html"
    for path in JS:
        for m in re.finditer(r"\$\(\s*'#([A-Za-z0-9_-]+)'\s*[),]", path.read_text(encoding="utf-8")):
            assert m.group(1) in ids, f"{path.name} uses #{m.group(1)} which is not in index.html"


def test_every_v15_panel_is_in_the_page():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for panel in ["card-brand", "card-weather", "card-news", "card-power", "panel-crew", "panel-quick", "panel-style", "panel-drill",
                  "panel-memory", "panel-focus", "panel-reminders", "panel-vision", "panel-mic", "panel-convo", "holo", "captions", "talkbar"]:
        assert f'id="{panel}"' in html
    for quick in ["brief", "headlines", "weather", "guesstimate", "debate", "roast", "party", "clean"]:
        assert f'data-quick="{quick}"' in html
    for drill in ["cv", "guesstimate", "case", "hr"]:
        assert f'data-drill="{drill}"' in html


def test_vendored_files_are_local_no_cdn():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8") + "".join(p.read_text(encoding="utf-8") for p in JS)
    assert not re.search(r"https?://(cdn|unpkg|cdnjs|fonts\.googleapis|storage\.googleapis)", html)
    for rel in ["three/three.module.js", "three/three.core.js", "three/addons/postprocessing/UnrealBloomPass.js", "mediapipe/vision_bundle.mjs",
                "mediapipe/wasm/vision_wasm_internal.wasm", "mediapipe/wasm/vision_wasm_internal.js",
                "mediapipe/models/hand_landmarker.task", "mediapipe/models/blaze_face_short_range.tflite"]:
        assert (ROOT / "web" / "vendor" / rel).exists(), rel


def test_mime_types_for_modules_and_wasm(client):
    assert client.get("/vendor/mediapipe/vision_bundle.mjs").headers["content-type"].startswith("text/javascript")
    assert client.get("/vendor/mediapipe/wasm/vision_wasm_internal.wasm").headers["content-type"] == "application/wasm"
    assert client.get("/src/main.js").headers["content-type"].startswith("text/javascript")
    res = client.get("/models/hand_landmarker.task")
    assert res.status_code == 200 and len(res.content) > 1_000_000
    assert client.get("/models/blaze_face_short_range.tflite").status_code == 200
    assert client.get("/models/evil.exe").status_code == 404


def test_every_get_route_answers(client):
    for method, path in sorted(routes()):
        if method != "GET" or "{}" in path or path == "/api/events":
            continue
        url = path + ("?persona=jarvis&text=hello" if path == "/api/tts" else "")
        res = client.get(url)
        assert res.status_code == 200, f"{path} -> {res.status_code} {res.text[:200]}"
