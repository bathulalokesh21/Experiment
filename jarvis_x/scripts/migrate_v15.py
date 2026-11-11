"""Copy (never move) your data from the previous build into JARVIS X.

   python scripts\\migrate_v15.py                      from C:\\jarvis_crew_v6
   python scripts\\migrate_v15.py D:\\somewhere\\else

The old folder is only read. Run it as often as you like: existing JARVIS X data is never overwritten
(use --overwrite to replace files that already exist)."""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import config, store  # noqa: E402
from server.memory import facts  # noqa: E402
from server.tools import comms  # noqa: E402

OVERWRITE = "--overwrite" in sys.argv
ENV_KEYS = re.compile(r"^(CITY|WHATSAPP_MODE|(JARVIS|FRIDAY|ROBIN)_(VOICE|RATE|PITCH|FALLBACK_VOICE)|VOICE_KEEP_COMMAS)$")


def copy_file(src: Path, dst: Path) -> str:
    if not src.exists():
        return "not found in the old build"
    if dst.exists() and not OVERWRITE:
        return "already here (kept yours)"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return "copied"


def copy_tree(src: Path, dst: Path) -> str:
    if not src.exists():
        return "not found in the old build"
    count = 0
    for path in src.rglob("*"):
        if path.is_file():
            target = dst / path.relative_to(src)
            if target.exists() and not OVERWRITE:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(path, target)
                count += 1
            except OSError:
                pass  # browser lock files etc.
    return f"{count} file(s) copied"


def import_facts(path: Path) -> str:
    if not path.exists():
        return "not found in the old build"
    added = skipped = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = re.sub(r"^\s*([-*•]|\d+[.)])\s*", "", raw).strip()
        line = re.sub(r"^\[[^\]]*\]\s*", "", line)
        if len(line) < 4 or line.startswith("#"):
            continue
        res = facts.add(line, "general", source="migrated")
        added += res["status"] == "added"
        skipped += res["status"] != "added"
    return f"{added} fact(s) imported, {skipped} skipped (duplicates or things I don't store)"


def import_contacts(path: Path) -> str:
    """v15 contacts.md: lines like '- Mom: +91 98765 43210, mom@example.com' or 'Mom | phone | email'."""
    if not path.exists():
        return "not found in the old build"
    count = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip().lstrip("-*• ").strip()
        if not line or line.startswith("#") or set(line) <= set("|-: "):
            continue
        email = re.search(r"[^\s|,;<>]+@[^\s|,;<>]+\.[a-z]{2,}", line, re.I)
        phone = re.search(r"\+?\d[\d\s-]{8,16}\d", line)
        name = re.split(r"[:|,]|\s-\s", line)[0].strip(" *_")
        if not name or name.lower() in ("name", "contact") or not (email or phone):
            continue
        try:
            comms.save_contact(name, phone.group(0) if phone else "", email.group(0) if email else "")
            count += 1
        except ValueError:
            continue
    return f"{count} contact(s) imported"


def import_drills(path: Path) -> str:
    if not path.exists():
        return "not found in the old build"
    return copy_file(path, config.data("memory", "drills_v15.md")) + " (kept as a reference file)"


def import_env(path: Path) -> str:
    if not path.exists():
        return "not found in the old build"
    target = config.ROOT / ".env"
    have = target.read_text(encoding="utf-8") if target.exists() else ""
    lines = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key = raw.split("=", 1)[0].strip()
        if "=" in raw and ENV_KEYS.match(key) and not re.search(rf"^{key}=", have, re.M):
            if key == "ROBIN_VOICE" and raw.split("=", 1)[1].strip().lower().startswith("ja-"):
                continue  # Japanese mode is gone: ROBIN uses her new English voice
            lines.append(raw.strip())
    if lines:
        with target.open("a", encoding="utf-8") as fh:
            fh.write(("\n" if have and not have.endswith("\n") else "") + "\n".join(lines) + "\n")
    return f"{len(lines)} setting(s) copied (API keys are never copied)"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    old = Path(args[0]) if args else Path(r"C:\jarvis_crew_v6")
    if not old.exists():
        print(f"I can't find the old build at {old}.\nRun: python scripts\\migrate_v15.py <path to the old folder>")
        return 1
    config.ensure_dirs()
    print(f"Migrating from {old}  ->  {config.DATA}   (copy only; the old folder is not changed)\n")
    steps = [
        ("Learned facts (memory\\facts.md)", lambda: import_facts(old / "memory" / "facts.md")),
        ("Contacts (memory\\contacts.md)", lambda: import_contacts(old / "memory" / "contacts.md")),
        ("Drill log (memory\\drills.md)", lambda: import_drills(old / "memory" / "drills.md")),
        ("Knowledge files (knowledge\\)", lambda: copy_tree(old / "knowledge", config.data("knowledge"))),
        ("Notes (notes.txt)", lambda: copy_file(old / "notes.txt", config.data("notes.txt"))),
        ("Gmail credentials", lambda: copy_file(old / "google" / "credentials.json", config.data("google", "credentials.json"))),
        ("Gmail login token", lambda: copy_file(old / "google" / "token.json", config.data("google", "token.json"))),
        ("WhatsApp login (whatsapp_profile\\)", lambda: copy_tree(old / "whatsapp_profile", config.data("whatsapp_profile"))),
        ("Your voice clips / models (voices\\)", lambda: copy_tree(old / "voices", config.data("voices"))),
        ("Camera models", lambda: copy_tree(old / "static" / "vendor" / "mediapipe" / "models", config.data("models"))),
        ("Settings from .env", lambda: import_env(old / ".env")),
    ]
    for label, fn in steps:
        try:
            print(f"  {label}: {fn()}")
        except Exception as exc:
            print(f"  {label}: skipped ({type(exc).__name__}: {exc})")
    store.save("migrated.json", {"from": str(old)})
    print("\nDone. Your profile is profile\\me.md (from the kit). Next: python scripts\\doctor.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
