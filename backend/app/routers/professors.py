"""Professor list: add one by one, edit, delete, import CSV/Excel, export CSV."""
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from .. import importer
from ..db import get_db, oid, out, utcnow
from ..security import current_user

router = APIRouter(prefix="/professors", tags=["professors"])
MAX_UPLOAD = 5 * 1024 * 1024


class ProfessorIn(BaseModel):
    name: str
    email: str
    research_area: str = ""
    university: str = ""
    department: str = ""
    profile_url: str = ""
    notes: str = ""


def _validated(body: ProfessorIn) -> dict:
    row, errors = importer.clean_row(body.model_dump())
    if errors:
        raise HTTPException(400, "; ".join(errors))
    return row


def prof_out(p: dict) -> dict:
    return out(p, drop=("user_id", "email_lower"))


@router.get("")
def list_professors(user=Depends(current_user), status: str = "", group: str = "", q: str = ""):
    query = {"user_id": user["_id"]}
    if status:
        query["status"] = status
    if group:
        query["reply_group"] = group
    rows = list(get_db().professors.find(query).sort("created_at", 1))
    if q:
        ql = q.lower()
        rows = [p for p in rows if ql in p["name"].lower() or ql in p["email_lower"]
                or ql in p.get("research_area", "").lower()]
    return [prof_out(p) for p in rows]


@router.post("")
def add_professor(body: ProfessorIn, user=Depends(current_user)):
    row = _validated(body)
    now = utcnow()
    doc = {**row, "user_id": user["_id"], "email_lower": row["email"].lower(), "status": "new",
           "reply_group": "", "created_at": now, "updated_at": now}
    try:
        res = get_db().professors.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, f"{row['email']} is already in your list")
    return prof_out(get_db().professors.find_one({"_id": res.inserted_id}))


@router.get("/export")
def export_csv(user=Depends(current_user)):
    rows = list(get_db().professors.find({"user_id": user["_id"]}).sort("created_at", 1))
    return Response(importer.to_csv(rows), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="professors.csv"'})


@router.get("/template")
def template_csv():
    return Response("Professor,Email,Research Area,University,Department,Profile URL,Notes\n",
                    media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="professors_template.csv"'})


async def _read(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, "File is larger than 5 MB")
    return data


@router.post("/import/preview")
async def import_preview(file: UploadFile = File(...), user=Depends(current_user)):
    """Check a file without saving. Shows matched columns and every row's problems."""
    result = importer.parse(file.filename or "", await _read(file))
    if not result["fatal"]:
        existing = {p["email_lower"] for p in get_db().professors.find({"user_id": user["_id"]}, {"email_lower": 1})}
        result["already_in_list"] = sum(1 for r in result["rows"]
                                        if not r["errors"] and r["data"]["email"].lower() in existing)
    return result


@router.post("/import")
async def import_file(file: UploadFile = File(...), update_existing: bool = Form(False),
                      user=Depends(current_user)):
    """Save the valid rows. Rows with problems are skipped and listed back."""
    result = importer.parse(file.filename or "", await _read(file))
    if result["fatal"]:
        raise HTTPException(400, result["fatal"])
    db = get_db()
    now = utcnow()
    added = updated = skipped = 0
    for r in result["rows"]:
        if r["errors"]:
            continue
        row = r["data"]
        key = {"user_id": user["_id"], "email_lower": row["email"].lower()}
        if db.professors.find_one(key):
            if update_existing:
                db.professors.update_one(key, {"$set": {**row, "updated_at": now}})
                updated += 1
            else:
                skipped += 1
            continue
        db.professors.insert_one({**row, **key, "status": "new", "reply_group": "", "created_at": now, "updated_at": now})
        added += 1
    return {"added": added, "updated": updated, "skipped_existing": skipped,
            "invalid_rows": [r for r in result["rows"] if r["errors"]],
            "column_warnings": result["column_warnings"]}


@router.post("/import-history")
async def import_history(file: UploadFile = File(...), timezone: str = Form("Asia/Taipei"),
                         user=Depends(current_user)):
    """Mark professors as already emailed, from an old send log (Email, Date[, Subject, Type]).

    Their replies will be found by address, and they can get reminders like everyone else.
    """
    import csv as _csv
    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(timezone)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Unknown timezone")
    text = (await _read(file)).decode("utf-8-sig", errors="replace")
    rows = list(_csv.DictReader(io.StringIO(text)))
    if not rows or "Email" not in rows[0] or "Date" not in rows[0]:
        raise HTTPException(400, "The file needs at least 'Email' and 'Date' columns")
    db = get_db()
    marked = missing = 0
    for r in rows:
        if (r.get("Type") or "initial").strip().lower() != "initial":
            continue
        p = db.professors.find_one({"user_id": user["_id"], "email_lower": (r.get("Email") or "").strip().lower()})
        try:
            sent_at = datetime.strptime(r["Date"].strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz) \
                .astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        except ValueError:
            continue
        if p is None:
            missing += 1
            continue
        if db.emails.find_one({"professor_id": p["_id"], "kind": "initial", "status": "sent"}):
            continue
        db.emails.insert_one({
            "user_id": user["_id"], "professor_id": p["_id"], "kind": "initial", "status": "sent",
            "subject": (r.get("Subject") or "").strip(), "body": "", "attachment_ids": [], "message_id": "",
            "legacy": True, "sent_at": sent_at, "created_at": utcnow(), "updated_at": utcnow()})
        db.professors.update_one({"_id": p["_id"]}, {"$set": {
            "status": "contacted", "first_contacted_at": sent_at, "reply_group": "no_reply"}})
        marked += 1
    return {"marked_contacted": marked, "not_in_list": missing}


@router.put("/{prof_id}")
def edit_professor(prof_id: str, body: ProfessorIn, user=Depends(current_user)):
    row = _validated(body)
    db = get_db()
    try:
        res = db.professors.update_one({"_id": oid(prof_id), "user_id": user["_id"]},
                                       {"$set": {**row, "email_lower": row["email"].lower(), "updated_at": utcnow()}})
    except DuplicateKeyError:
        raise HTTPException(409, f"{row['email']} is already in your list")
    if res.matched_count == 0:
        raise HTTPException(404, "Not found")
    return prof_out(db.professors.find_one({"_id": oid(prof_id)}))


class BulkDelete(BaseModel):
    ids: list[str]


def _delete(user, ids) -> int:
    db = get_db()
    q = {"_id": {"$in": ids}, "user_id": user["_id"]}
    n = db.professors.delete_many(q).deleted_count
    db.emails.delete_many({"user_id": user["_id"], "professor_id": {"$in": ids}, "status": {"$in": ["draft", "generating", "queued"]}})
    return n


@router.delete("/{prof_id}")
def delete_professor(prof_id: str, user=Depends(current_user)):
    if not _delete(user, [oid(prof_id)]):
        raise HTTPException(404, "Not found")
    return {"deleted": 1}


@router.post("/delete")
def delete_many(body: BulkDelete, user=Depends(current_user)):
    return {"deleted": _delete(user, [oid(i) for i in body.ids])}
