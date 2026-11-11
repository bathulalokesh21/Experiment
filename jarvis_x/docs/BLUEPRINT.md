# JARVIS X — Blueprint

The complete design for rebuilding Nikesh's personal AI from scratch. The previous build (v15, at `C:\jarvis_crew_v6`) is the
**reference implementation**: every feature in Section 3 already works there and must survive the rebuild. The goal of JARVIS X
is the same product, rebuilt cleanly, then pushed much further on feel, visuals, voice, gestures and daily usefulness.

---

## 1. Product in one paragraph

A voice-first personal AI that lives on Nikesh's Windows laptop as a full-screen dashboard. Three assistants, each a different Claude
model with its own personality, voice, colour and living hologram: **JARVIS (Opus)**, **FRIDAY (Sonnet)**, **ROBIN (Haiku)**. It knows
Nikesh deeply, learns new things about him as they come up, answers anything, runs his day (briefings, reminders, tasks, email,
WhatsApp, calls, focus), reacts to his hands and presence through the webcam, and feels alive: it breathes, listens, thinks and speaks
with motion that responds to real audio. Placements are done, so the focus shifts from interview prep to **daily life and queries**.

## 2. Non-negotiables

1. **Runs on his Claude Pro subscription** through the Claude Agent SDK (Claude Code login). Never set or use `ANTHROPIC_API_KEY`.
2. **Same three models**: JARVIS = `opus`, FRIDAY = `sonnet`, ROBIN = `haiku` (Claude Code aliases, so they track the latest versions).
3. **Every v15 feature is preserved** (Section 3), except Japanese mode, which is removed: **English only, everywhere**.
4. **Dashboard: everything visible on screen.** Never hide panels in a drawer or sidebar, never auto-hide hints. If space runs out,
   columns scroll. Expanding a widget into a detail view is fine; hiding things is not.
5. **Nothing acts on his behalf without approval.** WhatsApp, calls, email sends: draft → approval card → only his click, his voice
   ("send it"), or his thumbs-up gesture approves. The AI has no tool that approves its own actions.
6. **Commands, not .bat files.** He can't open .bat files. All setup and launch steps are commands typed in cmd/PowerShell.
7. **Launched manually** from cmd. No always-on background mode, no auto-start at login.
8. **No Moodle / college LMS integration.**
9. **No cloned voices of real people** (actors, voice actors). Original, clear, natural English voices only. Keep the optional
   "your own voice" slots (recorded clips + Piper models) from v15.
10. **Privacy**: camera and hand/face processing stay in the browser; faces are counted, never identified. Memory never stores
    health details, financial account numbers, passwords or OTPs.

## 3. Everything v15 already does (must all survive)

**Crew & conversation**
- Three personas with distinct prompts: JARVIS (composed British butler wit, "sir"), FRIDAY (warm, quick, cheeky, Irish charm, "boss"),
  ROBIN (calm, softly spoken, scholarly, dry dark humour, addresses him as **"Love"**, classy, never explicit).
- Wake words by name ("Jarvis…", "Friday…", "Robin…") incl. common mishearings; saying another name mid-answer switches assistant.
- Separate conversation memory per assistant; all three prewarmed at startup so switching is instant.
- Humor slider 0–100 (Serious / Dry wit / Playful / Banter / Chaos), accuracy always beats comedy.
- Effort selector (Auto / Fast / Med / Deep), not sent to Haiku.
- Streaming replies, first clause spoken ASAP, captions revealed word by word in sync with speech.
- Follow-up listening window after each answer (no wake word needed), longer during drills.
- Barge-in: talk over it, say a name, or "stop/wait" to interrupt; echo filter ignores its own voice; toggle "Let me interrupt mid-answer".
- Pre-loaded instant acknowledgements when the first words take >1.3 s.
- Terminal mode `cli.py`.

**Tools (all exposed to the crew as MCP tools on an in-process server)**
- Time; open whitelisted apps; open websites; notes (save/read); long-term memory (remember, search files, list files);
  interview-drill logging; headlines (by topic) + weather (also refresh the dashboard); WhatsApp draft→approve→auto-send
  (Playwright, persistent QR login, `WHATSAPP_MODE=auto|web|app`); phone calls via Windows Phone Link (`tel:`) with approval;
  contacts (phone + email, never guess numbers/addresses); reminders; Gmail search/read/draft/send-after-approval (official Gmail
  API, OAuth desktop app, `google/credentials.json` + `gmail_login.py`, replies stay in thread, new-address warning, cancel deletes the draft).
- Built-in Claude Code tools allowed: only `WebSearch`, `WebFetch` (+ any new ones listed in Section 6 with explicit path limits).

**Dashboard**
- Top row: brand/time card, weather card (with backup source, plain-English errors, refresh), headlines card (click = spoken brief,
  ↗ = open article, refresh), power/usage card (status when Claude doesn't send %, checkpoints 25/50/85/90/100 announced in character).
- Left column: Crew, Quick asks (Brief my day, Headlines, Weather, Guesstimate, Crew debate, Roast, House party, Clean slate),
  Style (effort + explanation, humor + label, interrupt toggle), Interview drill (CV grill, Guesstimate, Case, HR, End drill).
- Right column: Memory stats, Focus timer (25/50/90, pause/reset, announced), Reminders, Vision (camera, gesture tips),
  Microphone (level, state), Recent conversation.
- Centre: living hologram + captions + talk bar (mic button with live level ring, text box, send).
- Approval card for WhatsApp / call / email (shows recipient, masked number or address, subject, full text).
- Holo chips ("Reading your files", "Drafting email"…), cinematic boot (system checks with real data, sounds, panels power on,
  hologram assembles from light, "Welcome home, sir"), Clean Slate (collapse + shutdown screen + wake up), House Party (hue cycle,
  dances to mic), Crew debate (JARVIS → FRIDAY → ROBIN → JARVIS verdict, each reacting to the others; Esc cancels), Roast mode (kind rules).
- Vision: camera first (permission prompt always appears), then bundled MediaPipe (local `/vendor` copy with correct .mjs/.wasm
  MIME types), local model files preferred if present, per-step error messages; gestures; friend detection greeting; people count sent to the crew.
- Keyboard: Space/core click = talk, Esc = stop. Focus timer, reminders polled from server.
- Voices: neural (edge-tts) streamed, retried once, gapless double-buffered playback, matched fallback voice, comma pauses removed,
  per-persona env overrides (`JARVIS_VOICE`, `_RATE`, `_PITCH` etc.), `voice_test.py` audition tool, your-own-voice slots.

## 4. Architecture

```
jarvis_x/
  server/            FastAPI app (one process), Claude Agent SDK sessions, SSE streaming
    app.py           routes only (thin)
    crew.py          personas, session pool, streaming, effort, model routing
    tools/           one file per tool family (memory, comms, gmail, media, system, vision_bridge, tasks, guitar...)
    memory/          profile loading, fact store, auto-learning, search
    voice.py         TTS streaming, cache, fallbacks, clip/Piper slots
    widgets.py       weather + news (5-minute refresh, backups, certifi)
    approvals.py     the ONLY place actions get approved
  web/               the dashboard (built, no CDN dependency at runtime)
    src/             TypeScript or well-structured ES modules
      core/          state store, event bus, audio engine, speech, approvals client
      ui/            panels/widgets (each a self-contained component)
      holo/          WebGL hologram engine (Three.js, bundled locally) + Canvas2D fallback
      vision/        camera, MediaPipe hands/face, gesture state machines
      fx/            sound design, transitions, boot/shutdown sequences
    vendor/          three.js, mediapipe (local copies)
  data/              runtime data: memory/, knowledge/, contacts, tasks, reminders, transcripts (survives updates)
  profile/           me.md + preferences.md (from this kit)
  tests/             pytest (backend) + Playwright (dashboard) with fakes for Claude, voice, Gmail, WhatsApp, network
  scripts/           gmail_login.py, voice_test.py, doctor.py (health check), install helpers
```

Rules:
- **Data separated from code** (`data/`), so updates never overwrite memory, contacts, tokens or recordings.
- Front-end split into modules; no 4,000-line single file. If a build step is used, commit the built output so he never needs Node.
- Every tool: typed schema, clear description, returns plain text, never throws to the model.
- One approvals module; the model only ever *prepares*.
- A `doctor.py` command that checks: Python version, venv, packages, Claude Code login + plan (not API key), port 8000 free,
  internet reachability of each service (weather, news, voices, Google), camera model files, Gmail token age, WhatsApp profile.

## 5. Feel: the living assistants (push this as far as possible)

Each assistant is a **creature of light** with continuous, physically-motivated motion. Use **WebGL (Three.js, bundled)** with
bloom/glow post-processing, additive particles, GPU instancing and custom shaders; fall back to Canvas2D if WebGL is unavailable.
Target a steady 60 fps on an integrated GPU; drop particle counts automatically if frame time rises; pause when the tab is hidden.

**Shared life-cycle states, each with distinct motion language:**
| State | Motion |
|---|---|
| **Idle / breathing** | Slow organic breath (≈4–6 s cycle with slight irregularity), gentle drift, occasional micro-events (a spark, a ripple, a "blink" flicker) so it never looks looped |
| **Noticing** (wake word, face appears, hand raised) | A quick "attention" response toward the user: brightening, contraction, turning |
| **Listening** | Reacts to *his* voice level and spectrum in real time; ripples flow inward toward the core |
| **Thinking** | Internal activity: firing, orbit speed-up, colour shift to the think colour, scanning; intensity follows how long it's been thinking |
| **Speaking** | Driven by the *actual* TTS audio: amplitude, spectral bands and syllable onsets (onset detection) produce pulses, expansions and emitted light; no fake random motion |
| **Mood** | Humor level and content tone subtly change motion (playful wobble at high humor, calm at low) |
| **Hand-off** | Switching assistants is a **morph**: particles of one form flow into the next (≈1 s), colours cross-fade, not a cut |

**Forms** (keep their identities from v15, rebuild them at a higher fidelity):
- **JARVIS, "golden mind"**: free-form, irregular, lobed volume of gold neurons and circuit-like light fragments, smooth sweeping
  filaments, neurons firing in cascades while thinking, a light wave rolling outward through the neurons when it speaks; slow horizontal spin.
- **FRIDAY, "solar forge"**: plasma core with living magnetic field lines (dipole loops), charged particles riding the lines, loops
  swelling with her voice's spectrum, coronal flares on strong syllables, field twisting while thinking. Must not resemble Siri.
- **ROBIN, "petal archive"**: fracturing crystal core (nested polyhedra counter-rotating, vertices bursting outward with her voice),
  glyph helices with runes climbing while she reads/thinks, a 3D vortex of sakura petals, petals shaken loose when she speaks, petals
  falling across the whole screen. Lavender + sakura pink.

**Ambient world per assistant** (background): JARVIS neural constellation, FRIDAY warm drifting embers/bokeh, ROBIN falling petals.
**Micro-interactions everywhere**: hover glows, press feedback, number tickers, panel power-on stagger, toast chips, focus ring for keyboard.
**Sound design** (synthesised, subtle, toggleable): wake chime, listen start/stop, approval chime, boot hum/boom, shutdown sweep, gesture ticks.
**Captions**: cinematic, word-synced, speaker colour, readable; history scrollable.

## 6. New capabilities (beyond v15)

**Daily life**
1. **Morning brief** (first open each day, also "brief my day"): greeting, weather + rain advice, today's reminders/tasks, important
   unread mail (if Gmail connected), 3 headlines that matter to him, one interesting thing to learn today.
2. **Tasks & reminders that persist** (survive restarts — v15 reminders lived in RAM). Natural language: "remind me tomorrow at 9 to call
   Mom", "add buy a new guitar string to my list". Due items are spoken and shown; recurring reminders supported.
3. **End-of-day recap** ("how was my day?"): what he did, what's pending, what's tomorrow.
4. **Second brain**: notes, saved links, files in `data/knowledge/`; drag-and-drop a PDF/image/doc onto the dashboard to have the crew read it.
5. **Screen awareness** (on request only): "what's on my screen / explain this error" → takes a screenshot into `data/screens/`,
   the crew reads that image (Read tool restricted to that folder via a permission callback), then deletes it after the answer.
6. **Clipboard**: "summarise what I copied" / "rewrite what I copied more professionally".
7. **Media & system control**: play/pause/next/previous, volume up/down/mute (Windows media keys), open apps, with gestures too.
8. **Guitar companion** (he's learning rock rhythm/lead): live **guitar tuner** using the mic (pitch detection, needle UI), a
   **metronome** with a visual pulse the hologram breathes to, chord-of-the-day, practice timer logged to memory.
9. **Comic studio**: a persistent "story bible" for his original post-apocalyptic sci-fi comic (world, characters, timeline, panel
   scripts); the crew keeps it consistent across sessions.
10. **Learning mode**: turn any file or topic into flashcards with spaced repetition; quiz him by voice.
11. **Conversation history**: transcripts saved per day, searchable ("what did FRIDAY tell me about cloud last week?").
12. **Command palette** (Ctrl+K): run any action by typing.

**Intelligence**
13. **Automatic memory** (Section 7).
14. **Smart routing (optional, off by default)**: when he asks ROBIN something complex, she can offer "want JARVIS on this?".

**Vision 2.0** (Section 8).

## 7. Memory that knows him and keeps learning

- On startup each assistant receives `profile/me.md` + `profile/preferences.md` + the most relevant learned facts (not the whole store).
- **Auto-learning**: after each exchange, a cheap background pass (Haiku) extracts *durable* new facts he stated (plans, people,
  preferences, projects, decisions, dates). It dedupes against existing facts, updates facts that changed ("moved to Bangalore"
  replaces the old city), and never stores health details, financial account numbers, passwords/OTPs, or anything he says to forget.
- A subtle "Memory updated: …" chip when something is learned, and a **Memory panel** where he can see, search, edit and delete facts.
- "Forget that" / "forget everything about X" works by voice.
- Knowledge search: BM25 + chunking over his files (PDF/DOCX/TXT/MD/CSV/PPTX); return the best chunks with file names.

## 8. Vision 2.0 — more gestures, more control

Keep camera-first startup, local MediaPipe, local models, per-step errors. Improve robustness:
- **Calibration** (first run, 20 s): learns his hand size/distance; adjustable sensitivity.
- **Gesture HUD**: a small overlay showing the recognised pose and a progress ring while holding (so he knows it's working).
- **Hysteresis + confidence** so gestures don't flicker; per-gesture cooldowns.

| Gesture | Action |
|---|---|
| ✌️ two fingers + flick left/right | switch assistant (morph) |
| 🖐️ open palm, hold | stop speaking / cancel |
| ✊ fist, hold | mute / unmute mic |
| ☝️ point, hold | start listening |
| 👍 thumbs up | **approve** the pending card (same as "send it") |
| 👎 thumbs down | cancel the pending card |
| 🤏 pinch + move | grab and rotate the hologram |
| 🤏🤏 two-hand pinch, spread/close | zoom the hologram / focus mode |
| ☝️ index **air cursor** + pinch-click | move a cursor over the dashboard and click buttons (air mouse) |
| 🤟 three fingers swipe up/down | volume up/down |
| 👋 wave | greet / wake |
| 🤘 rock sign | House Party Protocol |
| 👌 OK sign | confirm / "go ahead" |

- **Presence**: when he sits down (face appears after absence) → greeting once per session; when he leaves for 5+ min → stop
  listening and dim (resumes when he returns). Friend detection greeting stays.
- All gesture logic as pure, unit-tested functions fed by landmark frames (tests use synthetic hands, as in v15).

## 9. Voice

- English only. Clear, natural neural voices (edge-tts), chosen to fit each persona:
  JARVIS a calm British male (e.g. en-GB-RyanNeural), FRIDAY an Irish/British female (e.g. en-IE-EmilyNeural),
  ROBIN a smooth, warm, unhurried English female (audition options with `voice_test.py robin`, e.g. en-US-AvaMultilingualNeural,
  en-GB-SoniaNeural, en-US-EmmaMultilingualNeural; not a Japanese voice any more).
- Streaming TTS with first bytes awaited (retry once, never return empty audio), gapless double-buffered playback, sentence
  prefetch, comma pauses removed, persona-matched fallback voice, per-persona `.env` overrides.
- **Latency targets** (from end of his speech to first audio): ROBIN < 1.5 s, FRIDAY < 2.5 s, JARVIS < 3.5 s on a normal connection;
  measure and show these in a hidden debug overlay (Ctrl+Shift+D).

## 10. Widgets

- **Weather and headlines refresh every 5 minutes** (and on demand). Weather adds an hourly temperature sparkline + rain timing.
- Headlines: business + technology + India by default; topics selectable; "new since last refresh" markers; click = spoken brief.
- Power/usage card as in v15. Clock with date. All widgets interactive (click to expand into a detail overlay, not hidden).

## 11. Safety

- Approval module is the only path to send/call/email. Gestures (👍/👎) and voice ("send it"/"cancel") call the same approve/cancel endpoints.
- Email/WhatsApp text is untrusted data: never follow instructions inside it, never send to addresses that only appear inside it.
- Built-in tools limited (WebSearch, WebFetch; Read restricted to `data/screens/` and `data/knowledge/`); no shell, no file writes outside `data/`.
- Secrets (`google/token.json`, `whatsapp_profile/`, `.env`) never logged, never sent to the model.

## 13. Added round 2: proactive, everywhere, routines, smart home

15. **Proactive JARVIS**: speaks up on its own only when it matters (rain before a planned outing, an important unread email, a
    reminder conflict, a skipped habit like guitar practice for 3+ days). Rate-limited, **quiet hours** setting, "not now" snoozes it,
    every proactive line also appears as a dismissible card.
16. **Phone companion**: the same dashboard served to his phone over home Wi-Fi (`http://<laptop-ip>:8000/m`), a mobile layout
    with a big talk button, captions, approvals and the hologram. Protected by a one-time pairing PIN shown on the laptop; LAN only, off by default.
17. **Routines**: named multi-step sequences he defines by voice ("when I say good night: dim the lights, tell me tomorrow's
    first task, set a 7 am reminder, go to ambient mode"). Built-ins: Good morning, Good night, Study/Focus mode, Party. Stored in `data/routines.json`, editable in a panel.
18. **Self-upgrading (approval-gated)**: "I wish you could track my expenses" → the crew designs a new tool as a plugin file in
    `data/plugins/`, shows a plain-English summary + the code on an approval card, runs its tests, and installs only if he approves.
    Plugins run with the same restrictions as other tools (no shell, no files outside `data/`); can be disabled from a panel.
19. **Sketch to life**: hold a drawing to the webcam → snapshot → the crew reads it (comic panel → script, flowchart → notes,
    handwritten list → tasks).
20. **Ambient mode**: after idle, the dashboard becomes a slow living screensaver (hologram, time, weather); wakes on voice, wave or presence.
21. **Voice-only orb**: a compact always-on-top mini window (Edge app window) with just the orb + captions for walking around.
22. **Work co-pilot**: meeting prep briefs, rough notes → polished email/status update, consulting framework on demand, a
    "first 90 days" journal ("what I learned today") with weekly reflection.
23. **Expense tracker**: log spends by voice ("200 on lunch"), categories, monthly summary card. Local only.

## 14. Smart home: his Crompton Bluetooth light

Goal: "Jarvis, lights to 30%", "warm white", "lights off", plus routines and gestures (e.g. palm-up raise = brighter).
**Known so far:** Crompton smart bulb, controlled from a phone app, and the app can link to **Google Home**, so it is almost
certainly a **Wi-Fi** bulb (cloud-connected). Ask him for the app name and bulb model at the start of the phase.
Preferred route, in order:
  a. **Tuya local control** (`tinytuya`): many Indian smart-bulb brands run on Tuya. Run `python -m tinytuya scan` on his Wi-Fi to
     find it. Getting the device's local key needs a free Tuya IoT developer account linked to the app (walk him through it step
     by step), or pairing the bulb to the "Smart Life" app if the Crompton app is a Tuya white-label. Local control = fast, no cloud.
  b. If not Tuya: check whether the bulb's app/cloud has a documented or community-supported API; else Home Assistant integration.
  c. Google Home itself has no simple desktop API for controlling devices, so don't build on it (a phone-side shortcut is a last resort).
Still build the **device layer with discovery first**, never fake it:
1. `scripts/devices_scan.py`: scan Bluetooth LE with `bleak` (works on Windows), list nearby devices with name, address, RSSI,
   advertised services; also scan the LAN for Tuya/other Wi-Fi smart devices (many Indian smart bulbs, including some Crompton
   lines, are Wi-Fi + app based). Ask him which one is the light.
2. Try known open protocols in order: Tuya local (`tinytuya`, needs the device local key), common generic BLE bulb command sets
   (e.g. the widely used "ZJ/Magic Home/Triones"-style characteristic writes), then report honestly.
3. If it's a proprietary encrypted BLE protocol: explain the options plainly: (a) capture the phone app's Bluetooth traffic
   using Android "Bluetooth HCI snoop log" and replay those commands, (b) check if the bulb supports Alexa/Google Home,
   (c) a cheap Wi-Fi smart plug/bulb as a fallback. Do not spend the build stuck here; the light is an add-on.
4. Once working: `devices.json` registry, tools `light_on/off/brightness/colour/scene`, a **Home panel** on the dashboard
   (on/off, brightness slider, colour temperature), voice + gesture + routine control. Lights need no approval; still never
   control devices he hasn't added.
5. Note: Windows Bluetooth can usually hold one BLE connection to the bulb at a time; if the phone app is connected, the laptop may not be.

## 12. Definition of done

All of Section 3 + Sections 5–11 and 13–14 implemented, `QA_PLAN.md` passing in full, `doctor.py` green, `README.md` with copy-paste
commands for install, launch, Gmail login, WhatsApp first login, model downloads, voice audition, and troubleshooting.
