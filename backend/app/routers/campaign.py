"""Templates and the two send buttons: 'Send first emails' and 'Send reminders'."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import ai
from ..db import DRAFT, INITIAL, get_db, oid, out, utcnow
from ..security import current_user
from ..services import reminders, sending, templates

router = APIRouter(tags=["campaign"])


@router.get("/templates")
def get_templates(user=Depends(current_user)):
    return {"templates": templates.get(user), "placeholders": list(ai.PLACEHOLDERS)}


@router.get("/templates/basic")
def basic_templates(user=Depends(current_user)):
    """Base templates for the student's goal, to fill in by hand (nothing is saved)."""
    return {"templates": templates.basic(user)}


@router.get("/templates/prompt")
def get_prompt(include_text: bool = False, user=Depends(current_user)):
    """The prompt the student copies into any AI, together with their documents."""
    return templates.prompt(user, include_text)


class ParseIn(BaseModel):
    text: str


@router.post("/templates/parse")
def parse_answer(body: ParseIn, user=Depends(current_user)):
    """Split the AI's answer into subject + three emails (nothing is saved)."""
    return templates.parse(body.text)


class VersionIn(BaseModel):
    subject: str = ""
    body: str = ""


class TemplatesIn(BaseModel):
    initial: list[VersionIn]          # 1-3 versions of email 1, sent in turn
    reminder1_body: str
    reminder2_body: str


@router.put("/templates")
def save_templates(body: TemplatesIn, user=Depends(current_user)):
    return {"templates": templates.save(user, body.model_dump())}


class PreviewIn(BaseModel):
    professor_id: str | None = None


@router.post("/templates/preview")
def preview(body: PreviewIn, user=Depends(current_user)):
    """The three emails exactly as one professor would receive them."""
    db = get_db()
    q = {"user_id": user["_id"]}
    if body.professor_id:
        q["_id"] = oid(body.professor_id)
    prof = db.professors.find_one(q, sort=[("created_at", 1)])
    if prof is None:
        prof = {"name": "Prof. Example Chen", "research_area": "Computer Vision", "university": ""}
    t = templates.require(user)
    versions = []
    for i in range(len(t["initial"])):
        subject, text = templates.render(user, prof, INITIAL, version=i)
        versions.append({"subject": subject, "body": text})
    subject, initial = versions[0]["subject"], versions[0]["body"]
    return {"professor": {"id": str(prof.get("_id", "")), "name": prof["name"]},
            "versions": versions,
            "subject": subject, "reminder_subject": ai.re_subject(subject),
            "initial": initial,
            "reminder1": templates.render(user, prof, "reminder1")[1],
            "reminder2": templates.render(user, prof, "reminder2")[1]}


class SendIn(BaseModel):
    professor_ids: list[str] = []      # empty = everyone eligible


def _queue(user: dict, items: list[tuple[dict, str]]) -> dict:
    """items: (professor, kind). Creates the emails and puts them in the send queue."""
    if not (user.get("gmail") or {}).get("app_password_enc"):
        raise HTTPException(400, "Connect your Gmail account first.")
    templates.require(user)
    db = get_db()
    now = utcnow()
    from ..services import student
    att = student.attachment_ids(user)
    n_versions = len(templates.require(user)["initial"])
    # Carry the A/B/C rotation on from earlier batches
    turn = db.emails.count_documents({"user_id": user["_id"], "kind": INITIAL,
                                      "status": {"$in": ["queued", "sending", "sent"]}})
    ids = []
    for prof, kind in items:
        prev = None if kind == INITIAL else templates.last_sent(user["_id"], prof["_id"])
        version = turn % n_versions if kind == INITIAL else None
        subject, body = templates.render(user, prof, kind, prev, version or 0)
        doc = {"user_id": user["_id"], "professor_id": prof["_id"], "kind": kind, "status": DRAFT,
               "subject": subject, "body": body, "attachment_ids": att if kind == INITIAL else [],
               "message_id": "", "error": "", "created_at": now, "updated_at": now}
        if kind == INITIAL:
            doc["version"] = "ABC"[version]
            turn += 1
        if prev:
            doc["in_reply_to"] = prev.get("message_id", "")
            doc["references"] = (prev.get("references") or []) + ([prev["message_id"]] if prev.get("message_id") else [])
        ids.append(db.emails.insert_one(doc).inserted_id)
    try:
        res = sending.queue(user, ids)
    except Exception:
        db.emails.delete_many({"_id": {"$in": ids}})
        raise
    return out(res)


@router.post("/send/initial")
def send_initial(body: SendIn, user=Depends(current_user)):
    db = get_db()
    q = {"user_id": user["_id"], "status": "new"}
    if body.professor_ids:
        q["_id"] = {"$in": [oid(i) for i in body.professor_ids]}
    busy = {e["professor_id"] for e in db.emails.find(
        {"user_id": user["_id"], "kind": INITIAL, "status": {"$in": ["queued", "sending", "sent"]}})}
    profs = [p for p in db.professors.find(q).sort("created_at", 1) if p["_id"] not in busy]
    if not profs:
        raise HTTPException(400, "Everyone selected has already been emailed.")
    return _queue(user, [(p, INITIAL) for p in profs])


@router.post("/send/reminders")
def send_reminders(body: SendIn, user=Depends(current_user)):
    st = reminders.state(user)
    if st["analysis_needed"]:
        raise HTTPException(409, "Tap 'Analyse replies' first so nobody who already replied gets a reminder.")
    wanted = {oid(i) for i in body.professor_ids}
    items = [e for e in st["eligible"] if not wanted or e["professor_id"] in wanted]
    if not items:
        raise HTTPException(400, "Nobody selected is due for a reminder.")
    profs = {p["_id"]: p for p in get_db().professors.find({"_id": {"$in": [e["professor_id"] for e in items]}})}
    return _queue(user, [(profs[e["professor_id"]], e["kind"]) for e in items])


class SkipIn(BaseModel):
    skip: bool


@router.post("/professors/{prof_id}/reminders")
def skip_reminders(prof_id: str, body: SkipIn, user=Depends(current_user)):
    """The student removes (or puts back) a professor from the reminder list."""
    res = get_db().professors.update_one({"_id": oid(prof_id), "user_id": user["_id"]},
                                         {"$set": {"skip_reminders": body.skip}})
    if not res.matched_count:
        raise HTTPException(404, "Not found")
    return {"ok": True, "skip": body.skip}
