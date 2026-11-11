"""Audition voices.
   python scripts\\voice_test.py                 all three current voices
   python scripts\\voice_test.py robin           options for ROBIN, saved as mp3 files you can play
   python scripts\\voice_test.py list en-GB      every available voice for a locale
Files land in data\\voice_tests\\. Put the one you like in .env, e.g. ROBIN_VOICE=en-GB-SoniaNeural"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import config, voice  # noqa: E402

OPTIONS = {
    "jarvis": ["en-GB-RyanNeural", "en-GB-ThomasNeural", "en-AU-WilliamMultilingualNeural", "en-US-AndrewMultilingualNeural"],
    "friday": ["en-IE-EmilyNeural", "en-GB-SoniaNeural", "en-GB-LibbyNeural", "en-AU-NatashaNeural"],
    "robin": ["en-US-AvaMultilingualNeural", "en-GB-SoniaNeural", "en-US-EmmaMultilingualNeural", "en-GB-MaisieNeural", "en-US-JennyNeural"],
}
LINES = {"jarvis": "Welcome home, sir. All systems are online, and you have two reminders today.",
         "friday": "Hey boss! Weather's grand, your inbox is quiet, and I've queued up your focus timer.",
         "robin": "There you are, Love. I've read the file. Shall I tell you the short version, or the true one?"}


async def save(text: str, name: str, rate: str, pitch: str, path: Path) -> bool:
    import edge_tts
    try:
        await edge_tts.Communicate(text, name, rate=rate, pitch=pitch).save(str(path))
        return path.stat().st_size > 500
    except Exception as exc:
        print(f"  [FAIL] {name}: {type(exc).__name__} (check the internet connection)")
        return False


async def main() -> int:
    config.load_env()
    out = config.data("voice_tests")
    out.mkdir(parents=True, exist_ok=True)
    args = [a.lower() for a in sys.argv[1:]]
    if args and args[0] == "list":
        import edge_tts
        locale = sys.argv[2] if len(sys.argv) > 2 else "en-"
        for v in await edge_tts.list_voices():
            if v["ShortName"].lower().startswith(locale.lower()):
                print(f"{v['ShortName']:38} {v['Gender']}")
        return 0
    who = [a for a in args if a in OPTIONS] or list(OPTIONS)
    for persona in who:
        cfg = voice.settings_for(persona)
        names = OPTIONS[persona] if args else [cfg["voice"]]
        print(f"{persona.upper()} (current: {cfg['voice']})")
        for name in names:
            path = out / f"{persona}_{name}.mp3"
            if await save(LINES[persona], name, cfg["rate"], cfg["pitch"], path):
                print(f"  [ OK ] {name} -> {path}")
                if len(names) == 1 and sys.platform == "win32":
                    os.startfile(str(path))  # type: ignore[attr-defined]
    print(f"\nOpen the folder to listen:  explorer {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
