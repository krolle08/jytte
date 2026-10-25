"""FEAT-002: the Home Hub routes, without the lifespan.

The lifespan would start the scheduler and every widget fetch; these
tests only need templates and a database, so they set both up by hand.
No network: the n8n API URL points at a closed port, apps.yml is a temp
file without checks.

    python -m pytest tests/test_hub_routes.py
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, jobs, main  # noqa: E402
from app.hub import monitor, n8n  # noqa: E402
from app.hub import registry as hreg  # noqa: E402

HX = {"HX-Request": "true"}

# Strings from the POC's mock data. None of them may reach a page.
POC_MOCKS = ("312.500 kr.", "428.320 kr.", "Finance Sync", "Photo Backup",
             "Update Docker containers", "OpenAI releases new developer tools",
             "Trustworks A/S loenoverfoersel", "8412")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JYTTE_SITE", raising=False)
    monkeypatch.delenv("JYTTE_PEER_URL", raising=False)
    monkeypatch.delenv("N8N_API_KEY", raising=False)
    monkeypatch.setenv("N8N_API_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "jytte.db")
    asyncio.run(db.init_db())
    monkeypatch.setattr(jobs, "DIR", REPO / "deploy" / "n8n" / "workflows")
    apps = tmp_path / "apps.yml"
    apps.write_text("apps:\n  - id: demo\n    name: Demo app\n    url: http://demo.lan\n",
                    encoding="utf-8")
    monkeypatch.setattr(monitor, "APPS_PATH", apps)
    monkeypatch.setenv("JYTTE_TASKS_PATH", str(tmp_path / "vault"))
    main.app.state.templates = main._templates()
    return TestClient(main.app, raise_server_exceptions=True)


def test_overview_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    for s in ("N8N Pipeline Overview", "Pipeline Flow:", "My Apps &amp; Services",
              "System Monitoring", "Maintenance &amp; Operations", "Budget Overview",
              "Salary &amp; Income", "Investments", "Latest News"):
        assert s in r.text, s


def test_no_poc_mock_values(client):
    pages = [client.get("/").text] + [client.get(it.href).text
                                      for it in hreg.NAV if it.hub and it.key != "overview"]
    for body in pages:
        for m in POC_MOCKS:
            assert m not in body, m


def test_full_and_partial(client):
    full = client.get("/logs")
    assert full.status_code == 200 and "<html" in full.text and 'id="nav"' in full.text
    part = client.get("/logs", headers=HX)
    assert part.status_code == 200 and "<html" not in part.text and "Execution Logs" in part.text


def test_every_nav_page_renders(client):
    for it in (*hreg.NAV, hreg.SETTINGS):
        if not it.hub:
            continue
        r = client.get(it.href)
        assert r.status_code == 200, it.href
        assert it.label.split(" ")[0] in r.text, it.href


def test_tab_filter_and_row_detail(client):
    r = client.get("/jobs?tab=Paused", headers=HX)
    assert r.status_code == 200
    m = re.search(r'hx-get="/frag/jobs/row/([^"?]+)', client.get("/jobs", headers=HX).text)
    assert m, "pipelines rows should open a panel"
    d = client.get(f"/frag/jobs/row/{m.group(1)}")
    assert d.status_code == 200 and 'class="det"' in d.text and "deploy/n8n/workflows" in d.text
    assert client.get("/frag/jobs/row/nope").status_code == 404


def test_pipeline_sel(client):
    body = client.get("/").text
    m = re.search(r'hx-get="/jobs\?sel=([^"]+)"', body)
    assert m, "overview rows open the pipelines page with sel"
    r = client.get(f"/jobs?sel={m.group(1)}", headers=HX)
    assert "Pipeline Flow:" in r.text and "Pipeline details" in r.text


def test_actions_need_hx_header(client):
    assert client.post("/act/notes", data={"text": "x"}).status_code == 403


def test_notes_roundtrip(client):
    r = client.post("/act/notes", data={"text": "Check the NAS firmware"}, headers=HX)
    assert r.status_code == 200 and "Check the NAS firmware" in r.text
    nid = re.search(r'/act/notes/(\d+)/delete', r.text).group(1)
    r = client.post(f"/act/notes/{nid}/delete", headers=HX)
    assert "Check the NAS firmware" not in r.text


def test_bookmark_rejects_script_urls(client):
    r = client.post("/act/bookmarks", data={"title": "x", "url": "javascript:alert(1)"}, headers=HX)
    assert "Only http and https" in r.text and "javascript:" not in r.text
    r = client.post("/act/bookmarks", data={"title": "n8n docs", "url": "docs.n8n.io", "tag": "Automation"},
                    headers=HX)
    assert "https://docs.n8n.io" in r.text


def test_settings_toggle(client):
    before = client.get("/settings", headers=HX).text
    assert "Auto-pause after failures" in before
    client.post("/act/settings/autopause/toggle", headers=HX)
    after = client.get("/settings", headers=HX).text
    row = lambda t: re.search(r"Auto-pause after failures.*?>(On|Off)<", t, re.S).group(1)  # noqa: E731
    assert row(before) != row(after)
    assert client.post("/act/settings/nope/toggle", headers=HX).status_code == 404


def test_toggle_without_key(client, monkeypatch):
    called = []
    monkeypatch.setattr(n8n, "set_active", lambda *a, **k: called.append(a))
    m = re.search(r'/act/jobs/([^/"]+)/toggle', client.get("/jobs", headers=HX).text)
    r = client.post(f"/act/jobs/{m.group(1)}/toggle", headers=HX)
    assert r.status_code == 200 and "N8N_API_KEY" in r.text
    assert not called


def test_only_monitoring_polls(client):
    pages = {"/": client.get("/").text}
    for it in hreg.NAV:
        if it.hub:
            pages[it.href] = client.get(it.href).text
    for path, body in pages.items():
        for m in re.finditer(r'hx-get="([^"]+)"[^>]*hx-trigger="every', body):
            assert m.group(1) == "/frag/monitoring/card", (path, m.group(1))


def test_no_secret_in_html(client, monkeypatch):
    monkeypatch.setenv("N8N_API_KEY", "nk-test-value-1234567890")
    monkeypatch.setenv("JYTTE_INTERNAL_SECRET", "is-test-value-0987654321")
    bodies = [client.get("/").text] + [client.get(it.href).text for it in hreg.NAV if it.hub]
    bodies.append(client.get("/credentials").text)
    for b in bodies:
        assert "nk-test-value" not in b and "is-test-value" not in b
    assert "N8N_API_KEY" in client.get("/credentials").text


def test_search(client):
    client.post("/act/notes", data={"text": "zebra crossing note"}, headers=HX)
    r = client.get("/search?q=zebra", headers=HX)
    assert "zebra crossing note" in r.text and "Notes" in r.text
    assert "Good " in client.get("/search?q=", headers=HX).text


def test_adopted_page_has_hub_chrome(client):
    r = client.get("/opslag")
    assert r.status_code == 200
    assert 'id="nav"' in r.text and "/static/hub-adopt.css" in r.text


def test_overview_filter_sees_every_pipeline(client):
    """The tab counts cover all pipelines, so the rows must too, not
    only the first eight (code review finding on FEAT-002)."""
    r = client.get("/frag/overview/n8n?filter=paused", headers=HX).text
    n = int(re.search(r"Paused \((\d+)\)", r).group(1))
    assert r.count('class="trow "') + r.count('class="trow sel"') == min(8, n)
