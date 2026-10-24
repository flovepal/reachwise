"""Analyse replies, the categorised summary, reminders, notifications."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..db import GROUP_OF, INITIAL, LABELS, get_db, oid, out, utcnow
from ..jobs import submit
from ..security import current_user
from ..services import analysis, reminders

router = APIRouter(tags=["replies"])


def gmail_link(user: dict, message_id: str) -> str:
    acct = (user.get("gmail") or {}).get("address", "")
    q = quote(f"in:anywhere rfc822msgid:{message_id.strip('<>')}", safe="")
    return f"https://mail.google.com/mail/?authuser={quote(acct)}#search/{q}"


def reply_out(user: dict, r: dict, profs: dict) -> dict:
    o = out(r, drop=("user_id",))
    p = profs.get(r.get("professor_id"))
    o["professor"] = {"id": str(p["_id"]), "name": p["name"], "email": p["email"]} if p else None
    o["candidates"] = [{"id": str(profs[c]["_id"]), "name": profs[c]["name"], "email": profs[c]["email"]}
                       for c in r.get("candidate_ids", []) if c in profs]
    o["gmail_link"] = gmail_link(user, r["message_id"])
    o.pop("body", None)
    return o


@router.post("/replies/analyse")
def start_analysis(user=Depends(current_user)):
    if not (user.get("gmail") or {}).get("app_password_enc"):
        raise HTTPException(400, "Connect your Gmail account first.")
    if (user.get("analysis") or {}).get("status") == "running":
        return {"status": "running"}
    get_db().users.update_one({"_id": user["_id"]}, {"$set": {"analysis": {"status": "running", "started_at": utcnow()}}})
    submit(analysis.run, user["_id"])
    return {"status": "running"}


@router.get("/replies/summary")
def summary(user=Depends(current_user)):
    """Status of the last analysis + counts per group + reminder availability."""
    st = reminders.state(user)
    return out({
        "analysis": user.get("analysis") or {"status": "never"},
        "last_analysed_at": user.get("last_analysed_at"),
        "counts": analysis.summary_counts(user["_id"]),
        "reminders_available": len(st["eligible"]),
        "next_reminder_at": st["upcoming"][0]["due_at"] if st["upcoming"] else None,
        "analysis_needed": st["analysis_needed"],
    })


@router.get("/replies")
def list_replies(user=Depends(current_user), group: str = "", status: str = "confirmed"):
    db = get_db()
    q = {"user_id": user["_id"], "status": {"$in": status.split(",")}}
    if group:
        q["group"] = group
    profs = {p["_id"]: p for p in db.professors.find({"user_id": user["_id"]})}
    # Replies to double-check first, then newest first
    rows = sorted(db.replies.find(q), key=lambda r: (not r.get("needs_check"), -r["received_at"].timestamp()))
    return [reply_out(user, r, profs) for r in rows]


@router.get("/replies/no-reply")
def no_reply(user=Depends(current_user)):
    """Professors contacted who haven't answered (out-of-office counts as no reply)."""
    st = reminders.state(user)
    due = {e["professor_id"]: e for e in st["eligible"] + st["upcoming"]}
    rows = []
    for p in get_db().professors.find({"user_id": user["_id"], "status": "contacted"}):
        e = due.get(p["_id"])
        rows.append({"id": str(p["_id"]), "name": p["name"], "email": p["email"],
                     "auto_reply": p.get("reply_label") == "auto_reply",
                     "possible_reply": bool(p.get("possible_reply")),
                     "next_reminder": e["kind"] if e else None,
                     "reminder_due_at": out({"t": e["due_at"]})["t"] if e else None})
    return rows


@router.get("/replies/{reply_id}")
def reply_detail(reply_id: str, user=Depends(current_user)):
    db = get_db()
    r = db.replies.find_one({"_id": oid(reply_id), "user_id": user["_id"]})
    if r is None:
        raise HTTPException(404, "Not found")
    profs = {p["_id"]: p for p in db.professors.find({"user_id": user["_id"]})}
    o = reply_out(user, r, profs)
    o["body"] = r.get("body", "")
    if r.get("professor_id"):
        first = db.emails.find_one({"professor_id": r["professor_id"], "kind": INITIAL, "status": "sent"})
        o["your_email"] = {"subject": first["subject"], "body": first["body"]} if first else None
    return o


class ConfirmIn(BaseModel):
    professor_id: str | None = None    # None = not a reply from any of my professors


@router.post("/replies/{reply_id}/confirm")
def confirm(reply_id: str, body: ConfirmIn, user=Depends(current_user)):
    pid = oid(body.professor_id) if body.professor_id else None
    if pid and not get_db().professors.find_one({"_id": pid, "user_id": user["_id"]}):
        raise HTTPException(404, "Professor not found")
    analysis.resolve_possible(user, oid(reply_id), pid)
    return {"ok": True}


@router.post("/replies/{reply_id}/checked")
def mark_checked(reply_id: str, user=Depends(current_user)):
    """'Yes, this reply is from that professor' (clears the please-check note)."""
    analysis.mark_checked(user, oid(reply_id))
    return {"ok": True}


class LabelIn(BaseModel):
    label: str


@router.post("/replies/{reply_id}/label")
def set_label(reply_id: str, body: LabelIn, user=Depends(current_user)):
    """The student corrects the category."""
    if body.label not in LABELS:
        raise HTTPException(400, f"label must be one of {LABELS}")
    analysis.relabel(user, oid(reply_id), body.label)
    return {"ok": True, "group": GROUP_OF[body.label]}


# ---- reminders ---------------------------------------------------------------

@router.get("/reminders")
def reminder_state(user=Depends(current_user)):
    st = reminders.state(user)
    return out({**st, "message": _reminder_message(st)})


def _reminder_message(st: dict) -> str:
    if st["eligible"] and st["analysis_needed"]:
        return "Tap 'Analyse replies' first. Reminders only go to professors who haven't answered."
    if st["eligible"]:
        return f"{len(st['eligible'])} professors haven't replied in {st['wait_days']}+ days. You can send them a reminder."
    if st["upcoming"]:
        return (f"Reminders are suggested {st['wait_days']} days after your last email. "
                "The next ones become available soon.")
    return "No reminders needed right now."


# ---- notifications -------------------------------------------------------------

@router.get("/notifications")
def notifications(user=Depends(current_user)):
    rows = get_db().notifications.find({"user_id": user["_id"]}).sort("created_at", -1).limit(50)
    return [out(n, drop=("user_id",)) for n in rows]


@router.post("/notifications/read")
def mark_read(user=Depends(current_user)):
    get_db().notifications.update_many({"user_id": user["_id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}


class DeviceIn(BaseModel):
    token: str
    platform: str = ""


@router.post("/devices")
def register_device(body: DeviceIn, user=Depends(current_user)):
    """Firebase push token from the phone app."""
    db = get_db()
    db.users.update_one({"_id": user["_id"]}, {"$pull": {"devices": {"token": body.token}}})
    db.users.update_one({"_id": user["_id"]}, {"$push": {"devices": {
        "token": body.token, "platform": body.platform, "added_at": utcnow()}}})
    return {"ok": True, "push_enabled": bool(settings.firebase_credentials)}
