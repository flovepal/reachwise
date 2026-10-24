import pytest

from app import prompts

STUDENT = {"name": "John Paul S", "goal": "teep",
           "details": {"full_name": "John Paul S", "start_date": "February 2027", "end_date": "July 2027"},
           "attachment_names": ["my CV", "my research proposal"],
           "on_request_names": ["my recommendation letter", "my internship report"]}
DOCS = [{"kind": "cv", "attach": True, "text": "John Paul S\nB.Tech IT\nPhysics-guided deep learning project"},
        {"kind": "proposal", "attach": True, "text": "Proposal: flood forecasting"},
        {"kind": "recommendation", "attach": False, "text": "I recommend John."},
        {"kind": "internship_report", "attach": False, "text": "Internship at Infinite Computer Solutions"},
        {"kind": "offer_letter", "attach": False, "text": ""}]

A = ("Dear {professor},\n\nI'm John Paul S, a B.Tech IT graduate. I read about your work{research_in} and would like "
     "to ask about a TEEP internship.\n\nBest regards,\nJohn Paul S")
B = ("Dear {professor},\n\nI am writing about a possible TEEP internship in your lab. Your research{research_in} "
     "is close to my final-year project.\n\nBest regards,\nJohn Paul S")
C = ("Dear {professor},\n\nMy final-year project used physics-guided deep learning, which brought me to your "
     "research{research_in}.\n\nBest regards,\nJohn Paul S")
E2 = "Dear {professor},\n\nFollowing up on my email.\n\nBest regards,\nJohn Paul S"
E3 = "Dear {professor},\n\nThis is my last follow-up.\n\nBest regards,\nJohn Paul S"
CLEAN = (f"@@@ SUBJECT A @@@\nTEEP internship inquiry - John Paul S\n@@@ EMAIL 1A @@@\n{A}\n"
         f"@@@ SUBJECT B @@@\nQuestion about a TEEP internship\n@@@ EMAIL 1B @@@\n{B}\n"
         f"@@@ SUBJECT C @@@\nPhysics-guided deep learning and TEEP\n@@@ EMAIL 1C @@@\n{C}\n"
         f"@@@ EMAIL 2 @@@\n{E2}\n@@@ EMAIL 3 @@@\n{E3}\n@@@ END @@@")


def test_prompt_asks_for_three_versions_and_plain_writing():
    p = prompts.build_prompt(STUDENT, DOCS)
    assert "THREE different versions of email 1" in p
    for v in "ABC":
        assert f"@@@ SUBJECT {v} @@@" in p and f"@@@ EMAIL 1{v} @@@" in p
    assert "I hope this message finds you well" in p and "Do not use these phrases" in p
    assert "Email 1 attaches only: my CV and research proposal" in p
    assert "offering to send my recommendation letter, internship report and offer letter" in p
    assert "TEEP" in p and "February 2027" in p
    assert "Internship at Infinite" not in p                       # document text only when asked
    p2 = prompts.build_prompt(STUDENT, DOCS, include_text=True)
    assert "===== My internship report =====" in p2 and "===== My offer letter =====" not in p2


def test_base_template_is_short_and_plain():
    t = prompts.base_templates(STUDENT)
    body = t["initial"][0]["body"]
    assert "I am available from February 2027 to July 2027." in body
    assert "I have attached my CV and my research proposal." in body
    assert "happy to send my recommendation letter and my internship report" in body
    assert "hope this message finds you well" not in body.lower()
    assert len(body.split()) < 130


def test_parse_three_versions():
    t, warnings = prompts.parse_answer(CLEAN)
    assert [v["subject"] for v in t["initial"]] == ["TEEP internship inquiry - John Paul S",
                                                    "Question about a TEEP internship",
                                                    "Physics-guided deep learning and TEEP"]
    assert [v["body"] for v in t["initial"]] == [A, B, C]
    assert t["reminder1_body"] == E2 and t["reminder2_body"] == E3
    assert warnings == []


def test_parse_with_code_fence_and_chatter():
    t, _ = prompts.parse_answer("Sure! Here you go:\n\n```text\n" + CLEAN + "\n```\nWant changes?")
    assert len(t["initial"]) == 3 and t["reminder2_body"] == E3


def test_parse_markdown_headings_and_version_words():
    text = (f"### Subject (Version A)\nTEEP inquiry\n\n### Email 1 (Version A)\n{A}\n\n"
            f"**Subject - B**\nAnother subject\n\n**Email 1 - B**\n{B}\n\n"
            f"## Version C\nSubject: Third subject\n\n## Email 1\n{C}\n\n## EMAIL 2:\n{E2}\n\n**Email 3**\n{E3}\n")
    t, _ = prompts.parse_answer(text)
    assert [v["subject"] for v in t["initial"]][:2] == ["TEEP inquiry", "Another subject"]
    assert [v["body"] for v in t["initial"]] == [A, B, C]
    assert t["reminder1_body"] == E2


def test_old_single_version_format_still_works_with_a_nudge():
    old = f"@@@ SUBJECT @@@\nTEEP inquiry\n@@@ EMAIL 1 @@@\n{A}\n@@@ EMAIL 2 @@@\n{E2}\n@@@ EMAIL 3 @@@\n{E3}\n@@@ END @@@"
    t, warnings = prompts.parse_answer(old)
    assert t["initial"] == [{"subject": "TEEP inquiry", "body": A}]
    assert any("Only one version" in w for w in warnings)


def test_placeholders_repaired():
    bad = CLEAN.replace("Dear {professor},\n\nI'm John", "Dear Professor {Professor_Name},\n\nI'm John") \
               .replace("your work{research_in}", "your work{{research_in}}") \
               .replace("Dear {professor},\n\nFollowing", "Dear [Professor's Name],\n\nFollowing")
    t, warnings = prompts.parse_answer(bad)
    assert t["initial"][0]["body"].startswith("Dear {professor},") and "{research_in}" in t["initial"][0]["body"]
    assert t["reminder1_body"].startswith("Dear {professor},")
    assert warnings == []


def test_warnings():
    bad = CLEAN.replace(B, A).replace("a B.Tech IT graduate", "[your degree]")
    _, warnings = prompts.parse_answer(bad)
    assert any("version A still has parts in [square brackets]" in w for w in warnings)
    assert any("identical" in w for w in warnings)


def test_missing_sections_explained():
    with pytest.raises(prompts.ParseError) as e:
        prompts.parse_answer("Here is your email: Dear Professor, I am interested...")
    assert "EMAIL 1" in str(e.value)
