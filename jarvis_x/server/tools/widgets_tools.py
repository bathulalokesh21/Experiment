"""Weather + headlines tools (they also refresh the dashboard cards)."""
from __future__ import annotations

from .. import widgets
from .registry import tool


@tool("get_weather", "Current weather, today's high/low and rain timing for his city (or another city).",
      optional={"city": "str: city name, default his city"}, chip="Checking the weather", family="widgets")
async def get_weather(city: str = ""):
    w = await widgets.refresh_weather(city or None)
    if not w["ok"]:
        return w["error"]
    hours = ", ".join(f"{h['t']} {h['temp']}°C {h['pop']}%" for h in w["hourly"][:8:2])
    return (f"{w['city']}: {w['temp']}°C (feels {w['feels']}°C), {w['desc']}. High {w['high']}°C, low {w['low']}°C, "
            f"humidity {w['humidity']}%, wind {w['wind']} km/h. {w['rain']} Next hours (time temp rain%): {hours}.")


@tool("get_headlines", "Latest news headlines. topic: top, business, technology, india, world, sports, science, ai, "
      "startups, or any search words.", optional={"topic": "str: topic, default top"}, chip="Scanning the headlines",
      family="widgets")
async def get_headlines(topic: str = "top"):
    n = await widgets.refresh_news(topic or "top")
    if not n["items"]:
        return n.get("error") or "No headlines found."
    return "\n".join(f"- {i['title']} ({i['source']})" + (f": {i['summary'][:140]}" if i.get("summary") else "")
                     for i in n["items"][:7])
