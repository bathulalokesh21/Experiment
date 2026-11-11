"""One-time Gmail login.   python scripts\\gmail_login.py

Needs data\\google\\credentials.json (an OAuth "Desktop app" client from Google Cloud Console; see README).
Opens your browser, you approve, and the token is saved to data\\google\\token.json."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import config, gmail  # noqa: E402


def main() -> int:
    config.load_env()
    config.ensure_dirs()
    cred = config.data("google", "credentials.json")
    if not cred.exists():
        print(f"Put your OAuth client file here first:\n  {cred}\nSee README, section 'Gmail login'.")
        return 1
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Missing packages. Run: pip install -r requirements.txt")
        return 1
    flow = InstalledAppFlow.from_client_secrets_file(str(cred), gmail.SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    config.data("google", "token.json").write_text(creds.to_json(), encoding="utf-8")
    print("Gmail is connected. Restart JARVIS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
