"""Telling the student something happened: in-app list, push (optional), and email to themselves."""
import logging

from .config import settings
from .db import get_db, utcnow

log = logging.getLogger("profmail.notify")
_firebase_ready = None


def _push(user: dict, title: str, body: str) -> None:
    global _firebase_ready
    tokens = [d["token"] for d in user.get("devices", []) if d.get("token")]
    if not tokens or not settings.firebase_credentials:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
        if _firebase_ready is None:
            firebase_admin.initialize_app(credentials.Certificate(settings.firebase_credentials))
            _firebase_ready = True
        messaging.send_each_for_multicast(messaging.MulticastMessage(
            tokens=tokens, notification=messaging.Notification(title=title, body=body)))
    except Exception as e:  # noqa: BLE001
        log.warning("Push failed: %s", e)


def _email_self(user: dict, title: str, body: str) -> None:
    from .mail import smtp
    try:
        account = smtp.account_for(user)
        msg = smtp.build_message(account, account.address, f"[{settings.app_name}] {title}",
                                 f"{body}\n\nOpen {settings.app_name} to continue.")
        smtp.send(account, msg)
    except Exception as e:  # noqa: BLE001
        log.warning("Self-email failed for %s: %s", user.get("email"), e)


def notify(user: dict, title: str, body: str, kind: str = "info", email: bool = False) -> None:
    get_db().notifications.insert_one({
        "user_id": user["_id"], "title": title, "body": body, "kind": kind,
        "read": False, "created_at": utcnow()})
    _push(user, title, body)
    if email:
        _email_self(user, title, body)
