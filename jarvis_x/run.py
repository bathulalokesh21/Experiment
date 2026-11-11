"""Launch JARVIS X.   cd /d C:\\jarvis_x && venv\\Scripts\\activate && python run.py

Manual launch only: no background mode, no auto-start."""
from __future__ import annotations

import socket
import sys
import threading
import webbrowser


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex(("127.0.0.1", port)) == 0


PORT_HELP = """
Port {port} is already in use, probably by an older JARVIS that is still running.
Free it with these two commands in cmd, then start again:

    netstat -ano | findstr :{port}
    taskkill /PID <the number in the last column> /F
"""


def main() -> int:
    from server import config
    config.load_env()  # also removes ANTHROPIC_API_KEY: the crew runs on the Claude Code login
    config.ensure_dirs()
    if sys.version_info < (3, 11):
        print("JARVIS X needs Python 3.11 or newer.")
        return 1
    if port_in_use(config.PORT):
        print(PORT_HELP.format(port=config.PORT))
        return 1
    if not sys.stdout.isatty() and not config.fake_mode():
        print("Start JARVIS from a normal cmd window (python run.py). Claude Code needs a real terminal.")
    lan = bool(config.settings().get("phone_companion"))
    config.HOST = "0.0.0.0" if lan else "127.0.0.1"
    url = f"http://localhost:{config.PORT}"
    print(f"\n  JARVIS X is starting at {url}")
    print("  Phone companion: " + ("ON (LAN, PIN required)" if lan else "off"))
    print("  Stop with Ctrl+C.\n")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.6, lambda: webbrowser.open(url)).start()
    import uvicorn
    uvicorn.run("server.app:app", host=config.HOST, port=config.PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
