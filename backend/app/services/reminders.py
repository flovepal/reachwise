"""Who can get a reminder, and when."""
from datetime import timedelta

from ..config import settings
from ..db import CANCELLED, DRAFT, FAILED, QUEUED, REMINDER1, REMINDER2, SENDING, SENT, get_db, utcnow

NEXT_KIND = {0: REMINDER1, 1: REMINDER2}


def state(user: dict) -> dict:
    """{'eligible': [...], 'upcoming': [...], 'analysis_needed': bool}"""
    db = get_db()
    now = utcnow()
    wait = timedelta(days=settings.reminder_after_days)
    eligible, upcoming, removed = [], [], []
    for p in db.professors.find({"user_id": user["_id"], "status": "contacted"}):
        if p.get("possible_reply"):
            continue
        emails = list(db.emails.find({"professor_id": p["_id"], "status": {"$nin": [CANCELLED, FAILED]}}))
        if any(e["status"] in (DRAFT, QUEUED, SENDING) and e["kind"] != "initial" for e in emails):
            continue  # a reminder is already waiting
        sent = sorted((e for e in emails if e["status"] == SENT), key=lambda e: e["sent_at"])
        if not sent:
            continue
        reminders_sent = sum(1 for e in sent if e["kind"] != "initial")
        if reminders_sent >= settings.max_reminders or reminders_sent not in NEXT_KIND:
            continue
        # A student who wrote to the professor themselves doesn't need a reminder now
        if p.get("student_replied_at") and p["student_replied_at"] > sent[-1]["sent_at"]:
            continue
        due = sent[-1]["sent_at"] + wait
        item = {"professor_id": p["_id"], "name": p["name"], "email": p["email"],
                "kind": NEXT_KIND[reminders_sent], "last_sent_at": sent[-1]["sent_at"], "due_at": due}
        if p.get("skip_reminders"):
            removed.append(item)      # the student took them off the reminder list
        else:
            (eligible if due <= now else upcoming).append(item)
    last = user.get("last_analysed_at")
    earliest_due = min((e["due_at"] for e in eligible), default=None)
    return {
        "eligible": eligible,
        "upcoming": sorted(upcoming, key=lambda x: x["due_at"]),
        "removed": removed,
        # Replies must be checked after reminders became due, and recently
        "analysis_needed": bool(eligible) and (last is None or last < now - timedelta(hours=12)
                                               or (earliest_due is not None and last < earliest_due)),
        "last_analysed_at": last,
        "wait_days": settings.reminder_after_days,
    }
