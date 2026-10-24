"""Drafts, sending, and the queue."""
from fastapi import APIRouter, Depends, HTTPException

from ..db import DRAFT, FAILED, KINDS, SENT, get_db, out
from ..security import current_user
from ..services import sending

router = APIRouter(prefix="/emails", tags=["emails"])


def email_out(e: dict, profs: dict | None = None) -> dict:
    o = out(e, drop=("user_id",))
    p = (profs or {}).get(e["professor_id"])
    if p is None and profs is None:
        p = get_db().professors.find_one({"_id": e["professor_id"]})
    o["professor"] = {"id": str(p["_id"]), "name": p["name"], "email": p["email"]} if p else None
    return o


@router.get("")
def list_emails(user=Depends(current_user), status: str = "", kind: str = ""):
    q = {"user_id": user["_id"]}
    if status:
        q["status"] = {"$in": status.split(",")}
    if kind:
        q["kind"] = kind
    rows = list(get_db().emails.find(q).sort([("scheduled_at", 1), ("created_at", 1)]))
    profs = {p["_id"]: p for p in get_db().professors.find({"user_id": user["_id"]})}
    return [email_out(e, profs) for e in rows]


@router.post("/retry")
def retry_failed(user=Depends(current_user)):
    """Put failed emails back in the queue."""
    db = get_db()
    ids = [e["_id"] for e in db.emails.find({"user_id": user["_id"], "status": FAILED}, {"_id": 1})]
    if not ids:
        raise HTTPException(400, "Nothing to retry.")
    db.emails.update_many({"_id": {"$in": ids}}, {"$set": {"status": DRAFT, "error": ""}})
    return out(sending.queue(user, ids))


@router.get("/queue")
def queue_status(user=Depends(current_user)):
    return out(sending.status(user))


@router.post("/pause")
def pause(user=Depends(current_user)):
    sending.pause(user, True)
    return out(sending.status(get_db().users.find_one({"_id": user["_id"]})))


@router.post("/resume")
def resume(user=Depends(current_user)):
    sending.pause(user, False)
    return out(sending.status(get_db().users.find_one({"_id": user["_id"]})))


@router.post("/cancel")
def cancel(user=Depends(current_user)):
    """Stop everything that hasn't gone out yet."""
    return {"cancelled": sending.cancel_queued(user)}


@router.get("/stats")
def stats(user=Depends(current_user)):
    db = get_db()
    res = {k: {} for k in KINDS}
    for e in db.emails.find({"user_id": user["_id"]}, {"kind": 1, "status": 1}):
        res[e["kind"]][e["status"]] = res[e["kind"]].get(e["status"], 0) + 1
    res["sent_total"] = db.emails.count_documents({"user_id": user["_id"], "status": SENT})
    return res
