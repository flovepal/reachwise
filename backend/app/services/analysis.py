"""'Analyse replies': find replies in the student's mailbox, sort them, update professors."""
import imaplib
import logging
import ssl
from datetime import timedelta

from .. import ai
from ..db import GROUP_OF, INITIAL, NON_BLOCKING, SENT, get_db, utcnow
from ..mail import imap, smtp
from ..matching import Context, bounce_target, match_message, normalize_subject, pick_by_name, searchable_name

log = logging.getLogger("profmail.analysis")


def build_context(user: dict) -> tuple[Context, dict]:
    db = get_db()
    profs = {str(p["_id"]): p for p in db.professors.find({"user_id": user["_id"]})}
    sent = list(db.emails.find({"user_id": user["_id"], "status": SENT}))
    first_sent, prof_of_mid, subject_profs = {}, {}, {}
    for e in sent:
        pid = str(e["professor_id"])
        if pid not in profs:
            continue
        if e.get("message_id"):
            prof_of_mid[e["message_id"]] = pid
        if pid not in first_sent or e["sent_at"] < first_sent[pid]:
            first_sent[pid] = e["sent_at"]
        subject_profs.setdefault(normalize_subject(e.get("subject", "")), set()).add(pid)
    # Professors imported as "already contacted" (no email record) still count
    for pid, p in profs.items():
        if pid not in first_sent and p.get("first_contacted_at"):
            first_sent[pid] = p["first_contacted_at"]
    ctx = Context(
        user_address=user["gmail"]["address"],
        prof_by_email={p["email_lower"]: pid for pid, p in profs.items()},
        prof_of_mid=prof_of_mid, first_sent=first_sent, subject_profs=subject_profs,
        prof_names={pid: p["name"] for pid, p in profs.items()},
        prof_emails={pid: p["email_lower"] for pid, p in profs.items()})
    return ctx, profs


def _first_email_text(user_id, prof_id) -> str:
    e = get_db().emails.find_one({"user_id": user_id, "professor_id": prof_id, "kind": INITIAL, "status": SENT})
    return e.get("body", "") if e else ""


def process(reader, user: dict, ctx: Context, profs: dict, m) -> str | None:
    """Handle one mailbox message. Returns the kind of match stored, if any."""
    db = get_db()
    match = match_message(m, ctx)
    if match is None:
        return None
    key = m.message_id or f"<{m.folder}:{m.uid}@{ctx.user_address}>"

    if match.kind == "student_followup":
        # An old send imported from history: learn its Message-ID so reminders can thread
        legacy = db.emails.find_one({"professor_id": profs[match.professor_id]["_id"], "status": SENT,
                                     "legacy": True, "message_id": ""})
        if legacy and m.date and m.message_id and abs(m.date - legacy["sent_at"]) < timedelta(hours=2):
            db.emails.update_one({"_id": legacy["_id"]}, {"$set": {"message_id": m.message_id}})
            ctx.prof_of_mid[m.message_id] = match.professor_id
            return "backfilled"
        db.professors.update_one({"_id": profs[match.professor_id]["_id"]},
                                 {"$max": {"student_replied_at": m.date or utcnow()}})
        return "student_followup"

    if db.replies.find_one({"user_id": user["_id"], "message_id": key}):
        return None

    body = reader.body(m)
    pid = match.professor_id
    status = "possible" if match.kind == "possible" else "confirmed"
    needs_check = False
    if match.kind == "possible":
        # Check E: sender name + signature (+ university for ties)
        named, cands = pick_by_name(m, imap.strip_quoted(body), ctx, match.candidates)
        if named:
            pid, status, needs_check = named, "confirmed", True
            match.how, match.candidates = "name", [named]
        else:
            match.candidates = cands
            pid = cands[0] if len(cands) == 1 else None
    if match.kind == "bounce":
        pid = pid or bounce_target(body, ctx)
        if pid is None:
            return None
        result = {"label": "bounced", "group": "problem",
                  "summary": f"Your email to {profs[pid]['email']} could not be delivered.",
                  "action": "Check the address and correct it in your professor list.", "key_dates": ""}
        clean = body[:3000]
    else:
        clean = imap.strip_quoted(body)
        name = profs[pid]["name"] if pid else "unknown"
        sent_text = _first_email_text(user["_id"], profs[pid]["_id"]) if pid else ""
        result = ai.classify_reply(name, m.subject, clean, sent_text)

    db.replies.insert_one({
        "user_id": user["_id"], "professor_id": profs[pid]["_id"] if pid else None,
        "candidate_ids": [profs[c]["_id"] for c in match.candidates],
        "message_id": key, "from_addr": m.from_addr, "subject": m.subject,
        "received_at": m.date or utcnow(), "body": clean, "in_spam": m.in_spam,
        "how": match.how or match.kind, "status": status, "needs_check": needs_check,
        "label": result["label"], "group": result["group"], "summary": result.get("summary", ""),
        "action": result.get("action", ""), "key_dates": result.get("key_dates", ""),
        "created_at": utcnow()})
    return "name" if needs_check else match.kind


def recompute(user_id, prof_ids=None) -> None:
    """Professor status/group from their stored replies."""
    db = get_db()
    q = {"user_id": user_id}
    if prof_ids is not None:
        q["_id"] = {"$in": list(prof_ids)}
    for p in db.professors.find(q):
        reps = list(db.replies.find({"user_id": user_id, "professor_id": p["_id"],
                                     "status": "confirmed"}).sort("received_at", 1))
        # Only a possible reply pointing at exactly this professor holds back reminders;
        # one that could be from any of several professors is just listed for the student.
        possible = db.replies.count_documents({"user_id": user_id, "status": "possible", "professor_id": p["_id"]})
        contacted = bool(p.get("first_contacted_at")) or db.emails.count_documents(
            {"professor_id": p["_id"], "status": SENT}) > 0
        blocking = [r for r in reps if r["label"] not in NON_BLOCKING]
        real = [r for r in blocking if r["label"] != "bounced"]
        if real:
            latest = real[-1]
            status, group, label, at = "replied", latest["group"], latest["label"], latest["received_at"]
        elif blocking:
            status, group, label, at = "bounced", "problem", "bounced", blocking[-1]["received_at"]
        elif contacted:
            status, group = "contacted", "no_reply"
            label = "auto_reply" if reps else ""
            at = reps[-1]["received_at"] if reps else None
        else:
            status, group, label, at = "new", "", "", None
        db.professors.update_one({"_id": p["_id"]}, {"$set": {
            "status": status, "reply_group": group, "reply_label": label, "last_reply_at": at,
            "possible_reply": possible > 0}})


def run(user_id) -> dict:
    """Full analysis for one student. Runs in a worker thread."""
    db = get_db()
    user = db.users.find_one({"_id": user_id})
    db.users.update_one({"_id": user_id}, {"$set": {"analysis": {"status": "running", "started_at": utcnow()}}})
    try:
        account = smtp.account_for(user)
        ctx, profs = build_context(user)
        counts = {"reply": 0, "possible": 0, "name": 0, "bounce": 0, "student_followup": 0, "backfilled": 0}
        skipped = 0
        if ctx.first_sent:
            since = min(ctx.first_sent.values()) - timedelta(days=1)
            addrs = [profs[pid]["email_lower"] for pid in ctx.first_sent]
            subjects = sorted({s for s in ctx.subject_profs if s})[:40]
            with imap.open_reader(account) as reader:
                names = sorted({n for pid in ctx.first_sent if (n := searchable_name(profs[pid]["name"]))})
                msgs = _retry(reader, lambda: reader.collect(since, addrs, subjects, names))
                for m in sorted(msgs, key=lambda x: x.date or utcnow()):
                    try:
                        kind = _retry(reader, lambda: process(reader, user, ctx, profs, m))
                    except NETWORK_ERRORS as e:
                        # One slow message shouldn't stop the whole check; the next check tries it again
                        log.warning("Skipped a message after retrying (%s)", e)
                        skipped += 1
                        continue
                    if kind:
                        counts[kind] += 1
        recompute(user_id)
        summary = summary_counts(user_id)
        db.users.update_one({"_id": user_id}, {"$set": {
            "analysis": {"status": "done", "finished_at": utcnow(), "new": counts, "skipped": skipped},
            "last_analysed_at": utcnow()}})
        return summary
    except Exception as e:  # noqa: BLE001
        log.exception("Analysis failed")
        db.users.update_one({"_id": user_id}, {"$set": {
            "analysis": {"status": "failed", "finished_at": utcnow(), "error": str(e)[:300]}}})
        raise


NETWORK_ERRORS = (OSError, imaplib.IMAP4.abort, ssl.SSLError)   # TimeoutError is an OSError


def _retry(reader, fn):
    """Run fn; after a timeout or dropped connection, reconnect once and try again."""
    try:
        return fn()
    except NETWORK_ERRORS as e:
        log.warning("Gmail connection problem (%s); reconnecting and retrying", e)
        if hasattr(reader, "reconnect"):
            reader.reconnect()
        return fn()


def summary_counts(user_id) -> dict:
    db = get_db()
    out = {"positive": 0, "negative": 0, "other": 0, "problem": 0, "no_reply": 0, "not_contacted": 0}
    for p in db.professors.find({"user_id": user_id}, {"reply_group": 1, "status": 1}):
        g = p.get("reply_group") or ("not_contacted" if p.get("status", "new") == "new" else "no_reply")
        out[g] = out.get(g, 0) + 1
    out["possible_to_confirm"] = db.replies.count_documents({"user_id": user_id, "status": "possible"})
    # One "Replied" tab: every real answer, whatever its tone
    out["replied"] = out["positive"] + out["negative"] + out["other"]
    out["needs_check"] = db.replies.count_documents({"user_id": user_id, "status": "confirmed", "needs_check": True})
    return out


def has_replied(user: dict, prof: dict, account) -> bool:
    """Fresh check right before a reminder goes out. Raises if the inbox can't be read."""
    db = get_db()
    prof = db.professors.find_one({"_id": prof["_id"]})
    if prof.get("status") in ("replied", "bounced") or prof.get("possible_reply"):
        return True
    ctx, profs = build_context(user)
    pid = str(prof["_id"])
    if pid not in ctx.first_sent:
        return False
    since = ctx.first_sent[pid] - timedelta(days=1)
    with imap.open_reader(account) as reader:
        for m in reader.from_one(since, prof["email_lower"]):
            process(reader, user, ctx, profs, m)
    recompute(user["_id"], [prof["_id"]])
    prof = db.professors.find_one({"_id": prof["_id"]})
    return prof.get("status") in ("replied", "bounced") or bool(prof.get("possible_reply"))


def resolve_possible(user: dict, reply_id, professor_id=None) -> None:
    """Student confirms which professor a 'possible' reply came from, or dismisses it."""
    db = get_db()
    r = db.replies.find_one({"_id": reply_id, "user_id": user["_id"]})
    if r is None:
        return
    affected = set(r.get("candidate_ids") or []) | ({r["professor_id"]} if r.get("professor_id") else set())
    if professor_id is None:
        db.replies.update_one({"_id": reply_id}, {"$set": {"status": "dismissed"}})
    else:
        db.replies.update_one({"_id": reply_id}, {"$set": {"status": "confirmed", "professor_id": professor_id,
                                                           "needs_check": False}})
        affected.add(professor_id)
    recompute(user["_id"], affected)


def mark_checked(user: dict, reply_id) -> None:
    """The student confirms a name-matched reply really is from that professor."""
    get_db().replies.update_one({"_id": reply_id, "user_id": user["_id"]}, {"$set": {"needs_check": False}})


def relabel(user: dict, reply_id, label: str) -> None:
    db = get_db()
    r = db.replies.find_one({"_id": reply_id, "user_id": user["_id"]})
    if r is None:
        return
    db.replies.update_one({"_id": reply_id}, {"$set": {"label": label, "group": GROUP_OF[label], "relabelled": True}})
    if r.get("professor_id"):
        recompute(user["_id"], [r["professor_id"]])
