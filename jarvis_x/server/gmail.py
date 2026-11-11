"""Gmail through the official API (OAuth desktop app). Token + credentials live in
data/google/ and are never logged or shown to the model."""
from __future__ import annotations

import base64
import html
import re
from email.message import EmailMessage
from email.utils import parseaddr

from . import config

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
LOGIN_HELP = "Gmail isn't connected. In cmd run: python scripts\\gmail_login.py"
_service_factory = None  # tests inject a fake here


class GmailError(Exception):
    pass


def set_service_factory(factory) -> None:
    global _service_factory
    _service_factory = factory


def connected() -> bool:
    return _service_factory is not None or config.data("google", "token.json").exists()


def service():
    if _service_factory is not None:
        return _service_factory()
    token = config.data("google", "token.json")
    if not token.exists():
        raise GmailError(LOGIN_HELP)
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GmailError("The Google packages aren't installed. Run: pip install -r requirements.txt") from exc
    creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if not creds.valid:
        try:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                token.write_text(creds.to_json(), encoding="utf-8")
            else:
                raise GmailError("Your Gmail login has expired. In cmd run: python scripts\\gmail_login.py")
        except GmailError:
            raise
        except Exception as exc:
            raise GmailError("Your Gmail login has expired or was revoked. In cmd run: "
                             "python scripts\\gmail_login.py") from exc
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", raw)
    raw = re.sub(r"(?i)</t[dh]>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", "", raw)          # inline tags vanish without leaving a gap before punctuation
    raw = html.unescape(raw)
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in raw.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _header(msg: dict, name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def body_text(payload: dict) -> str:
    plain, rich = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            rich.append(html_to_text(_decode(data)))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return ("\n".join(plain) if plain else "\n".join(rich)).strip()


def search(query: str, limit: int = 5) -> list[dict]:
    svc = service()
    res = svc.users().messages().list(userId="me", q=query, maxResults=limit).execute()
    out = []
    for ref in res.get("messages", []) or []:
        msg = svc.users().messages().get(userId="me", id=ref["id"], format="metadata",
                                         metadataHeaders=["From", "Subject", "Date"]).execute()
        out.append({"id": msg["id"], "thread": msg.get("threadId", ""), "from": _header(msg, "From"),
                    "subject": _header(msg, "Subject") or "(no subject)", "date": _header(msg, "Date"),
                    "snippet": html.unescape(msg.get("snippet", "")),
                    "unread": "UNREAD" in msg.get("labelIds", [])})
    return out


def read(message_id: str) -> dict:
    msg = service().users().messages().get(userId="me", id=message_id, format="full").execute()
    return {"id": msg["id"], "thread": msg.get("threadId", ""), "from": _header(msg, "From"),
            "to": _header(msg, "To"), "subject": _header(msg, "Subject") or "(no subject)",
            "date": _header(msg, "Date"), "message_id": _header(msg, "Message-ID"),
            "references": _header(msg, "References"), "body": body_text(msg.get("payload", {}))[:8000]}


def known_address(address: str) -> bool:
    """Has he ever exchanged mail with this address?"""
    try:
        res = service().users().messages().list(userId="me", q=f"from:{address} OR to:{address}",
                                                maxResults=1).execute()
        return bool(res.get("messages"))
    except Exception:
        return True  # can't check: don't cry wolf


def create_draft(to: str, subject: str, body: str, reply_to_id: str = "") -> dict:
    svc = service()
    mail = EmailMessage()
    thread = None
    if reply_to_id:
        original = read(reply_to_id)
        thread = original["thread"]
        to = to or parseaddr(original["from"])[1]
        subject = original["subject"] if original["subject"].lower().startswith("re:") else "Re: " + original["subject"]
        if original["message_id"]:
            mail["In-Reply-To"] = original["message_id"]
            mail["References"] = (original["references"] + " " + original["message_id"]).strip()
    mail["To"] = to
    mail["Subject"] = subject
    mail.set_content(body)
    message = {"raw": base64.urlsafe_b64encode(mail.as_bytes()).decode()}
    if thread:
        message["threadId"] = thread
    draft = svc.users().drafts().create(userId="me", body={"message": message}).execute()
    return {"draft_id": draft["id"], "to": to, "subject": subject, "thread": thread or ""}


def send_draft(draft_id: str) -> None:
    service().users().drafts().send(userId="me", body={"id": draft_id}).execute()


def delete_draft(draft_id: str) -> None:
    service().users().drafts().delete(userId="me", id=draft_id).execute()
