"""The send queue.

When the student presses Send, every email gets a planned send time spaced
70-120 s apart (and at most DAILY_CAP per 24 h). A background job sends whatever
is due. Because times are stored in the database, a server restart loses nothing.
"""
import logging
import random
import smtplib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi import HTTPException

from ..config import settings
from ..db import CANCELLED, DRAFT, FAILED, INITIAL, QUEUED, SENDING, SENT, get_db, utcnow
from ..mail import smtp
from ..notify import notify
from . import analysis, student

log = logging.getLogger("profmail.sending")

EXPLANATION = (
    "Your emails will go out one at a time, about {gap} apart, from your own Gmail. "
    "This deliberate delay keeps your account from looking like a bulk sender, so your emails "
    "are less likely to be flagged as spam. You can close the app; sending continues on the server. "
    "At most {cap} emails are sent per 24 hours.")


def explanation() -> str:
    gap = f"{settings.min_gap_seconds // 60 or 1}-{max(1, round(settings.max_gap_seconds / 60))} minutes"
    return EXPLANATION.format(gap=gap, cap=settings.daily_cap)


def _gap() -> timedelta:
    return timedelta(seconds=random.randint(settings.min_gap_seconds, settings.max_gap_seconds))


def plan_times(start, existing: list, count: int, cap: int) -> list:
    """Planned send times for `count` emails.

    existing: send times already used (sent in the last 24 h, or queued).
    Keeps a random gap between emails and no more than `cap` in any 24 h window.
    """
    times = sorted(existing)
    out = []
    t = max([start] + [x + _gap() for x in times[-1:]])
    for _ in range(count):
        while True:
            window = [x for x in times if t - timedelta(hours=24) < x <= t]
            if len(window) < cap:
                break
            t = window[0] + timedelta(hours=24, seconds=1)
        out.append(t)
        times.append(t)
        times.sort()
        t = t + _gap()
    return out


def queue(user: dict, email_ids: list) -> dict:
    db = get_db()
    if not (user.get("gmail") or {}).get("app_password_enc"):
        raise HTTPException(400, "Connect your Gmail account first.")
    rows = list(db.emails.find({"_id": {"$in": email_ids}, "user_id": user["_id"], "status": DRAFT}))
    if not rows:
        raise HTTPException(400, "No drafts selected.")
    current = student.attachment_ids(user)
    student.check_attachment_size(current)
    for r in rows:
        if not r.get("subject", "").strip() or not r.get("body", "").strip():
            raise HTTPException(400, "One of the drafts has an empty subject or body.")
        if r["kind"] == INITIAL:
            # Use the attachments switched on right now, not when the draft was written
            r["attachment_ids"] = current
            db.emails.update_one({"_id": r["_id"]}, {"$set": {"attachment_ids": current}})
    # Initial emails first, then reminders; keep professor order stable
    rows.sort(key=lambda r: (r["kind"] != INITIAL, r["created_at"]))

    now = utcnow()
    existing = [r["sent_at"] for r in db.emails.find(
        {"user_id": user["_id"], "status": SENT, "sent_at": {"$gt": now - timedelta(hours=24)}}, {"sent_at": 1})]
    existing += [r["scheduled_at"] for r in db.emails.find(
        {"user_id": user["_id"], "status": {"$in": [QUEUED, SENDING]}}, {"scheduled_at": 1})]
    times = plan_times(now + timedelta(seconds=5), existing, len(rows), settings.daily_cap)
    for r, t in zip(rows, times):
        db.emails.update_one({"_id": r["_id"], "status": DRAFT},
                             {"$set": {"status": QUEUED, "scheduled_at": t, "error": "", "updated_at": now}})
    db.users.update_one({"_id": user["_id"]}, {"$set": {"sending_paused": False}})
    return {"queued": len(rows), "first_at": times[0], "last_at": times[-1], "explanation": explanation()}


def status(user: dict) -> dict:
    db = get_db()
    q = list(db.emails.find({"user_id": user["_id"], "status": {"$in": [QUEUED, SENDING]}},
                            {"scheduled_at": 1}).sort("scheduled_at", 1))
    since = utcnow() - timedelta(hours=24)
    return {
        "paused": bool(user.get("sending_paused")),
        "queued": len(q),
        "next_at": q[0]["scheduled_at"] if q else None,
        "finish_at": q[-1]["scheduled_at"] if q else None,
        "sent_last_24h": db.emails.count_documents({"user_id": user["_id"], "status": SENT, "sent_at": {"$gt": since}}),
        "daily_cap": settings.daily_cap,
        "failed": db.emails.count_documents({"user_id": user["_id"], "status": FAILED}),
        "explanation": explanation(),
    }


def pause(user: dict, paused: bool) -> None:
    db = get_db()
    db.users.update_one({"_id": user["_id"]}, {"$set": {"sending_paused": paused}})
    if not paused:
        # Re-plan whatever was waiting so it doesn't all go out at once
        ids = [r["_id"] for r in db.emails.find({"user_id": user["_id"], "status": QUEUED}).sort("scheduled_at", 1)]
        db.emails.update_many({"_id": {"$in": ids}}, {"$set": {"status": DRAFT}})
        if ids:
            queue(db.users.find_one({"_id": user["_id"]}), ids)


def cancel_queued(user: dict) -> int:
    res = get_db().emails.update_many({"user_id": user["_id"], "status": QUEUED},
                                      {"$set": {"status": CANCELLED, "error": "Cancelled by you", "scheduled_at": None}})
    return res.modified_count


# ----------------------------------------------------------------------------
# Background
# ----------------------------------------------------------------------------

_pool = ThreadPoolExecutor(max_workers=settings.send_workers, thread_name_prefix="send")


def dispatch_due(limit: int = 200) -> int:
    """Send what is due. Called every few seconds by the scheduler.

    Each student's emails go out one at a time (their own spacing), but different
    students are sent in parallel, so many students sending at once don't queue
    behind each other.
    """
    db = get_db()
    now = utcnow()
    picked: dict = {}                       # user_id -> (user, row): one email per student per round
    for row in db.emails.find({"status": QUEUED, "scheduled_at": {"$lte": now}}).sort("scheduled_at", 1).limit(limit):
        if row["user_id"] in picked:
            continue
        user = db.users.find_one({"_id": row["user_id"]})
        if user is None or user.get("sending_paused"):
            continue
        last = user.get("last_sent_at")
        if last and utcnow() - last < timedelta(seconds=settings.min_gap_seconds):
            db.emails.update_one({"_id": row["_id"]}, {"$set": {"scheduled_at": last + _gap()}})
            continue
        claimed = db.emails.find_one_and_update({"_id": row["_id"], "status": QUEUED},
                                                {"$set": {"status": SENDING, "updated_at": utcnow()}})
        if claimed:
            picked[row["user_id"]] = (user, claimed)
    if not picked:
        return 0
    results = list(_pool.map(lambda pair: _safe_send(*pair), picked.values()))
    return sum(1 for ok in results if ok)


def _safe_send(user: dict, row: dict) -> bool:
    try:
        return send_one(user, row)
    except Exception as e:  # noqa: BLE001
        log.exception("Unexpected error sending %s", row.get("_id"))
        _fail(row, f"Unexpected error: {e}")
        return False


def send_one(user: dict, row: dict) -> bool:
    db = get_db()
    prof = db.professors.find_one({"_id": row["professor_id"]})
    if prof is None:
        db.emails.update_one({"_id": row["_id"]}, {"$set": {"status": CANCELLED, "error": "Professor was deleted"}})
        return False
    try:
        account = smtp.account_for(user)
    except Exception as e:  # noqa: BLE001
        _fail(row, str(e))
        return False

    if row["kind"] != INITIAL:
        # Never remind someone who already answered
        try:
            if analysis.has_replied(user, prof, account):
                db.emails.update_one({"_id": row["_id"]}, {"$set": {
                    "status": CANCELLED, "error": "Not sent: the professor has replied", "updated_at": utcnow()}})
                return False
        except Exception as e:  # noqa: BLE001
            # Could not check the inbox -> wait and try again rather than risk it
            db.emails.update_one({"_id": row["_id"]}, {"$set": {
                "status": QUEUED, "scheduled_at": utcnow() + timedelta(minutes=10),
                "error": f"Waiting: couldn't check your inbox for replies ({e})"[:300]}})
            return False

    try:
        attachments = student.load_attachments(row.get("attachment_ids") or [])
        msg = smtp.build_message(account, prof["email"], row["subject"], row["body"], attachments,
                                 row.get("in_reply_to", ""), row.get("references") or [])
        mid = smtp.send(account, msg)
    except smtplib.SMTPAuthenticationError:
        _fail(row, "Gmail rejected your app password.")
        db.users.update_one({"_id": user["_id"]}, {"$set": {"sending_paused": True}})
        notify(user, "Sending paused", "Gmail rejected your app password. Reconnect Gmail in the app, "
                                       "then resume sending.", "error")
        return False
    except Exception as e:  # noqa: BLE001
        log.warning("Send failed to %s: %s", prof["email"], e)
        _fail(row, str(e))
        return False

    now = utcnow()
    refs = (row.get("references") or [])
    db.emails.update_one({"_id": row["_id"]}, {"$set": {
        "status": SENT, "sent_at": now, "message_id": mid, "references": refs, "error": "", "updated_at": now}})
    db.users.update_one({"_id": user["_id"]}, {"$set": {"last_sent_at": now}})
    upd = {"updated_at": now}
    if prof.get("status", "new") == "new":
        upd.update(status="contacted", first_contacted_at=now)
    db.professors.update_one({"_id": prof["_id"]}, {"$set": upd})
    _maybe_done(user)
    return True


def _fail(row: dict, error: str) -> None:
    get_db().emails.update_one({"_id": row["_id"]}, {"$set": {
        "status": FAILED, "error": error[:400], "updated_at": utcnow()}})


def _maybe_done(user: dict) -> None:
    db = get_db()
    if db.emails.count_documents({"user_id": user["_id"], "status": {"$in": [QUEUED, SENDING]}}) == 0:
        n = db.emails.count_documents({"user_id": user["_id"], "status": SENT,
                                       "sent_at": {"$gt": utcnow() - timedelta(hours=24)}})
        notify(user, "All emails sent",
               f"{n} emails went out in the last 24 hours. Come back in {settings.reminder_after_days} "
               "days and tap Analyse replies.", "sent")


def recover_interrupted() -> None:
    """Rows left in 'sending' by a crash may or may not have gone out."""
    get_db().emails.update_many(
        {"status": SENDING, "updated_at": {"$lt": utcnow() - timedelta(minutes=10)}},
        {"$set": {"status": FAILED, "error": "Interrupted by a server restart. Check your Gmail Sent "
                                             "folder before sending this again."}})
