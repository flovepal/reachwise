"""Whole student journey against a fake Gmail and an in-memory database."""
from datetime import timedelta

from app import db as dbmod
from app import jobs
from app.db import utcnow
from app.services import sending

from .conftest import TESTDATA, login

PROF_CSV = (TESTDATA / "professors.csv").read_bytes()


def setup_student(client):
    login(client)
    r = client.post("/gmail", json={"app_password": "abcd efgh ijkl mnop"})
    assert r.status_code == 200 and r.json()["gmail"]["connected"]
    stored = dbmod.get_db().users.find_one()["gmail"]
    assert "abcdefgh" not in stored["app_password_enc"]          # encrypted at rest

    r = client.post("/professors/import/preview", files={"file": ("professors.csv", PROF_CSV, "text/csv")})
    assert r.json()["valid"] == 65
    r = client.post("/professors/import", files={"file": ("professors.csv", PROF_CSV, "text/csv")})
    assert r.json()["added"] == 65

    r = client.post("/documents", data={"kind": "cv"},
                    files={"file": ("John Paul S Resume.pdf", (TESTDATA / "cv.pdf").read_bytes(), "application/pdf")})
    assert r.status_code == 200 and r.json()["has_text"], r.text
    r = client.put("/profile", json={"goal": "admission", "details": {
        "full_name": "John Paul S", "degree": "Master's", "start_date": "Fall 2027",
        "current_location": "Taiwan", "scholarship": "NSTC Graduate Research Fellowship"}})
    assert r.json()["setup"] == {"gmail": True, "professors": 65, "cv": True, "goal": True, "templates": False, "sent": 0}


def send_all_due():
    db = dbmod.get_db()
    db.emails.update_many({"status": "queued"}, {"$set": {"scheduled_at": utcnow() - timedelta(seconds=1)}})
    db.users.update_many({}, {"$unset": {"last_sent_at": ""}})
    total = 0
    for _ in range(200):
        db.users.update_many({}, {"$unset": {"last_sent_at": ""}})
        n = sending.dispatch_due(limit=1)
        if n == 0 and not db.emails.count_documents({"status": "queued", "scheduled_at": {"$lte": utcnow()}}):
            break
        total += n
    return total


def age_sent(days):
    db = dbmod.get_db()
    for e in db.emails.find({"status": "sent"}):
        db.emails.update_one({"_id": e["_id"]}, {"$set": {"sent_at": e["sent_at"] - timedelta(days=days)}})
    for p in db.professors.find({"first_contacted_at": {"$exists": True}}):
        db.professors.update_one({"_id": p["_id"]}, {"$set": {"first_contacted_at": p["first_contacted_at"] - timedelta(days=days)}})
    # Time passes for everything, including the last analysis
    for u in db.users.find({"last_analysed_at": {"$exists": True}}):
        db.users.update_one({"_id": u["_id"]}, {"$set": {"last_analysed_at": u["last_analysed_at"] - timedelta(days=days)}})



def _unbracket(x):
    if isinstance(x, str):
        return x.replace("[", "").replace("]", "")
    if isinstance(x, list):
        return [_unbracket(v) for v in x]
    if isinstance(x, dict):
        return {k: _unbracket(v) for k, v in x.items()}
    return x


def basic_filled(client):
    """The starter templates with their [guidance] brackets stripped, ready to save."""
    return _unbracket(client.get("/templates/basic").json()["templates"])

def test_full_journey(client, box):
    setup_student(client)
    db = dbmod.get_db()

    # --- the three emails: copy the prompt into any AI, paste the answer back ---
    assert client.post("/send/initial", json={}).status_code == 400      # no templates yet
    client.post("/documents", data={"kind": "recommendation"},
                files={"file": ("Recommendation.txt", b"I strongly recommend John Paul S.", "text/plain")})
    pr = client.get("/templates/prompt").json()
    assert "attaches only: my CV." in pr["prompt"] and "offering to send my recommendation letter" in pr["prompt"] and "@@@ EMAIL 1A @@@" in pr["prompt"]
    assert {f["kind"] for f in pr["files"]} == {"cv", "recommendation"}
    assert "I strongly recommend" in client.get("/templates/prompt", params={"include_text": True}).json()["prompt"]
    ai_answer = """Here you go!
```
@@@ SUBJECT A @@@
Master's study inquiry - John Paul S
@@@ EMAIL 1A @@@
Dear Professor {Professor},

I came across your research{research_in}, and I am interested in pursuing a Master's degree under your supervision.
[Mention your best project here]

Sincerely,
John Paul S
@@@ SUBJECT B @@@
Question about joining your lab
@@@ EMAIL 1B @@@
Dear {professor},

I am applying for a Master's degree and your research{research_in} matches my final-year project.

Sincerely,
John Paul S
@@@ SUBJECT C @@@
Prospective Master's student
@@@ EMAIL 1C @@@
Dear {professor},

My final-year project used physics-guided deep learning, which led me to your research{research_in}.

Sincerely,
John Paul S
@@@ EMAIL 2 @@@
Dear {professor},

Following up on my previous email.

Sincerely,
John Paul S
@@@ EMAIL 3 @@@
Dear {professor},

This is my last follow-up.

Sincerely,
John Paul S
@@@ END @@@
```"""
    r = client.post("/templates/parse", json={"text": ai_answer}).json()
    t = r["templates"]
    assert len(t["initial"]) == 3
    assert t["initial"][0]["body"].startswith("Dear {professor},")      # "Professor {Professor}" repaired
    assert any("square brackets" in w for w in r["warnings"])
    assert client.put("/templates", json=t).status_code == 400            # leftover [ ] blocks saving
    t["initial"][0]["body"] = t["initial"][0]["body"].replace("[Mention your best project here]",
                                                              "My final-year project used physics-guided deep learning.")
    assert client.post("/templates/parse", json={"text": "Dear Professor, hi"}).status_code == 400
    basic = client.get("/templates/basic").json()["templates"]
    assert "Master's degree" in basic["initial"][0]["body"]
    # a typo'd placeholder is caught
    bad = {**t, "reminder1_body": t["reminder1_body"] + " {profesor}"}
    r = client.put("/templates", json=bad)
    assert r.status_code == 400 and "{profesor}" in r.json()["detail"]
    t["reminder1_body"] += "\nP.S. I am in Taipei until December."
    assert client.put("/templates", json=t).status_code == 200
    pv = client.post("/templates/preview", json={}).json()
    assert pv["initial"].startswith("Dear Professor Cheng,")
    assert "your research in Web Mining, Information Retrieval" in pv["initial"]
    assert "Taipei until December" in pv["reminder1"] and pv["reminder_subject"].startswith("Re: ")
    kate = db.professors.find_one({"email": "katelin@csie.ntu.edu.tw"})
    pv = client.post("/templates/preview", json={"professor_id": str(kate["_id"])}).json()
    assert "Dear Professor Lin," in pv["initial"] and "your research, and" in pv["initial"]   # "Not specified" area

    # --- send: spaced out, explanation returned ---
    r = client.post("/send/initial", json={})
    assert r.status_code == 200, r.text
    assert r.json()["queued"] == 65 and "spam" in r.json()["explanation"]
    times = sorted(e["scheduled_at"] for e in db.emails.find({"status": "queued"}))
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    assert min(gaps) >= 70 and max(gaps) <= 24 * 3600 + 120
    assert send_all_due() == 65
    assert len(box.sent) == 65
    assert box.sent[0]["Message-ID"] and box.sent[0].get_payload()[1].get_filename() == "John Paul S Resume.pdf"
    assert db.professors.count_documents({"status": "contacted"}) == 65
    # the three versions take turns: A, B, C, A, ...
    order = [e["version"] for e in db.emails.find({"kind": "initial"}).sort("scheduled_at", 1)]
    assert order[:4] == ["A", "B", "C", "A"] and {order.count(v) for v in "ABC"} == {22, 21}
    assert {m["Subject"] for m in box.sent} == {v["subject"] for v in t["initial"]}
    assert any(n["title"] == "All emails sent" for n in client.get("/notifications").json())

    sent = {e["professor_id"]: e for e in db.emails.find({"status": "sent"})}
    prof = {p["email"]: p for p in db.professors.find()}
    mid = lambda email: sent[prof[email]["_id"]]["message_id"]  # noqa: E731
    subj = sent[prof["pjcheng@csie.ntu.edu.tw"]["_id"]]["subject"]

    # --- replies arrive in different ways ---
    soon = utcnow() + timedelta(days=1)
    box.add("pjcheng@csie.ntu.edu.tw", f"Re: {subj}", "Could we meet on Zoom next Tuesday at 10am?\n\nOn Mon, John wrote:\n> Dear Professor",
            soon, refs=[mid("pjcheng@csie.ntu.edu.tw")])                       # same thread
    box.add("cyy@csie.ntu.edu.tw", "About your application",
            "Unfortunately I have no openings this year.", soon)                     # NEW thread, same address
    box.add("hung.personal@gmail.com", f"Re: {subj}", "Happy to talk. - Yi-Ping", soon)  # different address
    box.add("mailer-daemon@googlemail.com", "Delivery Status Notification (Failure)",
            "Address not found\nYour message wasn't delivered to katelin@csie.ntu.edu.tw", soon)  # bounce
    box.add("sdlin@csie.ntu.edu.tw", "Automatic reply: " + subj, "I am out of office until Sept 1.", soon)  # auto reply
    box.add("ming@csie.ntu.edu.tw", f"Re: {subj}", "Please contact Professor Lee instead.", soon, in_spam=True)  # in spam
    box.add("student@gmail.com", "Re: follow up", "Thanks for your reply", soon, to=["htlin@csie.ntu.edu.tw"])  # manual
    box.add("random@news.com", "Weekly digest", "nothing", soon)                   # unrelated

    r = client.post("/replies/analyse")
    assert r.json()["status"] == "running"
    s = client.get("/replies/summary").json()
    assert s["analysis"]["status"] == "done", s
    c = s["counts"]
    assert c["positive"] == 1 and c["negative"] == 2 and c["problem"] == 1
    assert c["possible_to_confirm"] == 1
    assert c["no_reply"] == 61                       # includes the out-of-office professor

    replies = client.get("/replies").json()
    labels = {r["professor"]["email"]: r["label"] for r in replies if r["professor"]}
    assert labels["pjcheng@csie.ntu.edu.tw"] == "interview"
    assert labels["cyy@csie.ntu.edu.tw"] == "rejection"
    assert labels["katelin@csie.ntu.edu.tw"] == "bounced"
    assert labels["ming@csie.ntu.edu.tw"] == "redirect"
    assert replies[0]["label"] == "interview" and "mail.google.com" in replies[0]["gmail_link"]
    detail = client.get(f"/replies/{replies[0]['id']}").json()
    assert "Zoom" in detail["body"] and "Dear Professor" not in detail["body"]       # quoted part removed

    # the different-address reply: student confirms who sent it
    possible = client.get("/replies", params={"status": "possible"}).json()
    same_subject = db.emails.count_documents({"status": "sent", "subject": subj})
    assert same_subject == 22                       # only professors who got this version are candidates
    assert len(possible) == 1 and len(possible[0]["candidates"]) == same_subject
    r = client.post(f"/replies/{possible[0]['id']}/confirm", json={"professor_id": str(prof["hung@csie.ntu.edu.tw"]["_id"])})
    assert r.status_code == 200
    assert db.professors.find_one({"email": "hung@csie.ntu.edu.tw"})["status"] == "replied"

    # --- reminders: not before 5 days ---
    st = client.get("/reminders").json()
    assert st["eligible"] == [] and len(st["upcoming"]) == 59   # 65 - 4 replied - 1 bounced - 1 manual follow-up
    assert client.post("/send/reminders", json={}).status_code == 400

    age_sent(6)
    st = client.get("/reminders").json()
    assert st["analysis_needed"] is True                       # last analysis was before reminders became due
    assert client.post("/send/reminders", json={}).status_code == 409

    # nudge goes out (in-app + email to self)
    box.sent.clear()
    assert jobs.nudge_students() == 1
    assert box.sent[0]["To"] == "student@gmail.com" and "days" in box.sent[0]["Subject"]
    assert jobs.nudge_students() == 0                          # not again within 3 days

    client.post("/replies/analyse")
    st = client.get("/reminders").json()
    assert st["analysis_needed"] is False
    emails = {e["email"] for e in st["eligible"]}
    assert len(emails) == 59
    assert "sdlin@csie.ntu.edu.tw" in emails                     # out-of-office still gets a reminder
    for gone in ["pjcheng@csie.ntu.edu.tw", "cyy@csie.ntu.edu.tw", "hung@csie.ntu.edu.tw",
                 "katelin@csie.ntu.edu.tw", "ming@csie.ntu.edu.tw", "htlin@csie.ntu.edu.tw"]:
        assert gone not in emails

    # the student takes one professor off the reminder list by hand
    lyuu = prof["lyuu@csie.ntu.edu.tw"]["_id"]
    assert client.post(f"/professors/{lyuu}/reminders", json={"skip": True}).json()["skip"] is True
    st = client.get("/reminders").json()
    assert len(st["eligible"]) == 58 and [x["email"] for x in st["removed"]] == ["lyuu@csie.ntu.edu.tw"]

    # a professor replies after the student pressed Send but before the reminder goes out
    box.add("cjlin@csie.ntu.edu.tw", "hi", "Please send your transcript.", utcnow())
    box.sent.clear()
    r = client.post("/send/reminders", json={})
    assert r.status_code == 200 and r.json()["queued"] == 58
    rem = client.get("/emails", params={"kind": "reminder1"}).json()
    assert all(e["subject"].startswith("Re: ") for e in rem)
    assert all("Taipei until December" in e["body"] and "{" not in e["body"] for e in rem)
    send_all_due()
    assert len(box.sent) == 57
    cancelled = db.emails.find_one({"kind": "reminder1", "status": "cancelled"})
    assert db.professors.find_one({"_id": cancelled["professor_id"]})["email"] == "cjlin@csie.ntu.edu.tw"
    first = box.sent[0]
    assert first["In-Reply-To"] and first["In-Reply-To"] == first["References"]   # threaded
    assert first["Subject"].startswith("Re: ")
    assert not first.is_multipart()                                                # no CV re-attached

    # inbox unreachable -> reminder waits instead of being sent
    box.fail_reads = True
    age_sent(6)
    assert client.post("/send/reminders", json={}).status_code == 409   # not fresh enough: blocked
    db.users.update_one({}, {"$set": {"last_analysed_at": utcnow()}})
    assert client.post("/send/reminders", json={}).status_code == 200
    box.sent.clear()
    db.emails.update_many({"status": "queued"}, {"$set": {"scheduled_at": utcnow() - timedelta(seconds=1)}})
    sending.dispatch_due(limit=1)
    assert box.sent == []
    waiting = db.emails.find_one({"kind": "reminder2", "error": {"$regex": "Waiting"}})
    assert waiting and waiting["status"] == "queued"


def test_send_plan_respects_daily_cap():
    now = utcnow()
    times = sending.plan_times(now, [], 10, cap=4)
    assert len(times) == 10
    for t in times:
        window = [x for x in times if t - timedelta(hours=24) < x <= t]
        assert len(window) <= 4
    assert times[4] - times[0] > timedelta(hours=24)


def test_users_are_isolated_and_account_deletion(client, box):
    setup_student(client)
    login(client, "other@gmail.com", "Other")
    assert client.get("/professors").json() == []
    assert client.get("/documents").json() == []
    login(client)
    assert len(client.get("/professors").json()) == 65
    assert client.delete("/auth/account").json() == {"deleted": True}
    db = dbmod.get_db()
    assert db.professors.count_documents({}) == 0 and db.documents.count_documents({}) == 0
    assert client.get("/me").status_code == 401


def test_professor_crud_and_validation(client, box):
    login(client)
    r = client.post("/professors", json={"name": "Prof A", "email": "bad"})
    assert r.status_code == 400 and "Invalid email" in r.json()["detail"]
    r = client.post("/professors", json={"name": "Prof A", "email": "a@uni.edu", "research_area": "ML"})
    pid = r.json()["id"]
    assert client.post("/professors", json={"name": "Dup", "email": "A@uni.edu"}).status_code == 409
    r = client.put(f"/professors/{pid}", json={"name": "Prof A", "email": "a@uni.edu", "research_area": "NLP"})
    assert r.json()["research_area"] == "NLP"
    assert "Prof A,a@uni.edu,NLP" in client.get("/professors/export").text
    assert client.delete(f"/professors/{pid}").json() == {"deleted": 1}


def test_import_old_send_log_then_remind(client, box):
    """John's real situation: 63 emails sent on 22 Aug 2026 by the old script."""
    setup_student(client)
    db = dbmod.get_db()
    log = (TESTDATA / "sent_log.csv").read_bytes()
    r = client.post("/professors/import-history", files={"file": ("sent_log.csv", log, "text/csv")})
    assert r.json() == {"marked_contacted": 63, "not_in_list": 0}
    first = db.emails.find_one({"legacy": True})
    assert first["sent_at"].hour == 2                      # 10:05 Taipei time = 02:05 UTC
    # the copy of the old email in Gmail's Sent folder gives us its Message-ID
    from datetime import datetime
    box.add("student@gmail.com", first["subject"], "Dear Professor Cheng, ...",
            datetime(2026, 8, 22, 2, 5, 14), to=["pjcheng@csie.ntu.edu.tw"], message_id="<old-1@gmail.com>")
    box.add("pjcheng@csie.ntu.edu.tw", "Re: " + first["subject"], "Sorry, no positions.",
            datetime(2026, 8, 25), refs=["<old-1@gmail.com>"])
    client.post("/replies/analyse")
    s = client.get("/replies/summary").json()
    assert s["analysis"]["new"]["backfilled"] == 1 and s["counts"]["negative"] == 1
    st = client.get("/reminders").json()
    assert len(st["eligible"]) == 62 and st["analysis_needed"] is False
    assert client.get("/emails/stats").json()["sent_total"] == 63


def test_many_students_send_in_parallel(client, box):
    """Due emails from different students go out in the same round."""
    for i in range(5):
        login(client, f"s{i}@gmail.com", f"Student {i}")
        client.post("/gmail", json={"app_password": "abcd efgh ijkl mnop"})
        client.post("/professors", json={"name": f"Prof {i}", "email": f"p{i}@uni.edu"})
        client.post("/documents", data={"kind": "cv"}, files={"file": ("cv.txt", b"my cv", "text/plain")})
        client.put("/profile", json={"goal": "teep", "details": {"full_name": f"Student {i}"}})
        t = basic_filled(client)
        assert client.put("/templates", json=t).status_code == 200
        assert client.post("/send/initial", json={}).status_code == 200
    db = dbmod.get_db()
    db.emails.update_many({"status": "queued"}, {"$set": {"scheduled_at": utcnow() - timedelta(seconds=1)}})
    assert sending.dispatch_due() == 5
    assert sorted(m["From"].split("<")[-1].rstrip(">") for m in box.sent) == [f"s{i}@gmail.com" for i in range(5)]


def test_scholarship_left_out_for_internships(client, box):
    setup_student(client)
    client.put("/profile", json={"goal": "iipp", "details": {"full_name": "John Paul S", "scholarship": "NSTC"}})
    p = client.get("/templates/prompt").json()["prompt"]
    assert "International Internship Pilot Program (IIPP)" in p and "NSTC" not in p


def test_analysis_survives_gmail_timeouts(client, box, monkeypatch):
    """A slow message is retried once; one that keeps failing is skipped, the rest still count."""
    from tests.conftest import FakeReader
    setup_student(client)
    db = dbmod.get_db()
    t = basic_filled(client)
    client.put("/templates", json=t)
    client.post("/send/initial", json={"professor_ids": [str(p["_id"]) for p in db.professors.find().limit(3)]})
    send_all_due()
    profs = [db.professors.find_one({"_id": e["professor_id"]})["email"] for e in db.emails.find({"status": "sent"})]
    soon = utcnow() + timedelta(hours=1)
    slow = box.add(profs[0], "Re: hi", "Can we meet on Zoom?", soon)        # times out once, then works
    broken = box.add(profs[1], "Re: hi", "Unfortunately no openings.", soon)  # always times out
    box.add(profs[2], "Re: hi", "I don't have vacancy.", soon)               # fine
    calls = {"slow": 0, "reconnects": 0}
    real_body = FakeReader.body

    def flaky_body(self, m):
        if m is slow:
            calls["slow"] += 1
            if calls["slow"] == 1:
                raise TimeoutError("The read operation timed out")
        if m is broken:
            raise TimeoutError("The read operation timed out")
        return real_body(self, m)

    monkeypatch.setattr(FakeReader, "body", flaky_body)
    monkeypatch.setattr(FakeReader, "reconnect", lambda self: calls.__setitem__("reconnects", calls["reconnects"] + 1), raising=False)
    client.post("/replies/analyse")
    s = client.get("/replies/summary").json()
    assert s["analysis"]["status"] == "done", s
    assert s["analysis"]["skipped"] == 1 and calls["reconnects"] >= 2
    assert s["counts"]["positive"] == 1 and s["counts"]["negative"] == 1


def test_email_text_not_base64():
    from app.mail import smtp
    acc = smtp.Account("me@gmail.com", "pw", "John Paul S")
    msg = smtp.build_message(acc, "prof@uni.edu", "Inquiry - John", "Dear Professor Lin,\n\nI’m interested – thanks.\n",
                             [("cv.pdf", b"%PDF-1.4", "application/pdf")])
    text_part = msg.get_payload()[0]
    assert text_part["Content-Transfer-Encoding"] == "quoted-printable"
    assert "I’m interested" in text_part.get_content()


def test_reply_matched_by_name_needs_check(client, box):
    """A professor writes from a personal address: matched by sender name or signature,
    counted as replied (no reminder) with a please-check note the student can confirm or undo."""
    setup_student(client)
    db = dbmod.get_db()
    t = basic_filled(client)
    client.put("/templates", json=t)
    client.post("/send/initial", json={})
    send_all_due()
    subj = db.emails.find_one({"status": "sent"})["subject"]
    soon = utcnow() + timedelta(hours=1)
    # 1) new subject, personal address, display name only
    box.add("pjcheng.home@gmail.com", "About your internship", "Hi John, happy to talk next week.", soon,
            from_name="Pu-Jen Cheng")
    # 2) [EXTERNAL] subject from an assistant's address, name only in the signature
    box.add("lab.office@gmail.com", f"RE:[EXTERNAL] Re: [External] {subj}",
            "Dear John,\n\nI don't have vacancy this year.\n\nBest regards,\nChih-Jen Lin\nDept. of CSIE, NTU", soon)
    # 3) unknown sender, no name: still asks the student
    box.add("someone@gmail.com", f"Re: {subj}", "Interesting, tell me more.", soon)
    client.post("/replies/analyse")
    s = client.get("/replies/summary").json()
    assert s["analysis"]["new"]["name"] == 2, s
    assert s["counts"]["replied"] == 2 and s["counts"]["needs_check"] == 2
    assert s["counts"]["possible_to_confirm"] == 1
    replies = client.get("/replies").json()
    by = {r["professor"]["email"]: r for r in replies}
    assert by["pjcheng@csie.ntu.edu.tw"]["needs_check"] and by["pjcheng@csie.ntu.edu.tw"]["how"] == "name"
    assert by["cjlin@csie.ntu.edu.tw"]["label"] == "rejection"
    assert db.professors.find_one({"email": "cjlin@csie.ntu.edu.tw"})["status"] == "replied"
    # Student: "yes, that's him" for one, "not from this professor" for the other
    assert client.post(f"/replies/{by['cjlin@csie.ntu.edu.tw']['id']}/checked").status_code == 200
    client.post(f"/replies/{by['pjcheng@csie.ntu.edu.tw']['id']}/confirm", json={"professor_id": None})
    assert client.get("/replies/summary").json()["counts"]["needs_check"] == 0
    assert db.professors.find_one({"email": "pjcheng@csie.ntu.edu.tw"})["status"] == "contacted"   # back to reminders
    assert db.professors.find_one({"email": "cjlin@csie.ntu.edu.tw"})["status"] == "replied"


def test_versions_keep_rotating_across_batches(client, box):
    setup_student(client)
    db = dbmod.get_db()
    t = basic_filled(client)
    t["initial"] = [{"subject": f"Subject {v}", "body": f"Dear {{professor}},\n\nVersion {v}.\n\nJohn"} for v in "ABC"]
    assert client.put("/templates", json=t).status_code == 200
    ids = [str(p["_id"]) for p in db.professors.find().limit(5)]
    client.post("/send/initial", json={"professor_ids": ids[:2]})
    client.post("/send/initial", json={"professor_ids": ids[2:]})
    order = [e["version"] for e in db.emails.find({"kind": "initial"}).sort("scheduled_at", 1)]
    assert order == ["A", "B", "C", "A", "B"]
    pv = client.post("/templates/preview", json={}).json()
    assert [v["subject"] for v in pv["versions"]] == ["Subject A", "Subject B", "Subject C"]
