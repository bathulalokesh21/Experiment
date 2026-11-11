"""Paths, .env loading and settings. Code and data are strictly separate:
everything the app writes lives under DATA (default: <project>/data)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
PROFILE = ROOT / "profile"
DATA = Path(os.environ.get("JARVIS_DATA") or ROOT / "data")

HOST = "127.0.0.1"
PORT = int(os.environ.get("JARVIS_PORT") or 8000)


def set_data_dir(path) -> None:
    """Point the app at another data folder (used by tests)."""
    global DATA
    DATA = Path(path)
    ensure_dirs()


def data(*parts: str) -> Path:
    return DATA.joinpath(*parts)


SUBDIRS = [
    "memory", "knowledge", "transcripts", "screens", "plugins", "voices", "cache/tts",
    "google", "comic", "uploads", "sketches",
]


def ensure_dirs() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    for sub in SUBDIRS:
        (DATA / sub).mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    """Read <project>/.env into os.environ (without overriding real env vars) and
    make sure the app can never run on an API key: it must use the Claude Code login."""
    env_file = ROOT / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    strip_api_key()


def strip_api_key() -> None:
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        os.environ.pop(key, None)


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def fake_mode() -> bool:
    """JARVIS_FAKE=1 swaps Claude, TTS and the network for local fakes (tests, demos)."""
    return os.environ.get("JARVIS_FAKE", "") == "1"


DEFAULT_SETTINGS = {
    "humor": 35,
    "effort": "auto",
    "interrupt": True,
    "sound": True,
    "proactive": True,
    "quiet_start": "23:00",
    "quiet_end": "07:00",
    "phone_companion": False,
    "smart_routing": False,
    "ambient_minutes": 5,
    "news_topics": ["business", "technology", "india"],
    "gesture_sensitivity": 1.0,
    "calibration": None,
    "active": "jarvis",
}


def settings() -> dict:
    from . import store
    merged = dict(DEFAULT_SETTINGS)
    merged.update(store.load("settings.json", {}))
    merged["city"] = merged.get("city") or env("CITY", "Shillong")
    return merged


def update_settings(patch: dict) -> dict:
    from . import store
    allowed = set(DEFAULT_SETTINGS) | {"city"}
    current = store.load("settings.json", {})
    for key, value in patch.items():
        if key in allowed:
            current[key] = value
    if "humor" in current:
        current["humor"] = max(0, min(100, int(current["humor"])))
    if current.get("effort") not in (None, "auto", "fast", "med", "deep"):
        current["effort"] = "auto"
    store.save("settings.json", current)
    return settings()
