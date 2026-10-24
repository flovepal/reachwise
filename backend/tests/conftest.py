import os
import sys
from email.utils import make_msgid
from pathlib import Path

from cryptography.fernet import Fernet

os.environ.update({
    "JWT_SECRET": "test-secret-test-secret-test-secret",
    "ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "RUN_SCHEDULER": "false",
    "DEV_LOGIN": "true",
    "ANTHROPIC_API_KEY": "",
    "MIN_GAP_SECONDS": "70",
    "MAX_GAP_SECONDS": "120",
    "GENERATION_LIMIT": "100",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mongomock  # noqa: E402
import mongomock.gridfs  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

mongomock.gridfs.enable_gridfs_integration()

from app import db as dbmod  # noqa: E402
from app.mail import imap, smtp  # noqa: E402

TESTDATA = Path(__file__).resolve().parents[2] / "testdata"


class FakeMailbox:
    """Stands in for Gmail: records sent mail, serves inbox messages."""

    def __init__(self):
        self.sent = []          # EmailMessage objects
        self.inbox: list[imap.Msg] = []
        self.fail_reads = False
        self.next_uid = 1

    def add(self, from_addr, subject, body, date, to=None, refs=(), message_id=None, in_spam=False, from_name=""):
        m = imap.Msg(folder="[Gmail]/Spam" if in_spam else "[Gmail]/All Mail", uid=self.next_uid,
                     from_addr=from_addr.lower(), to=[t.lower() for t in (to or ["student@gmail.com"])],
                     message_id=message_id or make_msgid(domain="example.edu"), refs=list(refs),
                     subject=subject, date=date, in_spam=in_spam, body=body, from_name=from_name)
        self.next_uid += 1
        self.inbox.append(m)
        return m


class FakeReader:
    def __init__(self, box: FakeMailbox, account):
        self.box, self.account = box, account

    def __enter__(self):
        if self.box.fail_reads:
            raise OSError("IMAP down")
        return self

    def __exit__(self, *a):
        return False

    def collect(self, since, addrs, subjects, names=()):
        out = []
        for m in self.box.inbox:
            if m.date and m.date < since:
                continue
            if (m.from_addr in addrs or any(s.lower() in m.subject.lower() for s in subjects)
                    or m.from_addr.startswith(("mailer-daemon", "postmaster"))
                    or any(n.lower() in m.from_name.lower() for n in names)
                    or (m.from_addr == self.account.address and any(t in addrs for t in m.to))):
                out.append(m)
        return out

    def from_one(self, since, address):
        return [m for m in self.box.inbox if m.from_addr == address and (not m.date or m.date >= since)]

    def body(self, m):
        return m.body


@pytest.fixture()
def box(monkeypatch):
    b = FakeMailbox()
    monkeypatch.setattr(smtp, "test_login", lambda account: None)

    def fake_send(account, msg):
        b.sent.append(msg)
        return msg["Message-ID"]

    monkeypatch.setattr(smtp, "send", fake_send)
    monkeypatch.setattr(imap, "open_reader", lambda account: FakeReader(b, account))
    return b


@pytest.fixture()
def client(monkeypatch, box):
    dbmod.set_db(mongomock.MongoClient()["profmail_test"])
    # Background work runs immediately in tests
    from app.routers import replies as replies_router

    def run_now(fn, *a, **k):
        fn(*a, **k)

    monkeypatch.setattr(replies_router, "submit", run_now)
    from app.main import app
    with TestClient(app) as c:
        yield c


def login(client, email="student@gmail.com", name="John Paul S"):
    r = client.post("/auth/dev", json={"email": email, "name": name})
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return r.json()["user"]
