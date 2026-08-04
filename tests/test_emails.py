"""FEAT-001 emails widget tests. Pure-function + fetch behaviour.

Uses asyncio.run() so only plain pytest is needed (no pytest-asyncio).
"""

import asyncio
import email
import imaplib

from app.widgets.emails import fetch as f


def _cfg(**over):
    base = {
        "host": "imap.example.com", "port": 993, "user": "u", "password": "p",
        "mailbox": "INBOX", "limit": 30,
        "trustworks": ["trustworks.dk"], "dagrofa": ["dagrofa.dk", "dagrofa.com"],
    }
    base.update(over)
    return base


def test_classify_and_shape():
    cfg = _cfg()
    assert f._classify("trustworks.dk", cfg) == "trustworks"
    assert f._classify("mail.trustworks.dk", cfg) == "trustworks"
    assert f._classify("dagrofa.com", cfg) == "dagrofa"
    assert f._classify("gmail.com", cfg) == "private"
    assert f._classify("", cfg) == "private"


def _msg(headers: dict, parts=None, body="hello world"):
    if parts is None:
        m = email.message.EmailMessage()
        for k, v in headers.items():
            m[k] = v
        m.set_content(body)
        return m
    # multipart
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    m = MIMEMultipart(parts["subtype"])
    for k, v in headers.items():
        m[k] = v
    for p in parts["items"]:
        m.attach(p)
    return m


def test_attachment_detection():
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication

    # alternative (plain + html) -> NOT an attachment
    plain = MIMEText("hi", "plain")
    html = MIMEText("<b>hi</b>", "html")
    alt = _msg({"Subject": "x", "From": "a@b.com"},
               parts={"subtype": "alternative", "items": [plain, html]})
    assert f._has_attachments(alt) is False

    # mixed with a real attachment -> True
    att = MIMEApplication(b"PDFDATA", _subtype="pdf")
    att.add_header("Content-Disposition", "attachment", filename="report.pdf")
    mixed = _msg({"Subject": "x", "From": "a@b.com"},
                 parts={"subtype": "mixed", "items": [MIMEText("body"), att]})
    assert f._has_attachments(mixed) is True


def test_urgency():
    assert f._urgency(_msg({"X-Priority": "1"}), "hi") == "high"
    assert f._urgency(_msg({"Importance": "High"}), "hi") == "high"
    assert f._urgency(_msg({}), "This is URGENT please") == "high"
    assert f._urgency(_msg({}), "det haster lidt") == "high"
    assert f._urgency(_msg({}), "just a normal note") == "normal"


def test_normalize_fields():
    m = _msg({"Subject": "Weekly report", "From": "Jane Doe <jane@trustworks.dk>",
              "Date": "Mon, 27 Jul 2026 10:00:00 +0000"}, body="Here is the summary text.")
    row = f._normalize("42", m, _cfg())
    assert row["uid"] == "42"
    assert row["title"] == "Weekly report"
    assert row["topic"] == "Jane Doe"
    assert row["from_addr"] == "jane@trustworks.dk"
    assert row["_bucket"] == "trustworks"
    assert row["urgency"] == "normal"
    assert "summary text" in row["description"]
    assert row["date"].startswith("2026-07-27")


def test_unconfigured(monkeypatch):
    for var in ("EMAIL_IMAP_HOST", "EMAIL_IMAP_USER", "EMAIL_IMAP_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    data = asyncio.run(f.fetch())
    assert data["ready"] is True
    assert data["configured"] is False
    assert data["counts"] == {"trustworks": 0, "dagrofa": 0, "private": 0}
    assert data["buckets"] == {"trustworks": [], "dagrofa": [], "private": []}


def test_fetch_is_now_n8n_push_stub(monkeypatch):
    # emails is source: n8n (FEAT-009) - fetch() no longer does IMAP; it just
    # returns an awaiting-push shape. Real mail arrives via POST /state.
    data = asyncio.run(f.fetch())
    assert data["ready"] is True and data["configured"] is False
    assert data["buckets"] == {"trustworks": [], "dagrofa": [], "private": []}


def test_dagrofa_gate(monkeypatch):
    from app.widgets.emails import view
    monkeypatch.delenv("EMAILS_DAGROFA_ENABLED", raising=False)
    assert view.context({})["dagrofa_enabled"] is False   # gated by default
    monkeypatch.setenv("EMAILS_DAGROFA_ENABLED", "true")
    assert view.context({})["dagrofa_enabled"] is True
    monkeypatch.setenv("EMAILS_DAGROFA_ENABLED", "false")
    assert view.context({})["dagrofa_enabled"] is False
