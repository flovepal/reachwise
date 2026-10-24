"""Everything about a student that the email writer needs, plus attachments."""
from fastapi import HTTPException

from ..config import settings
from ..db import fs, get_db

LABELS = {"cv": "CV", "loi": "letter of interest", "proposal": "research proposal",
          "recommendation": "recommendation letter", "internship_report": "internship report",
          "offer_letter": "offer letter", "other": "document"}


def documents(user_id) -> list[dict]:
    return list(get_db().documents.find({"user_id": user_id}).sort("uploaded_at", 1))


def context(user: dict) -> dict:
    docs = documents(user["_id"])
    cv = next((d for d in docs if d["kind"] == "cv"), None)
    return {
        "name": user.get("name", ""),
        "goal": user.get("goal") or "admission",
        "details": user.get("details") or {},
        "cv_text": cv.get("text", "") if cv else "",
        # Recommendation letters are attached but not used for writing
        "extra_docs": [{"label": LABELS[d["kind"]], "text": d.get("text", "")}
                       for d in docs if d["kind"] in ("loi", "proposal") and d.get("text")],
        "attachment_names": [f"my {LABELS[d['kind']]}" for d in docs if d.get("attach")],
        "on_request_names": [f"my {LABELS[d['kind']]}" for d in docs if not d.get("attach")],
    }


def attachment_ids(user: dict) -> list:
    return [d["_id"] for d in documents(user["_id"]) if d.get("attach")]


def check_attachment_size(ids: list) -> None:
    total = sum(d.get("size", 0) for d in get_db().documents.find({"_id": {"$in": ids}}))
    if total > settings.max_attachments_mb * 1024 * 1024:
        raise HTTPException(400, f"Attachments add up to {total / 1048576:.1f} MB. Gmail allows about "
                                 f"{settings.max_attachments_mb} MB; turn off some attachments.")


def load_attachments(ids: list) -> list[tuple[str, bytes, str]]:
    out = []
    for d in get_db().documents.find({"_id": {"$in": ids}}):
        out.append((d["filename"], fs().get(d["gridfs_id"]).read(), d["content_type"]))
    return out
