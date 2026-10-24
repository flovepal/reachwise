"""Email template helpers, and (optional) Claude for sorting replies.

Writing the emails is done by the student with any AI they like (see prompts.py),
so no paid AI is needed for that. Sorting replies uses Claude only if
ANTHROPIC_API_KEY is set; otherwise simple keyword rules are used.
"""
import logging
import re

from .config import settings
from .db import GROUP_OF, LABELS

log = logging.getLogger("profmail.ai")


def client():
    """Anthropic client, or None. Replaced in tests."""
    if not settings.anthropic_api_key:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _tool_call(model: str, system: list, user: str, tool: dict, max_tokens: int = 1500) -> dict:
    resp = client().messages.create(
        model=model, max_tokens=max_tokens, system=system,
        tools=[tool], tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Claude returned no structured result")


# ----------------------------------------------------------------------------
# Filling the three emails in for each professor
# ----------------------------------------------------------------------------

PLACEHOLDERS = ("{professor}", "{research_in}", "{research_area}", "{university}")


def signature(student: dict) -> str:
    d = student.get("details") or {}
    if d.get("signature"):
        return d["signature"]
    parts = ["Sincerely,", d.get("full_name") or student.get("name") or ""]
    for k in ("phone", "linkedin"):
        if d.get(k):
            parts.append(d[k])
    return "\n".join(p for p in parts if p)


def default_subject(student: dict) -> str:
    d = student.get("details") or {}
    name = d.get("full_name") or student.get("name") or ""
    goal = student.get("goal") or "admission"
    if goal == "teep":
        s = "TEEP Research Internship Inquiry"
    elif goal == "iipp":
        s = "IIPP Research Internship Inquiry"
    else:
        s = f"Prospective {d.get('degree') or 'Graduate'} Student - Research Supervision Inquiry"
    return f"{s} - {name}" if name else s


def _area(prof: dict) -> str:
    a = (prof.get("research_area") or "").strip()
    return "" if a.lower() in ("", "not specified", "n/a", "na", "-", "unknown") else a


def re_subject(s: str) -> str:
    return "Re: " + re.sub(r"^(re:\s*)+", "", s, flags=re.I)


def surname(name: str) -> str:
    name = re.sub(r"\(.*?\)", "", name).strip()
    name = re.sub(r"^(prof\.?|professor|dr\.?)\s+", "", name, flags=re.I)
    return name.split()[-1] if name.split() else name


def fill(text: str, prof: dict) -> str:
    """Put one professor's details into a template."""
    area = _area(prof)
    values = {
        "{professor}": f"Professor {surname(prof['name'])}",
        "{research_in}": f" in {area}" if area else "",
        "{research_area}": area or "your research area",
        "{university}": prof.get("university") or "your university",
    }
    for k, v in values.items():
        text = text.replace(k, v)
    return text


def unknown_placeholders(text: str) -> list[str]:
    return sorted({m for m in re.findall(r"\{[^{}\s]{1,40}\}", text) if m not in PLACEHOLDERS})


# ----------------------------------------------------------------------------
# Sorting replies
# ----------------------------------------------------------------------------

CLASSIFY_TOOL = {
    "name": "classify_reply",
    "description": "Classify a professor's reply to a student's inquiry.",
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": [l for l in LABELS if l != "bounced"]},
            "summary": {"type": "string", "description": "1-2 sentence summary of what the professor said"},
            "action": {"type": "string", "description": "What the student should do next, one sentence"},
            "key_dates": {"type": "string", "description": "Meeting times, deadlines or dates mentioned, else empty"},
        },
        "required": ["label", "summary", "action", "key_dates"],
    },
}

CLASSIFY_RULES = """You sort replies that professors sent to a student asking about internships or graduate supervision.
Labels:
- interview: proposes or asks for a meeting, interview, call or lab visit
- interested: interested or encouraging (e.g. "apply and list me") without a meeting yet
- needs_info: asks a question or requests documents before deciding
- redirect: points the student to another professor, office or the formal application process instead
- rejection: no openings, no funding, not a fit, or declines
- auto_reply: automatic out-of-office or acknowledgement
- other: anything else
If a reply both declines and redirects, choose redirect. Be literal; do not guess dates."""


def classify_reply(prof_name: str, subject: str, body: str, sent_text: str = "") -> dict:
    text = body.strip()[:6000]
    result = None
    if client():
        user = (f"Professor: {prof_name}\nSubject: {subject}\n\nReply:\n{text}"
                + (f"\n\nStudent's original email (context):\n{sent_text[:1500]}" if sent_text else ""))
        try:
            result = _tool_call(settings.claude_fast_model, [{"type": "text", "text": CLASSIFY_RULES}],
                                user, CLASSIFY_TOOL, 600)
        except Exception as e:  # noqa: BLE001
            log.warning("Classification failed, using keywords: %s", e)
    if not result:
        result = keyword_classify(subject, text)
    if result.get("label") not in LABELS:
        result["label"] = "other"
    result["group"] = GROUP_OF[result["label"]]
    return result


_AUTO = ["out of office", "out-of-office", "automatic reply", "auto-reply", "autoreply", "away from the office",
         "on leave until", "limited access to email", "limited email access", "自動回覆", "自动回复"]
# "I don't have vacancy", "we do not have any open positions", "no funding this year", ...
_NO_ROOM = re.compile(
    r"\b(?:no|not|don'?t|do not|doesn'?t|does not|cannot|can'?t|unable to|not able to)\b[^.!?\n]{0,40}?"
    r"\b(?:vacanc\w*|positions?|openings?|slots?|space|room|funding|capacity|places?|quota)\b", re.I)
_REFUSE = ["retire", "retiring", "retirement", "is full", "lab is full", "group is full", "fully booked",
           "not accepting", "not taking", "cannot take", "can't take", "cannot accept", "can't accept",
           "unable to accept", "not able to accept", "unable to take", "not able to take", "not recruiting",
           "find a suitable professor", "find another professor", "find a suitable advisor", "find another advisor",
           "find a suitable supervisor", "not a good fit", "not a fit", "does not match", "doesn't match",
           "not possible", "have to decline", "must decline", "no longer", "on sabbatical"]
_REDIRECT = ["please contact", "contact professor", "contact prof", "reach out to professor", "reach out to prof",
             "my colleague", "admission office", "instead"]
_MEET = ["interview", "meet with", "meeting", "zoom", "google meet", "teams", "skype", "visit my lab",
         "come to my office", "schedule a", "a call", "video call", "available on", "talk on"]
_WEAK_NO = ["unfortunately", "regret", "sorry", "afraid"]
_INFO = ["could you send", "please send", "can you send", "transcript", "can you tell me", "could you tell me",
         "gpa", "toefl", "ielts", "publication list", "more details"]
_YES = ["welcome", "interested", "please apply", "happy to", "glad to", "would like to have you", "list me",
        "apply through", "apply via", "potential advisor", "as your advisor", "as your supervisor"]


def keyword_classify(subject: str, body: str) -> dict:
    """Free fallback when no Claude key is set. Refusals win over polite words like
    "thank you for your interest", so "Good to know you are interested, but I don't
    have a vacancy" is sorted as declined."""
    t = f"{subject}\n{body}".lower()
    has = lambda words: any(w in t for w in words)  # noqa: E731
    if has(_AUTO):
        label = "auto_reply"
    elif has(["list me", "potential advisor", "as your advisor", "as your supervisor"]) and not (has(_REFUSE) or _NO_ROOM.search(t)):
        label = "interested"
    elif has(_REDIRECT) and (has(_REFUSE) or _NO_ROOM.search(t) or has(_WEAK_NO) or "instead" in t):
        label = "redirect"
    elif has(_REFUSE) or _NO_ROOM.search(t):
        label = "rejection"
    elif has(_REDIRECT):
        label = "redirect"
    elif has(_MEET):
        label = "interview"
    elif has(_WEAK_NO):
        label = "rejection"
    elif has(_INFO):
        label = "needs_info"
    elif has(_YES):
        label = "interested"
    else:
        label = "other"
    return {"label": label, "summary": " ".join(body.split())[:200],
            "action": "Read the reply and respond in Gmail.", "key_dates": ""}
