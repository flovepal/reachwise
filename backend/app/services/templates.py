"""The student's emails: written with any AI via a copy-paste prompt (or by hand), saved once,
and filled in per professor when sending.

Shape: {"initial": [{"subject", "body"}, ... up to 3 versions], "reminder1_body", "reminder2_body"}
The versions of email 1 are sent in turn (A to the 1st professor, B to the 2nd, C to the 3rd, A again...).
"""
from fastapi import HTTPException

from .. import ai, prompts
from ..db import INITIAL, REMINDER1, REMINDER2, SENT, get_db, utcnow
from . import student

MAX_VERSIONS = 3
BODY_FOR = {REMINDER1: "reminder1_body", REMINDER2: "reminder2_body"}


def normalize(t: dict | None) -> dict | None:
    """Accept the older single-version shape too."""
    if not t:
        return None
    if "initial" in t:
        initial = [{"subject": (x.get("subject") or ""), "body": (x.get("body") or "")} for x in t["initial"]]
    else:
        initial = [{"subject": t.get("initial_subject", ""), "body": t.get("initial_body", "")}]
    return {"initial": initial, "reminder1_body": t.get("reminder1_body", ""),
            "reminder2_body": t.get("reminder2_body", "")}


def get(user: dict) -> dict | None:
    return normalize(user.get("templates"))


def basic(user: dict) -> dict:
    """The base templates for the student's goal, to fill in by hand."""
    if not user.get("goal"):
        raise HTTPException(400, "Choose your goal (TEEP, IIPP or Admission) first.")
    return prompts.base_templates(student.context(user))


def prompt(user: dict, include_text: bool) -> dict:
    if not user.get("goal"):
        raise HTTPException(400, "Choose your goal (TEEP, IIPP or Admission) first.")
    docs = student.documents(user["_id"])
    if not any(d["kind"] == "cv" for d in docs):
        raise HTTPException(400, "Upload your CV first.")
    text = prompts.build_prompt(student.context(user), docs, include_text)
    return {"prompt": text, "characters": len(text),
            "files": [{"id": str(d["_id"]), "filename": d["filename"], "kind": d["kind"]} for d in docs],
            "unreadable": [d["filename"] for d in docs if not d.get("text")]}


def parse(text: str) -> dict:
    try:
        data, warnings = prompts.parse_answer(text)
    except prompts.ParseError as e:
        raise HTTPException(400, str(e))
    return {"templates": data, "warnings": warnings}


def save(user: dict, data: dict) -> dict:
    t = normalize(data)
    t["initial"] = [{"subject": x["subject"].strip(), "body": x["body"].strip()} for x in t["initial"]
                    if x["subject"].strip() or x["body"].strip()][:MAX_VERSIONS]
    t["reminder1_body"], t["reminder2_body"] = t["reminder1_body"].strip(), t["reminder2_body"].strip()
    if not t["initial"] or any(not x["subject"] or not x["body"] for x in t["initial"]):
        raise HTTPException(400, "Every version of email 1 needs a subject and a body.")
    if not t["reminder1_body"] or not t["reminder2_body"]:
        raise HTTPException(400, "Fill in email 2 and email 3.")
    texts = [v for x in t["initial"] for v in (x["subject"], x["body"])] + [t["reminder1_body"], t["reminder2_body"]]
    bad = sorted({p for v in texts for p in ai.unknown_placeholders(v)})
    if bad:
        raise HTTPException(400, f"Unknown placeholder(s): {', '.join(bad)}. Allowed: {', '.join(ai.PLACEHOLDERS)}")
    left = [b for v in texts for b in prompts.brackets(v)]
    if left:
        raise HTTPException(400, "Some parts are still in [square brackets], e.g. " + left[0][:80]
                                 + ". Fill them in or delete them, so professors don't see them.")
    get_db().users.update_one({"_id": user["_id"]}, {"$set": {"templates": {**t, "saved_at": utcnow()}}})
    return t


def require(user: dict) -> dict:
    t = get(user)
    if not t or not t["initial"] or not all(x["subject"] and x["body"] for x in t["initial"]) \
            or not t["reminder1_body"] or not t["reminder2_body"]:
        raise HTTPException(400, "Write your emails first.")
    return t


def render(user: dict, prof: dict, kind: str, previous: dict | None = None, version: int = 0) -> tuple[str, str]:
    t = require(user)
    if kind == INITIAL:
        v = t["initial"][version % len(t["initial"])]
        return ai.fill(v["subject"], prof), ai.fill(v["body"], prof)
    body = ai.fill(t[BODY_FOR[kind]], prof)
    base = (previous or {}).get("subject") or ai.fill(t["initial"][0]["subject"], prof)
    return ai.re_subject(base), body


def last_sent(user_id, prof_id) -> dict | None:
    return get_db().emails.find_one({"user_id": user_id, "professor_id": prof_id, "status": SENT},
                                    sort=[("sent_at", -1)])
