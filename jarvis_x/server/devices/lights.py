"""Smart-light layer. Discovery first, never faked: a light only exists here after
he has added it to data/devices.json (scripts/devices_scan.py helps find it).

Drivers:
  tuya  - Wi-Fi bulbs on the Tuya platform (many Indian brands), local control via tinytuya
  ble   - generic BLE bulbs speaking the common Triones / MagicHome-style command set, via bleak
  fake  - an in-memory bulb for tests and for trying the Home panel
"""
from __future__ import annotations

import asyncio

from .. import bus, store

FILE = "devices.json"
SCENES = {
    "focus": {"on": True, "brightness": 80, "kelvin": 5500},
    "relax": {"on": True, "brightness": 35, "kelvin": 2700},
    "movie": {"on": True, "brightness": 12, "kelvin": 2700},
    "reading": {"on": True, "brightness": 70, "kelvin": 4000},
    "party": {"on": True, "brightness": 100, "colour": "magenta"},
    "night": {"on": True, "brightness": 5, "kelvin": 2700},
    "bright": {"on": True, "brightness": 100, "kelvin": 6500},
}
COLOURS = {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255), "white": (255, 255, 255),
           "warm white": (255, 180, 100), "cool white": (220, 235, 255), "yellow": (255, 220, 0),
           "orange": (255, 120, 0), "purple": (150, 0, 255), "magenta": (255, 0, 180), "pink": (255, 90, 160),
           "cyan": (0, 220, 255), "gold": (255, 190, 60), "lavender": (190, 150, 255), "teal": (0, 180, 160)}
_fake_state: dict[str, dict] = {}


class LightError(Exception):
    pass


def registry() -> list[dict]:
    return store.load(FILE, [])


def public(dev: dict) -> dict:
    """Never expose local keys to the dashboard or the model."""
    return {k: v for k, v in dev.items() if k not in ("local_key",)}


def add_device(dev: dict) -> dict:
    if dev.get("driver") not in ("tuya", "ble", "fake"):
        raise LightError("driver must be tuya, ble or fake")
    if not dev.get("name"):
        raise LightError("the device needs a name")
    items = [d for d in registry() if d["name"].lower() != dev["name"].lower()]
    dev.setdefault("state", {"on": False, "brightness": 100, "kelvin": 4000, "colour": ""})
    items.append(dev)
    store.save(FILE, items)
    bus.publish("lights", devices=[public(d) for d in items])
    return dev


def remove_device(name: str) -> bool:
    items = registry()
    kept = [d for d in items if d["name"].lower() != name.lower()]
    store.save(FILE, kept)
    bus.publish("lights", devices=[public(d) for d in kept])
    return len(kept) != len(items)


def pick(name: str = "") -> dict:
    items = registry()
    if not items:
        raise LightError("No light has been added yet. Run: python scripts\\devices_scan.py and follow the steps "
                         "(README, 'Smart light').")
    if name:
        hit = next((d for d in items if name.lower() in d["name"].lower()), None)
        if not hit:
            raise LightError(f"No light called '{name}'. Known: " + ", ".join(d["name"] for d in items))
        return hit
    return items[0]


# ---- drivers ---------------------------------------------------------------------------------

def _tuya_apply(dev: dict, change: dict) -> None:
    try:
        import tinytuya
    except ImportError as exc:
        raise LightError("tinytuya isn't installed. Run: pip install tinytuya") from exc
    bulb = tinytuya.BulbDevice(dev["id"], dev.get("ip") or "Auto", dev["local_key"], version=float(dev.get("version", 3.3)))
    bulb.set_socketTimeout(4)
    res = None
    if "on" in change:
        res = bulb.turn_on() if change["on"] else bulb.turn_off()
    if "brightness" in change:
        res = bulb.set_brightness_percentage(int(change["brightness"]))
    if "kelvin" in change:
        pct = max(0, min(100, round((int(change["kelvin"]) - 2700) / (6500 - 2700) * 100)))
        res = bulb.set_colourtemp_percentage(pct)
    if "rgb" in change:
        res = bulb.set_colour(*change["rgb"])
    if isinstance(res, dict) and res.get("Error"):
        raise LightError(f"The bulb refused the command: {res['Error']}. Check the local key and that the laptop "
                         f"is on the same Wi-Fi as the bulb.")


async def _ble_apply(dev: dict, change: dict) -> None:
    try:
        from bleak import BleakClient
    except ImportError as exc:
        raise LightError("bleak isn't installed. Run: pip install bleak") from exc
    char = dev.get("characteristic", "0000ffd9-0000-1000-8000-00805f9b34fb")
    state = dev.get("state", {})
    packets = []
    if "on" in change:
        packets.append(bytes([0xCC, 0x23 if change["on"] else 0x24, 0x33]))
    rgb = change.get("rgb")
    level = change.get("brightness", state.get("brightness", 100)) / 100
    if rgb or "brightness" in change or "kelvin" in change:
        if rgb is None:
            k = change.get("kelvin", state.get("kelvin", 4000))
            warm = (6500 - k) / (6500 - 2700)
            rgb = (255, int(255 - 75 * warm), int(255 - 155 * warm))
        r, g, b = (int(c * level) for c in rgb)
        packets.append(bytes([0x56, r, g, b, 0x00, 0xF0, 0xAA]))
    try:
        async with BleakClient(dev["address"], timeout=8) as client:
            for packet in packets:
                await client.write_gatt_char(char, packet, response=False)
    except Exception as exc:
        raise LightError("I couldn't reach the bulb over Bluetooth. It may be out of range, switched off at the wall, "
                         "or still connected to the phone app (Bluetooth bulbs usually accept one connection: close "
                         f"the app on your phone and try again). [{type(exc).__name__}]") from exc


async def apply(change: dict, name: str = "") -> dict:
    """change keys: on, brightness (1-100), kelvin (2700-6500), colour (name) / rgb."""
    dev = pick(name)
    change = dict(change)
    if "brightness" in change:
        change["brightness"] = max(1, min(100, int(change["brightness"])))
        change.setdefault("on", True)
    if "kelvin" in change:
        change["kelvin"] = max(2700, min(6500, int(change["kelvin"])))
        change.setdefault("on", True)
    if change.get("colour"):
        key = str(change["colour"]).lower().strip()
        if key not in COLOURS:
            raise LightError("I know these colours: " + ", ".join(sorted(COLOURS)))
        change["rgb"] = COLOURS[key]
        change.setdefault("on", True)
    driver = dev["driver"]
    if driver == "fake":
        _fake_state.setdefault(dev["name"], {}).update(change)
    elif driver == "tuya":
        try:
            await asyncio.to_thread(_tuya_apply, dev, change)
        except LightError:
            raise
        except Exception as exc:
            raise LightError(f"The bulb didn't answer on Wi-Fi ({type(exc).__name__}). Is it powered and on the same "
                             f"network as the laptop?") from exc
    elif driver == "ble":
        await _ble_apply(dev, change)
    items = registry()
    for d in items:
        if d["name"] == dev["name"]:
            state = d.setdefault("state", {})
            for key in ("on", "brightness", "kelvin"):
                if key in change:
                    state[key] = change[key]
            if "colour" in change:
                state["colour"] = change["colour"]
            elif "kelvin" in change:
                state["colour"] = ""
            dev = d
    store.save(FILE, items)
    bus.publish("lights", devices=[public(d) for d in items])
    return public(dev)
