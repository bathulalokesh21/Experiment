"""Find your smart light.   python scripts\\devices_scan.py

1. Scans Bluetooth LE (works on Windows) and lists nearby devices.
2. Scans the Wi-Fi network for Tuya-based smart devices (many Indian smart bulbs are Tuya inside).
3. Lets you add the light to data\\devices.json so the crew and the Home panel can control it.

   python scripts\\devices_scan.py --add-fake     add a pretend bulb to try the Home panel
Nothing is ever controlled unless you add it here."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import config  # noqa: E402
from server.devices import lights  # noqa: E402

BULB_HINTS = ("bulb", "light", "led", "lamp", "triones", "magic", "elk", "crompton", "wipro", "syska", "philips", "smart")


async def scan_ble(seconds: float = 8.0) -> list[dict]:
    try:
        from bleak import BleakScanner
    except ImportError:
        print("  Bluetooth scan skipped: bleak isn't installed (pip install bleak).")
        return []
    try:
        found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    except Exception as exc:
        print(f"  Bluetooth scan failed ({type(exc).__name__}). Is Bluetooth switched on? "
              f"Settings > Bluetooth & devices.")
        return []
    out = []
    for address, (device, adv) in found.items():
        name = device.name or adv.local_name or "(no name)"
        out.append({"name": name, "address": address, "rssi": adv.rssi, "services": list(adv.service_uuids or []),
                    "likely": any(h in name.lower() for h in BULB_HINTS)})
    return sorted(out, key=lambda d: (-d["likely"], -d["rssi"]))


def scan_tuya() -> list[dict]:
    try:
        import tinytuya
    except ImportError:
        print("  Wi-Fi scan skipped: tinytuya isn't installed (pip install tinytuya).")
        return []
    try:
        found = tinytuya.deviceScan(verbose=False, maxretry=12)
    except Exception as exc:
        print(f"  Wi-Fi scan failed ({type(exc).__name__}). Is the laptop on the same Wi-Fi as the bulb?")
        return []
    return [{"ip": ip, "id": info.get("gwId") or info.get("id"), "version": info.get("version"),
             "product": info.get("productKey")} for ip, info in (found or {}).items()]


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def main() -> int:
    config.load_env()
    config.ensure_dirs()
    if "--add-fake" in sys.argv:
        lights.add_device({"name": "Demo light", "driver": "fake"})
        print("Added 'Demo light' (pretend bulb). Remove it later from data\\devices.json.")
        return 0

    print("Scanning Bluetooth for 8 seconds...")
    ble = asyncio.run(scan_ble())
    for i, d in enumerate(ble, 1):
        print(f"  B{i}. {d['name']:28} {d['address']}  signal {d['rssi']} dBm{'   <- looks like a light' if d['likely'] else ''}")
    if not ble:
        print("  No Bluetooth devices listed.")
    print("\nScanning the Wi-Fi network for Tuya devices (about 20 seconds)...")
    tuya = scan_tuya()
    for i, d in enumerate(tuya, 1):
        print(f"  W{i}. Tuya device  ip {d['ip']}  id {d['id']}  protocol {d['version']}")
    if not tuya:
        print("  No Tuya devices answered.")

    if "--json" in sys.argv:
        print(json.dumps({"ble": ble, "tuya": tuya}, indent=1))
        return 0
    if not ble and not tuya:
        print("\nNothing found. Check that the bulb is powered, and that the laptop is on the same Wi-Fi (for Wi-Fi bulbs)\n"
              "or has Bluetooth on (for Bluetooth bulbs). See README, 'Smart light', for the other options.")
        return 0

    choice = ask("\nWhich one is your light? (e.g. W1 or B2, Enter to skip): ").upper()
    if not choice:
        return 0
    name = ask("Name for it (e.g. Desk light): ") or "My light"
    try:
        index = int(choice[1:]) - 1
        if choice.startswith("W"):
            dev = tuya[index]
            print("\nA Tuya bulb needs its 'local key' (a password the bulb shares with its app).\n"
                  "Get it once: README, 'Smart light', steps 1-5 (free Tuya IoT account, then `python -m tinytuya wizard`).")
            key = ask("Local key (Enter to stop here): ")
            if not key:
                return 0
            lights.add_device({"name": name, "driver": "tuya", "id": dev["id"], "ip": dev["ip"], "local_key": key,
                               "version": dev["version"] or 3.3})
        else:
            dev = ble[index]
            lights.add_device({"name": name, "driver": "ble", "address": dev["address"],
                               "characteristic": "0000ffd9-0000-1000-8000-00805f9b34fb"})
            print("Added with the common generic Bluetooth bulb command set. If the light does not react, the bulb uses\n"
                  "a private protocol: see README, 'Smart light', for the honest options.")
    except (ValueError, IndexError):
        print("I didn't understand that choice.")
        return 1
    except lights.LightError as exc:
        print(f"Not added: {exc}")
        return 1
    print(f"Saved '{name}'. Start JARVIS and try: \"Jarvis, lights to 30 percent\".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
