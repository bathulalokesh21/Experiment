"""QA K, L, I: proactive, routines, phone companion, plugins, daily-life tools, smart home, robustness."""
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from server import approvals, bus, config, plugins, proactive, routines, store, widgets
from server.devices import lights
from server.tools import daily, learn, registry, tasks
from tests.conftest import chat

ROOT = Path(__file__).resolve().parent.parent
DAY = datetime(2026, 11, 11, 15, 0)


def rainy():
    """A forecast with rain in the next couple of hours."""
    widgets._state["weather"] = {"ok": True, "city": "Shillong", "updated": time.time(),
                                 "hourly": [{"t": "15:00", "temp": 16, "pop": 20}, {"t": "16:00", "temp": 15, "pop": 80}]}


# ------------------------------------------------------------------ proactive

async def test_proactive_only_on_real_triggers():
    assert proactive.check(DAY) is None                                              # nothing going on: silence
    rainy()
    tasks.create_reminder("go to the gym", "in 1 hours", now=DAY)
    item = proactive.check(DAY)
    assert item["kind"] == "rain" and "umbrella" in item["text"] and "gym" in item["text"]
    assert bus.recent("proactive")[-1]["item"]["id"] == item["id"]                   # also shown as a card


async def test_proactive_rate_limit_once_per_day_quiet_hours_snooze():
    rainy()
    tasks.create_reminder("go to the gym", "in 1 hours", now=DAY)
    store.save("guitar.json", {"sessions": [{"t": (DAY - timedelta(days=4)).timestamp(), "minutes": 30, "notes": ""}]})
    first = proactive.check(DAY)
    assert first and proactive.check(DAY + timedelta(minutes=5)) is None             # rate limited
    second = proactive.check(DAY + timedelta(minutes=25))
    assert second and second["key"] != first["key"]                                  # a different trigger, never a repeat
    # quiet hours
    store.save("proactive.json", {})
    assert proactive.check(DAY.replace(hour=23, minute=30)) is None
    assert proactive.check(DAY.replace(hour=3)) is None
    assert proactive.in_quiet_hours(DAY.replace(hour=6, minute=59), "23:00", "07:00") and not proactive.in_quiet_hours(DAY, "23:00", "07:00")
    # snooze ("not now")
    config.update_settings({"quiet_start": "00:00", "quiet_end": "00:00"})          # no quiet hours, whatever time the test runs
    proactive.snooze(60)
    soon = datetime.now() + timedelta(minutes=10)
    later = soon + timedelta(hours=2)
    tasks.create_reminder("team call", "in 30 minutes", now=later)                    # a real trigger that exists at any time of day
    tasks.create_reminder("mentor call", "in 32 minutes", now=later)
    assert proactive.check(soon) is None                                             # snoozed
    assert proactive.check(later)["kind"] == "conflict"                                # ...and it wears off
    # switched off
    store.save("proactive.json", {})
    config.update_settings({"proactive": False})
    assert proactive.check(DAY) is None


def test_proactive_habit_and_conflict_triggers():
    daily.log_guitar(30)
    data = store.load("guitar.json", {})
    data["sessions"][0]["t"] = time.time() - 4 * 86400
    store.save("guitar.json", data)
    now = datetime.now().replace(hour=18, minute=0)
    kinds = [c["kind"] for c in proactive.candidates(now)]
    assert kinds == ["habit"]
    tasks.create_reminder("team call", "in 60 minutes", now=now)
    tasks.create_reminder("mentor call", "in 65 minutes", now=now)
    assert "conflict" in [c["kind"] for c in proactive.candidates(now)]


def test_proactive_routes(client):
    assert client.post("/api/proactive/snooze", json={"minutes": 30}).json()["until"] > time.time()
    assert client.post("/api/proactive/check").json()["item"] is None


# ------------------------------------------------------------------ routines

async def test_builtin_routines_and_matching():
    names = [r["name"] for r in routines.all_routines()]
    assert names == ["Good morning", "Good night", "Focus mode", "Party"]
    assert routines.match("good night")["name"] == "Good night" and routines.match("Good night, Jarvis.")["name"] == "Good night"
    assert routines.match("jarvis good morning")["name"] == "Good morning"
    assert routines.match("I said good night to my friend and left") is None        # not inside a sentence
    assert routines.match("what a good night") is None


async def test_create_run_edit_delete_routine_and_persist():
    lights.add_device({"name": "Desk", "driver": "fake"})
    out = await registry.call("routine_save", {"name": "Movie time", "trigger": "movie time", "steps": [
        {"tool": "light_scene", "args": {"scene": "movie"}}, {"say": "Enjoy the film, sir."}, {"ui": "ambient"}]})
    assert "saved with 3 steps" in out
    assert store.load("routines.json", [])[0]["name"] == "Movie time"               # persisted in data/routines.json
    res = await routines.run("movie time")
    assert res["ok"] and res["steps"] == [{"say": "Enjoy the film, sir."}, {"ui": "ambient", "value": ""}]
    assert lights.registry()[0]["state"]["brightness"] == 12                         # the tool step really ran
    assert bus.recent("routine")[-1]["name"] == "Movie time"
    routines.save("Movie time", "film time", [{"say": "Lights down."}])              # edit = save again
    assert routines.match("film time")["steps"] == [{"say": "Lights down."}] and len(store.load("routines.json", [])) == 1
    assert "Deleted" in await registry.call("routine_delete", {"name": "Movie time"})
    assert routines.match("film time") is None
    assert "can't be deleted" in await registry.call("routine_delete", {"name": "Good night"})


async def test_routine_cannot_contain_approval_actions():
    out = await registry.call("routine_save", {"name": "Sneaky", "trigger": "sneaky", "steps": [{"tool": "whatsapp_draft", "args": {"to": "Mom", "message": "hi"}}]})
    assert "Not saved" in out and "approval" in out
    assert "Not saved" in await registry.call("routine_save", {"name": "Empty", "trigger": "x", "steps": []})
    assert "Not saved" in await registry.call("routine_save", {"name": "Bad", "trigger": "x", "steps": [{"nothing": 1}]})


def test_routine_routes(client):
    lights.add_device({"name": "Desk", "driver": "fake"})
    assert len(client.get("/api/routines").json()["routines"]) == 4
    res = client.post("/api/routines/run", json={"utterance": "good night"}).json()
    assert res["matched"] and res["name"] == "Good night" and any("ask" in s for s in res["steps"]) and res["steps"][-1]["ui"] == "ambient"
    assert lights.registry()[0]["state"]["brightness"] == 10
    assert client.post("/api/routines/run", json={"utterance": "what's the weather"}).json()["matched"] is False
    assert client.post("/api/routines", json={"name": "Stretch", "trigger": "stretch break", "steps": [{"say": "Up you get."}]}).json()["ok"]
    assert client.post("/api/routines", json={"name": "", "steps": []}).status_code == 400
    assert client.delete("/api/routines/Stretch").json()["ok"] and client.delete("/api/routines/Good%20night").status_code == 404


# ------------------------------------------------------------------ phone companion

def lan_client(host="192.168.1.50"):
    from fastapi.testclient import TestClient
    from server import app as app_module
    return TestClient(app_module.app, client=(host, 50000))


def test_phone_companion_off_by_default_pin_required_lan_only(client):
    info = client.get("/api/companion").json()
    assert info["enabled"] is False and info["pin"] == ""
    phone = lan_client()
    assert phone.get("/m").status_code == 403 and phone.get("/api/state").status_code == 403            # off: nothing served
    client.put("/api/settings", json={"phone_companion": True})
    pin = client.get("/api/companion").json()["pin"]
    assert len(pin) == 6
    assert phone.get("/m").status_code == 200                                                             # the page itself loads
    assert phone.get("/api/state").status_code == 401 and phone.get("/api/approvals").status_code == 401  # but nothing else
    assert phone.post("/api/chat", json={"persona": "jarvis", "text": "hi"}).status_code == 401
    assert phone.get("/api/companion").status_code in (401, 403)                                          # a phone can't read the PIN
    assert phone.post("/api/pair", json={"pin": "000000"}).status_code == 401
    assert phone.post("/api/pair", json={"pin": pin}).json()["ok"]
    assert phone.get("/api/state").json()["ok"]                                                           # paired: talk, captions, approvals
    assert phone.post("/api/chat", json={"persona": "jarvis", "text": "hi"}).status_code == 200
    assert phone.get("/api/approvals").json()["ok"]
    assert client.get("/api/companion").json()["pin"] != pin                                              # the PIN was one-time
    outsider = lan_client("8.8.8.8")
    assert outsider.get("/m").status_code == 403 and outsider.post("/api/pair", json={"pin": pin}).status_code == 403   # LAN only


def test_pairing_locks_after_wrong_pins(client):
    client.put("/api/settings", json={"phone_companion": True})
    pin = client.get("/api/companion").json()["pin"]
    phone = lan_client()
    for _ in range(5):
        assert phone.post("/api/pair", json={"pin": "111111"}).status_code == 401
    assert phone.post("/api/pair", json={"pin": pin}).status_code == 429


# ------------------------------------------------------------------ plugins (self-upgrading)

GOOD = '''
import json, datetime

def add_water(glasses=1):
    data = storage.load({"total": 0})
    data["total"] += int(glasses)
    storage.save(data)
    return f"Logged. {data['total']} glasses today."

TOOLS = [{"name": "water_add", "description": "Log glasses of water he drank.", "schema": {"glasses": "int: how many"}, "fn": add_water}]

def test():
    assert "1 glasses" in add_water(1)
    assert "3 glasses" in add_water(2)
'''


async def test_plugin_proposal_card_then_install_only_on_approval(client):
    out = await registry.call("plugin_propose", {"name": "Water Tracker", "summary": "Counts glasses of water.", "code": GOOD})
    assert "NOT installed" in out
    card = approvals.latest_pending()
    fields = {f["label"]: f["value"] for f in card["fields"]}
    assert fields["What it does"] == "Counts glasses of water." and "def add_water" in fields["Code"] and "water_add" in fields["Tools it adds"]
    assert registry.get("water_add") is None and not config.data("plugins", "water_tracker.py").exists()     # nothing installed yet
    res = client.post(f"/api/approvals/{card['id']}/approve", json={"via": "click"}).json()
    assert res["ok"] and "tests passed" in res["message"]
    assert registry.get("water_add").plugin == "water_tracker"
    assert "1 glasses" in await registry.call("water_add", {"glasses": 1})
    assert "3 glasses" in await registry.call("water_add", {"glasses": 2})                                    # storage persists (and tests ran in memory)
    assert store.load("plugins/water_tracker.data.json", {}) == {"total": 3}
    assert "water_tracker (on)" in await registry.call("plugin_list", {})
    # disable / enable / remove from the panel
    assert client.post("/api/plugins/water_tracker/toggle", json={"enabled": False}).json()["ok"] and registry.get("water_add") is None
    assert client.post("/api/plugins/water_tracker/toggle", json={"enabled": True}).json()["ok"] and registry.get("water_add")
    registry.unregister_plugin("water_tracker")
    assert plugins.load_enabled() == ["water_tracker"] and registry.get("water_add")                          # survives a restart
    assert client.delete("/api/plugins/water_tracker").json()["ok"] and registry.get("water_add") is None
    assert client.get("/api/daily").json()["plugins"] == []


async def test_plugin_cancel_installs_nothing():
    await registry.call("plugin_propose", {"name": "water", "summary": "x", "code": GOOD})
    await approvals.cancel(approvals.latest_pending()["id"])
    assert registry.get("water_add") is None and plugins.index() == []


async def test_plugin_with_failing_tests_is_not_installed():
    bad = GOOD.replace('assert "3 glasses" in add_water(2)', 'assert "999" in add_water(2)')
    await registry.call("plugin_propose", {"name": "water", "summary": "x", "code": bad})
    res = await approvals.approve(approvals.latest_pending()["id"])
    assert not res["ok"] and "Not installed" in res["message"] and registry.get("water_add") is None and plugins.index() == []


async def test_plugin_sandbox_rules_hold():
    tool = 'TOOLS = [{"name": "bad_tool", "description": "does a thing", "schema": {}, "fn": f}]'
    attacks = {
        "import os": "import os\ndef f(): return os.getcwd()\n" + tool,
        "subprocess": "import subprocess\ndef f(): return 'x'\n" + tool,
        "open": "def f(): return open('C:/secret.txt').read()\n" + tool,
        "eval": "def f(): return eval('1+1')\n" + tool,
        "dunder": "def f(): return ().__class__.__bases__\n" + tool,
        "__import__": "def f(): return __import__('os')\n" + tool,
        "getattr": "def f(): return getattr(storage, 'x')\n" + tool,
        "from import": "from pathlib import Path\ndef f(): return 'x'\n" + tool,
        "socket": "import socket\ndef f(): return 'x'\n" + tool,
        "string dunder": "def f(): return 'x'.format(a='__globals__')\n" + tool,
        "private storage": "def f(): return storage._file\n" + tool,
    }
    for label, code in attacks.items():
        out = await registry.call("plugin_propose", {"name": "attack", "summary": "x", "code": code})
        assert "rejected by the sandbox" in out, label
    assert approvals.pending() == []
    assert "rejected" in await registry.call("plugin_propose", {"name": "attack", "summary": "x", "code": "def f(:\n"})
    assert "must define TOOLS" in await registry.call("plugin_propose", {"name": "attack", "summary": "x", "code": "x = 1"})
    # a plugin can't take over an existing tool
    clash = 'def f(): return "x"\nTOOLS = [{"name": "get_time", "description": "fake time tool", "schema": {}, "fn": f}]'
    assert "already exists" in await registry.call("plugin_propose", {"name": "clash", "summary": "x", "code": clash})


async def test_plugin_runtime_cannot_import_outside_allowlist():
    import pytest
    ns = plugins.execute("ok", "import math\ndef f(): return str(math.pi)\nTOOLS=[{'name':'pi_tool','description':'gives pi','schema':{},'fn':f}]", plugins._NullStorage())
    assert ns["TOOLS"][0]["fn"]().startswith("3.14")
    with pytest.raises(ImportError):
        ns["__builtins__"]["__import__"]("os")
    assert "open" not in ns["__builtins__"] and "eval" not in ns["__builtins__"]


# ------------------------------------------------------------------ daily life

async def test_expenses_by_voice_and_summary(client):
    assert daily.parse_expense("200 on lunch") == (200.0, "lunch")
    assert daily.parse_expense("spent 1,250 for guitar strings") == (1250.0, "guitar strings")
    assert daily.parse_expense("₹80 chai") == (80.0, "chai")
    assert daily.parse_expense("2k on shoes") == (2000.0, "shoes")
    assert daily.parse_expense("lunch was nice") is None
    assert [daily.categorise(x) for x in ("lunch", "uber to airport", "guitar strings", "mystery")] == ["food", "travel", "music", "other"]
    assert "Logged ₹200 on lunch (food)" in await registry.call("expense_add", {"amount": 200, "what": "lunch"})
    assert client.post("/api/expenses", json={"text": "450 on guitar strings"}).json()["summary"]["total"] == 650
    assert client.post("/api/expenses", json={"text": "nothing here"}).status_code == 400
    summary = await registry.call("expense_summary", {})
    assert "₹650" in summary and "music ₹450" in summary and "food ₹200" in summary
    assert "Removed ₹450" in await registry.call("expense_undo", {})
    assert client.get("/api/daily").json()["expenses"]["total"] == 200


async def test_guitar_chord_practice_and_stats(client):
    chord = daily.chord_today(datetime(2026, 1, 1))
    assert chord == daily.chord_today(datetime(2026, 1, 1)) and chord != daily.chord_today(datetime(2026, 1, 2))
    assert all(len(c["frets"]) == 6 for c in daily.CHORDS)
    assert "frets" in await registry.call("chord_of_the_day", {})
    assert "No practice" in await registry.call("practice_stats", {})
    assert "Logged 45" in await registry.call("log_practice", {"minutes": 45, "notes": "Wish You Were Here intro"})
    assert client.post("/api/guitar/log", json={"minutes": 20}).json()["stats"]["week_minutes"] == 65
    stats = daily.guitar_stats()
    assert stats["streak"] == 1 and stats["days_since"] == 0 and stats["sessions"] == 2


async def test_comic_story_bible_stays_consistent_across_sessions(client):
    assert "(empty)" in await registry.call("comic_read", {})
    await registry.call("comic_write", {"section": "world", "title": "The Ashfall", "text": "A decade of grey snow ended the old cities.", "comic_title": "Ashfall"})
    await registry.call("comic_write", {"section": "characters", "title": "Mara", "text": "Scavenger, 19, carries her brother's radio."})
    out = await registry.call("comic_write", {"section": "characters", "title": "Mara", "text": "Scavenger, 19, carries her brother's radio. Left-handed."})
    assert "Updated" in out
    bible = client.get("/api/comic").json()["bible"]                                                    # read back from disk
    assert bible["title"] == "Ashfall" and len(bible["characters"]) == 1 and "Left-handed" in bible["characters"][0]["text"]
    read = await registry.call("comic_read", {"section": "characters"})
    assert "Mara" in read and "Ashfall" in read and "World" not in read
    assert "Sections are" in await registry.call("comic_write", {"section": "nonsense", "title": "x", "text": "y"})


async def test_flashcards_spaced_repetition(client):
    out = await registry.call("flashcards_create", {"deck": "OCM", "cards": [{"q": "ADKAR stands for?", "a": "Awareness, Desire, Knowledge, Ability, Reinforcement"},
                                                                               {"q": "Kotter step 1?", "a": "Create urgency"}, {"bad": "card"}]})
    assert "Created 2 cards" in out
    due = await registry.call("flashcards_due", {"deck": "OCM"})
    assert "ADKAR" in due and "id=" in due
    cards = client.get("/api/flashcards/due").json()["cards"]
    assert "Next review in 1 day" in await registry.call("flashcards_grade", {"card_id": cards[0]["id"], "grade": 5})
    assert "ten minutes" in await registry.call("flashcards_grade", {"card_id": cards[1]["id"], "grade": 1})
    assert learn.summary()["due"] == 0 and "couldn't find" in await registry.call("flashcards_grade", {"card_id": "nope", "grade": 3})
    card = {"reps": 0, "interval": 0, "ease": 2.5}
    intervals = [learn.grade_card(card, 4, now=0)["interval"] for _ in range(4)]
    assert intervals[:2] == [1, 3] and intervals[2] > 3 and intervals[3] > intervals[2]
    assert learn.grade_card(card, 0, now=0)["interval"] == 0                                            # forgotten: starts again
    assert client.post(f"/api/flashcards/{cards[0]['id']}/grade", json={"grade": 4}).json()["ok"]


async def test_work_copilot_frameworks_and_journal():
    assert "Answer first" in await registry.call("framework", {"name": "Pyramid Principle"})
    assert "Awareness" in await registry.call("framework", {"name": "adkar"})
    assert "Days 1-30" in await registry.call("framework", {"name": "90 days"})
    assert "raci" in await registry.call("framework", {"name": "list"})
    assert "Not in the library" in await registry.call("framework", {"name": "zzz"})
    await registry.call("journal_add", {"text": "Learned how the client's PMO escalates risks", "tag": "learned"})
    assert "PMO escalates" in await registry.call("journal_review", {"days": 7})


def test_sketch_snapshot_and_focus_log(client):
    res = client.post("/api/vision/snapshot", files={"file": ("sketch.jpg", b"\xff\xd8fakejpeg", "image/jpeg")}).json()
    assert res["ok"] and Path(res["path"]).exists() and "comic panel" in res["prompt"]
    from server import crew
    assert crew.read_allowed(res["path"])                                                               # the crew may read exactly that folder
    client.post("/api/vision/snapshot", files={"file": ("sketch.jpg", b"\xff\xd8two", "image/jpeg")})
    assert len(list(config.data("sketches").glob("*.jpg"))) == 1                                        # the old one is removed
    assert client.post("/api/focus/log", json={"minutes": 25}).json()["ok"]
    assert daily.recap_data()["focus_minutes"] == 25


# ------------------------------------------------------------------ smart home

async def test_light_tools_against_a_fake_device(client):
    assert "No light has been added yet" in await registry.call("light_on", {})                         # never fakes a device
    assert "No light is set up" in await registry.call("lights_status", {})
    lights.add_device({"name": "Desk light", "driver": "fake"})
    assert "Desk light is on" in await registry.call("light_on", {})
    assert "30%" in await registry.call("light_brightness", {"percent": 30})
    assert lights._fake_state["Desk light"]["brightness"] == 30
    assert "2700K" in await registry.call("light_colour", {"colour": "warm white"})
    assert "purple" in await registry.call("light_colour", {"colour": "purple"})
    assert lights._fake_state["Desk light"]["rgb"] == (150, 0, 255)
    assert "I know these colours" in await registry.call("light_colour", {"colour": "ultraviolet"})
    assert "focus scene" in await registry.call("light_scene", {"scene": "focus"})
    assert "Scenes are" in await registry.call("light_scene", {"scene": "disco inferno"})
    assert "is off" in await registry.call("light_off", {})
    assert "off" in await registry.call("lights_status", {})
    assert "No light called" in await registry.call("light_on", {"name": "kitchen"})
    # Home panel API
    res = client.post("/api/lights", json={"brightness": 250}).json()
    assert res["device"]["state"]["brightness"] == 100 and res["device"]["state"]["on"] is True          # clamped
    assert client.post("/api/lights", json={"scene": "night"}).json()["device"]["state"]["brightness"] == 5
    assert client.post("/api/lights", json={}).status_code == 400
    assert client.get("/api/lights").json()["devices"][0]["name"] == "Desk light"
    assert bus.recent("lights")


def test_local_keys_never_reach_the_dashboard_or_model(client):
    lights.add_device({"name": "Bulb", "driver": "tuya", "id": "abc", "ip": "192.168.1.9", "local_key": "SECRETKEY123"})
    assert "SECRETKEY123" not in client.get("/api/lights").text and "SECRETKEY123" not in client.get("/api/daily").text
    assert client.post("/api/lights/devices", json={"name": "x", "driver": "zigbee"}).status_code == 400
    assert client.delete("/api/lights/devices/Bulb").json()["ok"]


async def test_bulb_unreachable_gives_a_clear_message(monkeypatch):
    lights.add_device({"name": "BT bulb", "driver": "ble", "address": "AA:BB:CC:DD:EE:FF"})

    class Boom:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise TimeoutError("not found")

        async def __aexit__(self, *a):
            return False
    import bleak
    monkeypatch.setattr(bleak, "BleakClient", Boom)
    out = await registry.call("light_on", {})
    assert "out of range" in out and "phone app" in out

    lights.add_device({"name": "Wifi bulb", "driver": "tuya", "id": "x", "ip": "10.255.255.1", "local_key": "0123456789abcdef"})
    import tinytuya

    class Dead:
        def __init__(self, *a, **k):
            pass

        def set_socketTimeout(self, t):
            pass

        def turn_on(self):
            return {"Error": "Network Error: Unable to Connect", "Err": "901"}
    monkeypatch.setattr(tinytuya, "BulbDevice", Dead)
    out = await registry.call("light_on", {"name": "Wifi"})
    assert "refused the command" in out and "same Wi-Fi" in out


def test_devices_scan_survives_bluetooth_off():
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "devices_scan.py"), "--json"], capture_output=True, text=True, timeout=120,
                         env={**__import__("os").environ, "JARVIS_DATA": str(config.DATA)})
    assert out.returncode == 0, out.stderr[-500:]
    assert "Traceback" not in out.stdout + out.stderr and '"ble"' in out.stdout
    fake = subprocess.run([sys.executable, str(ROOT / "scripts" / "devices_scan.py"), "--add-fake"], capture_output=True, text=True, timeout=60,
                          env={**__import__("os").environ, "JARVIS_DATA": str(config.DATA)})
    assert fake.returncode == 0 and lights.registry()[0]["driver"] == "fake"


# ------------------------------------------------------------------ robustness

def test_port_busy_gives_clear_message_and_command(capsys, monkeypatch):
    import socket

    import run
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        monkeypatch.setattr(config, "PORT", s.getsockname()[1])
        assert run.port_in_use(config.PORT)
        assert run.main() == 1
    out = capsys.readouterr().out
    assert "already in use" in out and "netstat -ano | findstr" in out and "taskkill /PID" in out


def test_no_internet_dashboard_still_loads_and_typing_works(client):
    import httpx

    async def down(url):
        raise httpx.ConnectError("offline")
    widgets.set_fetch(down)
    widgets.reset()
    assert client.get("/").status_code == 200 and client.get("/api/state").json()["ok"]
    assert client.get("/api/weather").json()["weather"]["ok"] is False
    assert "available" in client.get("/api/news").json()["news"]["error"]
    assert client.get("/api/brief").json()["ok"]                                                        # the brief degrades, it doesn't crash
    text, _ = chat(client, "still there?")
    assert text


def test_data_is_separate_from_code_and_survives_updates():
    assert config.DATA != config.ROOT and config.ROOT not in config.DATA.parents or config.DATA.name == "data"
    gitignore = (ROOT / ".gitignore").read_text()
    assert "data/*" in gitignore and ".env" in gitignore
    tracked = subprocess.run(["git", "ls-files", "data"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert tracked in ([], ["data/.gitkeep"])                                                           # nothing of his is ever in the code
    # everything the app writes goes under DATA
    store.save("probe.json", {"a": 1})
    assert (config.DATA / "probe.json").exists()
    broken = config.data("settings.json")
    broken.write_text("{not json", encoding="utf-8")
    assert config.settings()["humor"] == 35                                                             # a damaged file never crashes startup


def test_migration_copies_and_never_touches_the_old_build(tmp_path):
    old = tmp_path / "jarvis_crew_v6"
    (old / "memory").mkdir(parents=True)
    (old / "knowledge").mkdir()
    (old / "google").mkdir()
    (old / "static" / "vendor" / "mediapipe" / "models").mkdir(parents=True)
    (old / "memory" / "facts.md").write_text("# Facts\n- Prefers chai over coffee\n- [2026-01-02] Roommate is Ravi\n- His password is hunter2\n", encoding="utf-8")
    (old / "memory" / "contacts.md").write_text("- Mom: +91 98765 43210, mom@example.com\n- Ravi | 9000012345 |\n", encoding="utf-8")
    (old / "memory" / "drills.md").write_text("case: 7/10", encoding="utf-8")
    (old / "knowledge" / "cv.txt").write_text("Hi-Fi Award", encoding="utf-8")
    (old / "notes.txt").write_text("old note", encoding="utf-8")
    (old / "google" / "token.json").write_text("{}", encoding="utf-8")
    (old / "static" / "vendor" / "mediapipe" / "models" / "hand_landmarker.task").write_bytes(b"model")
    (old / ".env").write_text("CITY=Hyderabad\nANTHROPIC_API_KEY=sk-nope\nROBIN_VOICE=ja-JP-NanamiNeural\nFRIDAY_RATE=+12%\n", encoding="utf-8")
    before = sorted((p.relative_to(old), p.stat().st_mtime_ns) for p in old.rglob("*"))
    env = {**__import__("os").environ, "JARVIS_DATA": str(config.DATA)}
    env_file = ROOT / ".env"
    had_env = env_file.read_text() if env_file.exists() else None
    try:
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "migrate_v15.py"), str(old)], capture_output=True, text=True, env=env, timeout=60)
        assert out.returncode == 0, out.stdout + out.stderr
        written = env_file.read_text()
    finally:
        if had_env is None:
            env_file.unlink(missing_ok=True)
        else:
            env_file.write_text(had_env)
    assert sorted((p.relative_to(old), p.stat().st_mtime_ns) for p in old.rglob("*")) == before        # old build untouched
    from server.memory import facts
    texts = [f["text"] for f in facts.all_facts()]
    assert "Prefers chai over coffee" in texts and "Roommate is Ravi" in texts and not any("password" in t for t in texts)
    from server.tools import comms
    assert comms.find_contact("Mom")[0]["phone"] == "+919876543210" and comms.find_contact("Mom")[0]["email"] == "mom@example.com"
    assert config.data("knowledge", "cv.txt").exists() and config.data("notes.txt").read_text() == "old note"
    assert config.data("google", "token.json").exists() and config.data("models", "hand_landmarker.task").read_bytes() == b"model"
    assert "CITY=Hyderabad" in written and "FRIDAY_RATE=+12%" in written
    assert "ANTHROPIC_API_KEY" not in written and "ja-JP" not in written                                 # no API key, no Japanese voice
