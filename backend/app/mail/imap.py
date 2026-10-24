"""Reading the student's mailbox over IMAP.

We never download the whole inbox. We only search for:
  * mail FROM each professor the student contacted
  * mail whose SUBJECT contains one of the subjects we sent ("Re: ...")
  * bounce notices (mailer-daemon / postmaster)
  * mail the student sent TO a professor themselves (manual follow-ups)
in "All Mail" (inbox + archived + sent) and in "Spam".
"""
import email
import html
import imaplib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.policy import default as default_policy
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

from .smtp import Account

HEADER_FIELDS = "FROM TO CC MESSAGE-ID IN-REPLY-TO REFERENCES SUBJECT DATE"


@dataclass
class Msg:
    folder: str
    uid: int
    from_addr: str
    to: list[str]
    message_id: str
    refs: list[str]          # In-Reply-To + References
    subject: str
    date: datetime | None
    in_spam: bool = False
    body: str = field(default="", repr=False)
    from_name: str = ""      # display name, e.g. "Pu-Jen Cheng" in "Pu-Jen Cheng <x@gmail.com>"


def _ids(value) -> list[str]:
    return re.findall(r"<[^>]+>", str(value or ""))


def _date(value) -> datetime | None:
    try:
        dt = parsedate_to_datetime(str(value))
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:  # noqa: BLE001
        return None


def parse_headers(folder: str, uid: int, h, in_spam: bool = False) -> Msg:
    name, addr = parseaddr(str(h.get("From", "")))
    return Msg(
        folder=folder, uid=uid,
        from_addr=addr.lower(), from_name=name.strip(),
        to=[a.lower() for _, a in getaddresses([str(h.get("To", "")), str(h.get("Cc", ""))]) if a],
        message_id=str(h.get("Message-ID", "")).strip(),
        refs=_ids(h.get("In-Reply-To")) + _ids(h.get("References")),
        subject=str(h.get("Subject", "")),
        date=_date(h.get("Date")),
        in_spam=in_spam,
    )


def extract_text(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        text = part.get_content()
    except Exception:  # noqa: BLE001
        text = (part.get_payload(decode=True) or b"").decode(errors="ignore")
    if part.get_content_type() == "text/html":
        text = re.sub(r"(?is)<(script|style).*?</\1>", "", text)
        text = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", text)
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return text


def strip_quoted(text: str) -> str:
    """Drop the quoted copy of the student's email below a reply."""
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if (re.match(r"^On .+wrote:$", s) or re.match(r"^.{0,80}於.+寫道[:：]?$", s)
                or s.startswith("-----Original Message") or (re.match(r"^From: .+", s) and lines)):
            break
        if s.startswith(">"):
            continue
        lines.append(line)
    out = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", out)[:8000]


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _or_tree(key: str, values: list[str]) -> list[str]:
    """IMAP 'OR' is binary: OR a OR b c."""
    terms = [f"{key} {_quote(v)}" for v in values]
    expr = terms[-1]
    for t in reversed(terms[:-1]):
        expr = f"OR {t} {expr}"
    return [expr]


class MailboxReader:
    """Context manager around one IMAP session."""

    def __init__(self, account: Account):
        self.account = account
        self.conn: imaplib.IMAP4_SSL | None = None
        self._selected = None
        self.all_mail = "INBOX"
        self.spam: str | None = None

    def __enter__(self):
        self._connect()
        return self

    def _connect(self):
        self.conn = imaplib.IMAP4_SSL(self.account.imap_host, 993, timeout=90)
        self.conn.login(self.account.address, self.account.password)
        self._selected = None
        self._find_folders()

    def reconnect(self):
        """Start a fresh session after a timeout or dropped connection."""
        try:
            self.conn.logout()
        except Exception:  # noqa: BLE001
            pass
        self._connect()

    def __exit__(self, *exc):
        try:
            self.conn.logout()
        except Exception:  # noqa: BLE001
            pass

    def _find_folders(self) -> None:
        typ, data = self.conn.list()
        if typ != "OK":
            return
        for raw in data or []:
            line = raw.decode(errors="ignore") if isinstance(raw, bytes) else str(raw)
            m = re.search(r'"((?:[^"\\]|\\.)*)"\s*$', line) or re.search(r"(\S+)\s*$", line)
            if not m:
                continue
            name = m.group(1)
            # Special-use flags are language independent ("[Gmail]/所有郵件" etc.)
            if "\\All" in line:
                self.all_mail = name
            elif "\\Junk" in line:
                self.spam = name

    def folders(self) -> list[tuple[str, bool]]:
        out = [(self.all_mail, False)]
        if self.spam:
            out.append((self.spam, True))
        return out

    def _select(self, folder: str) -> bool:
        if self._selected == folder:
            return True
        typ, _ = self.conn.select(_quote(folder), readonly=True)
        self._selected = folder if typ == "OK" else None
        return typ == "OK"

    def search(self, folder: str, since: datetime, criteria: str) -> list[int]:
        if not self._select(folder):
            return []
        query = f"(SINCE {since.strftime('%d-%b-%Y')} {criteria})"
        try:
            typ, data = self.conn.uid("SEARCH", None, query)
        except imaplib.IMAP4.error:
            return []
        return [int(u) for u in (data[0] or b"").split()] if typ == "OK" else []

    def search_any(self, folder: str, since: datetime, key: str, values: list[str], chunk: int = 15) -> set[int]:
        uids: set[int] = set()
        values = [v for v in values if v and v.isascii()]
        for i in range(0, len(values), chunk):
            uids.update(self.search(folder, since, _or_tree(key, values[i:i + chunk])[0]))
        return uids

    def headers(self, folder: str, uids, in_spam: bool = False) -> list[Msg]:
        uids = sorted(uids)
        if not uids or not self._select(folder):
            return []
        parser = email.parser.BytesHeaderParser(policy=default_policy)
        out = []
        for i in range(0, len(uids), 200):
            batch = uids[i:i + 200]
            typ, data = self.conn.uid("FETCH", ",".join(map(str, batch)),
                                      f"(UID BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})])")
            if typ != "OK":
                continue
            for item in data:
                if isinstance(item, tuple):
                    m = re.search(rb"UID (\d+)", item[0])
                    if m:
                        out.append(parse_headers(folder, int(m.group(1)), parser.parsebytes(item[1]), in_spam))
        return out

    def body(self, m: Msg) -> str:
        if not self._select(m.folder):
            return ""
        # Only the first 256 KB: enough for the text of any reply, and it skips big
        # attachments, which are what makes downloads slow and time out.
        typ, data = self.conn.uid("FETCH", str(m.uid), "(BODY.PEEK[]<0.262144>)")
        for item in data or []:
            if isinstance(item, tuple):
                try:
                    return extract_text(email.message_from_bytes(item[1], policy=default_policy))
                except Exception:  # noqa: BLE001  (message cut mid-attachment)
                    return item[1][:20000].decode("utf-8", errors="ignore")
        return ""

    # ---- what the analysis needs --------------------------------------------
    def collect(self, since: datetime, professor_addrs: list[str], subjects: list[str],
                names: list[str] = ()) -> list[Msg]:
        """All candidate messages, de-duplicated by Message-ID.

        names: professors' full names. The FROM search also matches the sender's display
        name, so this finds a professor writing from another address with a new subject."""
        seen: dict[str, Msg] = {}
        for folder, is_spam in self.folders():
            uids = set()
            uids |= self.search_any(folder, since, "FROM", professor_addrs)
            uids |= self.search_any(folder, since, "SUBJECT", subjects, chunk=8)
            uids |= self.search_any(folder, since, "FROM", ["mailer-daemon", "postmaster"])
            uids |= self.search_any(folder, since, "FROM", list(names))
            if not is_spam:
                # Mail the student sent to professors from Gmail directly
                for i in range(0, len(professor_addrs), 15):
                    to_expr = _or_tree("TO", professor_addrs[i:i + 15])[0]
                    uids.update(self.search(folder, since, f"FROM {_quote(self.account.address)} {to_expr}"))
            for m in self.headers(folder, uids, is_spam):
                key = m.message_id or f"{folder}:{m.uid}"
                if key not in seen or (seen[key].in_spam and not is_spam):
                    seen[key] = m
        return list(seen.values())

    def from_one(self, since: datetime, address: str) -> list[Msg]:
        """Quick check used right before sending a reminder."""
        found = []
        for folder, is_spam in self.folders():
            found += self.headers(folder, self.search(folder, since, f"FROM {_quote(address)}"), is_spam)
        return found


def open_reader(account: Account) -> MailboxReader:
    """Factory, replaced in tests."""
    return MailboxReader(account)
