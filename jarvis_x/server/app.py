"""FastAPI app: routes only. Logic lives in the modules next door."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import mimetypes
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import approvals, bus, config, crew, gmail, plugins, proactive, routines, store, voice, widgets
from .devices import lights
from .memory import autolearn, facts, search, transcripts
from .tools import comms, daily, learn, registry, system, tasks

# Windows doesn't always know these; a wrong type silently breaks ES modules and MediaPipe.
for ext, kind in ((".js", "text/javascript"), (".mjs", "text/javascript"), (".wasm", "application/wasm"),
                  (".css", "text/css"), (".json", "application/json"), (".svg", "image/svg+xml"),
                  (".task", "application/octet-stream"), (".tflite", "application/octet-stream"),
                  (".binarypb", "application/octet-stream")):
    mimetypes.add_type(kind, ext)

CHECKPOINTS = [25, 50, 85, 90, 100]
CHECKPOINT_LINES = {
    "jarvis": {25: "A quarter of today's power is spent, sir.", 50: "We are at half power, sir.",
               85: "Eighty five percent used, sir. I'd ration the deep questions.",
               90: "Ninety percent, sir. Reserve power only.", 100: "We've hit the limit, sir. I'll be back when it resets."},
    "friday": {25: "Quarter of the tank gone, boss.", 50: "Halfway through the juice, boss.",
               85: "Eighty five percent, boss. Maybe go easy.", 90: "Ninety, boss. Running on fumes.",
               100: "That's the limit, boss. See you after the reset."},
    "robin": {25: "A quarter of the candle has burned, Love.", 50: "Half the candle, Love.",
              85: "Eighty five percent, Love. Choose your questions.", 90: "Ninety, Love. Nearly dark.",
              100: "The candle is out, Love. Until the reset."},
}
state = {"usage": {"status": "unknown", "utilization": None, "resets_at": None, "limit_type": None, "updated": 0},
         "announced": [], "people": 0, "pin": "", "tokens": set(), "ready": {}, "tasks": [], "started": time.time(),
         "current": {}}


def ok(**data):
    return {"ok": True, **data}


def fail(message: str, status: int = 400):
    return JSONResponse({"ok": False, "message": message}, status_code=status)


async def reminder_loop():
    while True:
        try:
            if bus.listeners():  # only fire when a dashboard is open to speak them
                for item in tasks.pop_due():
                    bus.publish("reminder", item=item)
        except Exception:
            pass
        await asyncio.sleep(5)


async def proactive_loop():
    await asyncio.sleep(45)
    while True:
        try:
            if bus.listeners():
                proactive.check()
        except Exception:
            pass
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.load_env()
    config.ensure_dirs()
    bus.bind_loop(asyncio.get_running_loop())
    registry.load_all()
    plugins.load_enabled()
    system.clear_screens()
    if config.fake_mode():
        voice.set_synth(voice.fake_synth)
    loops = [reminder_loop(), proactive_loop(), crew.brain().prewarm()]
    if not config.fake_mode():
        loops.append(widgets.refresh_loop())
    state["tasks"] = [asyncio.create_task(c) for c in loops]
    if config.settings().get("phone_companion"):
        state["pin"] = f"{secrets.randbelow(900000) + 100000}"
    yield
    for task in state["tasks"]:
        task.cancel()
    await crew.brain().close()


app = FastAPI(title="JARVIS X", lifespan=lifespan, docs_url=None, redoc_url=None)


# ------------------------------------------------------------------ phone companion gate

def is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost", "testclient")


def is_lan(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


PHONE_OPEN = ("/m", "/api/pair", "/css/", "/src/", "/vendor/", "/favicon.ico")


@app.middleware("http")
async def gate(request: Request, call_next):
    host = request.client.host if request.client else "127.0.0.1"
    if not is_loopback(host):
        if not config.settings().get("phone_companion") or not is_lan(host):
            return JSONResponse({"ok": False, "message": "This JARVIS only answers on its own laptop."}, status_code=403)
        path = request.url.path
        paired = request.cookies.get("jx_pair") in state["tokens"]
        if not paired and not (path == "/m" or any(path.startswith(p) for p in PHONE_OPEN)):
            return JSONResponse({"ok": False, "message": "Pair this phone first: open /m and enter the PIN."}, status_code=401)
    response = await call_next(request)
    if request.url.path.startswith(("/src/", "/css/")) or request.url.path in ("/", "/m"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ------------------------------------------------------------------ pages

@app.get("/")
async def index():
    return FileResponse(config.WEB / "index.html")


@app.get("/m")
async def mobile():
    return FileResponse(config.WEB / "m.html")


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(config.WEB / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/state")
async def get_state():
    return ok(personas=crew.public_personas(), settings=config.settings(), usage=state["usage"],
              memory=facts.stats(), knowledge=len(search.files()), fake=config.fake_mode(),
              gmail=gmail.connected(), whatsapp_mode=comms.whatsapp_mode(),
              humor_labels=crew.HUMOR_LABELS, ready=state["ready"], uptime=time.time() - state["started"],
              tools=len(registry.all_tools()))


@app.get("/api/boot")
async def boot_checks():
    """Real data for the cinematic boot sequence."""
    s = config.settings()
    snap = tasks.snapshot()
    return ok(checks=[
        {"label": "Crew link", "value": "offline demo brain" if config.fake_mode() else "Claude Code login (Agent SDK)"},
        {"label": "Tools online", "value": f"{len(registry.all_tools())} tools"},
        {"label": "Long-term memory", "value": f"{facts.stats()['facts']} facts, {len(search.files())} files"},
        {"label": "Reminders", "value": f"{len(snap['reminders'])} pending, {len(snap['tasks'])} tasks"},
        {"label": "Gmail", "value": "connected" if gmail.connected() else "not connected"},
        {"label": "WhatsApp", "value": f"mode {comms.whatsapp_mode()}"},
        {"label": "Smart home", "value": f"{len(lights.registry())} light(s)"},
        {"label": "Location", "value": s["city"]},
    ])


@app.get("/api/events")
async def events(request: Request):
    queue = bus.subscribe()

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    if event["type"] == "crew_ready":
                        state["ready"][event["persona"]] = event
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ chat

def note_usage(event: dict, persona: str) -> list[dict]:
    """Track the power meter; return checkpoint announcements that are newly crossed."""
    usage = state["usage"]
    if usage.get("resets_at") and event.get("resets_at") and event["resets_at"] != usage["resets_at"]:
        state["announced"] = []
    usage.update(status=event.get("status") or usage["status"], utilization=event.get("utilization"),
                 resets_at=event.get("resets_at"), limit_type=event.get("limit_type"), updated=time.time())
    out = []
    pct = event.get("utilization")
    if pct is None and event.get("status") == "rejected":
        pct = 1.0
    if pct is not None:
        pct = pct * 100 if pct <= 1.0 else pct
        usage["percent"] = round(pct)
        crossed = [c for c in CHECKPOINTS if pct >= c and c not in state["announced"]]
        if crossed:
            state["announced"].extend(crossed)
            top = max(crossed)
            out.append({"type": "checkpoint", "value": top, "text": CHECKPOINT_LINES[persona][top]})
    else:
        usage["percent"] = None
    bus.publish("usage", usage=usage)
    return out


async def after_exchange(user_text: str, reply: str) -> None:
    try:
        await autolearn.learn(user_text, reply)
    except Exception:
        pass
    system.clear_screens()


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    persona = body.get("persona") if body.get("persona") in crew.PERSONAS else "jarvis"
    text = str(body.get("text", "")).strip()
    if not text:
        return fail("Say or type something first.")
    s = config.settings()
    humor = int(body.get("humor", s["humor"]))
    effort = body.get("effort", s["effort"])
    context = dict(body.get("context") or {})
    context.setdefault("people", state["people"])
    transcripts.log("nikesh", text, persona)
    prompt = text
    forgot = autolearn.handle_forget(text)
    if forgot is not None:
        what = "; ".join(forgot["forgot"]) or "nothing matching was stored"
        prompt += f"\n(System note: memory has already been updated. Forgotten: {what}. Confirm briefly.)"
    if body.get("silent_log"):
        pass
    brain = crew.brain()
    state["current"][persona] = time.time()

    async def gen():
        full, start, first = "", time.time(), None
        extra: list[dict] = []
        try:
            async for event in brain.stream(persona, prompt, effort, humor, context):
                if event["type"] == "usage":
                    extra.extend(note_usage(event, persona))
                    continue
                if event["type"] == "delta":
                    if first is None:
                        first = time.time() - start
                        yield f"data: {json.dumps({'type': 'timing', 'first_token_ms': round(first * 1000)})}\n\n"
                    full += event["text"]
                if event["type"] == "done":
                    full = event.get("text") or full
                    event["text"] = full
                    for cp in extra:
                        yield f"data: {json.dumps(cp)}\n\n"
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': crew.friendly_error(exc)})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'text': full})}\n\n"
        finally:
            if full.strip():
                transcripts.log(persona, full, persona)
                if forgot is None and not body.get("no_learn"):
                    asyncio.create_task(after_exchange(text, full))
                else:
                    system.clear_screens()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/stop")
async def stop(request: Request):
    body = await request.json() if await request.body() else {}
    for pid in ([body["persona"]] if body.get("persona") in crew.PERSONAS else crew.ORDER):
        await crew.brain().interrupt(pid)
    return ok()


@app.post("/api/log")
async def log_line(request: Request):
    """Lines spoken without the model (reminders, greetings) still belong in the transcript."""
    body = await request.json()
    transcripts.log(str(body.get("who", "jarvis")), str(body.get("text", "")), str(body.get("persona", "")))
    return ok()


# ------------------------------------------------------------------ voice

@app.get("/api/tts")
async def tts(persona: str = "jarvis", text: str = "", cache: int = 0):
    if persona not in crew.PERSONAS:
        persona = "jarvis"
    stream = voice.synth(persona, text[:1200], cache=bool(cache))
    try:
        first = await anext(stream)
    except (voice.VoiceError, StopAsyncIteration) as exc:
        return fail(f"Voice unavailable: {exc}", 503)

    async def body():
        yield first
        async for chunk in stream:
            yield chunk

    media = "audio/wav" if first[:4] == b"RIFF" else "audio/mpeg"
    return StreamingResponse(body(), media_type=media, headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ widgets

@app.get("/api/weather")
async def get_weather(refresh: int = 0):
    return ok(weather=await (widgets.refresh_weather() if refresh else widgets.weather()))


@app.get("/api/news")
async def get_news(refresh: int = 0, topic: str = ""):
    if topic:
        return ok(news=await (widgets.refresh_news(topic) if refresh else widgets.news(topic)))
    return ok(news=await widgets.headlines_mix(force=bool(refresh)))


# ------------------------------------------------------------------ approvals

@app.get("/api/approvals")
async def list_approvals():
    return ok(cards=[approvals.public(c) for c in approvals.pending()])


@app.post("/api/approvals/{card_id}/{action}")
async def act_on_approval(card_id: str, action: str, request: Request):
    if action not in ("approve", "cancel"):
        return fail("Unknown action.", 404)
    body = await request.json() if await request.body() else {}
    via = str(body.get("via", "click"))
    if card_id == "latest":
        card = approvals.latest_pending()
        if card is None:
            return fail("There's nothing waiting for approval.", 404)
        card_id = card["id"]
    result = await (approvals.approve(card_id, via) if action == "approve" else approvals.cancel(card_id, via))
    if result.get("ok") and action == "approve" and result.get("card", {}).get("kind") == "plugin":
        await crew.brain().refresh_tools()
    return result


# ------------------------------------------------------------------ memory + knowledge + transcripts

@app.get("/api/memory/facts")
async def memory_facts(q: str = ""):
    items = facts.search(q, 200) if q else sorted(facts.all_facts(), key=lambda f: -f.get("updated", 0))
    return ok(facts=items, stats=facts.stats(), knowledge=[p.name for p in search.files()])


@app.post("/api/memory/facts")
async def memory_add(request: Request):
    body = await request.json()
    res = facts.add(str(body.get("text", "")), str(body.get("category", "general")), source="told")
    if res["status"] == "refused":
        return fail(f"I don't store {res['reason']}.")
    return ok(**res)


@app.put("/api/memory/facts/{fact_id}")
async def memory_edit(fact_id: str, request: Request):
    body = await request.json()
    res = facts.update(fact_id, str(body.get("text", "")), body.get("category"))
    if res["status"] == "refused":
        return fail(f"I don't store {res['reason']}.")
    return ok(**res) if res["status"] == "updated" else fail("That fact no longer exists.", 404)


@app.delete("/api/memory/facts/{fact_id}")
async def memory_delete(fact_id: str):
    return ok() if facts.delete(fact_id) else fail("That fact no longer exists.", 404)


@app.post("/api/knowledge/upload")
async def knowledge_upload(file: UploadFile = File(...)):
    content = await file.read()
    if len(content) > 40 * 1024 * 1024:
        return fail("That file is over 40 MB.")
    name = file.filename or "file"
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        safe = f"drop_{int(time.time())}{ext}"
        path = config.data("uploads", safe)
        path.write_bytes(content)
        return ok(kind="image", name=name, path=str(path),
                  prompt=f"I dropped an image on the dashboard. Read this image file and tell me what it is: {path}")
    if ext not in search.SUPPORTED:
        return fail("I can read PDF, DOCX, PPTX, CSV, TXT, MD and images.")
    path = search.save_upload(name, content)
    chars = len(search.extract_text(path))
    bus.publish("memory", action="file", text=f"Added to your files: {path.name}")
    return ok(kind="file", name=path.name, chars=chars,
              prompt=f"I just added the file '{path.name}' to my knowledge folder. Search it and give me a short summary.")


@app.get("/api/transcripts")
async def get_transcripts(q: str = "", day: str = "", who: str = ""):
    if q:
        return ok(items=transcripts.search(q, 60, who, 30))
    return ok(items=transcripts.read_day(day or None), days=transcripts.days_with_data())


# ------------------------------------------------------------------ settings

@app.get("/api/settings")
async def get_settings():
    return ok(settings=config.settings())


@app.put("/api/settings")
async def put_settings(request: Request):
    return ok(settings=config.update_settings(await request.json()))


# ------------------------------------------------------------------ tasks, reminders, focus

@app.get("/api/tasks")
async def get_tasks():
    return ok(**tasks.snapshot())


@app.post("/api/tasks")
async def post_task(request: Request):
    body = await request.json()
    text = str(body.get("text", "")).strip()
    if not text:
        return fail("What's the task?")
    return ok(task=tasks.add_task_item(text))


@app.post("/api/tasks/{task_id}/done")
async def task_done(task_id: str):
    return ok() if tasks.set_task_done(task_id) else fail("Task not found.", 404)


@app.delete("/api/tasks/{task_id}")
async def task_delete(task_id: str):
    return ok() if tasks.remove("tasks", task_id) else fail("Task not found.", 404)


@app.post("/api/reminders")
async def post_reminder(request: Request):
    body = await request.json()
    text = str(body.get("text", "")).strip()
    item = tasks.create_reminder(text, str(body.get("when", "")) or text, str(body.get("repeat", "")))
    if item is None:
        return fail("I couldn't work out when. Try 'in 10 minutes' or 'tomorrow at 9'.")
    return ok(reminder=item)


@app.delete("/api/reminders/{rem_id}")
async def reminder_delete(rem_id: str):
    return ok() if tasks.remove("reminders", rem_id) else fail("Reminder not found.", 404)


@app.post("/api/focus/log")
async def focus_log(request: Request):
    body = await request.json()
    items = store.load("focus.json", [])
    items.append({"t": time.time(), "minutes": float(body.get("minutes", 0))})
    store.save("focus.json", items)
    return ok()


# ------------------------------------------------------------------ routines, brief, proactive

@app.get("/api/routines")
async def get_routines():
    return ok(routines=routines.all_routines())


@app.post("/api/routines")
async def post_routine(request: Request):
    body = await request.json()
    try:
        return ok(routine=routines.save(str(body.get("name", "")), str(body.get("trigger", "")), body.get("steps")))
    except ValueError as exc:
        return fail(str(exc))


@app.delete("/api/routines/{name}")
async def delete_routine(name: str):
    return ok() if routines.delete(name) else fail("Only your own routines can be deleted.", 404)


@app.post("/api/routines/run")
async def run_routine(request: Request):
    body = await request.json()
    routine = routines.match(str(body.get("utterance", ""))) if body.get("utterance") else routines.find(str(body.get("name", "")))
    if routine is None:
        return ok(matched=False)
    return ok(matched=True, **(await routines.run(routine["name"], publish=False)))


@app.get("/api/brief")
async def get_brief():
    today = datetime.now().strftime("%Y-%m-%d")
    seen = store.load("brief.json", {}).get("last") == today
    data = await daily.brief_data()
    return ok(first_today=not seen, brief=data, text=daily.brief_text(data))


@app.post("/api/brief/seen")
async def brief_seen():
    store.save("brief.json", {"last": datetime.now().strftime("%Y-%m-%d")})
    return ok()


@app.get("/api/recap")
async def get_recap():
    return ok(recap=daily.recap_data())


@app.post("/api/proactive/snooze")
async def proactive_snooze(request: Request):
    body = await request.json() if await request.body() else {}
    return ok(until=proactive.snooze(int(body.get("minutes", 60))))


@app.post("/api/proactive/check")
async def proactive_check():
    return ok(item=proactive.check())


# ------------------------------------------------------------------ daily-life panels

@app.get("/api/daily")
async def get_daily():
    """One call that feeds the guitar, expenses, flashcards, comic, journal and plugin panels."""
    bible = daily.comic_bible()
    journal = store.load("journal.json", [])
    return ok(guitar={"stats": daily.guitar_stats(), "chord": daily.chord_today()},
              expenses=daily.expense_summary_data(), flashcards=learn.summary(),
              comic={"title": bible["title"], "counts": {s: len(bible[s]) for s in daily.COMIC_SECTIONS}},
              journal={"count": len(journal), "latest": journal[-1] if journal else None},
              plugins=plugins.index(), lights=[lights.public(d) for d in lights.registry()],
              scenes=sorted(lights.SCENES), learn=daily.learn_today())


@app.post("/api/guitar/log")
async def guitar_log(request: Request):
    body = await request.json()
    return ok(stats=daily.log_guitar(float(body.get("minutes", 0)), str(body.get("notes", ""))))


@app.post("/api/expenses")
async def post_expense(request: Request):
    body = await request.json()
    parsed = daily.parse_expense(str(body.get("text", "")))
    if not parsed:
        return fail("Try something like '200 on lunch'.")
    return ok(expense=daily.add_expense(*parsed), summary=daily.expense_summary_data())


@app.get("/api/flashcards/due")
async def flashcards_due(deck: str = ""):
    return ok(cards=learn.due_cards(deck, 20), summary=learn.summary())


@app.post("/api/flashcards/{card_id}/grade")
async def flashcards_grade(card_id: str, request: Request):
    body = await request.json()
    card = learn.grade(card_id, int(body.get("grade", 4)))
    return ok(card=card) if card else fail("Card not found.", 404)


@app.get("/api/comic")
async def get_comic():
    return ok(bible=daily.comic_bible())


@app.post("/api/plugins/{name}/toggle")
async def plugin_toggle(name: str, request: Request):
    body = await request.json()
    try:
        found = plugins.set_enabled(name, bool(body.get("enabled")))
    except Exception as exc:
        return fail(f"The plugin failed to load: {exc}")
    if found:
        await crew.brain().refresh_tools()
    return ok() if found else fail("Plugin not found.", 404)


@app.delete("/api/plugins/{name}")
async def plugin_remove(name: str):
    found = plugins.remove(name)
    if found:
        await crew.brain().refresh_tools()
    return ok() if found else fail("Plugin not found.", 404)


# ------------------------------------------------------------------ smart home

@app.get("/api/lights")
async def get_lights():
    return ok(devices=[lights.public(d) for d in lights.registry()], scenes=sorted(lights.SCENES),
              colours=sorted(lights.COLOURS))


@app.post("/api/lights")
async def set_lights(request: Request):
    body = await request.json()
    change = {k: body[k] for k in ("on", "brightness", "kelvin", "colour") if k in body}
    if body.get("scene"):
        change = dict(lights.SCENES.get(str(body["scene"]).lower(), {}))
    if not change:
        return fail("Nothing to change.")
    try:
        return ok(device=await lights.apply(change, str(body.get("name", ""))))
    except lights.LightError as exc:
        return fail(str(exc))


@app.post("/api/lights/devices")
async def add_light(request: Request):
    try:
        return ok(device=lights.public(lights.add_device(await request.json())))
    except lights.LightError as exc:
        return fail(str(exc))


@app.delete("/api/lights/devices/{name}")
async def remove_light(name: str):
    return ok() if lights.remove_device(name) else fail("No such light.", 404)


# ------------------------------------------------------------------ vision bridge + quick tools

@app.post("/api/vision/context")
async def vision_context(request: Request):
    body = await request.json()
    state["people"] = max(0, min(20, int(body.get("people", 0))))
    return ok()


@app.post("/api/vision/snapshot")
async def vision_snapshot(file: UploadFile = File(...)):
    """Sketch to life: a webcam frame he chose to capture. Stays local; removed on the next capture."""
    for old in config.data("sketches").glob("*.jpg"):
        old.unlink(missing_ok=True)
    path = config.data("sketches", f"sketch_{int(time.time())}.jpg")
    path.write_bytes(await file.read())
    return ok(path=str(path), prompt=("I'm holding something up to the camera. Read this image file: " + str(path) +
                                      " . If it's a comic panel write the script, if it's a flowchart turn it into notes, "
                                      "if it's a handwritten list offer to add the items as tasks."))


UI_TOOLS = {"media_control", "volume", "open_app", "open_website", "light_on", "light_off", "light_brightness",
            "light_scene", "light_colour", "get_time", "chord_of_the_day"}


@app.post("/api/tool")
async def run_ui_tool(request: Request):
    """Gestures and the command palette use a small set of harmless tools directly."""
    body = await request.json()
    name = str(body.get("name", ""))
    if name not in UI_TOOLS:
        return fail("That tool can't be run from the dashboard directly.", 403)
    return ok(result=await registry.call(name, body.get("args") or {}))


# ------------------------------------------------------------------ phone companion

@app.get("/api/companion")
async def companion(request: Request):
    host = request.client.host if request.client else ""
    if not is_loopback(host):
        return fail("Only the laptop can see the pairing PIN.", 403)
    enabled = bool(config.settings().get("phone_companion"))
    if enabled and not state["pin"]:
        state["pin"] = f"{secrets.randbelow(900000) + 100000}"
    return ok(enabled=enabled, pin=state["pin"] if enabled else "", ip=local_ip(), port=config.PORT,
              listening_lan=config.HOST == "0.0.0.0", paired=len(state["tokens"]))


@app.post("/api/pair")
async def pair(request: Request):
    body = await request.json()
    if not config.settings().get("phone_companion") or not state["pin"]:
        return fail("The phone companion is switched off on the laptop.", 403)
    state.setdefault("pair_fails", 0)
    if state["pair_fails"] >= 5:
        return fail("Too many wrong PINs. Restart JARVIS on the laptop for a new PIN.", 429)
    if not secrets.compare_digest(str(body.get("pin", "")), state["pin"]):
        state["pair_fails"] += 1
        return fail("Wrong PIN.", 401)
    token = secrets.token_urlsafe(24)
    state["tokens"].add(token)
    state["pin"] = f"{secrets.randbelow(900000) + 100000}"  # one-time: a new PIN for the next device
    response = JSONResponse(ok())
    response.set_cookie("jx_pair", token, httponly=True, samesite="strict", max_age=7 * 86400)
    return response


def local_ip() -> str:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


# ------------------------------------------------------------------ static

@app.get("/models/{name}")
async def model_file(name: str):
    """MediaPipe model files: his local copies in data/models (migrated from v15 or fetched once)."""
    if name not in ("hand_landmarker.task", "blaze_face_short_range.tflite"):
        return Response(status_code=404)
    path = config.data("models", name)  # his own copy wins, then the bundled one
    if not path.exists():
        path = config.WEB / "vendor" / "mediapipe" / "models" / name
    if not path.exists():
        return Response(status_code=404)
    return FileResponse(path, media_type="application/octet-stream")


app.mount("/src", StaticFiles(directory=config.WEB / "src"), name="src")
app.mount("/css", StaticFiles(directory=config.WEB / "css"), name="css")
app.mount("/vendor", StaticFiles(directory=config.WEB / "vendor"), name="vendor")
