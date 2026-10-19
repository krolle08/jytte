"""The bank consent callback: escaping, log hygiene, route shape.

The callback is the one URL in this project that carries a credential,
and once a tunnel is in front of it, the one URL reachable from the
internet. Both facts are easy to undo by accident, so they are pinned
here rather than left to a comment.

Run:  docker compose exec jytte python -m pytest tests/test_bank_callback.py -q
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import bankauth  # noqa: E402


def _record(path: str) -> logging.LogRecord:
    """An access-log record shaped the way uvicorn emits one."""
    r = logging.LogRecord("uvicorn.access", logging.INFO, "", 0,
                          '%s - "%s %s HTTP/%s" %d', None, None)
    r.args = ("10.0.0.1:1234", "GET", path, "1.1", 200)
    return r


# ----------------------------------------------------------------------
# the code must not reach the log
# ----------------------------------------------------------------------
def test_the_code_is_redacted_from_the_access_log():
    # uvicorn logs the whole request line. Without this filter the
    # authorization code is written to disk the moment the bank
    # redirects, which is CLAUDE.md rule 3 broken by a dependency.
    r = _record("/bank/callback?code=abc123&state=xyz")
    bankauth._RedactCallbackQuery().filter(r)
    assert r.args[2] == "/bank/callback?<redacted>"
    assert "abc123" not in str(r.args)


def test_a_callback_without_a_query_is_left_alone():
    r = _record("/bank/callback")
    bankauth._RedactCallbackQuery().filter(r)
    assert r.args[2] == "/bank/callback"


def test_other_paths_keep_their_query_string():
    # Redacting everything would make the access log useless for the
    # pages that have nothing to hide.
    r = _record("/vacation?r=oest")
    bankauth._RedactCallbackQuery().filter(r)
    assert r.args[2] == "/vacation?r=oest"


def test_the_filter_never_drops_a_record():
    assert bankauth._RedactCallbackQuery().filter(_record("/el")) is True


def test_a_record_of_another_shape_does_not_raise():
    # Not every logger that ends up here emits uvicorn's five-tuple.
    r = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "%s", None, None)
    r.args = ("something else",)
    assert bankauth._RedactCallbackQuery().filter(r) is True


# ----------------------------------------------------------------------
# the page reflects the query back, so it has to escape it
# ----------------------------------------------------------------------
def test_the_code_is_escaped_before_it_is_rendered():
    out = bankauth._esc('<script>alert("x")</script>')
    assert "<script>" not in out
    assert out == "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;"


def test_escaping_does_the_ampersand_first():
    # &lt; must not become &amp;lt;, which it does when & is escaped last.
    assert bankauth._esc("a&b<c") == "a&amp;b&lt;c"


# ----------------------------------------------------------------------
# route shape
# ----------------------------------------------------------------------
def test_the_router_exposes_one_path_and_only_GET():
    paths = [(r.path, sorted(r.methods - {"HEAD"}))
             for r in bankauth.router.routes]
    assert paths == [("/bank/callback", ["GET"])]


def test_nothing_here_writes_to_the_database():
    """Jytte stores no part of the consent. The code is short-lived and
    is a bearer credential while it lives; the session that replaces it
    belongs in n8n's credential store, not in jytte.db."""
    src = (Path(__file__).resolve().parents[1] / "app" / "bankauth.py").read_text(
        encoding="utf-8")
    for forbidden in ("aiosqlite", "from app import db", "record_edit",
                      "INSERT", "UPDATE "):
        assert forbidden not in src, forbidden
