"""Weather + headlines. Refreshed every 5 minutes, backups for both, certifi for
HTTPS, and plain-English errors when the network says no."""
from __future__ import annotations

import asyncio
import html
import re
import ssl
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import certifi
import httpx

from . import bus, config

REFRESH_SECONDS = 300
UA = {"User-Agent": "Mozilla/5.0 (JarvisX dashboard)"}
_state: dict = {"weather": None, "news": {}, "seen_links": {}}
_fetch_override = None  # tests: async (url) -> str

WMO = {0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Icy fog",
       51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
       61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
       71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Light showers", 81: "Showers",
       82: "Violent showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm",
       96: "Thunderstorm with hail", 99: "Thunderstorm with hail"}

TOPIC_QUERIES = {"business": "business", "technology": "technology", "india": "India", "world": "world",
                 "sports": "sports", "science": "science", "ai": "artificial intelligence",
                 "startups": "India startups", "consulting": "consulting industry", "anime": "anime",
                 "music": "rock music"}
BACKUP_FEEDS = {
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "india": "https://www.thehindu.com/news/national/feeder/default.rss",
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "sports": "https://feeds.bbci.co.uk/sport/rss.xml",
}


def set_fetch(fn) -> None:
    global _fetch_override
    _fetch_override = fn


def explain(exc: Exception) -> str:
    name = type(exc).__name__
    text = str(exc)
    if "CERTIFICATE" in text.upper() or "SSL" in name.upper():
        return "the secure connection was refused (a network filter or an out-of-date certificate store)"
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)) or "getaddrinfo" in text:
        return "no internet connection, or this network blocks the site"
    if isinstance(exc, httpx.TimeoutException):
        return "the service took too long to answer"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"the service answered with an error ({exc.response.status_code})"
    return f"unexpected problem ({name})"


async def fetch(url: str, timeout: float = 9.0) -> str:
    if _fetch_override is not None:
        return await _fetch_override(url)
    ctx = ssl.create_default_context(cafile=certifi.where())
    async with httpx.AsyncClient(verify=ctx, headers=UA, timeout=timeout, follow_redirects=True) as client:
        res = await client.get(url)
        res.raise_for_status()
        return res.text


# ---------------------------------------------------------------- weather

def rain_summary(hourly: list[dict], now_hour: int | None = None) -> str:
    """hourly: [{"t": "HH:MM", "temp": .., "pop": 0-100}] starting at the current hour."""
    upcoming = hourly[:12]
    wet = [h for h in upcoming if (h.get("pop") or 0) >= 50]
    if not wet:
        maybe = [h for h in upcoming if (h.get("pop") or 0) >= 30]
        if maybe:
            return f"Small chance of rain around {_clock(maybe[0]['t'])}."
        return "No rain expected in the next 12 hours."
    first = wet[0]
    if upcoming and first is upcoming[0]:
        dry = next((h for h in upcoming if (h.get("pop") or 0) < 40), None)
        return "Rain likely now" + (f", easing around {_clock(dry['t'])}." if dry else " and for the next few hours.") + \
            " Take an umbrella."
    return f"Rain likely around {_clock(first['t'])} ({first['pop']}%). Take an umbrella if you're heading out."


def _clock(hhmm: str) -> str:
    hour = int(hhmm.split(":")[0])
    return f"{hour % 12 or 12} {'am' if hour < 12 else 'pm'}"


async def _open_meteo(city: str) -> dict:
    import json
    geo = json.loads(await fetch(
        f"https://geocoding-api.open-meteo.com/v1/search?name={quote_plus(city)}&count=1&language=en&format=json"))
    if not geo.get("results"):
        raise ValueError(f"couldn't find a place called {city}")
    place = geo["results"][0]
    data = json.loads(await fetch(
        "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day"
        "&hourly=temperature_2m,precipitation_probability&daily=temperature_2m_max,temperature_2m_min"
        "&forecast_days=2&timezone=auto".format(lat=place["latitude"], lon=place["longitude"])))
    cur = data["current"]
    times = data["hourly"]["time"]
    start = next((i for i, t in enumerate(times) if t >= cur["time"][:13]), 0)
    hourly = [{"t": times[i][11:16], "temp": round(data["hourly"]["temperature_2m"][i]),
               "pop": data["hourly"]["precipitation_probability"][i] or 0}
              for i in range(start, min(start + 24, len(times)))]
    return {"ok": True, "city": place["name"], "temp": round(cur["temperature_2m"]),
            "feels": round(cur["apparent_temperature"]), "desc": WMO.get(cur["weather_code"], "Weather"),
            "code": cur["weather_code"], "humidity": cur["relative_humidity_2m"],
            "wind": round(cur["wind_speed_10m"]), "is_day": bool(cur.get("is_day", 1)),
            "high": round(data["daily"]["temperature_2m_max"][0]), "low": round(data["daily"]["temperature_2m_min"][0]),
            "hourly": hourly, "rain": rain_summary(hourly), "source": "Open-Meteo"}


async def _wttr(city: str) -> dict:
    import json
    data = json.loads(await fetch(f"https://wttr.in/{quote_plus(city)}?format=j1"))
    cur = data["current_condition"][0]
    hourly = []
    now_h = datetime.now().hour
    for d, day in enumerate(data.get("weather", [])[:2]):
        for slot in day.get("hourly", []):
            hour = int(slot["time"]) // 100
            if d == 0 and hour < now_h - 2:
                continue
            hourly.append({"t": f"{hour:02d}:00", "temp": int(slot["tempC"]), "pop": int(slot.get("chanceofrain", 0))})
    today = data["weather"][0]
    return {"ok": True, "city": city, "temp": int(cur["temp_C"]), "feels": int(cur["FeelsLikeC"]),
            "desc": cur["weatherDesc"][0]["value"], "code": -1, "humidity": int(cur["humidity"]),
            "wind": int(cur["windspeedKmph"]), "is_day": 6 <= now_h < 18, "high": int(today["maxtempC"]),
            "low": int(today["mintempC"]), "hourly": hourly[:24], "rain": rain_summary(hourly), "source": "wttr.in (backup)"}


async def refresh_weather(city: str | None = None) -> dict:
    city = city or config.settings()["city"]
    errors = []
    for source in (_open_meteo, _wttr):
        try:
            result = await source(city)
            result["updated"] = time.time()
            _state["weather"] = result
            bus.publish("weather", weather=result)
            return result
        except Exception as exc:
            errors.append(explain(exc) if not isinstance(exc, ValueError) else str(exc))
    previous = _state.get("weather")
    result = {"ok": False, "city": city, "updated": time.time(),
              "error": f"Weather isn't available right now: {errors[0]}. I tried two services.",
              "stale": previous if previous and previous.get("ok") else None}
    if not (previous and previous.get("ok")):
        _state["weather"] = result
    bus.publish("weather", weather=result)
    return result


async def weather(max_age: float = REFRESH_SECONDS) -> dict:
    cur = _state.get("weather")
    if cur and time.time() - cur.get("updated", 0) < max_age:
        return cur
    return await refresh_weather()


# ---------------------------------------------------------------- news

def parse_rss(xml_text: str, limit: int = 8) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        title = html.unescape((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        source = (item.findtext("source") or "").strip()
        if not source and " - " in title:
            title, _, source = title.rpartition(" - ")
        elif source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        published = 0.0
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "").timestamp()
        except (TypeError, ValueError):
            pass
        summary = re.sub(r"<[^>]+>", " ", html.unescape(item.findtext("description") or "")).strip()
        if title and link:
            items.append({"title": title, "link": link, "source": source, "published": published,
                          "summary": summary[:300]})
        if len(items) >= limit:
            break
    return items


async def refresh_news(topic: str = "top") -> dict:
    topic = (topic or "top").strip().lower()
    query = TOPIC_QUERIES.get(topic, topic)
    urls = []
    if topic == "top":
        urls.append("https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en")
    else:
        urls.append(f"https://news.google.com/rss/search?q={quote_plus(query)}+when:1d&hl=en-IN&gl=IN&ceid=IN:en")
    urls.append(BACKUP_FEEDS.get(topic, "https://feeds.bbci.co.uk/news/rss.xml"))
    errors = []
    for i, url in enumerate(urls):
        try:
            items = parse_rss(await fetch(url))
            if not items:
                raise ValueError("the feed came back empty")
            seen = _state["seen_links"].setdefault(topic, set())
            first_time = not seen
            for item in items:
                item["new"] = (not first_time) and item["link"] not in seen
                item["topic"] = topic
            seen.update(item["link"] for item in items)
            result = {"ok": True, "topic": topic, "items": items, "updated": time.time(),
                      "source": "Google News" if i == 0 else "backup feed"}
            _state["news"][topic] = result
            return result
        except Exception as exc:
            errors.append(str(exc) if isinstance(exc, ValueError) else explain(exc))
    previous = _state["news"].get(topic)
    result = {"ok": False, "topic": topic, "items": previous["items"] if previous and previous.get("ok") else [],
              "updated": time.time(), "error": f"Headlines aren't available right now: {errors[0]}."}
    if not (previous and previous.get("ok")):
        _state["news"][topic] = result
    return result


async def news(topic: str = "top", max_age: float = REFRESH_SECONDS) -> dict:
    topic = (topic or "top").strip().lower()
    cur = _state["news"].get(topic)
    if cur and time.time() - cur.get("updated", 0) < max_age:
        return cur
    return await refresh_news(topic)


async def headlines_mix(topics: list[str] | None = None, per_topic: int = 4, force: bool = False) -> dict:
    """The headlines card: business + technology + India by default, interleaved."""
    topics = topics or config.settings()["news_topics"]
    results = await asyncio.gather(*[(refresh_news(t) if force else news(t)) for t in topics])
    items, errors = [], []
    for rank in range(per_topic):
        for res in results:
            if rank < len(res["items"]):
                items.append(res["items"][rank])
    for res in results:
        if not res["ok"]:
            errors.append(res["error"])
    out = {"ok": bool(items), "topics": topics, "items": items, "updated": time.time(),
           "error": errors[0] if errors and not items else ""}
    bus.publish("news", news=out)
    return out


async def refresh_loop() -> None:
    """Every 5 minutes, forever."""
    while True:
        try:
            await refresh_weather()
            await headlines_mix(force=True)
        except Exception:
            pass
        await asyncio.sleep(REFRESH_SECONDS)


def reset() -> None:
    _state.update(weather=None, news={}, seen_links={})
