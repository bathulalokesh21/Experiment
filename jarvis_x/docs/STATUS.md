# JARVIS X: what was built and what was verified where

This build was written and tested on a Linux cloud machine, not on the Windows laptop. This page says plainly
what that means for each part.

## Verified by automated tests here (149 tests: `python -m pytest tests -q`)

- **Static/QA-A**: every Python file compiles; every route the UI calls exists; a route inventory that fails if a
  route disappears; every element ID the scripts use exists; no .bat, Moodle, Japanese mode or background mode;
  pinned requirements; Three.js, MediaPipe and both camera models are served locally with correct MIME types.
- **Crew/QA-B**: three personas (opus/sonnet/haiku, sir/boss/Love), prompts carry profile + preferences + learned
  facts; humor and effort reach the model (effort never to Haiku); separate memory per assistant; usage status vs
  percentage; checkpoints 25/50/85/90/100 announced once each, after the answer; plain-English errors; API key
  stripped; voice retry then persona-matched fallback, never empty audio. The real `ClaudeAgentOptions` are built
  against the installed SDK in a test.
- **Memory/QA-C**: add, dedupe, update-not-duplicate, forget by voice, refusal of health/account/password/OTP,
  Memory panel, search across PDF/DOCX/PPTX/CSV/TXT/MD, drag-and-drop, transcripts per day and search.
- **Tools/QA-D**: every tool returns text and never raises; WhatsApp/call/email are draft → card → approval only,
  by click, voice and 👍 (same endpoint); Gmail search/read/draft/send/cancel/reply-in-thread/new-address warning/
  expired login, against a fake Gmail service; contacts never guessed; reminders persist, natural-language times,
  recurring, late reminders; screen capture only on request and deleted after; Read limited to allowed folders;
  clipboard, media keys, volume, app and website whitelists.
- **Widgets/QA-E**: weather + headlines with backups and plain-English errors, 5-minute refresh, sparkline,
  "new" markers, morning brief on first open of the day, recap.
- **Dashboard/QA-F,G,H** in a real Chromium with a fake mic/camera: loads with zero console errors at 1920×1080,
  1440×900 and 1366×768 with every panel reachable; boot; streaming speech with word-synced captions; wake words
  and mishearings; mid-answer switch; barge-in, echo filter and its toggle; instant acknowledgement; WebGL
  hologram draws three different creatures, states, audio reactivity, morph, auto quality, pause when hidden,
  Canvas2D fallback; every gesture in the table from synthetic landmarks with hysteresis/cooldowns; air cursor;
  presence; camera-first then local MediaPipe actually loading its wasm and both models; calibration; palette,
  Space, Esc, debug overlay; focus timer, quick asks, drills, debate order and Esc cancel, roast; phone page.
- **Round 2/QA-K,L,I**: proactive triggers, rate limit, quiet hours, snooze; routines; phone pairing PIN and LAN
  only; plugins (proposal card, tests run, sandbox rules, disable); expenses, flashcards, comic, journal; light
  tools against a fake device; port-busy message; no-internet behaviour; data separate from code; v15 migration
  (copy only, old folder untouched).

## Verified once by hand here

- **The real Claude Agent SDK path**: one short ROBIN (Haiku) exchange on a Claude Code login. She called the
  `get_time` tool, answered in character, remembered the previous question, and the usage event arrived.
- **Open-Meteo** forecast and geocoding responses were fetched and match the parser field for field.
- Both MediaPipe model URLs were downloaded (hand_landmarker.task, blaze_face_short_range.tflite) and are bundled.

## NOT verified here: needs your laptop

| Part | Why | What to do |
|---|---|---|
| Installing the pinned packages on Windows / Python 3.12 | Built on Linux / Python 3.13 | `pip install -r requirements.txt`; if one pin has no Windows wheel, tell Claude Code the error |
| Neural voices (edge-tts) | The voice service was blocked on the build network, so voice names were not auditioned | `python scripts\voice_test.py` reports any voice that fails; change it in `.env` |
| Google News / wttr.in / BBC feeds | Blocked on the build network; parsers are tested against sample feeds | `python scripts\doctor.py` shows which are reachable |
| JARVIS (Opus) and FRIDAY (Sonnet) live, and latency targets | Only one Haiku call was made, to spare your usage limit | Ask each one something; Ctrl+Shift+D shows first-audio latency against the targets |
| Speech recognition | Uses the browser's Web Speech API (Edge/Chrome, needs internet); tests inject recognised text | Say "Jarvis, what's the weather?" |
| Real camera gestures | Tested with synthetic hand landmarks, not a real hand | Turn on camera → Calibrate → try the table in the README |
| WhatsApp auto-send | Drives WhatsApp Web in your Edge/Chrome; WhatsApp changes its page from time to time | First approval: scan the QR. If the send button isn't found, set `WHATSAPP_MODE=web` |
| Gmail against Google | Tested with a fake service | `python scripts\gmail_login.py`, then ask it to draft a mail to yourself |
| Phone Link calls, media keys, clipboard, screenshots, app launching | Windows-only APIs, replaced by fakes in tests | Try each once |
| Migration from `C:\jarvis_crew_v6` | The old build was not available; tested against a made-up v15 folder | Run it; if your `contacts.md`/`facts.md` use another layout, some lines may be skipped (it tells you how many) |
| Crompton light (Phase 7) | No bulb here. The device layer, scan script, tools, Home panel and routines are built and tested against a fake bulb | README section 8. The blueprint asks for the bulb's app name and model first |
| Piper own-voice models | Optional dependency, untested | README section 4 |

## Known limits (by design or by platform)

- **Phone companion voice input**: phone browsers only allow the microphone on https pages, so over plain
  home-Wi-Fi http you type or use the keyboard's dictation key. Replies are spoken and approvals work.
- **Voice-only orb**: uses the browser's Document Picture-in-Picture window (always on top, recent Edge/Chrome).
- **Smart routing**: ROBIN may *offer* JARVIS; she does not hand over by herself.
- **Plugins**: the sandbox is a static check plus a restricted runtime (no imports beyond a short list, no files,
  network or shell) and its tests run in a separate process. You still see the full code before approving.
- **Screen awareness / sketch to life**: the image is read by the model through Claude Code's Read tool, limited
  to `data\screens`, `data\sketches`, `data\uploads` and `data\knowledge`.
- Not built: a "palm-up raise = brighter" light gesture (the blueprint lists it as an example).
