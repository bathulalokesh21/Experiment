"""Terminal mode: talk to the crew without the dashboard.   python cli.py [jarvis|friday|robin]"""
from __future__ import annotations

import asyncio
import sys


async def main() -> None:
    from server import config, crew, plugins
    from server.tools import registry
    config.load_env()
    config.ensure_dirs()
    registry.load_all()
    plugins.load_enabled()
    persona = sys.argv[1].lower() if len(sys.argv) > 1 and sys.argv[1].lower() in crew.PERSONAS else "jarvis"
    brain = crew.brain()
    print(f"Talking to {crew.PERSONAS[persona]['name']}. Type a name to switch, 'quit' to leave.\n")
    try:
        while True:
            try:
                text = (await asyncio.to_thread(input, "you > ")).strip()
            except EOFError:
                break
            if text.lower() in ("quit", "exit"):
                break
            if text.lower() in crew.PERSONAS:
                persona = text.lower()
                print(f"({crew.PERSONAS[persona]['name']} is listening)")
                continue
            if not text:
                continue
            print(f"{crew.PERSONAS[persona]['name'].lower()} > ", end="", flush=True)
            async for event in brain.stream(persona, text, config.settings()["effort"], config.settings()["humor"]):
                if event["type"] == "delta":
                    print(event["text"], end="", flush=True)
                elif event["type"] == "chip":
                    print(f"[{event['text']}] ", end="", flush=True)
                elif event["type"] == "error":
                    print(f"\n! {event['message']}")
            print()
    finally:
        await brain.close()


if __name__ == "__main__":
    asyncio.run(main())
