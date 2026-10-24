from datetime import datetime

from app.mail import imap
from app.mail.smtp import Account


def test_or_tree_builds_valid_imap_or():
    assert imap._or_tree("FROM", ["a@x", "b@x", "c@x"]) == ['OR FROM "a@x" OR FROM "b@x" FROM "c@x"']
    assert imap._or_tree("FROM", ["a@x"]) == ['FROM "a@x"']


class FakeConn:
    def __init__(self):
        self.searches = []

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"',
                      b'(\\All \\HasNoChildren) "/" "[Gmail]/&YkBnCZCuTvY-"',
                      b'(\\HasNoChildren \\Junk) "/" "[Gmail]/Spam"',
                      b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"']

    def select(self, folder, readonly=True):
        return "OK", [b"1"]

    def uid(self, cmd, *args):
        if cmd == "SEARCH":
            self.searches.append(args[1])
            return "OK", [b"3 7"]
        return "OK", []


def test_folders_found_by_flag_and_search_query_shape():
    r = imap.MailboxReader(Account("me@gmail.com", "pw"))
    r.conn = FakeConn()
    r._find_folders()
    assert r.all_mail == "[Gmail]/&YkBnCZCuTvY-"       # localized name, found via \All
    assert r.spam == "[Gmail]/Spam"
    uids = r.search_any(r.all_mail, datetime(2026, 8, 21), "FROM", ["a@x", "b@x", "非ascii"])
    assert uids == {3, 7}
    assert r.conn.searches == ['(SINCE 21-Aug-2026 OR FROM "a@x" FROM "b@x")']


def test_strip_quoted_handles_gmail_and_chinese_clients():
    text = "Sure, let's meet.\n\nOn Tue, Aug 22, 2026 John <x@y> wrote:\n> Dear Professor"
    assert imap.strip_quoted(text) == "Sure, let's meet."
    text = "好的\n\n2026年8月22日 週二 John 於 寫道：\n> Dear"
    assert imap.strip_quoted(text) == "好的"
