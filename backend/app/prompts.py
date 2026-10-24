"""Base templates, the copy-paste prompt for any AI, and reading the AI's answer back.

Flow: the student copies `build_prompt()` into ChatGPT / Gemini / Claude / any AI
together with their documents, then pastes the AI's reply. `parse_answer()` splits it
into the subject and the three emails, and repairs the mistakes AIs commonly make.
"""
import re

from . import ai

# ---------------------------------------------------------------------------
# Base templates. Parts in [square brackets] are filled in by the AI (or by the
# student by hand). {professor}, {research_in}, {research_area}, {university} are
# filled in for each professor when sending.
# ---------------------------------------------------------------------------

GOAL_PHRASE = {
    "teep": "a research internship in your lab through TEEP (Taiwan Experience Education Program)",
    "iipp": "a research internship in your lab through the International Internship Pilot Program (IIPP)",
    "admission": "pursuing a [Master's / PhD] degree under your supervision",
}

FIRST = """Dear {professor},

My name is [your name], and I am [your current degree or position, and your institution]. I would like to ask whether you might have a place for GOAL.DATES

I came across your research{research_in}, and it connects with what I have been working on: [one or two plain sentences about your most relevant project, internship or result, and what you did in it].

I have attached ATTACHED. ONREQUEST

Thank you for your time.

SIGNATURE"""

SECOND = """Dear {professor},

I am following up on my earlier email about SHORTGOAL.

[One new, short detail from your documents that the first email did not mention, such as a skill, a result, or your availability.]

I would be grateful to know whether this might be possible. Thank you for your time.

SIGNATURE"""

THIRD = """Dear {professor},

This is my last follow-up about SHORTGOAL. If it is not possible this year, I completely understand, and a short reply either way would help me plan.

Thank you again.

SIGNATURE"""

SHORT_GOAL = {
    "teep": "a TEEP research internship in your lab",
    "iipp": "an IIPP research internship in your lab",
    "admission": "graduate study under your supervision",
}

DOC_NAMES = {"cv": "CV", "recommendation": "recommendation letter", "internship_report": "internship report",
             "offer_letter": "offer letter", "loi": "letter of interest", "proposal": "research proposal",
             "other": "other document"}

VERSIONS = "ABC"          # email 1 is written in three versions, sent in turn


def goal_phrase(student: dict) -> str:
    goal = student.get("goal") or "admission"
    d = student.get("details") or {}
    phrase = GOAL_PHRASE[goal]
    if goal == "admission" and d.get("degree"):
        phrase = phrase.replace("[Master's / PhD]", d["degree"])
    return phrase


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def base_templates(student: dict) -> dict:
    """The starting templates for this student's goal, with what we already know filled in.

    Shape: {"initial": [{"subject", "body"}, ...], "reminder1_body", "reminder2_body"}"""
    goal = student.get("goal") or "admission"
    d = student.get("details") or {}
    dates = ""
    if goal in ("teep", "iipp"):
        if d.get("start_date") and d.get("end_date"):
            dates = f" I am available from {d['start_date']} to {d['end_date']}."
        elif d.get("start_date"):
            dates = f" I am available from {d['start_date']}."
        else:
            dates = " [Your available dates, e.g. from February to July 2027.]"
    elif d.get("start_date"):
        dates = f" I hope to begin in {d['start_date']}."
    sig = ai.signature(student)
    attached = student.get("attachment_names") or ["my CV"]
    extra = student.get("on_request_names") or []
    offer = f"If it would help, I am happy to send {_and(extra)}." if extra else ""
    first = (FIRST.replace("GOAL", goal_phrase(student)).replace("DATES", dates).replace("SIGNATURE", sig)
             .replace("ATTACHED", _and(attached)).replace(" ONREQUEST", f" {offer}" if offer else ""))
    if d.get("full_name"):
        first = first.replace("[your name]", d["full_name"])
    return {
        "initial": [{"subject": ai.default_subject(student), "body": first}],
        "reminder1_body": SECOND.replace("SHORTGOAL", SHORT_GOAL[goal]).replace("SIGNATURE", sig),
        "reminder2_body": THIRD.replace("SHORTGOAL", SHORT_GOAL[goal]).replace("SIGNATURE", sig),
    }


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

MARK = "@@@"

# Phrases that make an email read like a template, a cover letter or marketing
AVOID = ['"I hope this message finds you well"', '"I am writing to express my interest"', '"I am thrilled"',
         '"I am excited"', '"passionate"', '"esteemed"', '"renowned"', '"cutting-edge"', '"delve"',
         '"leverage"', '"groundbreaking"', '"unique opportunity"', '"I believe I would be a great fit"',
         '"I would be honored"', '"Thank you for considering my application"']


def build_prompt(student: dict, docs: list[dict], include_text: bool = False) -> str:
    """One prompt the student pastes into any AI, with their documents attached."""
    d = student.get("details") or {}
    t = base_templates(student)
    names = [DOC_NAMES.get(x["kind"], "document") for x in docs]
    attached = [DOC_NAMES.get(x["kind"], "document") for x in docs if x.get("attach")] or ["CV"]
    others = [DOC_NAMES.get(x["kind"], "document") for x in docs if not x.get("attach")]

    applying = goal_phrase(student).replace("your lab", "a professor's lab").replace("your supervision", "a professor's supervision")
    about = [f"- Applying for: {applying}"]
    goal = student.get("goal") or "admission"
    for key, label in [("full_name", "Name"), ("degree", "Degree I want"), ("start_date", "Start date"),
                       ("end_date", "End date"), ("current_location", "Where I am now"),
                       ("scholarship", "Scholarships I am applying for"), ("plans", "My plans, in my words"),
                       ("instructions", "Extra instructions")]:
        if key == "scholarship" and goal != "admission":
            continue  # TEEP / IIPP don't need a scholarship request
        if d.get(key):
            about.append(f"- {label}: {d[key]}")

    if include_text:
        docs_line = "The text of my documents is included at the end of this message."
    elif names:
        docs_line = f"I have attached these documents to this message: my {', my '.join(names)}."
    else:
        docs_line = "I have attached my CV to this message."

    parts = [
        "You are helping me, a student, write short emails to university professors.",
        "",
        docs_line,
        "",
        "About me:",
        *about,
        "",
        "TASK",
        "Using ONLY facts from my documents and the details above, write:",
        "- THREE different versions of email 1 (A, B and C), each with its own subject line,",
        "- one version of email 2 (first follow-up) and one of email 3 (last follow-up).",
        "Start from the templates below. Replace every part in [square brackets] with real content from my",
        "documents, or delete it if my documents don't support it. The final emails must not contain square brackets.",
        "",
        "HOW THE EMAILS MUST READ",
        "- Like a real student writing to one professor: plain, direct, short sentences. Not like a cover letter,",
        "  a template or marketing. Email 1: 110 to 170 words. Email 2: 50 to 90 words. Email 3: 40 to 70 words.",
        "- One short paragraph about me is enough: who I am and my single most relevant experience.",
        "- Do not use these phrases or anything similar: " + ", ".join(AVOID) + ".",
        "- No flattery, no exclamation marks, no links, no bold, no bullet points, no emojis, no ALL CAPS.",
        "",
        "THE THREE VERSIONS OF EMAIL 1",
        "- They are sent to different professors in turn, so they must not look like copies of each other.",
        "  Give each version a different opening sentence, a different order of points, different wording and a",
        "  different subject line. Keep the same facts in all three. Do not just swap synonyms.",
        "- Subject lines: short and specific (under 9 words), no words like \"opportunity\" or \"urgent\".",
        "",
        "RULES FOR ALL EMAILS",
        "- The same emails go to many professors. Keep these placeholders exactly as written, with the curly braces:",
        "  {professor} (in the greeting) and {research_in} (once in each version of email 1). They are filled in",
        "  automatically for each professor. Do not add any other curly-brace placeholders.",
        "- Do not mention any specific professor, lab, paper or university by name.",
        "- Do not invent anything: no made-up projects, results, grades, publications, dates or skills.",
        f"- Email 1 attaches only: my {_and(attached)}. Do not claim anything else is attached."
        + (f" You may add one short sentence offering to send my {_and(others)} if the professor is interested."
           if others else ""),
        "- My other documents are for your information: use their facts, but they are not attached.",
        "- Emails 2 and 3 are follow-ups in the same thread, so they need no subject line.",
        "- End every email with my signature exactly as it appears in the templates.",
        "",
        "TEMPLATES",
        "",
        f"Subject of email 1: {t['initial'][0]['subject']}",
        "",
        "--- Email 1 ---",
        t["initial"][0]["body"],
        "",
        "--- Email 2 ---",
        t["reminder1_body"],
        "",
        "--- Email 3 ---",
        t["reminder2_body"],
        "",
        "OUTPUT FORMAT",
        "Put your whole answer inside ONE code block, so it is easy to copy. Inside it, use exactly this structure,",
        f"keeping the {MARK} lines exactly as shown, with nothing before the first line or after the last line:",
        "",
    ]
    for v in VERSIONS:
        parts += [f"{MARK} SUBJECT {v} {MARK}", f"(subject line of email 1, version {v})",
                  f"{MARK} EMAIL 1{v} {MARK}", f"(full text of email 1, version {v})"]
    parts += [f"{MARK} EMAIL 2 {MARK}", "(full text of email 2)",
              f"{MARK} EMAIL 3 {MARK}", "(full text of email 3)", f"{MARK} END {MARK}"]
    if include_text:
        parts += ["", "MY DOCUMENTS"]
        for x in docs:
            if x.get("text"):
                parts += ["", f"===== My {DOC_NAMES.get(x['kind'], 'document')} =====", x["text"][:15000]]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Reading the AI's answer
# ---------------------------------------------------------------------------

# Marker lines, e.g. "@@@ SUBJECT B @@@", "@@@ EMAIL 1C @@@", "### Email 1 (Version A)", "**EMAIL 2**"
_MARKER = re.compile(
    r"^[\s>#*_`|-]*(?:@{2,}\s*)?"
    r"(?:(?P<subj>subject(?:\s*line)?)(?:\s*(?:for\s*)?(?:email\s*1\s*)?[-–(]?\s*(?:version\s*)?(?P<sv>[abc])\)?)?"
    r"|email\s*(?P<num>[123])\s*(?:[-–(]?\s*(?:version\s*)?(?P<ev>[abc])\)?)?"
    r"|version\s*(?P<vv>[abc])"
    r"|(?P<end>end))"
    r"(?:\s*@{2,})?[\s#*_`:|-]*$",
    re.I | re.M)

_PLACEHOLDER_FIXES = [
    # Common ways AIs mangle the placeholders
    (r"\{\{\s*professor(?:[ _]?name)?\s*\}\}|\{\s*professor(?:[ _]?name)?\s*\}|\[\s*professor(?:'?s)?[ _]?name\s*\]",
     "{professor}"),
    (r"\{\{\s*research[ _]in\s*\}\}|\{\s*research[ _]in\s*\}", "{research_in}"),
    (r"\{\{\s*research[ _]area\s*\}\}|\{\s*research[ _]area\s*\}", "{research_area}"),
    (r"\{\{\s*university\s*\}\}|\{\s*university\s*\}", "{university}"),
]


class ParseError(ValueError):
    pass


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace(" ", " ")
    # Drop code-fence lines and markdown emphasis that some AIs add anyway
    text = "\n".join(l for l in text.split("\n") if not l.strip().startswith("```"))
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return text


def _fix_placeholders(body: str) -> str:
    for pattern, repl in _PLACEHOLDER_FIXES:
        body = re.sub(pattern, repl, body, flags=re.I)
    # "Dear Professor {professor}" would become "Dear Professor Professor Chen"
    body = re.sub(r"\b(?:Professor|Prof\.?|Dr\.?)\s+\{professor\}", "{professor}", body)
    return body


def _tidy(body: str) -> str:
    lines = [l.rstrip() for l in body.strip().split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _subject_line(raw: str) -> str:
    line = (raw or "").strip().split("\n")[0]
    return re.sub(r"^\s*subject\s*:\s*", "", line, flags=re.I).strip(" *_")


def parse_answer(text: str) -> tuple[dict, list[str]]:
    """Return (templates, warnings). Raises ParseError if the structure can't be found.

    Accepts up to three versions of email 1 (A/B/C), or the older single-version format."""
    text = _clean(text or "")
    found = list(_MARKER.finditer(text))
    sections: dict[str, str] = {}
    current_version = "A"
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(text)
        chunk = text[m.end():end]
        if m.group("end"):
            continue
        if m.group("vv"):                      # "Version B" heading on its own line
            current_version = m.group("vv").upper()
            continue
        if m.group("subj"):
            v = (m.group("sv") or current_version).upper()
            sections.setdefault(f"subject{v}", chunk)
        else:
            num = m.group("num")
            if num == "1":
                v = (m.group("ev") or current_version).upper()
                current_version = v
                sections.setdefault(f"email1{v}", chunk)
            else:
                sections.setdefault(f"email{num}", chunk)

    versions = [v for v in VERSIONS if sections.get(f"email1{v}", "").strip()]
    missing = (["EMAIL 1"] if not versions else []) + [n for n, k in [("EMAIL 2", "email2"), ("EMAIL 3", "email3")]
                                                        if not sections.get(k, "").strip()]
    if missing:
        raise ParseError(
            "Couldn't find " + ", ".join(missing) + " in what you pasted. Make sure you copied the AI's whole answer, "
            f"including the lines like “{MARK} EMAIL 1A {MARK}”. If the AI changed them, ask it to “use the exact "
            "output format from my message”.")

    initial = []
    for v in versions:
        subject = _subject_line(sections.get(f"subject{v}", ""))
        if not subject and v == versions[0]:
            # "Subject: ..." written on one line instead of the marker
            m = re.search(r"^[\s#*_>-]*subject(?:\s*line)?[\s*_]*:[\s*_]*(.+)$", text, re.I | re.M)
            subject = m.group(1).strip(" *_") if m else ""
        initial.append({"subject": subject, "body": _tidy(_fix_placeholders(sections[f"email1{v}"]))})
    out = {"initial": initial,
           "reminder1_body": _tidy(_fix_placeholders(sections["email2"])),
           "reminder2_body": _tidy(_fix_placeholders(sections["email3"]))}
    return out, check(out)


def check(t: dict) -> list[str]:
    """Problems worth telling the student about before they save."""
    warnings = []
    initial = t.get("initial") or []
    if len(initial) == 1:
        warnings.append("Only one version of email 1 was found. Three different versions make it much less likely "
                        "that your emails are marked as spam. Ask the AI for all three, or write more yourself.")
    bodies = [(f"Email 1 version {VERSIONS[i]}", x["body"]) for i, x in enumerate(initial)]
    bodies += [("Email 2", t.get("reminder1_body", "")), ("Email 3", t.get("reminder2_body", ""))]
    for i, x in enumerate(initial):
        if not x.get("subject", "").strip():
            warnings.append(f"Email 1 version {VERSIONS[i]} has no subject line. Type one in before saving.")
    for label, body in bodies:
        if "{professor}" not in body:
            warnings.append(f"{label} doesn't contain {{professor}}, so it won't greet each professor by name.")
        if brackets(body):
            warnings.append(f"{label} still has parts in [square brackets]: fill them in or delete them.")
        bad = ai.unknown_placeholders(body)
        if bad:
            warnings.append(f"{label} has placeholders we don't recognise: {', '.join(bad)}. Replace them with real text.")
    for i, x in enumerate(initial):
        words = len(x["body"].split())
        if words > 230:
            warnings.append(f"Email 1 version {VERSIONS[i]} is {words} words. Shorter emails read better; aim for under 170.")
    if len({_norm(x["body"]) for x in initial}) < len(initial):
        warnings.append("Two versions of email 1 are identical. Make them different, or delete one.")
    return warnings


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def brackets(text: str) -> list[str]:
    """Unfilled [guidance] parts left in a template."""
    return re.findall(r"\[[^\]\n]{3,}\]", text or "")
