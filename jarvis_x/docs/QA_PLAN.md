# JARVIS X — QA plan (all must pass)

Automated where possible (pytest + Playwright with fakes), plus a short manual checklist on the real laptop.

## A. Static / build
- [ ] Every Python file compiles; dashboard JS has zero syntax errors; no console errors on load or during the full UI run
- [ ] Every element/ID the scripts reference exists; every server route referenced by the UI exists and responds
- [ ] requirements.txt pinned; `doctor.py` runs and reports each check clearly
- [ ] No Japanese mode, no Moodle, no background/auto-start code, no .bat files

## B. Crew
- [ ] Three personas with the right model (opus/sonnet/haiku), prompt, voice, colour, form, greeting, address ("sir"/"boss"/"Love")
- [ ] Streaming: first audio starts after the first clause; captions word-synced; latency overlay records timings
- [ ] Humor and effort reach the model (effort not sent to Haiku); per-assistant conversation memory; prewarm works
- [ ] Wake words incl. mishearings; name mid-answer switches assistant and passes the rest of the sentence
- [ ] Barge-in by voice ("stop", "wait", 3+ words), echo of its own voice ignored, toggle off disables it
- [ ] Instant acknowledgement plays when the first words are slow
- [ ] Usage: status shown when no %, exact % when sent; checkpoints 25/50/85/90/100 announced once each, below the answer

## C. Memory
- [ ] Profile + preferences loaded into every assistant
- [ ] Auto-learning: a stated new fact is saved; a changed fact is updated, not duplicated; "forget X" removes it
- [ ] Never stores health details, account numbers, passwords/OTPs
- [ ] Memory panel lists, searches, edits, deletes facts; "Memory updated" chip appears
- [ ] Knowledge search finds content in PDF, DOCX, TXT, MD, CSV, PPTX; drag-and-drop adds a file
- [ ] Transcripts saved per day and searchable

## D. Tools & approvals
- [ ] Every tool runs and returns text (never crashes the model)
- [ ] WhatsApp: draft → card → nothing sent before approval; approve by click / "send it" / 👍; cancel by click / "cancel" / 👎;
      auto mode sends exact text to exact number; first-login keeps the draft; web/app modes open correctly
- [ ] Calls: approval → `tel:` opened with the right number
- [ ] Gmail: search, read (HTML → text), draft (in Drafts), approve sends that draft, cancel deletes it, replies keep the thread
      and "Re:", unknown name → asks, new address → warning, expired login → clear instruction, email text marked untrusted
- [ ] Contacts: phone and email saved; never guesses
- [ ] Tasks/reminders persist across restart; natural-language times; recurring; spoken when due
- [ ] Screen awareness only on request; screenshot deleted after; Read limited to allowed folders
- [ ] Clipboard, media keys, volume, app/website opening (whitelist enforced)

## E. Widgets
- [ ] Weather + headlines refresh every 5 minutes and on demand; backups used when primary fails; errors in plain English
- [ ] Headline click → spoken brief; ↗ opens article; hourly weather sparkline
- [ ] Morning brief on first open of the day; end-of-day recap on request

## F. Living assistants
- [ ] WebGL engine with Canvas2D fallback; steady frame rate with auto quality scaling; pauses when tab hidden
- [ ] Each form draws and is visually distinct (JARVIS mind, FRIDAY forge, ROBIN petal archive + falling petals)
- [ ] States visibly differ: idle breathing (non-looping), noticing, listening (reacts to mic), thinking, speaking (reacts to TTS audio)
- [ ] Switching assistants morphs (no hard cut); boot assembly and clean-slate collapse work
- [ ] Sound design plays and can be turned off

## G. Vision
- [ ] "Turn on camera" asks for camera immediately; preview shows even if models fail; clear per-step errors
- [ ] Local MediaPipe + local models preferred; correct MIME types
- [ ] Every gesture in BLUEPRINT §8 recognised from synthetic landmarks, with hysteresis and cooldowns; slow drift is not a swipe
- [ ] Air cursor clicks dashboard buttons; 👍/👎 approve/cancel; volume swipe; rock sign = party
- [ ] Presence: greet on sit-down once, dim + stop listening when away 5+ min; friend greeting; people count sent to crew
- [ ] Calibration and gesture HUD work

## H. Dashboard
- [ ] Every v15 panel visible; nothing hidden at 1920×1080, 1440×900, 1366×768; columns scroll when needed
- [ ] Command palette (Ctrl+K), Space to talk, Esc to stop, debug overlay (Ctrl+Shift+D)
- [ ] Focus timer, quick asks, drills, debate (order + Esc cancel), roast (kind rules, humor 95), protocols

## I. Robustness
- [ ] Port 8000 busy → clear message + command to free it
- [ ] No internet → dashboard still loads, typing works, honest messages
- [ ] Updating code never touches `data/`

## K. Round 2 features
- [ ] Proactive lines: only on real triggers, rate-limited, quiet hours respected, snooze works, also shown as cards
- [ ] Routines: create by voice, run, edit, delete; built-ins work; persist across restart
- [ ] Phone companion: off by default; pairing PIN required; LAN only; talk, captions, approvals work on a phone-sized screen
- [ ] Plugins: proposal shown on approval card, nothing installed without approval, plugin tests run, disable works, sandbox rules hold
- [ ] Sketch to life, ambient mode (enter + wake), voice-only orb, work co-pilot, expense tracker summaries

## L. Smart home
- [ ] `devices_scan.py` lists BLE + LAN devices without crashing when Bluetooth is off
- [ ] Light tools tested against a fake device; real device verified manually; Home panel controls work; routines/gestures control it
- [ ] Clear message if the bulb is connected to the phone app or out of range

## J. Manual checklist on the laptop (10 minutes)
1. `python scripts\doctor.py` is all green
2. Boot sequence → "Welcome home, sir"
3. Say "Jarvis, what's the weather?" → answer within the latency target
4. Talk over the answer → it stops and listens
5. "Friday, remind me in 2 minutes to stretch" → fires after 2 minutes, also after a restart
6. Turn on camera → ✌️ swipe to Robin (morph), 👍 approve a test email to yourself
7. "Robin, what do you know about me?" → accurate, from the profile
8. Tell it a new fact, restart, ask again → remembered
9. "Jarvis, lights to 30%" → the Crompton light changes (after Phase 7)
10. Say "good night" → your routine runs
