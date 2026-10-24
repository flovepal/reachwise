"""CV, letter of interest, proposal, recommendation letters."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from .. import extract
from ..db import DOC_KINDS, fs, get_db, oid, out, utcnow
from ..security import current_user

router = APIRouter(prefix="/documents", tags=["documents"])
MAX_FILE = 10 * 1024 * 1024


def doc_out(d: dict) -> dict:
    o = out(d, drop=("user_id", "gridfs_id", "text"))
    o["has_text"] = bool(d.get("text"))
    return o


@router.get("")
def list_documents(user=Depends(current_user)):
    return [doc_out(d) for d in get_db().documents.find({"user_id": user["_id"]}).sort("uploaded_at", 1)]


@router.post("")
async def upload(file: UploadFile = File(...), kind: str = Form("cv"), user=Depends(current_user)):
    if kind not in DOC_KINDS:
        raise HTTPException(400, f"kind must be one of {DOC_KINDS}")
    mime = extract.mime_for(file.filename or "")
    if mime is None:
        raise HTTPException(400, "Upload a PDF, Word (.docx) or text file")
    data = await file.read()
    if len(data) > MAX_FILE:
        raise HTTPException(400, "File is larger than 10 MB")
    if not data:
        raise HTTPException(400, "File is empty")
    db = get_db()
    text = extract.text_of(data, mime)
    if kind == "cv":
        for old in db.documents.find({"user_id": user["_id"], "kind": "cv"}):
            fs().delete(old["gridfs_id"])
            db.documents.delete_one({"_id": old["_id"]})
    gid = fs().put(data, filename=file.filename, contentType=mime)
    doc = {"user_id": user["_id"], "kind": kind, "filename": file.filename, "content_type": mime,
           "size": len(data), "gridfs_id": gid, "text": text,
           # Email 1 carries only the CV and research proposal; the rest are offered on request
           "attach": kind in ("cv", "proposal"), "uploaded_at": utcnow()}
    res = db.documents.insert_one(doc)
    result = doc_out(db.documents.find_one({"_id": res.inserted_id}))
    if not text:
        result["warning"] = ("No text could be read from this file (it may be a scanned image). It will still be "
                             "attached to your email, and you can still give the file itself to the AI.")
    return result


@router.get("/{doc_id}/file")
def download(doc_id: str, user=Depends(current_user)):
    d = get_db().documents.find_one({"_id": oid(doc_id), "user_id": user["_id"]})
    if d is None:
        raise HTTPException(404, "Not found")
    return Response(fs().get(d["gridfs_id"]).read(), media_type=d["content_type"],
                    headers={"Content-Disposition": f'attachment; filename="{d["filename"]}"'})


class DocPatch(BaseModel):
    attach: bool


@router.patch("/{doc_id}")
def set_attach(doc_id: str, body: DocPatch, user=Depends(current_user)):
    res = get_db().documents.update_one({"_id": oid(doc_id), "user_id": user["_id"]}, {"$set": {"attach": body.attach}})
    if not res.matched_count:
        raise HTTPException(404, "Not found")
    return doc_out(get_db().documents.find_one({"_id": oid(doc_id)}))


@router.delete("/{doc_id}")
def delete(doc_id: str, user=Depends(current_user)):
    db = get_db()
    d = db.documents.find_one({"_id": oid(doc_id), "user_id": user["_id"]})
    if d is None:
        raise HTTPException(404, "Not found")
    fs().delete(d["gridfs_id"])
    db.documents.delete_one({"_id": d["_id"]})
    # Drafts shouldn't point at a deleted file
    db.emails.update_many({"user_id": user["_id"], "status": {"$in": ["draft", "queued"]}},
                          {"$pull": {"attachment_ids": d["_id"]}})
    return {"deleted": True}
