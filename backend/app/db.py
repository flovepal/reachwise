"""MongoDB access, constants and small helpers."""
from datetime import datetime, timezone

import gridfs
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from .config import settings

# ---- email kinds / statuses ------------------------------------------------
INITIAL, REMINDER1, REMINDER2 = "initial", "reminder1", "reminder2"
KINDS = [INITIAL, REMINDER1, REMINDER2]

DRAFT, QUEUED, SENDING, SENT, FAILED, CANCELLED = "draft", "queued", "sending", "sent", "failed", "cancelled"

# ---- reply labels and the groups shown to the student -----------------------
LABELS = ["interview", "interested", "needs_info", "redirect", "rejection", "auto_reply", "bounced", "other"]
GROUP_OF = {
    "interview": "positive", "interested": "positive", "needs_info": "positive",
    "redirect": "negative", "rejection": "negative",
    "bounced": "problem",
    "auto_reply": "no_reply",      # out-of-office does not count as a reply
    "other": "other",
}
# Labels that do NOT stop reminders
NON_BLOCKING = {"auto_reply"}

GOALS = ["teep", "iipp", "admission"]
DOC_KINDS = ["cv", "recommendation", "internship_report", "offer_letter", "loi", "proposal", "other"]

_client: MongoClient | None = None
_db: Database | None = None


def utcnow() -> datetime:
    """Naive UTC; everything in the database is stored this way."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db() -> Database:
    global _client, _db
    if _db is None:
        _client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=10000)
        _db = _client[settings.mongodb_db]
        ensure_indexes(_db)
    return _db


def set_db(db: Database) -> None:
    """Used by tests to swap in an in-memory database."""
    global _db
    _db = db
    ensure_indexes(db)


def fs() -> gridfs.GridFS:
    return gridfs.GridFS(get_db())


def ensure_indexes(db: Database) -> None:
    db.users.create_index("google_sub", unique=True, sparse=True)
    db.users.create_index("email")
    db.professors.create_index([("user_id", ASCENDING), ("email_lower", ASCENDING)], unique=True)
    db.emails.create_index([("status", ASCENDING), ("scheduled_at", ASCENDING)])
    db.emails.create_index([("user_id", ASCENDING), ("professor_id", ASCENDING)])
    db.emails.create_index("message_id")
    db.replies.create_index([("user_id", ASCENDING), ("message_id", ASCENDING)], unique=True)
    db.notifications.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    db.documents.create_index("user_id")


def oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(404, "Not found")


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def out(doc: dict | None, drop: tuple = ()) -> dict | None:
    """Make a Mongo document JSON-friendly: ObjectId -> str, datetime -> ISO."""
    if doc is None:
        return None
    res = {}
    for k, v in doc.items():
        if k in drop:
            continue
        key = "id" if k == "_id" else k
        res[key] = _conv(v)
    return res


def _conv(v):
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, datetime):
        return iso(v)
    if isinstance(v, list):
        return [_conv(x) for x in v]
    if isinstance(v, dict):
        return {k: _conv(x) for k, x in v.items()}
    return v
