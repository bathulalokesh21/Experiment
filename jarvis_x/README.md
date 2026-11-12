# JARVIS X

A voice-first personal AI that lives on your Windows laptop as a full-screen dashboard. Three assistants, each a
different Claude model with its own personality, voice, colour and living hologram:

| | Model | Calls you | Form |
|---|---|---|---|
| **JARVIS** | Opus | sir | the golden mind |
| **FRIDAY** | Sonnet | boss | the solar forge |
| **ROBIN** | Haiku | Love | the petal archive |

It runs on your **Claude subscription through the Claude Code login** (Claude Agent SDK). It never uses an API key,
and removes `ANTHROPIC_API_KEY` from its environment at startup.

Everything here is typed into **cmd**. There are no .bat files, no background mode and no auto-start.

---

## 1. Install (once)

Put this folder at `C:\jarvis_x`, then:

```
cd /d C:\jarvis_x
```
```
python -m venv venv
```
```
venv\Scripts\activate
```
```
pip install -r requirements.txt
```

Claude Code must be installed and logged in with your subscription (run `claude` once, `/login`).

Bring your data over from the previous build (copies only; `C:\jarvis_crew_v6` is never changed):

```
python scripts\migrate_v15.py
```

Check everything:

```
python scripts\doctor.py
```

## 2. Launch

```
cd /d C:\jarvis_x && venv\Scripts\activate && python run.py
```

Your browser opens `http://localhost:8000`. Click once (browsers need a click before sound and the mic), and the boot
sequence runs. Stop with **Ctrl+C** in the cmd window.

Terminal-only mode: `python cli.py` (or `python cli.py friday`).

Try it without Claude, voices or internet (offline demo brain, canned weather/news):

```
set JARVIS_FAKE=1 && python run.py
```

## 3. Using it

- **Talk**: say "Jarvis…", "Friday…" or "Robin…". After an answer you have a few seconds to follow up without the name.
  Space (or the mic button) = talk now. **Esc** = stop. Talk over it, say "stop", or say another name to interrupt.
- **Type**: the box at the bottom. **Ctrl+K** opens the command palette. **Ctrl+Shift+D** shows frame rate and latency.
- **Approvals**: WhatsApp, calls, email and new plugins are only ever *prepared*. A card appears; nothing happens
  until you click, say **"send it"** (or "cancel"), or show a 👍 (or 👎).
- **Memory**: tell it things about you; a "Memory updated" chip appears. Open the Memory panel to search, edit or
  delete. Say "forget that" or "forget everything about X". Drop a PDF/DOCX/PPTX/CSV/TXT/image anywhere to add it.
- **Daily**: "brief my day", "how was my day?", "remind me tomorrow at 9 to call Mom", "add buy strings to my list",
  "200 on lunch", "what's on my screen?", "summarise what I copied", "quiz me", "add to my comic: …",
  "when I say movie time: dim the lights and start ambient mode".
- **Guitar**: tuner, metronome (the hologram pulses with it), chord of the day, practice timer.
- **Camera** (Vision panel → *Turn on camera*, then *Calibrate* once):

  | Gesture | Action |
  |---|---|
  | ✌️ flick left/right | switch assistant |
  | 🖐️ hold | stop |
  | ✊ hold | mute / unmute |
  | ☝️ hold | listen |
  | 👍 / 👎 | approve / cancel the card |
  | 🤏 + move | rotate the hologram |
  | 🤏🤏 spread | zoom |
  | 🤟 swipe up/down | volume |
  | 👋 wave | wake |
  | 🤘 | House Party |
  | ☝️ + pinch (Air mouse on) | move a cursor and click |

  Hands and faces are processed in the browser only. Faces are counted, never identified.

## 4. Settings: `.env`

Copy `.env.example` to `.env` and edit. The useful ones:

```
CITY=Shillong
WHATSAPP_MODE=auto
ROBIN_VOICE=en-GB-SoniaNeural
```

Audition voices (files land in `data\voice_tests\`):

```
python scripts\voice_test.py robin
```

Your own voice: put clips named after the phrase in `data\voices\jarvis\clips\` (e.g. `welcome_home_sir.mp3`), or a
Piper `.onnx` model in `data\voices\jarvis\` (needs `pip install piper-tts`).

## 5. Gmail login (once)

1. In Google Cloud Console create a project, enable the **Gmail API**, create an **OAuth client ID** of type
   **Desktop app**, download the JSON.
2. Save it as `C:\jarvis_x\data\google\credentials.json` (the migration copies your old one automatically).
3. Run:
   ```
   python scripts\gmail_login.py
   ```
If JARVIS later says the login expired, run that command again.

## 6. WhatsApp

- `WHATSAPP_MODE=auto`: after you approve, a browser window opens WhatsApp Web and sends the exact text. The first time
  you scan the QR code; the login is remembered in `data\whatsapp_profile\`. It uses your installed Edge or Chrome.
- `web`: opens WhatsApp Web with the text typed; you press Enter.
- `app`: opens the WhatsApp desktop app with the text typed; you press Enter.

Calls use Windows **Phone Link** (`tel:`), so your phone must be linked there.

## 7. Phone companion

Tick "Serve a phone page on my Wi-Fi" in the Phone companion panel, restart JARVIS, then open the address shown
(`http://<laptop-ip>:8000/m`) on your phone and enter the 6-digit PIN from the panel. LAN only, off by default.
Phone browsers only allow the microphone on https pages, so on the phone you type or use the keyboard's mic key;
replies are spoken and approvals work.

## 8. Smart light

Nothing is controlled until you add it. Start with:

```
python scripts\devices_scan.py
```

It lists nearby Bluetooth devices and Tuya-based Wi-Fi devices and lets you add your light.

**If it shows up as a Tuya (Wi-Fi) device** (most likely for a bulb that links to Google Home), it needs a "local key":
1. Create a free account at iot.tuya.com → Cloud → Create a project (data centre: India).
2. In the project: Devices → Link App Account → scan the QR with the bulb's app (or the Smart Life app, after pairing
   the bulb there).
3. Run `python -m tinytuya wizard`, enter the project's Access ID / Secret; it prints each device's **local key**.
4. Run `python scripts\devices_scan.py` again, choose the bulb, paste the key.
5. Say "Jarvis, lights to 30 percent".

**If it shows up as a Bluetooth device**, it is added with the common generic bulb command set. If the light doesn't
react, the bulb speaks a private protocol; the honest options are: capture the app's commands with Android's
"Bluetooth HCI snoop log" and replay them, control it through Alexa/Google Home routines on the phone instead, or
use a cheap Tuya Wi-Fi bulb or plug. A Bluetooth bulb usually accepts one connection at a time: close the phone app.

Try the Home panel with a pretend bulb: `python scripts\devices_scan.py --add-fake`.

## 9. Your data

Everything JARVIS writes lives in `data\` (memory, knowledge files, contacts, tasks, transcripts, tokens, voices).
Code never lives there and updates never touch it. To update JARVIS, replace everything **except** `data\`, `.env`
and `profile\`. Back up by copying `data\`.

`profile\me.md` and `profile\preferences.md` are yours to edit; every assistant reads them at startup.

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| "Port 8000 is already in use" | `netstat -ano \| findstr :8000` then `taskkill /PID <number> /F` |
| The crew says Claude isn't logged in | Run `claude`, type `/login`, choose your subscription, restart JARVIS |
| "Claude Code needs a real terminal" | Start it from a normal cmd window with `python run.py` |
| No voice | `python scripts\doctor.py` → "Voices". On a filtered network it falls back to a matching Windows voice |
| Weather/headlines unavailable | The card says why in plain English; two sources are tried for each. Try a hotspot |
| Camera prompt never appears | Click the lock icon in the address bar → allow camera; the panel names the failing step |
| Mic "blocked" | Same lock icon → allow microphone. Voice recognition needs Edge or Chrome |
| Hologram is in "simple mode" | WebGL is off: enable hardware acceleration in the browser settings |
| Usage limit reached | It resets on its own. ROBIN (Haiku) is the lightest on your limit |

## 11. Tests

```
python -m pytest tests -q
```

Backend tests use fakes for Claude, voices, Gmail, WhatsApp and the network. Dashboard tests drive a real Chromium
(Playwright's, or your Edge/Chrome) with a fake mic and camera and synthetic hand landmarks. First time only, if you
have no Playwright browser: `python -m playwright install chromium` (or it will use Edge).

## Layout

```
run.py  cli.py            launchers
server/                   FastAPI app, crew (Agent SDK), tools/, memory/, devices/, voice, widgets, approvals
web/                      dashboard: src/core, src/ui, src/holo, src/vision, src/fx, src/guitar; vendor/ (three.js, MediaPipe)
profile/                  me.md, preferences.md
scripts/                  doctor, migrate_v15, gmail_login, voice_test, devices_scan, fetch_models
tests/                    pytest + Playwright
docs/                     BLUEPRINT.md, QA_PLAN.md, STATUS.md (what was verified where)
data/                     your data (never in git, never touched by updates)
```
