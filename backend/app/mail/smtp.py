"""Sending mail with the student's own Gmail app password."""
import imaplib
import smtplib
import socket
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from ..security import decrypt


@dataclass
class Account:
    address: str
    password: str
    display_name: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    imap_host: str = "imap.gmail.com"


class MailLoginError(Exception):
    """Login failed; the message is safe to show to the student."""


def account_for(user: dict) -> Account:
    g = user.get("gmail") or {}
    if not g.get("app_password_enc"):
        raise MailLoginError("Connect your Gmail account first.")
    return Account(
        address=g["address"], password=decrypt(g["app_password_enc"]),
        display_name=g.get("display_name") or user.get("name", ""),
        smtp_host=g.get("smtp_host", "smtp.gmail.com"), imap_host=g.get("imap_host", "imap.gmail.com"),
    )


def build_message(account: Account, to: str, subject: str, body: str,
                  attachments: list[tuple[str, bytes, str]] = (),
                  in_reply_to: str = "", references: list[str] = ()) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((account.display_name, account.address)) if account.display_name else account.address
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=account.address.split("@")[-1])
    if in_reply_to:
        # Puts reminders in the same thread as the first email
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = " ".join(list(references) or [in_reply_to])
    # Quoted-printable instead of base64 for the text: base64-encoded text bodies are a
    # common spam signal, and AI-written emails often contain non-ASCII quotes and dashes.
    msg.set_content(body, cte="quoted-printable")
    for filename, data, mime in attachments:
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=filename)
    return msg


def send(account: Account, msg: EmailMessage) -> str:
    """Send and return the Message-ID."""
    with smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=60) as server:
        server.starttls()
        server.login(account.address, account.password)
        server.send_message(msg)
    return msg["Message-ID"]


def test_login(account: Account) -> None:
    """Try both sending (SMTP) and reading (IMAP). Raise MailLoginError with a readable reason."""
    try:
        with smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(account.address, account.password)
    except smtplib.SMTPAuthenticationError:
        raise MailLoginError(
            "Gmail rejected the app password. Check it was copied correctly, that 2-Step "
            "Verification is on, and that it is an app password (not your normal password).")
    except (socket.timeout, OSError) as e:
        raise MailLoginError(f"Could not reach the mail server ({e}).")

    try:
        conn = imaplib.IMAP4_SSL(account.imap_host, 993, timeout=30)
        try:
            conn.login(account.address, account.password)
        finally:
            try:
                conn.logout()
            except Exception:  # noqa: BLE001
                pass
    except imaplib.IMAP4.error:
        raise MailLoginError(
            "Sending works, but reading replies failed. Turn on IMAP in Gmail: Settings → "
            "See all settings → Forwarding and POP/IMAP → Enable IMAP.")
    except (socket.timeout, OSError) as e:
        raise MailLoginError(f"Could not reach the mail server for reading replies ({e}).")
