"""Deciding which professor an incoming email belongs to (pure logic, no I/O).

Order of checks for each message found in the mailbox:
  1. It is one of the emails we sent                       -> ignore
  2. The student sent it to a professor from Gmail         -> student_followup
  3. Delivery failure notice                               -> bounce
  4. Its In-Reply-To / References point to an email we sent -> reply  (how="thread")
  5. It comes from a professor's address after we wrote     -> reply  (how="address")
     (this catches replies that start a NEW thread with a new subject)
  6. Subject is "Re: <a subject we sent>" from an unknown address
                                                          -> possible (student confirms)
  7. Unknown address, but the sender's name (or, once the text is read, the signature)
     matches exactly one professor                         -> reply (how="name"), with a
     "please check" note for the student. The professor's university/department, taken
     from their email domain (e.g. csie.ntu.edu.tw), breaks ties.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

BOUNCE_LOCALS = ("mailer-daemon", "postmaster")
# Reply/forward prefixes, plus tags that university mail systems add, e.g.
# "RE:[EXTERNAL] Re: [External] Subject", "[EXT] RE: Subject", "EXTERNAL: Re: Subject"
_TAG = r"(?:\[\s*(?:external|ext|外部|外部郵件|caution|warning|spam\?*|suspected spam)\s*\]|\(\s*(?:external|ext)\s*\)|(?:external|ext)\s*[:：])"
_REPLY = r"(?:re|fw|fwd|aw|sv|antw|回覆|回复|答复|轉寄|转发)\s*(?:\[\d+\])?\s*[:：]"
_PREFIX = re.compile(rf"^\s*(?:(?:{_TAG}|{_REPLY})\s*)+", re.I)
_HAS_REPLY = re.compile(rf"^\s*(?:{_TAG}\s*)*{_REPLY}", re.I)


def normalize_subject(subject: str) -> str:
    return re.sub(r"\s+", " ", _PREFIX.sub("", subject or "")).strip().lower()


def is_reply_subject(subject: str) -> bool:
    return bool(_HAS_REPLY.match(subject or ""))


@dataclass
class Context:
    user_address: str
    prof_by_email: dict[str, str]                 # lower email -> professor id
    prof_of_mid: dict[str, str]                   # Message-ID we sent -> professor id
    first_sent: dict[str, datetime]               # professor id -> first send time
    subject_profs: dict[str, set[str]] = field(default_factory=dict)  # normalized subject -> professor ids
    prof_names: dict[str, str] = field(default_factory=dict)          # professor id -> name
    prof_emails: dict[str, str] = field(default_factory=dict)         # professor id -> email

    @property
    def sent_mids(self) -> set[str]:
        return set(self.prof_of_mid)


@dataclass
class Match:
    kind: str                     # reply | possible | bounce | student_followup
    professor_id: str | None
    how: str = ""                 # thread | address | subject | name
    candidates: list[str] = field(default_factory=list)


def _after_first(ctx: Context, prof_id: str, date: datetime | None) -> bool:
    first = ctx.first_sent.get(prof_id)
    if first is None:
        return False
    return date is None or date >= first - timedelta(hours=1)


# ---- names ------------------------------------------------------------------
_TITLES = {"prof", "professor", "dr", "mr", "ms", "mrs", "assoc", "assistant", "associate", "phd"}
_GENERIC_DOMAIN = {"edu", "ac", "com", "org", "net", "gov", "tw", "cn", "jp", "kr", "in", "uk", "us", "hk", "sg",
                   "mail", "email", "www", "gmail", "yahoo", "hotmail", "outlook", "live", "icloud", "qq", "163"}


def name_tokens(name: str) -> list[str]:
    """'Prof. Pu-Jen Cheng (CSIE)' -> ['pu', 'jen', 'cheng']"""
    name = re.sub(r"\(.*?\)", " ", name or "")
    toks = [t for t in re.split(r"[^a-z]+", name.lower()) if t]
    return [t for t in toks if t not in _TITLES]


def name_keys(name: str) -> list[str]:
    """Spellings to look for: 'pujencheng' and surname-first 'chengpujen'. Empty for
    one-word names like 'Prof. Liu (GINM)', which are too ambiguous to match on."""
    toks = name_tokens(name)
    if len(toks) < 2:
        return []
    return ["".join(toks), "".join([toks[-1]] + toks[:-1])]


def searchable_name(name: str) -> str:
    """Full name as people write it, for the mailbox search ('' if too short)."""
    clean = re.sub(r"\(.*?\)", " ", name or "")
    clean = re.sub(r"^\s*(prof\.?|professor|dr\.?)\s+", "", clean, flags=re.I).strip()
    return clean if len(name_tokens(clean)) >= 2 and clean.isascii() else ""


def _compact(text: str) -> str:
    return re.sub(r"[^a-z]+", "", (text or "").lower())


def names_in(text: str, ctx: Context, pids) -> list[str]:
    """Professors whose full name appears in text."""
    flat = _compact(text)
    if not flat:
        return []
    return sorted(pid for pid in pids if any(k in flat for k in name_keys(ctx.prof_names.get(pid, ""))))


def university_tokens(email: str) -> set[str]:
    """'pjcheng@csie.ntu.edu.tw' -> {'csie', 'ntu'}"""
    domain = (email or "").split("@")[-1].lower()
    return {p for p in domain.split(".") if p and p not in _GENERIC_DOMAIN and len(p) > 1}


def signature(body: str, lines: int = 25) -> str:
    """The end of a reply, where people sign their name."""
    return "\n".join((body or "").strip().splitlines()[-lines:])


def pick_by_name(m, body: str, ctx: Context, candidates: list[str]) -> tuple[str | None, list[str]]:
    """Use the sender's name and the signature to find the professor.

    Returns (professor or None, remaining candidates)."""
    pool = candidates or [pid for pid in ctx.first_sent]
    pool = [p for p in pool if _after_first(ctx, p, m.date)]
    hits = names_in(f"{getattr(m, 'from_name', '')}\n{signature(body)}", ctx, pool)
    if len(hits) > 1:
        # Same name twice: prefer the one whose university/department appears in the
        # sender's domain or the signature
        where = f"{(m.from_addr or '').split('@')[-1]} {signature(body)}".lower()
        words = set(re.split(r"[^a-z]+", where))
        narrowed = [p for p in hits if university_tokens(ctx.prof_emails.get(p, "")) & words]
        hits = narrowed or hits
    if len(hits) == 1:
        return hits[0], hits
    return None, (hits or candidates)


def match_message(m, ctx: Context) -> Match | None:
    if m.message_id and m.message_id in ctx.prof_of_mid:
        return None

    sender = (m.from_addr or "").lower()
    if sender == ctx.user_address.lower():
        for addr in m.to:
            pid = ctx.prof_by_email.get(addr.lower())
            if pid and _after_first(ctx, pid, m.date):
                return Match("student_followup", pid)
        return None

    if sender.split("@")[0] in BOUNCE_LOCALS:
        pid = next((ctx.prof_of_mid[r] for r in m.refs if r in ctx.prof_of_mid), None)
        return Match("bounce", pid)

    for ref in m.refs:
        if ref in ctx.prof_of_mid:
            return Match("reply", ctx.prof_of_mid[ref], "thread")

    pid = ctx.prof_by_email.get(sender)
    if pid:
        return Match("reply", pid, "address") if _after_first(ctx, pid, m.date) else None

    contacted = [p for p in ctx.first_sent if _after_first(ctx, p, m.date)]
    by_name = names_in(getattr(m, "from_name", ""), ctx, contacted)

    if is_reply_subject(m.subject):
        cands = sorted(ctx.subject_profs.get(normalize_subject(m.subject), set()))
        cands = [c for c in cands if _after_first(ctx, c, m.date)]
        if cands:
            narrowed = [c for c in cands if c in by_name] or cands
            return Match("possible", narrowed[0] if len(narrowed) == 1 else None, "subject", narrowed)
    if by_name:
        # New subject from an unknown address, but the sender's name is a professor's
        return Match("possible", by_name[0] if len(by_name) == 1 else None, "name", by_name)
    return None


def bounce_target(body: str, ctx: Context) -> str | None:
    """Find which contacted professor a bounce notice is about."""
    low = (body or "").lower()
    for addr, pid in ctx.prof_by_email.items():
        if pid in ctx.first_sent and addr in low:
            return pid
    return None
