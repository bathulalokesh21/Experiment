"""WhatsApp, phone calls, contacts. Everything outbound is draft -> approval card."""
from __future__ import annotations

import re
from urllib.parse import quote

from .. import approvals, config, platform_win, store
from .registry import tool

FILE = "contacts.json"


def contacts() -> list[dict]:
    return store.load(FILE, [])


def find_contact(name: str) -> list[dict]:
    key = name.strip().lower()
    if not key:
        return []
    exact = [c for c in contacts() if c["name"].lower() == key or key in [a.lower() for a in c.get("aliases", [])]]
    if exact:
        return exact
    return [c for c in contacts() if key in c["name"].lower() or c["name"].lower().split()[0] == key]


def normalise_phone(phone: str) -> str | None:
    digits = re.sub(r"[^\d+]", "", phone or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    plain = digits.lstrip("+")
    if len(plain) == 10:  # Indian mobile without country code
        return "+91" + plain
    if 11 <= len(plain) <= 15:
        return "+" + plain
    return None


def mask_phone(phone: str) -> str:
    return phone[:3] + " " + "•" * max(0, len(phone) - 6) + " " + phone[-3:]


def mask_email(email: str) -> str:
    user, _, domain = email.partition("@")
    return (user[:2] + "•" * max(1, len(user) - 2)) + "@" + domain


def save_contact(name: str, phone: str = "", email: str = "") -> dict:
    items = contacts()
    entry = next((c for c in items if c["name"].lower() == name.strip().lower()), None)
    if entry is None:
        entry = {"name": name.strip(), "phone": "", "email": "", "aliases": []}
        items.append(entry)
    if phone:
        norm = normalise_phone(phone)
        if not norm:
            raise ValueError("that phone number doesn't look complete")
        entry["phone"] = norm
    if email:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", email.strip(), re.I):
            raise ValueError("that email address doesn't look valid")
        entry["email"] = email.strip()
    store.save(FILE, items)
    return entry


def _resolve(name: str, need: str):
    """Returns (contact, None) or (None, message). Never guesses numbers or addresses."""
    matches = find_contact(name)
    if not matches:
        return None, (f"No contact called '{name}' is saved. Ask him for their {need} and save it with "
                      f"contact_save first. Never guess.")
    if len(matches) > 1:
        return None, "More than one contact matches: " + ", ".join(m["name"] for m in matches) + ". Ask which one."
    if not matches[0].get(need):
        return None, f"{matches[0]['name']} has no {need} saved. Ask him for it. Never guess."
    return matches[0], None


@tool("contact_save", "Save or update a contact's phone and/or email. Only with details he gave you himself.",
      {"name": "str"}, {"phone": "str", "email": "str"}, chip="Saving the contact", family="comms")
def contact_save(name: str, phone: str = "", email: str = ""):
    if not phone and not email:
        return "I need a phone number or an email to save."
    try:
        entry = save_contact(name, phone, email)
    except ValueError as exc:
        return f"Not saved: {exc}. Ask him to repeat it."
    return f"Saved {entry['name']}."


@tool("contact_find", "Look up a saved contact (shows which details exist, masked).", {"name": "str"}, family="comms")
def contact_find(name: str):
    matches = find_contact(name)
    if not matches:
        return f"No contact called '{name}'."
    return "\n".join(f"{m['name']}: phone {mask_phone(m['phone']) if m.get('phone') else 'not saved'}, "
                     f"email {mask_email(m['email']) if m.get('email') else 'not saved'}" for m in matches)


@tool("contacts_list", "List saved contact names.", family="comms")
def contacts_list():
    names = [c["name"] for c in contacts()]
    return ", ".join(names) if names else "No contacts saved yet."


@tool("whatsapp_draft", "Prepare a WhatsApp message to a saved contact. This only creates an approval card: "
      "nothing is sent until HE approves (click, 'send it', or thumbs up). Tell him it's ready for approval.",
      {"to": "str: contact name", "message": "str: exact text to send"}, chip="Drafting WhatsApp", family="comms")
def whatsapp_draft(to: str, message: str):
    contact, problem = _resolve(to, "phone")
    if problem:
        return problem
    approvals.create("whatsapp", f"WhatsApp to {contact['name']}",
                     [{"label": "To", "value": f"{contact['name']} ({mask_phone(contact['phone'])})"},
                      {"label": "Message", "value": message}],
                     {"phone": contact["phone"], "name": contact["name"], "text": message})
    return (f"The WhatsApp to {contact['name']} is on an approval card. It is NOT sent. "
            f"He approves by clicking, saying 'send it', or a thumbs up.")


@tool("call_draft", "Prepare a phone call to a saved contact via Windows Phone Link. Creates an approval card; "
      "the call starts only when HE approves.", {"to": "str: contact name"}, chip="Preparing the call", family="comms")
def call_draft(to: str):
    contact, problem = _resolve(to, "phone")
    if problem:
        return problem
    approvals.create("call", f"Call {contact['name']}",
                     [{"label": "Call", "value": f"{contact['name']} ({mask_phone(contact['phone'])})"}],
                     {"phone": contact["phone"], "name": contact["name"]})
    return f"The call to {contact['name']} is waiting for his approval. It has NOT been placed."


# ---- executors (run only from approvals.approve) --------------------------------------------

def whatsapp_mode() -> str:
    mode = config.env("WHATSAPP_MODE", "auto").lower()
    return mode if mode in ("auto", "web", "app") else "auto"


def _send_whatsapp_auto(phone: str, text: str) -> tuple[bool, str]:
    """Drive WhatsApp Web in a persistent browser profile (QR login is remembered)."""
    from playwright.sync_api import sync_playwright
    profile = config.data("whatsapp_profile")
    profile.mkdir(parents=True, exist_ok=True)
    url = f"https://web.whatsapp.com/send?phone={phone.lstrip('+')}&text={quote(text)}"
    with sync_playwright() as pw:
        ctx = None
        for channel in ("msedge", "chrome", None):
            try:
                ctx = pw.chromium.launch_persistent_context(str(profile), headless=False, channel=channel,
                                                            viewport={"width": 1100, "height": 800})
                break
            except Exception:
                continue
        if ctx is None:
            return False, "I couldn't start Edge or Chrome for WhatsApp. Run: python -m playwright install chromium"
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            send = page.locator('[data-icon="send"], [data-icon="wds-ic-send-filled"], button[aria-label="Send"]')
            qr = page.locator('canvas[aria-label*="QR"], [data-ref] canvas, div[data-testid="qrcode"]')
            deadline = 150  # seconds: enough to scan the QR on first login
            for _ in range(deadline * 2):
                if send.count() and send.first.is_visible():
                    send.first.click()
                    page.wait_for_timeout(2500)
                    return True, "WhatsApp sent."
                if qr.count() and qr.first.is_visible():
                    page.wait_for_timeout(500)
                    continue
                page.wait_for_timeout(500)
            if qr.count():
                return False, ("WhatsApp needs a first login: scan the QR code in the window that opened, then "
                               "approve again. Your draft is kept.")
            return False, "WhatsApp Web didn't show the send button in time. Your draft is kept; try again."
        finally:
            ctx.close()


async def execute_whatsapp(payload: dict):
    import asyncio
    phone, text = payload["phone"], payload["text"]
    mode = whatsapp_mode()
    if mode == "app":
        ok = platform_win.open_uri(f"whatsapp://send?phone={phone.lstrip('+')}&text={quote(text)}")
        return ok, ("Opened the WhatsApp app with the message typed. Press Enter there to send."
                    if ok else "The WhatsApp desktop app didn't open. Is it installed?")
    if mode == "web":
        ok = platform_win.open_uri(f"https://web.whatsapp.com/send?phone={phone.lstrip('+')}&text={quote(text)}")
        return ok, "Opened WhatsApp Web with the message typed. Press Enter there to send."
    try:
        return await asyncio.to_thread(_send_whatsapp_auto, phone, text)
    except ImportError:
        return False, "Playwright isn't installed, so auto-send is off. Set WHATSAPP_MODE=web in .env or install it."
    except Exception as exc:
        return False, f"WhatsApp auto-send failed ({type(exc).__name__}). Your draft is kept; try again or set WHATSAPP_MODE=web."


def execute_call(payload: dict):
    ok = platform_win.open_uri("tel:" + payload["phone"])
    return ok, (f"Calling {payload['name']} through Phone Link." if ok else
                "Windows couldn't start the call. Open the Phone Link app and make sure your phone is connected.")


approvals.register_executor("whatsapp", execute_whatsapp)
approvals.register_executor("call", execute_call)
