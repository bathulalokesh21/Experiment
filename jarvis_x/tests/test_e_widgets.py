"""QA E: weather + headlines."""
import json

import httpx

from server import widgets
from server.tools import daily, registry, tasks


async def test_weather_from_primary_with_hourly_and_rain_timing():
    w = await widgets.refresh_weather("Shillong")
    assert w["ok"] and w["city"] == "Shillong" and w["source"] == "Open-Meteo" and w["temp"] == 17
    assert len(w["hourly"]) == 24 and w["hourly"][0]["t"] == "09:00"
    assert "Rain likely around 3 pm" in w["rain"] and "umbrella" in w["rain"]
    assert widgets._state["weather"] is w


async def test_weather_backup_used_when_primary_fails():
    async def fetch(url):
        if "open-meteo" in url:
            raise httpx.ConnectError("blocked")
        assert "wttr.in" in url
        return json.dumps({"current_condition": [{"temp_C": "19", "FeelsLikeC": "18", "humidity": "60", "windspeedKmph": "7",
                                                  "weatherDesc": [{"value": "Light rain"}]}],
                           "weather": [{"maxtempC": "22", "mintempC": "12", "hourly": [{"time": str(h * 100), "tempC": "18", "chanceofrain": "80"} for h in range(0, 24, 3)]}]})
    widgets.set_fetch(fetch)
    w = await widgets.refresh_weather("Shillong")
    assert w["ok"] and "backup" in w["source"] and w["temp"] == 19 and w["desc"] == "Light rain"


async def test_weather_error_is_plain_english_and_keeps_last_reading():
    good = await widgets.refresh_weather()

    async def down(url):
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")
    widgets.set_fetch(down)
    w = await widgets.refresh_weather()
    assert not w["ok"] and "no internet connection" in w["error"] and "two services" in w["error"]
    assert "Errno" not in w["error"] and "Traceback" not in w["error"]
    assert w["stale"]["temp"] == good["temp"]
    assert "no internet" in await registry.call("get_weather", {})

    async def cert(url):
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    widgets.set_fetch(cert)
    assert "secure connection" in (await widgets.refresh_weather())["error"]


def test_https_uses_certifi():
    import inspect
    assert "certifi.where()" in inspect.getsource(widgets.fetch)


def test_rain_summary_wording():
    dry = [{"t": f"{h:02d}:00", "temp": 20, "pop": 5} for h in range(12)]
    assert widgets.rain_summary(dry) == "No rain expected in the next 12 hours."
    now = [dict(h) for h in dry]
    now[0]["pop"], now[1]["pop"] = 90, 80
    assert widgets.rain_summary(now).startswith("Rain likely now, easing around 2 am")


async def test_headlines_mix_new_markers_and_refresh():
    n = await widgets.headlines_mix()
    assert n["ok"] and n["topics"] == ["business", "technology", "india"] and len(n["items"]) == 12
    assert {i["topic"] for i in n["items"][:3]} == {"business", "technology", "india"}               # interleaved
    assert not any(i["new"] for i in n["items"])                                                      # first load: nothing is "new"
    assert n["items"][0]["source"] == "Demo Times" and " - Demo Times" not in n["items"][0]["title"]

    async def fresh(url):
        return ("<rss><channel><item><title>Brand new launch - Wire</title><link>https://example.com/new</link></item>"
                "<item><title>Business demo headline 1 - Demo Times</title><link>https://example.com/Business/1</link></item></channel></rss>")
    widgets.set_fetch(fresh)
    again = await widgets.refresh_news("business")
    assert [i["new"] for i in again["items"]] == [True, False]


async def test_news_backup_and_plain_error():
    calls = []

    async def fetch(url):
        calls.append(url)
        if "news.google" in url:
            raise httpx.ReadTimeout("slow")
        return "<rss><channel><item><title>Backup story</title><link>https://bbc.example/1</link></item></channel></rss>"
    widgets.set_fetch(fetch)
    n = await widgets.refresh_news("technology")
    assert n["ok"] and n["source"] == "backup feed" and "bbci" in calls[1]

    async def down(url):
        raise httpx.ConnectError("x")
    widgets.set_fetch(down)
    widgets.reset()
    n = await widgets.refresh_news("business")
    assert not n["ok"] and n["error"].startswith("Headlines aren't available right now") and n["items"] == []
    assert "Headlines aren't available" in await registry.call("get_headlines", {"topic": "business"})


def test_widget_routes_and_five_minute_refresh(client):
    assert widgets.REFRESH_SECONDS == 300
    assert client.get("/api/weather").json()["weather"]["ok"]
    assert client.get("/api/weather", params={"refresh": 1}).json()["weather"]["ok"]
    assert len(client.get("/api/news").json()["news"]["items"]) == 12
    assert client.get("/api/news", params={"topic": "ai", "refresh": 1}).json()["news"]["topic"] == "ai"


def test_morning_brief_first_open_of_the_day_and_recap(client):
    tasks.create_reminder("gym session", "today at 23:59")
    tasks.add_task_item("finish SAPM report")
    res = client.get("/api/brief").json()
    assert res["first_today"] is True
    text = res["text"]
    for part in ("Weather: Shillong", "gym session", "finish SAPM report", "Headlines:", "One thing to learn today", "chord of the day"):
        assert part in text, part
    assert len(res["brief"]["headlines"]) == 3
    client.post("/api/brief/seen")
    assert client.get("/api/brief").json()["first_today"] is False
    tasks.set_task_done("SAPM")
    daily.log_guitar(40, "pentatonic")
    daily.add_expense(200, "lunch")
    recap = client.get("/api/recap").json()["recap"]
    assert recap["done"] == ["finish SAPM report"] and recap["guitar_minutes"] == 40 and recap["spent"] == 200


async def test_brief_and_recap_tools():
    assert "Weather" in await registry.call("morning_brief", {})
    assert "Completed today" in await registry.call("day_recap", {})
