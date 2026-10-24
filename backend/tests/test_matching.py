from datetime import datetime, timedelta

from app.mail.imap import Msg
from app.matching import Context, bounce_target, match_message, normalize_subject

T0 = datetime(2026, 8, 22, 2, 0)


def ctx():
    return Context(
        user_address="student@gmail.com",
        prof_by_email={"a@ntu.edu.tw": "A", "b@ntu.edu.tw": "B", "c@ntu.edu.tw": "C"},
        prof_of_mid={"<sent-a@gmail.com>": "A", "<sent-b@gmail.com>": "B", "<sent-c@gmail.com>": "C"},
        first_sent={"A": T0, "B": T0, "C": T0},
        subject_profs={"teep research internship inquiry": {"A", "B", "C"}, "unique subject for b": {"B"}},
    )


def msg(frm, subject="", refs=(), to=("student@gmail.com",), date=T0 + timedelta(days=2), mid="<x@y>"):
    return Msg("All", 1, frm, list(to), mid, list(refs), subject, date)


def test_normalize_subject():
    assert normalize_subject("RE: Re:  回覆: TEEP Research Internship Inquiry") == "teep research internship inquiry"


def test_reply_in_same_thread():
    m = match_message(msg("someone@else.org", "Re: x", refs=["<sent-a@gmail.com>"]), ctx())
    assert (m.kind, m.professor_id, m.how) == ("reply", "A", "thread")


def test_new_thread_from_professor_address():
    m = match_message(msg("B@ntu.edu.tw", "Meeting next week?"), ctx())
    assert (m.kind, m.professor_id, m.how) == ("reply", "B", "address")


def test_old_mail_from_professor_ignored():
    assert match_message(msg("b@ntu.edu.tw", "Old", date=T0 - timedelta(days=30)), ctx()) is None


def test_different_address_with_re_subject_is_possible():
    m = match_message(msg("prof.b.personal@gmail.com", "Re: Unique subject for B"), ctx())
    assert (m.kind, m.professor_id) == ("possible", "B")
    m = match_message(msg("someone@gmail.com", "RE: TEEP Research Internship Inquiry"), ctx())
    assert m.kind == "possible" and m.professor_id is None and m.candidates == ["A", "B", "C"]


def test_unrelated_mail_ignored():
    assert match_message(msg("news@site.com", "TEEP Research Internship Inquiry tips"), ctx()) is None


def test_our_own_sent_mail_ignored_and_manual_followup_detected():
    assert match_message(msg("student@gmail.com", mid="<sent-a@gmail.com>", to=["a@ntu.edu.tw"]), ctx()) is None
    m = match_message(msg("student@gmail.com", "Re: thanks", to=["c@ntu.edu.tw"]), ctx())
    assert (m.kind, m.professor_id) == ("student_followup", "C")


def test_bounce():
    m = match_message(msg("mailer-daemon@googlemail.com", "Delivery Status Notification (Failure)"), ctx())
    assert m.kind == "bounce" and m.professor_id is None
    assert bounce_target("Address not found: c@ntu.edu.tw couldn't be found", ctx()) == "C"


def test_external_tags_from_university_mail_systems():
    for subj in ["RE:[EXTERNAL] Re: [External] TEEP Research Internship Inquiry",
                 "[EXT] RE: TEEP Research Internship Inquiry",
                 "EXTERNAL: Re: TEEP Research Internship Inquiry",
                 "Re: [External] RE: [EXTERNAL] TEEP Research Internship Inquiry",
                 "(External) 回覆: TEEP Research Internship Inquiry"]:
        assert normalize_subject(subj) == "teep research internship inquiry", subj
        m = match_message(msg("prof.personal@gmail.com", subj), ctx())
        assert m is not None and m.kind == "possible", subj
    # A tag alone (no Re:) isn't treated as a reply from an unknown address
    assert match_message(msg("someone@x.org", "[EXTERNAL] TEEP Research Internship Inquiry"), ctx()) is None
    # From the professor's own address, any subject counts
    m = match_message(msg("a@ntu.edu.tw", "RE:[EXTERNAL] Re: [External] whatever"), ctx())
    assert (m.kind, m.professor_id) == ("reply", "A")


# ---- check E: name matching -------------------------------------------------
from app.matching import name_keys, pick_by_name, searchable_name, university_tokens  # noqa: E402


def name_ctx():
    c = ctx()
    c.prof_names = {"A": "Pu-Jen Cheng", "B": "Prof. Liu (GINM)", "C": "Chih-Jen Lin"}
    c.prof_emails = {"A": "pjcheng@csie.ntu.edu.tw", "B": "b@ntu.edu.tw", "C": "cjlin@csie.ntu.edu.tw"}
    return c


def test_name_helpers():
    assert name_keys("Pu-Jen Cheng") == ["pujencheng", "chengpujen"]
    assert name_keys("Prof. Liu (GINM)") == []                      # one word: too ambiguous
    assert searchable_name("Prof. Pu-Jen Cheng (CSIE)") == "Pu-Jen Cheng"
    assert searchable_name("鄭卜壬") == ""
    assert university_tokens("pjcheng@csie.ntu.edu.tw") == {"csie", "ntu"}


def test_sender_name_from_unknown_address_with_new_subject():
    m = msg("pjcheng.home@gmail.com", "About your internship")
    m.from_name = "Cheng Pu-Jen"                                   # surname first also works
    r = match_message(m, name_ctx())
    assert (r.kind, r.professor_id, r.how) == ("possible", "A", "name")
    pid, _ = pick_by_name(m, "Hi John, let's talk.\n\nPu-Jen", name_ctx(), r.candidates)
    assert pid == "A"


def test_signature_identifies_professor():
    m = msg("lab.assistant@gmail.com", "RE:[EXTERNAL] Re: [External] TEEP Research Internship Inquiry")
    r = match_message(m, name_ctx())
    assert r.kind == "possible" and r.professor_id is None          # same subject went to everyone
    body = "Dear John,\n\nPlease send your transcript.\n\nBest regards,\nChih-Jen Lin\nDept. of CSIE, National Taiwan University"
    pid, _ = pick_by_name(m, body, name_ctx(), r.candidates)
    assert pid == "C"


def test_same_name_resolved_by_university():
    c = name_ctx()
    c.prof_names["D"] = "Chih-Jen Lin"
    c.prof_emails["D"] = "cjlin@cs.nthu.edu.tw"
    c.first_sent["D"] = T0
    m = msg("cj.personal@gmail.com", "Hello")
    m.from_name = "Chih-Jen Lin"
    pid, _ = pick_by_name(m, "Thanks.\nChih-Jen Lin, NTHU CS", c, [])
    assert pid == "D"
    pid, cands = pick_by_name(m, "Thanks.\nChih-Jen", c, [])        # no university clue
    assert pid is None and sorted(cands) == ["C", "D"]


def test_no_name_no_match():
    m = msg("someone@gmail.com", "Hello there")
    m.from_name = "Random Person"
    assert match_message(m, name_ctx()) is None
