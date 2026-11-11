"""Thin wrappers around the few OS things JARVIS touches. Every function is
replaceable in tests (monkeypatch) and degrades to a clear message off Windows."""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser

IS_WINDOWS = sys.platform == "win32"

VK = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2,
      "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD}


def press_key(name: str, times: int = 1) -> bool:
    if not IS_WINDOWS:
        return False
    import ctypes
    code = VK[name]
    for _ in range(max(1, times)):
        ctypes.windll.user32.keybd_event(code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(code, 0, 2, 0)
    return True


def open_uri(uri: str) -> bool:
    """Open a URL or protocol link (tel:, whatsapp:) with the default handler."""
    try:
        if IS_WINDOWS:
            os.startfile(uri)  # type: ignore[attr-defined]
            return True
        return webbrowser.open(uri)
    except OSError:
        return False


def launch(command: list[str] | str) -> bool:
    try:
        if IS_WINDOWS and isinstance(command, str):
            os.startfile(command)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(command, shell=isinstance(command, str),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def clipboard_text() -> str | None:
    try:
        if IS_WINDOWS:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                                 capture_output=True, text=True, timeout=6, encoding="utf-8", errors="replace")
            return out.stdout
        for cmd in (["wl-paste"], ["xclip", "-selection", "clipboard", "-o"], ["pbpaste"]):
            try:
                return subprocess.run(cmd, capture_output=True, text=True, timeout=4).stdout
            except (OSError, subprocess.SubprocessError):
                continue
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def screenshot(path) -> bool:
    try:
        from PIL import ImageGrab
        image = ImageGrab.grab()
        image.thumbnail((1920, 1200))
        image.save(str(path), "PNG")
        return True
    except Exception:
        return False
