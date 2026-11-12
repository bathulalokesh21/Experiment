"""QA F, G, H: the dashboard in a real Chromium, with a fake mic/camera, synthetic hands and the fake crew.

Browser: uses Playwright's own Chromium if installed, else Edge, else Chrome.
Set JARVIS_CHROMIUM=<path to a chrome/edge exe> to force one."""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parent.parent
ARGS = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required",
        "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"]
IGNORE = ("GPU stall", "WebGL: INVALID", "GL Driver Message", "willReadFrequently", "Automatic fallback to software WebGL", "GroupMarkerNotSet")


def launch(p):
    candidates = []
    if os.environ.get("JARVIS_CHROMIUM"):
        candidates.append({"executable_path": os.environ["JARVIS_CHROMIUM"]})
    for found in sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome")):
        candidates.append({"executable_path": str(found)})
    candidates += [{}, {"channel": "msedge"}, {"channel": "chrome"}]
    last = None
    for option in candidates:
        try:
            return p.chromium.launch(args=ARGS, **option)
        except Exception as exc:
            last = exc
    pytest.skip(f"No Chromium, Edge or Chrome could be started for the dashboard tests ({last})")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    data = tmp_path_factory.mktemp("dash_data")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "JARVIS_FAKE": "1", "JARVIS_DATA": str(data), "JARVIS_PORT": str(port), "WHATSAPP_MODE": "web"}
    proc = subprocess.Popen([sys.executable, str(ROOT / "run.py"), "--no-browser"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            break
        except OSError:
            time.sleep(0.25)
    else:
        proc.kill()
        pytest.fail("the JARVIS server did not start: " + proc.stdout.read().decode()[-800:])
    yield {"url": url, "data": data}
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = launch(p)
        yield b
        b.close()


class Dash:
    def __init__(self, browser, server, width=1440, height=900, query="autoboot&fast&nobrief"):
        self.server = server
        self.ctx = browser.new_context(viewport={"width": width, "height": height}, permissions=["camera", "microphone"])
        self.page = self.ctx.new_page()
        self.errors, self.requests = [], []
        self.page.on("console", lambda m: self.errors.append(m.text) if m.type == "error" and not any(x in m.text for x in IGNORE) else None)
        self.page.on("pageerror", lambda e: self.errors.append(f"PAGEERROR {e}"))
        self.page.on("response", lambda r: self.errors.append(f"HTTP {r.status} {r.url}") if r.status >= 400 and "/api/approvals/latest" not in r.url else None)
        self.page.on("request", lambda r: self.requests.append(r))
        self.page.request.put(f"{server['url']}/api/settings", data=json.dumps({"active": "jarvis", "humor": 35, "effort": "auto", "interrupt": True, "sound": True}),
                              headers={"Content-Type": "application/json"})   # the server is shared between tests: start each from the defaults
        self.page.goto(f"{server['url']}/?{query}")
        self.page.wait_for_selector("body[data-ready='1']", timeout=30000)
        if "autoboot" in query:
            self.page.wait_for_function("JX.state.booted && !JX.state.speaking && !JX.state.busy", timeout=30000)

    def js(self, code, arg=None):
        return self.page.evaluate(code, arg)

    def idle(self, timeout=30000):
        self.page.wait_for_function("!JX.state.speaking && !JX.state.busy", timeout=timeout)

    def ask(self, text, wait=True):
        self.page.fill("#talk-input", text)
        self.page.press("#talk-input", "Enter")
        if wait:
            self.page.wait_for_function("JX.state.busy || JX.state.speaking || true")
            self.page.wait_for_timeout(150)
            self.idle()

    def convo(self):
        return self.js("[...document.querySelectorAll('#convo .line')].map(l => l.textContent)")

    def api(self, method, path, body=None):
        res = self.page.request.fetch(self.server["url"] + path, method=method, data=json.dumps(body) if body is not None else None,
                                      headers={"Content-Type": "application/json"})
        return res.json()

    def close(self):
        self.ctx.close()


@pytest.fixture
def dash(browser, server):
    d = Dash(browser, server)
    yield d
    errors = list(d.errors)
    d.close()
    assert errors == [], f"JavaScript/console/network errors during the test: {errors[:6]}"


FEED = """async ([pose, frames, opts]) => {
  const G = JX.gestures; let t = performance.now() / 1000 + 1000 * Math.random();
  const out = [];
  for (let i = 0; i < frames; i++) {
    t += 1 / 20;
    const k = i / Math.max(1, frames - 1);
    const hand = G.synthHand(pose, { cx: (opts.cx ?? 0.5) + (opts.dx ?? 0) * k, cy: (opts.cy ?? 0.5) + (opts.dy ?? 0) * k, size: opts.size ?? 0.2 });
    const hands = opts.two ? [hand, G.synthHand(pose, { cx: 0.2 - (opts.spread ?? 0) * k, cy: 0.5 })] : [hand];
    for (const ev of JX.vision.feed(hands, t)) out.push(ev.type);
  }
  JX.vision.feed([], t + 1); JX.vision.feed([], t + 1.1); JX.vision.feed([], t + 1.2); JX.vision.feed([], t + 1.3); JX.vision.feed([], t + 1.4); JX.vision.feed([], t + 1.5);
  JX.vision.engine.reset();
  return out;
}"""


# ---------------------------------------------------------------- H. layout: nothing hidden at any size

@pytest.mark.parametrize("width,height", [(1920, 1080), (1440, 900), (1366, 768)])
def test_loads_clean_and_every_panel_is_reachable(browser, server, width, height):
    d = Dash(browser, server, width, height)
    d.page.wait_for_function("[...document.querySelectorAll('.card, .panel')].every(n => +getComputedStyle(n).opacity > 0.99)", timeout=60000)   # power-on stagger finished
    info = d.js("""() => {
      const out = { panels: [], overflowX: document.documentElement.scrollWidth > innerWidth + 1, overflowY: document.documentElement.scrollHeight > innerHeight + 1 };
      for (const node of document.querySelectorAll('.card, .panel, #holo-wrap, #captions, #talkbar')) {
        node.scrollIntoView({ block: 'nearest' });
        const r = node.getBoundingClientRect(); const cs = getComputedStyle(node);
        out.panels.push({ id: node.id, visible: r.width > 60 && r.height > 20 && cs.display !== 'none' && cs.visibility !== 'hidden' && +cs.opacity > 0.9,
          inView: r.top >= -1 && r.left >= -1 && r.right <= innerWidth + 1 && r.top < innerHeight - 10 });
      }
      out.colsScroll = [...document.querySelectorAll('.col')].map(c => getComputedStyle(c).overflowY);
      out.holo = document.querySelector('#holo').getBoundingClientRect().height;
      return out; }""")
    assert len(info["panels"]) >= 24
    hidden = [p["id"] for p in info["panels"] if not (p["visible"] and p["inView"])]
    assert hidden == [], f"hidden or unreachable at {width}x{height}: {hidden}"
    assert not info["overflowX"] and not info["overflowY"], "the page itself must not scroll; the columns do"
    assert info["colsScroll"] == ["auto", "auto"]
    assert info["holo"] > 250, "the hologram keeps real space"
    assert d.js("JX.holo.stats().mode") == "webgl"
    assert d.errors == [], d.errors[:5]
    d.close()


def test_boot_sequence_real_checks_and_greeting(dash):
    lines = dash.js("[...document.querySelectorAll('#boot-lines li')].map(l => l.textContent)")
    assert any("Tools online" in ln and "tools" in ln for ln in lines) and any("Microphone" in ln for ln in lines)
    assert dash.js("document.querySelector('#boot').classList.contains('gone')")
    assert dash.js("document.body.classList.contains('powering')") is False
    assert "Welcome home, sir." in dash.convo()[0]
    assert dash.js("JX.holo.assembleTarget") == 1                       # the hologram assembled from light


def test_typed_chat_streams_speaks_and_captions_word_by_word(dash):
    dash.ask("tell me something", wait=False)
    dash.page.wait_for_function("JX.state.speaking && document.querySelectorAll('#caption-text .w').length > 3", timeout=15000)
    assert dash.js("document.querySelector('#caption-speaker').textContent") == "JARVIS"
    assert dash.js("JX.state.mode") == "speak" and dash.js("document.body.dataset.state") == "speak"
    dash.page.wait_for_function("(() => { const w = [...document.querySelectorAll('#caption-text .w')]; const on = w.filter(x => x.classList.contains('on')).length; return on > 0 && on < w.length; })()", timeout=5000)
    dash.idle()
    convo = dash.convo()
    assert convo[-2].startswith("YOU") and "tell me something" in convo[-2] and convo[-1].startswith("JARVIS") and "sir" in convo[-1]
    timing = dash.js("JX.state.timings.last")
    assert timing["persona"] == "jarvis" and timing["firstAudio"] > 0 and timing["firstToken"] >= 0
    tts = [r.url for r in dash.requests if "/api/tts" in r.url and "Understood" in r.url]
    assert tts and "Understood%2C" in tts[0] and "demo" not in tts[0], "the first clause is spoken on its own, as soon as it arrives"


def test_latency_debug_overlay(dash):
    dash.ask("quick one")
    dash.page.keyboard.press("Control+Shift+D")
    dash.page.wait_for_function("document.querySelector('#debug').textContent.includes('first audio')")
    text = dash.js("document.querySelector('#debug').textContent")
    assert "fps" in text and "particles" in text and "jarvis" in text
    dash.page.keyboard.press("Control+Shift+D")
    assert dash.js("document.querySelector('#debug').hidden")


def test_wake_words_mishearings_and_mid_sentence_switch(dash):
    assert dash.js("JX.text.parseWake('hey jarvus what is the time')") == {"persona": "jarvis", "rest": "what is the time", "index": 4}
    for heard, who in [("travis open youtube", "jarvis"), ("fry day play music", "friday"), ("robyn read this", "robin"), ("ruben are you there", "robin"),
                       ("freddy what's up", "friday"), ("okay javis", "jarvis")]:
        assert dash.js("t => JX.text.parseWake(t).persona", heard) == who, heard
    assert dash.js("JX.text.parseWake('what a lovely service at the hotel')") is None
    assert dash.js("JX.text.parseWake('just talking to myself')") is None
    # a name alone opens a listening window; then no wake word is needed
    dash.js("JX.hear('Friday', true)")
    assert dash.js("JX.state.persona") == "friday" and dash.js("JX.speech.capturing")
    dash.js("JX.hear('what is two plus two', true)")
    dash.page.wait_for_timeout(200)
    dash.idle()
    assert dash.convo()[-1].startswith("FRIDAY") and "boss" in dash.convo()[-1]
    # follow-up window: no wake word needed right after an answer
    dash.js("JX.hear('and one more thing', true)")
    dash.page.wait_for_timeout(200)
    dash.idle()
    assert "and one more thing" in dash.convo()[-2]
    # another name mid-answer switches assistant and passes on the rest of the sentence
    dash.ask("please talk for a little while about anything you like so I can interrupt you", wait=False)
    dash.page.wait_for_function("JX.state.speaking")
    dash.js("JX.hear('actually robin tell me a poem', true)")
    dash.page.wait_for_timeout(300)
    dash.idle()
    assert dash.js("JX.state.persona") == "robin"
    assert "tell me a poem" in dash.convo()[-2] and dash.convo()[-1].startswith("ROBIN") and "Love" in dash.convo()[-1]
    # with no name and no window, chatter in the room is ignored
    dash.js("JX.speech.cancelCapture()")
    before = len(dash.convo())
    dash.js("JX.hear('pass me the salt please', true)")
    dash.page.wait_for_timeout(400)
    assert len(dash.convo()) == before


def test_barge_in_echo_filter_and_toggle(dash):
    long = "please talk for a little while about anything you like so that I have time to interrupt you properly"
    # 1. its own voice coming back through the mic is ignored
    dash.ask(long, wait=False)
    dash.page.wait_for_function("JX.state.speaking && JX.state.currentReply.length > 20")
    dash.js("JX.hear(JX.state.currentReply.split(' ').slice(2, 9).join(' '), true)")
    dash.page.wait_for_timeout(250)
    assert dash.js("JX.state.speaking"), "echo of its own voice must not interrupt"
    dash.js("JX.hear('hmm', true)")
    assert dash.js("JX.state.speaking"), "a short noise is not an interruption"
    # 2. "stop" interrupts
    dash.js("JX.hear('stop', true)")
    dash.page.wait_for_function("!JX.state.speaking && JX.state.mode !== 'speak'", timeout=3000)
    # 3. three or more words interrupt and become the next request
    dash.ask(long, wait=False)
    dash.page.wait_for_function("JX.state.speaking")
    dash.js("JX.hear('no wait tell me the weather instead', true)")
    dash.page.wait_for_timeout(300)
    dash.idle()
    assert "tell me the weather instead" in dash.convo()[-2]
    # 4. toggle off: nothing interrupts
    dash.page.uncheck("#interrupt-toggle")
    dash.page.wait_for_function("JX.state.settings.interrupt === false")
    dash.ask(long, wait=False)
    dash.page.wait_for_function("JX.state.speaking")
    dash.js("JX.hear('stop', true); JX.hear('please be quiet right now', true)")
    dash.page.wait_for_timeout(300)
    assert dash.js("JX.state.speaking"), "with the toggle off it keeps talking"
    dash.page.keyboard.press("Escape")                                   # Esc always stops
    dash.page.wait_for_function("!JX.state.speaking")
    dash.page.check("#interrupt-toggle")
    assert dash.js("JX.text.bargeIn('wait', '', true).interrupt") and not dash.js("JX.text.bargeIn('wait', '', false).interrupt")


def test_instant_acknowledgement_when_first_words_are_slow(dash):
    dash.ask("!slow think hard", wait=False)
    dash.page.wait_for_function("JX.state.speaking", timeout=4000)       # the ack starts speaking before the answer exists
    assert dash.js("JX.state.currentReply") == ""
    dash.page.wait_for_timeout(300)
    dash.idle()
    acks = dash.js("JX.state.personas[0].acks")
    asked = [r.url for r in dash.requests if "/api/tts" in r.url and "cache=1" in r.url]
    from urllib.parse import unquote
    assert any(unquote(u.split("text=")[1].split("&")[0]) in acks for u in asked)
    assert "Sorry for the wait" in dash.convo()[-1]
    # a fast answer gets no acknowledgement
    n = len([r for r in dash.requests if "/api/tts" in r.url])
    dash.ask("fast one")
    new = [r.url for r in dash.requests if "/api/tts" in r.url][n:]
    assert not any("cache=1" in u for u in new)


# ---------------------------------------------------------------- approvals: click, voice, gesture

PLUGIN = '''def hello(name="you"):
    return "Hello " + str(name)

TOOLS = [{"name": "TOOLNAME", "description": "Says hello to someone.", "schema": {"name": "str: who"}, "fn": hello}]

def test():
    assert hello("x") == "Hello x"
'''


def propose(dash, name):
    payload = json.dumps({"name": name, "summary": f"Adds {name}.", "code": PLUGIN.replace("TOOLNAME", name + "_hello")})
    dash.ask("!plugin_propose " + payload)
    dash.page.wait_for_selector(".approval")


def test_approval_card_approve_by_click_voice_and_thumbs_up(dash):
    propose(dash, "alpha")
    card = dash.page.locator(".approval")
    assert "New ability: alpha" in card.inner_text() and "def hello" in card.inner_text() and "Sandboxed" in card.inner_text()
    assert dash.api("GET", "/api/daily")["plugins"] == []                # nothing installed before approval
    card.locator(".approve-btn").click()
    dash.page.wait_for_function("document.querySelectorAll('.approval').length === 0", timeout=20000)
    dash.idle()
    assert [p["name"] for p in dash.api("GET", "/api/daily")["plugins"]] == ["alpha"]
    assert "Installed 'alpha'" in dash.convo()[-1]
    propose(dash, "bravo")                                               # by voice: "send it"
    dash.js("JX.hear('Jarvis, send it', true)")
    dash.page.wait_for_function("document.querySelectorAll('.approval').length === 0", timeout=20000)
    dash.idle()
    propose(dash, "charlie")                                             # by gesture: thumbs up
    events = dash.js(FEED, ["thumbs_up", 20, {}])
    assert events == ["approve"]
    dash.page.wait_for_function("document.querySelectorAll('.approval').length === 0", timeout=20000)
    dash.idle()
    assert sorted(p["name"] for p in dash.api("GET", "/api/daily")["plugins"]) == ["alpha", "bravo", "charlie"]
    assert dash.page.locator("#plugin-list .item").count() == 3          # the Abilities panel lists them


def test_approval_cancel_by_click_voice_and_thumbs_down(dash):
    for how in ("click", "voice", "gesture"):
        propose(dash, "delta_" + how)
        if how == "click":
            dash.page.locator(".approval .cancel-btn").click()
        elif how == "voice":
            dash.js("JX.hear('Jarvis cancel', true)")
        else:
            assert dash.js(FEED, ["thumbs_down", 20, {}]) == ["cancel"]
        dash.page.wait_for_function("document.querySelectorAll('.approval').length === 0", timeout=10000)
        dash.idle()
    assert not [p for p in dash.api("GET", "/api/daily")["plugins"] if p["name"].startswith("delta")]
    assert dash.js("JX.text.quickCommand('send it', {hasApproval: false})") is None      # "send it" means nothing without a card


def test_whatsapp_card_shows_masked_number_and_full_text(dash):
    dash.ask('!contact_save {"name": "Mom", "phone": "9876543210"}')
    dash.ask('!whatsapp_draft {"to": "Mom", "message": "Reached the hostel safely."}')
    dash.page.wait_for_selector(".approval")
    text = dash.page.locator(".approval").inner_text()
    assert "WhatsApp to Mom" in text and "Reached the hostel safely." in text and "9876543210" not in text and "210" in text
    assert "NOT sent" in dash.convo()[-1]
    dash.page.locator(".approval .cancel-btn").click()
    dash.page.wait_for_function("document.querySelectorAll('.approval').length === 0")
    dash.idle()


# ---------------------------------------------------------------- G. vision

def test_every_gesture_from_synthetic_landmarks(dash):
    poses = dash.js("['open','fist','point','two','three','rock','thumbs_up','thumbs_down','pinch','ok'].map(p => [p, [0.12, 0.2, 0.32].map(s => JX.gestures.classify(JX.gestures.synthHand(p, {size: s})).pose)])")
    for pose, got in poses:
        assert got == [pose] * 3, (pose, got)                            # works near and far from the camera
    assert dash.js(FEED, ["open", 20, {}]) == ["stop"]
    assert dash.js(FEED, ["point", 22, {}]) == ["listen"]
    assert dash.js(FEED, ["rock", 20, {}]) == ["party"]
    assert dash.js(FEED, ["ok", 18, {}]) == ["confirm"]
    assert dash.js(FEED, ["two", 8, {"cx": 0.7, "dx": -0.4}]) == ["switch_next"]
    assert dash.js(FEED, ["two", 8, {"cx": 0.3, "dx": 0.4}]) == ["switch_prev"]
    assert dash.js(FEED, ["three", 8, {"cy": 0.7, "dy": -0.35}])[0] == "volume_up"
    assert dash.js(FEED, ["three", 8, {"cy": 0.3, "dy": 0.35}])[0] == "volume_down"
    rot = dash.js(FEED, ["pinch", 14, {"dx": 0.2}])
    assert set(rot) == {"rotate"} and len(rot) > 5
    zoom = dash.js(FEED, ["pinch", 12, {"two": True, "dx": 0.15, "spread": 0.1}])
    assert set(zoom) == {"zoom"}


def test_gesture_hysteresis_cooldowns_and_no_false_swipes(dash):
    out = dash.js("""() => {
      const G = JX.gestures, r = {};
      const run = (frames, e = new G.GestureEngine()) => { const ev = []; frames.forEach(([pose, o, t]) => ev.push(...e.update({ t, hands: pose ? [G.synthHand(pose, o)] : [] }).map(x => x.type))); return ev; };
      const seq = (pose, n, f = () => ({}), t0 = 0, dt = 0.05) => Array.from({ length: n }, (_, i) => [pose, f(i / (n - 1)), t0 + i * dt]);
      r.slowDrift = run(seq('two', 60, k => ({ cx: 0.7 - 0.4 * k })));                    // 3 s to cross: not a flick
      r.flicker = run(Array.from({ length: 30 }, (_, i) => [i % 2 ? 'open' : 'fist', {}, i * 0.05]));   // pose flickering: nothing fires
      r.tooShort = run(seq('thumbs_up', 6));                                               // 0.25 s: not held long enough
      const e = new G.GestureEngine();
      r.holdOnce = run(seq('open', 60), e);                                                // held 3 s: fires once, not repeatedly
      r.cooldown = run([...seq('fist', 20, undefined, 3.1), ...seq('open', 8, undefined, 4.2)], e);   // "stop" is still cooling down
      r.dropout = run([...seq('thumbs_up', 8), [null, {}, 0.42], ...seq('thumbs_up', 8, undefined, 0.45)]);   // one lost frame doesn't reset the hold
      r.wave = run(Array.from({ length: 30 }, (_, i) => ['open', { cx: 0.5 + 0.12 * Math.sin(i * 0.9) }, i * 0.05]));
      const far = new G.GestureEngine({ refSize: 0.1 });                                   // calibrated for a small/far hand
      r.calibratedFar = run(seq('two', 12, k => ({ cx: 0.7 - 0.36 * k, size: 0.1 })), far);   // a clear flick at his distance
      r.nearSmall = run(seq('two', 12, k => ({ cx: 0.7 - 0.36 * k, size: 0.4 })));            // same motion with the hand at the lens: too small to count
      const hud = new G.GestureEngine(); run(seq('open', 9), hud); r.hud = hud.hud;
      return r; }""")
    assert out["slowDrift"] == [] and out["flicker"] == [] and out["tooShort"] == []
    assert out["holdOnce"] == ["stop"]
    assert out["cooldown"] == ["mute"]
    assert out["dropout"] == ["approve"]
    assert "wave" in out["wave"] and "stop" not in out["wave"]
    assert out["calibratedFar"] == ["switch_next"] and out["nearSmall"] == []
    assert out["hud"]["pose"] == "open" and 0.3 < out["hud"]["progress"] < 1 and "stop" in out["hud"]["label"]


def test_gestures_drive_the_dashboard(dash):
    assert dash.js("JX.state.persona") == "jarvis"
    dash.js(FEED, ["two", 8, {"cx": 0.7, "dx": -0.4}])
    assert dash.js("JX.state.persona") == "friday" and dash.js("document.body.dataset.persona") == "friday"
    morph = dash.js("JX.holo.stats().morph")
    assert morph < 1, "switching is a morph, not a cut"
    dash.page.wait_for_function("JX.holo.stats().morph === 1", timeout=8000)
    dash.js(FEED, ["two", 8, {"cx": 0.3, "dx": 0.4}])
    assert dash.js("JX.state.persona") == "jarvis"
    dash.js(FEED, ["fist", 22, {}])
    assert dash.js("JX.state.muted") and dash.js("document.querySelector('#mic-mute').textContent") == "Unmute"
    dash.js("JX.hear('jarvis hello', true)")
    assert not dash.js("JX.state.busy"), "muted: it does not listen"
    dash.js(FEED, ["fist", 22, {}])
    assert not dash.js("JX.state.muted")
    dash.js(FEED, ["point", 22, {}])
    assert dash.js("JX.speech.capturing")
    dash.js("JX.speech.cancelCapture()")
    dash.ask("please talk for a little while about anything you like so I can stop you with my palm", wait=False)
    dash.page.wait_for_function("JX.state.speaking")
    dash.js(FEED, ["open", 20, {}])
    dash.page.wait_for_function("!JX.state.speaking")
    dash.js(FEED, ["rock", 20, {}])
    assert dash.js("document.body.classList.contains('party')") and dash.js("JX.holo.party")
    dash.idle()
    dash.js("JX.protocols.setParty(false)")
    before = dash.js("JX.holo.spin[0] + JX.holo.spinVel[0]")
    dash.js(FEED, ["pinch", 14, {"dx": 0.25}])
    assert dash.js("JX.holo.spin[0] + JX.holo.spinVel[0]") != before
    dash.js(FEED, ["pinch", 12, {"two": True, "dx": 0.2, "spread": 0.15}])
    assert dash.js("JX.holo.zoomTarget") > 1.05
    n = len([r for r in dash.requests if r.url.endswith("/api/tool")])
    dash.js(FEED, ["three", 8, {"cy": 0.7, "dy": -0.35}])
    dash.page.wait_for_timeout(300)
    tool = [r for r in dash.requests if r.url.endswith("/api/tool")][n:]
    assert tool and json.loads(tool[0].post_data)["name"] == "volume" and json.loads(tool[0].post_data)["args"]["action"] == "up"


def test_air_cursor_clicks_dashboard_buttons_and_hud(dash):
    dash.page.check("#air-toggle")
    clicked = dash.js("""() => {
      const G = JX.gestures; const target = document.querySelector('[data-focus="50"]').getBoundingClientRect();
      const tx = (target.left + target.width / 2) / innerWidth, ty = (target.top + target.height / 2) / innerHeight;
      // invert the cursor mapping (mirrored, with margins) to find where the fingertip must be
      const fx = 1 - (tx * 0.7 + 0.15), fy = ty * 0.6 + 0.15;
      let t = 50; const place = (pose) => { const h = G.synthHand(pose, { cx: 0.5, cy: 0.5 }); const dx = fx - h[8].x, dy = fy - h[8].y; return h.map(p => ({ x: p.x + dx, y: p.y + dy, z: 0 })); };
      const events = [];
      for (let i = 0; i < 40; i++) { t += 0.05; events.push(...JX.vision.feed([place('point')], t).map(e => e.type)); }
      const cur = document.querySelector('#air-cursor').getBoundingClientRect();
      for (let i = 0; i < 6; i++) { t += 0.05; events.push(...JX.vision.feed([place('pinch')], t).map(e => e.type)); }
      return { events: [...new Set(events)], near: Math.hypot(cur.left + 11 - (target.left + target.width / 2), cur.top + 11 - (target.top + target.height / 2)), hidden: document.querySelector('#air-cursor').hidden,
               hud: document.querySelector('#hud-label').textContent }; }""")
    assert "cursor" in clicked["events"] and "click" in clicked["events"] and "listen" not in clicked["events"]
    assert clicked["near"] < 40 and not clicked["hidden"] and clicked["hud"] == "air mouse"
    assert dash.js("document.querySelector('#focus-time').textContent") == "50:00", "the pinch clicked the 50-minute button"
    dash.page.uncheck("#air-toggle")


def test_presence_greets_once_dims_when_away_counts_people(dash):
    out = dash.js("""() => {
      const P = new JX.PresenceTracker(); const ev = []; const feed = (n, from, to, step = 0.5) => { for (let t = from; t <= to; t += step) ev.push(...P.update(n, t).map(e => e.type + (e.count != null ? e.count : ''))); };
      feed(0, 0, 20); feed(1, 20.5, 60); feed(0, 60.5, 70); feed(1, 70.5, 80);      // sits down, glances away, comes back
      const afterFirst = [...ev]; ev.length = 0;
      feed(0, 80.5, 400); const away = [...ev]; ev.length = 0;                      // gone for 5+ minutes
      feed(1, 400.5, 410); const back = [...ev]; ev.length = 0;
      feed(2, 410.5, 411); const blip = [...ev]; ev.length = 0;                      // a half-second false detection
      feed(1, 411.5, 415); feed(2, 415.5, 425); const friend = [...ev];
      return { afterFirst, away, back, blip, friend }; }""")
    assert out["afterFirst"].count("arrive") == 1, "greets on sit-down exactly once per session"
    assert "away" in out["away"] and out["back"].count("return") == 1 and "arrive" not in out["back"]
    assert out["blip"] == [] and out["friend"] == ["people2", "friend2"]
    # integration: away dims and stops listening; return restores; people count goes to the crew
    dash.js("""() => { let t = 5000; for (let i = 0; i < 12; i++) JX.vision.handleFaces(1, t += 0.5); for (let i = 0; i < 620; i++) JX.vision.handleFaces(0, t += 0.5); }""")
    assert dash.js("document.body.classList.contains('dim')") and dash.js("JX.state.muted")
    dash.js("() => { let t = 6000; for (let i = 0; i < 8; i++) JX.vision.handleFaces(2, t += 0.5); }")
    assert not dash.js("document.body.classList.contains('dim')") and not dash.js("JX.state.muted")
    assert dash.js("JX.state.people") == 2 and "People in view: 2" in dash.js("document.querySelector('#people-count').textContent")
    dash.ask("who is here")
    body = [json.loads(r.post_data) for r in dash.requests if r.url.endswith("/api/chat")][-1]
    assert body["context"]["people"] == 2


def test_camera_first_then_local_mediapipe_and_calibration(dash):
    order = []
    dash.page.on("request", lambda r: order.append(r.url) if ("/vendor/mediapipe" in r.url or "/models/" in r.url) else None)
    dash.page.click("#cam-toggle")
    dash.page.wait_for_function("document.querySelector('#cam').srcObject && document.querySelector('#cam').videoWidth > 0", timeout=15000)
    dash.page.wait_for_function("JX.state.cameraOn && document.querySelector('#cam-off').hidden", timeout=15000)   # the preview shows first
    dash.page.wait_for_function("/Vision ready|failed/.test(document.querySelector('#cam-status').textContent)", timeout=90000)
    status = dash.js("document.querySelector('#cam-status').textContent")
    assert "Vision ready" in status, status
    assert any("vision_bundle.mjs" in u for u in order) and any("vision_wasm_internal.wasm" in u for u in order)
    assert any("hand_landmarker.task" in u for u in order) and any("blaze_face_short_range.tflite" in u for u in order)
    assert all(u.startswith(dash.server["url"]) for u in order), "MediaPipe and its models are served locally, never from a CDN"
    assert not dash.js("document.querySelector('#gesture-hud').hidden")
    # calibration learns his hand size and saves it
    dash.js("JX.vision.beginCalibration(); let t = 9000; for (let i = 0; i < 30; i++) JX.vision.feed([JX.gestures.synthHand('open', {size: 0.26})], t += 0.05)")
    size = dash.js("JX.vision.finishCalibration()")
    assert abs(size - 0.26) < 0.01 and abs(dash.js("JX.vision.engine.refSize") - 0.26) < 0.01
    dash.page.wait_for_timeout(300)
    assert abs(dash.api("GET", "/api/settings")["settings"]["calibration"]["size"] - 0.26) < 0.01
    dash.page.click("#cam-toggle")
    assert not dash.js("JX.state.cameraOn") and "Turn on" in dash.js("document.querySelector('#cam-toggle').textContent")


def test_camera_blocked_gives_a_clear_step_message(browser, server):
    ctx = browser.new_context(viewport={"width": 1366, "height": 768}, permissions=[])
    page = ctx.new_page()
    page.goto(f"{server['url']}/?autoboot&fast&nobrief")
    page.wait_for_selector("body[data-ready='1']")
    page.evaluate("() => { navigator.mediaDevices.getUserMedia = () => Promise.reject(Object.assign(new Error('denied'), { name: 'NotAllowedError' })); }")
    page.click("#cam-toggle")
    page.wait_for_function("document.querySelector('#cam-status').textContent.includes('Step 1 failed')")
    assert "lock icon" in page.evaluate("document.querySelector('#cam-status').textContent")
    ctx.close()


# ---------------------------------------------------------------- F. living assistants

def test_hologram_forms_states_and_audio_reactivity(dash):
    assert dash.js("JX.holo.stats().mode") == "webgl"
    frames = dash.js("JX.holo.frames")
    dash.page.wait_for_function("f => JX.holo.frames > f + 2", arg=frames, timeout=20000)      # it keeps animating while idle
    for mode, index in (("listen", 0), ("think", 1), ("speak", 2), ("notice", 3)):
        dash.js("m => JX.holo.setState(m)", mode)
        dash.page.wait_for_function("i => JX.holo.stateW[i] > 0.6", arg=index, timeout=20000)
        assert dash.js("JX.holo.stats().state") == mode
    dash.js("JX.setMode('think'); JX.setMode('idle')")
    assert dash.js("JX.holo.stats().state") == "idle"                    # the conversation state drives the hologram
    # speaking is driven by the actual audio: the level uniform follows what the analyser hears
    assert dash.js("JX.holo.uniforms.uLevel.value") < 0.05
    dash.js("JX.holo.testFeatures = {out: {level: 0.7, bands: [0.6, 0.7, 0.4, 0.2], onset: 0.8}, mic: {level: 0.5, bands: [0.3, 0.3, 0.2, 0.1]}}")
    dash.page.wait_for_function("JX.holo.uniforms.uLevel.value > 0.6 && JX.holo.uniforms.uOnset.value > 0.7 && JX.holo.uniforms.uMic.value > 0.4")
    dash.js("JX.holo.testFeatures = null")
    # breathing is not a fixed loop: its rate drifts
    rates = dash.js("(async () => { const r = new Set(); for (let i = 0; i < 6; i++) { JX.holo.nextBreathShift = 0; const f = JX.holo.frames; while (JX.holo.frames < f + 2) await new Promise(x => setTimeout(x, 30)); r.add(JX.holo.breathRate); } return r.size; })()")
    assert rates >= 4
    # three distinct forms, morphing between them
    weights = {}
    for pid in ("friday", "robin", "jarvis"):
        dash.js("p => JX.convo.switchTo(p)", pid)
        mid = dash.js("JX.holo.stats().morph")
        assert mid < 0.5
        dash.page.wait_for_function("JX.holo.stats().morph === 1", timeout=10000)
        weights[pid] = dash.js("JX.holo.weights")
    assert weights == {"friday": [0, 1, 0], "robin": [0, 0, 1], "jarvis": [1, 0, 0]}
    vis = dash.js("[JX.holo.filaments.visible, JX.holo.core.visible, JX.holo.shells[0].visible]")
    assert vis == [True, False, False]
    # mood follows the humor slider
    dash.js("document.querySelector('#humor').value = 90; document.querySelector('#humor').dispatchEvent(new Event('input'))")
    assert abs(dash.js("JX.holo.humor") - 0.9) < 0.01 and dash.js("document.querySelector('#humor-label').textContent") == "Chaos"


def test_hologram_actually_draws_three_different_creatures(dash):
    def lit():
        return dash.js("""() => { const src = document.querySelector('#holo'); const c = document.createElement('canvas'); c.width = 64; c.height = 64;
          const g = c.getContext('2d'); g.drawImage(src, 0, 0, 64, 64); const d = g.getImageData(0, 0, 64, 64).data; let n = 0, r = 0, gr = 0, b = 0;
          for (let i = 0; i < d.length; i += 4) { if (d[i] + d[i + 1] + d[i + 2] > 40) { n++; r += d[i]; gr += d[i + 1]; b += d[i + 2]; } } return [n, r / (n || 1), gr / (n || 1), b / (n || 1)]; }""")
    dash.page.wait_for_timeout(1500)
    seen = {}
    for pid in ("jarvis", "friday", "robin"):
        dash.js("p => JX.convo.switchTo(p)", pid)
        dash.page.wait_for_function("JX.holo.stats().morph === 1", timeout=10000)
        dash.page.wait_for_timeout(700)
        seen[pid] = lit()
        assert seen[pid][0] > 25, f"{pid} draws nothing"
    assert seen["jarvis"][1] > seen["jarvis"][3] * 1.5, "JARVIS is gold"
    assert seen["robin"][3] > seen["jarvis"][3] * 1.5, "ROBIN is lavender/pink, not gold"
    assert seen["friday"][1] > seen["friday"][3], "FRIDAY is warm"


def test_auto_quality_scaling_and_pause_when_hidden(dash):
    dash.js("JX.holo.frames = 200; JX.holo.quality = 1; JX.holo.frameMs = 40; JX.holo.slowFrames = 2")
    dash.page.wait_for_function("JX.holo.quality < 1 && JX.holo.count < 16000", timeout=5000)
    assert dash.js("JX.holo.count") >= 3000
    dash.js("Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange'))")
    assert dash.js("JX.holo.paused")
    frames = dash.js("JX.holo.frames")
    dash.page.wait_for_timeout(400)
    assert dash.js("JX.holo.frames") - frames <= 1, "no rendering while the tab is hidden"
    dash.js("Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange'))")
    dash.page.wait_for_function("f => JX.holo.frames > f + 3", arg=frames)


def test_canvas2d_fallback_when_webgl_is_unavailable(browser, server):
    d = Dash(browser, server, 1366, 768, "autoboot&fast&nobrief&nogl")
    assert d.js("JX.holo.stats().mode") == "2d" and d.js("JX.holo.stats().particles") > 500
    d.page.wait_for_timeout(600)
    lit = d.js("""() => { const c = document.querySelector('#holo'); const dd = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 0; i < dd.length; i += 16) if (dd[i] > 60) n++; return n; }""")
    assert lit > 50
    d.ask("still works")
    d.js("JX.convo.switchTo('robin')")
    d.page.wait_for_timeout(400)
    assert d.errors == []
    d.close()


def test_clean_slate_house_party_ambient_and_sounds(dash):
    dash.page.click("[data-quick='party']")
    dash.page.wait_for_function("document.body.classList.contains('party')")
    dash.idle()
    dash.js("JX.hear('jarvis house party', true)")
    dash.page.wait_for_function("!document.body.classList.contains('party')")
    dash.page.click("[data-quick='clean']")
    dash.page.wait_for_selector("#shutdown:not([hidden])", timeout=15000)
    assert dash.js("JX.state.asleep") and dash.js("JX.holo.assembleTarget") == 0, "the hologram collapses"
    dash.page.click("#wake-btn")
    dash.page.wait_for_function("!JX.state.asleep && document.querySelector('#shutdown').hidden && JX.holo.assembleTarget === 1")
    dash.idle()
    dash.js("JX.protocols.enterAmbient()")
    assert dash.js("document.body.classList.contains('ambient')") and not dash.js("document.querySelector('#ambient-screen').hidden")
    assert dash.js("getComputedStyle(document.querySelector('#holo-wrap')).display") != "none"
    dash.js("JX.hear('friday', true)")                                   # wakes on voice
    assert not dash.js("document.body.classList.contains('ambient')")
    dash.js("JX.protocols.enterAmbient(); JX.emit('ui:action', {action: 'wake'})")     # wakes on a wave
    assert not dash.js("document.body.classList.contains('ambient')")
    # every sound plays without error, and the toggle turns them off
    made = dash.js("""() => { let n = 0; const AC = window.AudioContext.prototype; const orig = AC.createOscillator; AC.createOscillator = function () { n++; return orig.call(this); };
      for (const k of Object.keys(JX.sfx)) JX.sfx[k](); const on = n; JX.state.settings.sound = false; for (const k of Object.keys(JX.sfx)) JX.sfx[k]();
      const off = n - on; JX.state.settings.sound = true; AC.createOscillator = orig; return [on, off, Object.keys(JX.sfx).length]; }""")
    assert made[0] >= made[2] and made[1] == 0
    dash.page.uncheck("#sound-toggle")
    dash.page.wait_for_function("JX.state.settings.sound === false")
    dash.page.check("#sound-toggle")


# ---------------------------------------------------------------- H. panels and shortcuts

def test_command_palette_space_and_escape(dash):
    dash.page.keyboard.press("Control+k")
    dash.page.wait_for_selector("#palette:not([hidden])")
    assert dash.page.locator("#palette-list li").count() > 30
    dash.page.keyboard.type("switch robin")
    assert dash.page.locator("#palette-list li").first.inner_text() == "Switch to ROBIN"
    dash.page.keyboard.press("Enter")
    assert dash.js("JX.state.persona") == "robin" and dash.js("document.querySelector('#palette').hidden")
    dash.page.keyboard.press("Control+k")
    dash.page.keyboard.type("focus 50")
    dash.page.keyboard.press("Enter")
    dash.page.wait_for_function("document.querySelector('#focus-start').textContent === 'Pause'")
    dash.idle()
    dash.page.keyboard.press("Control+k")
    dash.page.keyboard.type("what is the capital of Meghalaya")
    assert "Ask ROBIN" in dash.page.locator("#palette-list li").last.inner_text()
    dash.page.keyboard.press("Escape")
    assert dash.js("document.querySelector('#palette').hidden")
    dash.page.click("#persona-tag")
    dash.page.keyboard.press("Space")
    dash.page.wait_for_function("JX.speech.capturing && JX.state.mode === 'listen'")
    dash.page.keyboard.press("Escape")
    dash.page.focus("#talk-input")
    dash.page.keyboard.type("a b")                                       # Space while typing just types
    assert dash.js("document.querySelector('#talk-input').value") == "a b"


def test_focus_timer_quick_asks_drills_and_style(dash):
    dash.page.click("[data-focus='90']")
    assert dash.js("document.querySelector('#focus-time').textContent") == "90:00"
    dash.page.click("#focus-start")
    dash.page.wait_for_function("document.querySelector('#focus-time').textContent !== '90:00'", timeout=5000)
    dash.idle()
    dash.page.click("#focus-start")
    dash.idle()
    paused = dash.js("document.querySelector('#focus-time').textContent")
    dash.page.wait_for_timeout(1200)
    assert dash.js("document.querySelector('#focus-time').textContent") == paused
    dash.page.click("#focus-reset")
    assert dash.js("document.querySelector('#focus-time').textContent") == "90:00"
    for quick, shown in (("brief", "Brief my day"), ("headlines", "Headlines"), ("weather", "Weather"), ("guesstimate", "Guesstimate"), ("recap", "How was my day?")):
        dash.page.click(f"[data-quick='{quick}']")
        dash.page.wait_for_timeout(200)
        dash.idle()
        assert shown in dash.convo()[-2]
    dash.page.click("[data-drill='case']")
    dash.page.wait_for_timeout(200)
    dash.idle()
    assert "CASE drill running" in dash.js("document.querySelector('#drill-status').textContent") and dash.js("JX.state.drill") == "case"
    body = [json.loads(r.post_data) for r in dash.requests if r.url.endswith("/api/chat")][-1]
    assert body["context"]["mode"] == "drill" and "ONE question at a time" in body["text"]
    dash.page.click("#drill-end")
    dash.page.wait_for_timeout(200)
    dash.idle()
    assert dash.js("JX.state.drill") is None
    # style: effort + humor reach the request
    dash.page.click("[data-effort='deep']")
    dash.page.wait_for_function("JX.state.settings.effort === 'deep'")
    assert "careful reasoning" in dash.js("document.querySelector('#effort-explain').textContent")
    dash.js("const h = document.querySelector('#humor'); h.value = 72; h.dispatchEvent(new Event('input')); h.dispatchEvent(new Event('change'))")
    dash.page.wait_for_function("JX.state.settings.humor === 72")
    dash.ask("styled question")
    body = [json.loads(r.post_data) for r in dash.requests if r.url.endswith("/api/chat")][-1]
    assert body["effort"] == "deep" and body["humor"] == 72
    dash.page.click("[data-effort='auto']")
    dash.js("const h = document.querySelector('#humor'); h.value = 35; h.dispatchEvent(new Event('change'))")
    dash.page.wait_for_function("JX.state.settings.humor === 35 && JX.state.settings.effort === 'auto'")


def test_crew_debate_order_esc_cancel_and_roast(dash):
    dash.page.fill("#talk-input", "tabs or spaces")
    dash.page.click("[data-quick='debate']")
    dash.page.wait_for_function("[...document.querySelectorAll('#convo .line')].filter(l => /^(JARVIS|FRIDAY|ROBIN)/.test(l.textContent)).length >= 5", timeout=90000)
    dash.idle()
    speakers = [ln.split("Understood")[0] for ln in dash.convo() if ln.startswith(("JARVIS", "FRIDAY", "ROBIN"))][-4:]
    assert speakers == ["JARVIS", "FRIDAY", "ROBIN", "JARVIS"]
    bodies = [json.loads(r.post_data) for r in dash.requests if r.url.endswith("/api/chat")][-4:]
    assert [b["persona"] for b in bodies] == ["jarvis", "friday", "robin", "jarvis"]
    assert "tabs or spaces" in bodies[0]["text"] and "So far:" in bodies[2]["text"] and "JARVIS:" in bodies[2]["text"] and "FRIDAY:" in bodies[2]["text"]
    assert "final verdict" in bodies[3]["text"]
    # Esc cancels the rest
    n = len([r for r in dash.requests if r.url.endswith("/api/chat")])
    dash.page.click("[data-quick='debate']")
    dash.page.wait_for_function("JX.state.speaking")
    dash.page.keyboard.press("Escape")
    dash.page.wait_for_timeout(2500)
    assert len([r for r in dash.requests if r.url.endswith("/api/chat")]) - n <= 1
    dash.idle()
    # roast: humor 95 with the kind rules
    dash.page.click("[data-quick='roast']")
    dash.page.wait_for_timeout(200)
    dash.idle()
    body = [json.loads(r.post_data) for r in dash.requests if r.url.endswith("/api/chat")][-1]
    assert body["humor"] == 95 and "never at looks, family, health" in body["text"] and "sincere compliment" in body["text"]


def test_widgets_weather_spark_headline_click_and_detail_overlays(dash):
    dash.page.wait_for_function("document.querySelector('#weather-temp').textContent.includes('17')")
    assert "Shillong" in dash.js("document.querySelector('#weather-desc').textContent")
    assert "Rain likely" in dash.js("document.querySelector('#weather-rain').textContent")
    drawn = dash.js("(() => { const c = document.querySelector('#weather-spark'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++; return n; })()")
    assert drawn > 100, "the hourly sparkline is drawn"
    assert dash.page.locator("#news-list li").count() == 12
    link = dash.page.locator("#news-list li a").first
    assert link.get_attribute("target") == "_blank" and link.get_attribute("href").startswith("https://example.com/")
    n = len([r for r in dash.requests if "/api/weather?refresh=1" in r.url or "/api/news?refresh=1" in r.url])
    dash.page.click("#weather-refresh")
    dash.page.click("#news-refresh")
    dash.page.wait_for_timeout(500)
    assert len([r for r in dash.requests if "/api/weather?refresh=1" in r.url or "/api/news?refresh=1" in r.url]) == n + 2
    dash.page.locator("#news-list .t").first.click()                     # click = spoken brief
    dash.page.wait_for_timeout(200)
    dash.idle()
    assert "Brief:" in dash.convo()[-2]
    for card, title in (("#card-weather", "WEATHER"), ("#card-power", "POWER"), ("#card-brand", "JARVIS X")):
        dash.page.click(f"{card} .label, {card} .brand")
        dash.page.wait_for_selector("#overlay:not([hidden])")
        assert title in dash.js("document.querySelector('#overlay-title').textContent").upper()
        dash.page.keyboard.press("Escape")
        assert dash.js("document.querySelector('#overlay').hidden")
    assert "Waiting" in dash.js("document.querySelector('#power-status').textContent") or dash.js("document.querySelector('#power-pct').textContent")
    dash.js("JX.emit('srv:usage', {usage: {status: 'allowed_warning', percent: 87, limit_type: 'five_hour', resets_at: 1800000000}})")
    assert dash.js("document.querySelector('#power-pct').textContent") == "87%" and dash.js("document.querySelector('#power-fill').style.width") == "87%"
    dash.js("JX.emit('srv:usage', {usage: {status: 'allowed', percent: null}})")
    assert dash.js("document.querySelector('#power-pct').textContent") == "OK"


def test_memory_panel_tasks_reminders_expenses_and_file_drop(dash):
    dash.page.click("#memory-open")
    dash.page.wait_for_selector("#overlay:not([hidden])")
    dash.page.fill("#overlay-body form input", "Favourite band is Audioslave")
    dash.page.press("#overlay-body form input", "Enter")
    dash.page.wait_for_selector("#overlay-body .fact[data-fact]")
    dash.page.wait_for_selector("#holo-chips .chip")                     # "Memory updated: …" chip
    assert "Memory updated" in dash.page.locator("#holo-chips .chip").first.inner_text()
    dash.page.fill("#overlay-body .fact input", "Favourite band is Pink Floyd")
    dash.page.click("#overlay-body .fact button:has-text('Save')")
    dash.page.wait_for_timeout(300)
    assert dash.api("GET", "/api/memory/facts")["facts"][0]["text"] == "Favourite band is Pink Floyd"
    dash.page.fill("#overlay-body > input", "floyd")
    dash.page.wait_for_timeout(300)
    assert dash.page.locator("#overlay-body .fact[data-fact]").count() == 1
    dash.page.click("#overlay-body .fact button:has-text('Forget')")
    dash.page.wait_for_function("document.querySelectorAll('#overlay-body .fact[data-fact]').length === 0")
    dash.page.keyboard.press("Escape")
    # tasks + reminders
    dash.page.fill("#task-input", "buy guitar strings")
    dash.page.press("#task-input", "Enter")
    dash.page.fill("#task-input", "remind me tomorrow at 9 to call Mom")
    dash.page.press("#task-input", "Enter")
    dash.page.wait_for_function("document.querySelectorAll('#task-list .item').length === 1 && document.querySelectorAll('#reminder-list .item').length === 1")
    assert dash.api("GET", "/api/tasks")["reminders"][0]["text"] == "call Mom"
    assert "call Mom" in dash.page.locator("#reminder-list .item").inner_text() and "tomorrow" in dash.page.locator("#reminder-list .item").inner_text()
    dash.page.locator("#task-list .item button").first.click()
    dash.page.wait_for_function("document.querySelectorAll('#task-list .item').length === 0")
    # expenses
    dash.page.fill("#exp-input", "200 on lunch")
    dash.page.press("#exp-input", "Enter")
    dash.page.wait_for_function("document.querySelector('#exp-total').textContent === '₹200'")
    assert "food" in dash.page.locator("#exp-bars").inner_text()
    # drag-and-drop a file: it is added to his files and the crew reads it
    dash.js("JX.extras.ingestFile(new File(['Palm muting keeps rock rhythm tight.'], 'guitar notes.txt', {type: 'text/plain'}))")
    dash.page.wait_for_function("[...document.querySelectorAll('#convo .line')].some(l => l.textContent.includes('Dropped: guitar notes.txt'))")
    dash.idle()
    dash.page.wait_for_function("document.querySelector('#mem-files').textContent === '1'")
    dash.ask('!search_knowledge {"query": "palm muting"}')
    assert "guitar notes.txt" in dash.convo()[-1]
    # history search
    dash.page.click("#history-open")
    dash.page.fill("#overlay-body > input", "palm muting")
    dash.page.wait_for_function("document.querySelectorAll('#overlay-body .fact').length >= 1")
    dash.page.keyboard.press("Escape")


def test_due_reminder_is_spoken_and_shown(dash):
    dash.api("POST", "/api/reminders", {"text": "stretch your back", "when": "2020-01-01 09:00"})
    dash.page.wait_for_function("[...document.querySelectorAll('#convo .line')].some(l => l.textContent.includes('Reminder, sir: stretch your back'))", timeout=15000)
    assert any("Reminder%2C%20sir" in r.url for r in dash.requests if "/api/tts" in r.url), "it is spoken, not just shown"
    dash.idle()
    assert not [r for r in dash.api("GET", "/api/tasks")["reminders"] if "stretch" in r["text"]]       # fired once, gone


def test_routine_by_voice_guitar_tools_home_panel_and_proactive_card(dash):
    dash.js("JX.hear('jarvis focus mode', true)")
    dash.page.wait_for_function("document.querySelector('#focus-start').textContent === 'Pause'", timeout=10000)
    dash.idle()
    assert any("Focus mode on" in ln for ln in dash.convo())
    assert len([r for r in dash.requests if r.url.endswith("/api/chat") and "focus mode" in (r.post_data or "")]) == 0, "a routine never goes to the model"
    dash.page.click("#focus-reset")
    assert dash.page.locator("#routine-list .item").count() == 4
    # guitar: chord of the day, metronome pulse reaches the hologram, tuner opens
    assert dash.js("document.querySelector('#chord-name').textContent") != "—" and len(dash.js("document.querySelector('#chord-frets').textContent")) == 6
    dash.js("document.querySelector('#metro-bpm').value = 200; document.querySelector('#metro-bpm').dispatchEvent(new Event('input'))")
    dash.page.click("#metro-toggle")
    dash.page.wait_for_function("JX.holo.beatEnv > 0.2", timeout=5000)
    dash.page.click("#metro-toggle")
    dash.page.click("#tuner-open")
    dash.page.wait_for_selector(".tuner .needle")
    dash.page.keyboard.press("Escape")
    # home panel: empty until he adds a light; then the controls work
    assert not dash.js("document.querySelector('#home-empty').hidden") and dash.js("document.querySelector('#home-controls').hidden")
    dash.api("POST", "/api/lights/devices", {"name": "Desk light", "driver": "fake"})
    dash.page.wait_for_function("!document.querySelector('#home-controls').hidden")
    dash.page.click("#light-toggle")
    dash.page.wait_for_function("document.querySelector('#light-toggle').textContent === 'On'")
    dash.js("const b = document.querySelector('#light-bright'); b.value = 30; b.dispatchEvent(new Event('change'))")
    dash.page.wait_for_timeout(400)
    assert dash.api("GET", "/api/lights")["devices"][0]["state"]["brightness"] == 30
    dash.ask('!light_scene {"scene": "night"}')
    dash.page.wait_for_function("document.querySelector('#light-bright').value === '5'")
    # proactive: spoken and shown as a dismissible card; "not now" snoozes
    dash.js("JX.emit('srv:proactive', {item: {id: 'p1', kind: 'habit', text: 'You have not practised guitar in 3 days.'}})")
    dash.page.wait_for_selector(".pro-card")
    dash.idle()
    assert any("practised guitar" in ln for ln in dash.convo())
    dash.js("JX.hear('jarvis not now', true)")
    dash.page.wait_for_function("document.querySelectorAll('.pro-card').length === 0")


def test_pure_helpers_chunker_pitch_and_text(dash):
    out = dash.js("""() => {
      const C = new JX.text.Chunker(); const pieces = [];
      for (const d of ['Good morning, ', 'sir. It is 21.5 degrees', ' today, e.g. mild. Take', ' an umbrella! Done']) pieces.push(...C.feed(d));
      pieces.push(...C.flush());
      const first = new JX.text.Chunker().feed('Right away then, I will check the weather for you now');
      const sine = (hz, rate = 48000, n = 4096) => Float32Array.from({ length: n }, (_, i) => 0.5 * Math.sin(2 * Math.PI * hz * i / rate) + 0.2 * Math.sin(4 * Math.PI * hz * i / rate));
      const notes = [82.41, 110, 146.83, 196, 246.94, 329.63].map(hz => { const d = JX.pitch.describe(JX.pitch.detectPitch(sine(hz), 48000)); return [d.string.name, Math.abs(d.stringCents)]; });
      const flat = JX.pitch.describe(JX.pitch.detectPitch(sine(107), 48000));
      return { pieces, first, notes, flat: [flat.string.name, flat.stringCents], silent: JX.pitch.detectPitch(new Float32Array(4096), 48000),
        echo: [JX.text.isEcho('welcome home sir', 'Welcome home, sir. All systems online.'), JX.text.isEcho('what is the weather', 'Welcome home, sir.')],
        caption: JX.text.captionText('**Three** things:\\n- one\\n- two'), labels: [0, 20, 50, 70, 95].map(JX.text.humorLabel) }; }""")
    assert out["pieces"] == ["Good morning, sir.", "It is 21.5 degrees today, e.g. mild.", "Take an umbrella!", "Done"]
    assert out["first"] == ["Right away then,"]                         # the first clause goes to the voice before the sentence ends
    assert [n[0] for n in out["notes"]] == ["E2", "A2", "D3", "G3", "B3", "E4"] and all(n[1] <= 3 for n in out["notes"]), out["notes"]
    assert out["flat"][0] == "A2" and -55 < out["flat"][1] < -40 and out["silent"] == 0
    assert out["echo"] == [True, False] and out["caption"] == "Three things: · one · two"
    assert out["labels"] == ["Serious", "Dry wit", "Playful", "Banter", "Chaos"]


def test_phone_companion_page(browser, server):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(f"{server['url']}/m")
    page.wait_for_selector("#crew button")
    assert page.locator("#crew button").count() == 3 and page.evaluate("document.querySelector('#pair').hidden")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.tap("#crew button:nth-child(2)")
    page.fill("#t", "hello from my phone")
    page.press("#t", "Enter")
    page.wait_for_function("document.querySelector('#speaker').textContent === 'FRIDAY' && document.querySelector('#caption').textContent.includes('boss')", timeout=15000)
    page.request.post(f"{server['url']}/api/chat", data=json.dumps({"persona": "jarvis", "text": '!contact_save {"name": "Dad", "phone": "9811122233"}'}), headers={"Content-Type": "application/json"})
    page.request.post(f"{server['url']}/api/chat", data=json.dumps({"persona": "jarvis", "text": '!call_draft {"to": "Dad"}'}), headers={"Content-Type": "application/json"})
    page.wait_for_selector("#cards .card", timeout=10000)
    assert "Call Dad" in page.locator("#cards .card").inner_text()
    page.locator("#cards .card button", has_text="Cancel").tap()
    page.wait_for_function("document.querySelectorAll('#cards .card').length === 0")
    assert errors == [], errors
    ctx.close()
