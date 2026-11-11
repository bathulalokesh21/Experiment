"""Smart-home tools. Lights need no approval, but only devices he added are controlled."""
from __future__ import annotations

from ..devices import lights
from .registry import tool


async def _do(change: dict, name: str, done: str) -> str:
    try:
        dev = await lights.apply(change, name)
    except lights.LightError as exc:
        return str(exc)
    return done.format(name=dev["name"])


@tool("light_on", "Turn his light on.", optional={"name": "str: which light"}, chip="Lights", family="home")
async def light_on(name: str = ""):
    return await _do({"on": True}, name, "{name} is on.")


@tool("light_off", "Turn his light off.", optional={"name": "str: which light"}, chip="Lights", family="home")
async def light_off(name: str = ""):
    return await _do({"on": False}, name, "{name} is off.")


@tool("light_brightness", "Set light brightness in percent (1-100).", {"percent": "int: 1-100"},
      {"name": "str: which light"}, chip="Lights", family="home")
async def light_brightness(percent: int, name: str = ""):
    return await _do({"brightness": percent}, name, "{name} set to " + f"{int(percent)}%.")


@tool("light_colour", "Set the light colour: a colour name (red, blue, purple, gold...) or a white temperature "
      "('warm white', 'cool white', or kelvin=2700-6500).", optional={"colour": "str: colour name", "kelvin": "int: 2700-6500",
                                                                      "name": "str: which light"}, chip="Lights", family="home")
async def light_colour(colour: str = "", kelvin: int = 0, name: str = ""):
    key = (colour or "").lower().strip()
    if key in ("warm", "warm white") and not kelvin:
        kelvin, key = 2700, ""
    if key in ("cool", "cool white", "daylight") and not kelvin:
        kelvin, key = 6500, ""
    if kelvin:
        return await _do({"kelvin": kelvin}, name, "{name} set to " + f"{int(kelvin)}K white.")
    if not key:
        return "Which colour?"
    return await _do({"colour": key}, name, "{name} is now " + key + ".")


@tool("light_scene", "Apply a light scene: " + ", ".join(sorted(lights.SCENES)) + ".", {"scene": "str"},
      {"name": "str: which light"}, chip="Lights", family="home")
async def light_scene(scene: str, name: str = ""):
    preset = lights.SCENES.get(scene.strip().lower())
    if not preset:
        return "Scenes are: " + ", ".join(sorted(lights.SCENES))
    return await _do(dict(preset), name, "{name}: " + scene.strip().lower() + " scene.")


@tool("lights_status", "Which lights are set up and their last known state.", family="home")
def lights_status():
    items = lights.registry()
    if not items:
        return "No light is set up yet. He can run: python scripts\\devices_scan.py"
    return "\n".join(f"{d['name']} ({d['driver']}): {'on' if d['state'].get('on') else 'off'}, "
                     f"{d['state'].get('brightness', '?')}%" for d in items)
