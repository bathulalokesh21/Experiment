"""Health check.   python scripts\\doctor.py

Checks Python, the venv, packages, the Claude Code login (and that no API key is in play), port 8000,
each internet service, the camera model files, the Gmail token and the WhatsApp profile."""
from __future__ import annotations

import importlib
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
results: list[tuple[str, str, str, str]] = []


def check(name: str, status: str, detail: str, fix: str = "") -> None:
    results.append((name, status, detail, fix))
    mark = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}[status]
    print(f"{mark} {name}: {detail}")
    if fix and status != "ok":
        print(f"         fix: {fix}")


def reach(url: str, timeout: float = 6.0) -> tuple[bool, str]:
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (JarvisX doctor)"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as res:
            return True, f"reachable ({res.status})"
    except Exception as exc:
        text = str(exc)
        if "CERTIFICATE" in text.upper():
            return False, "certificate check failed (network filter?)"
        return False, f"not reachable ({type(exc).__name__})"


def main() -> int:
    from server import config
    had_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    config.load_env()
    config.ensure_dirs()
    print("JARVIS X doctor\n")

    v = sys.version_info
    check("Python", "ok" if v >= (3, 11) else "fail", f"{v.major}.{v.minor}.{v.micro}", "Install Python 3.12.")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    check("Virtual environment", "ok" if in_venv else "warn", "active" if in_venv else "not active",
          "cd /d C:\\jarvis_x && venv\\Scripts\\activate")

    missing = []
    for mod, pip in [("claude_agent_sdk", "claude-agent-sdk"), ("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("httpx", "httpx"),
                     ("certifi", "certifi"), ("edge_tts", "edge-tts"), ("multipart", "python-multipart"), ("pypdf", "pypdf"),
                     ("docx", "python-docx"), ("pptx", "python-pptx"), ("PIL", "pillow"), ("playwright", "playwright"),
                     ("googleapiclient", "google-api-python-client"), ("google_auth_oauthlib", "google-auth-oauthlib")]:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pip)
    check("Packages", "ok" if not missing else "fail", "all installed" if not missing else "missing: " + ", ".join(missing),
          "pip install -r requirements.txt")

    check("API key", "warn" if had_key else "ok",
          "ANTHROPIC_API_KEY is set in your environment; JARVIS ignores and removes it at startup" if had_key
          else "none set (good: JARVIS runs on your Claude login)",
          "Optional: remove it for good with  setx ANTHROPIC_API_KEY \"\"")

    claude = shutil.which("claude")
    if not claude:
        check("Claude Code", "fail", "the `claude` command was not found", "Install Claude Code, then run `claude` and log in.")
    else:
        try:
            out = subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=20)
            check("Claude Code", "ok", (out.stdout or out.stderr).strip().splitlines()[0])
        except Exception as exc:
            check("Claude Code", "warn", f"found, but --version failed ({type(exc).__name__})")
        creds = [Path.home() / ".claude" / ".credentials.json", Path.home() / ".claude.json"]
        logged = any(p.exists() for p in creds)
        plan = ""
        try:
            data = json.loads(creds[0].read_text(encoding="utf-8"))
            plan = (data.get("claudeAiOauth") or {}).get("subscriptionType") or ""
        except Exception:
            pass
        check("Claude login", "ok" if logged else "fail",
              (f"logged in (plan: {plan})" if plan else "login files found") if logged else "no login found",
              "Run `claude`, type /login and choose your Claude subscription (not an API key).")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        busy = s.connect_ex(("127.0.0.1", config.PORT)) == 0
    check(f"Port {config.PORT}", "warn" if busy else "ok", "in use (JARVIS may already be running)" if busy else "free",
          f"netstat -ano | findstr :{config.PORT}   then   taskkill /PID <number> /F")

    for name, url in [("Weather (Open-Meteo)", "https://api.open-meteo.com/v1/forecast?latitude=25.57&longitude=91.88&current=temperature_2m"),
                      ("Weather backup (wttr.in)", "https://wttr.in/Shillong?format=3"),
                      ("News (Google News)", "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"),
                      ("News backup (BBC)", "https://feeds.bbci.co.uk/news/rss.xml"),
                      ("Voices (Microsoft)", "https://speech.platform.bing.com/consumer/speech/synthesize/readaloud/voices/list?trustedclienttoken=6A5AA1D4EAFF4E9FB37E23D68491D6F4"),
                      ("Google (Gmail API)", "https://gmail.googleapis.com/$discovery/rest?version=v1")]:
        good, detail = reach(url)
        check(name, "ok" if good else "warn", detail, "Blocked on this network? Try a phone hotspot. JARVIS still runs without it.")

    for name in ("hand_landmarker.task", "blaze_face_short_range.tflite"):
        mine, bundled = config.data("models", name), config.WEB / "vendor" / "mediapipe" / "models" / name
        found = mine if mine.exists() else bundled if bundled.exists() else None
        check(f"Camera model {name}", "ok" if found else "fail", f"present ({found.stat().st_size // 1024} KB)" if found else "missing",
              "python scripts\\fetch_models.py")
    wasm = config.WEB / "vendor" / "mediapipe" / "wasm" / "vision_wasm_internal.wasm"
    check("MediaPipe (bundled)", "ok" if wasm.exists() else "fail", "present" if wasm.exists() else "missing", "Re-copy the project folder.")
    three = config.WEB / "vendor" / "three" / "three.module.js"
    check("Three.js (bundled)", "ok" if three.exists() else "fail", "present" if three.exists() else "missing", "Re-copy the project folder.")

    cred, token = config.data("google", "credentials.json"), config.data("google", "token.json")
    if not cred.exists():
        check("Gmail", "warn", "not set up (credentials.json missing)", "See README, 'Gmail login'. Everything else works without it.")
    elif not token.exists():
        check("Gmail", "warn", "credentials found, but not logged in", "python scripts\\gmail_login.py")
    else:
        age = (time.time() - token.stat().st_mtime) / 86400
        check("Gmail", "ok", f"logged in (token last refreshed {age:.0f} day(s) ago)")

    profile = config.data("whatsapp_profile")
    has_profile = profile.exists() and any(profile.iterdir())
    check("WhatsApp", "ok" if has_profile else "warn",
          f"mode {os.environ.get('WHATSAPP_MODE', 'auto')}, " + ("login profile present" if has_profile else "no login yet"),
          "The first approved message opens WhatsApp Web: scan the QR once and it is remembered.")

    me = (config.PROFILE / "me.md").read_text(encoding="utf-8") if (config.PROFILE / "me.md").exists() else ""
    fills = me.count("[FILL]")
    check("Profile", "ok" if me and not fills else "warn", "complete" if me and not fills else f"{fills} [FILL] line(s) left in profile\\me.md",
          "Open profile\\me.md and fill them in (optional).")

    try:
        from server.tools import registry
        registry.load_all()
        check("Tools", "ok", f"{len(registry.all_tools())} tools load")
    except Exception as exc:
        check("Tools", "fail", f"{type(exc).__name__}: {exc}")

    fails = sum(1 for r in results if r[1] == "fail")
    warns = sum(1 for r in results if r[1] == "warn")
    print(f"\n{'All green.' if not fails and not warns else f'{fails} problem(s), {warns} warning(s).'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
