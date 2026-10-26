"""FEAT-003: every feature is placed by one line in config/features.yml.

Each test points JYTTE_FEATURES_CONFIG at its own file, so the committed
placement is never touched. Needs the app's dependencies (the image):

    python -m pytest tests/test_features.py
"""
from __future__ import annotations

import logging
import os
import sys
from collections import Counter
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient  # noqa: E402

from app import features, jobs, main, site  # noqa: E402
from app.hub import overview, views  # noqa: E402
from app.hub import registry as hreg  # noqa: E402
from app.registry import WidgetRegistry  # noqa: E402

WIDGETS = REPO / "app" / "widgets"
WF = REPO / "deploy" / "n8n" / "workflows"
if not WF.is_dir():
    WF = Path(os.getenv("JYTTE_N8N_WORKFLOWS_PATH", "/jytte/n8n-workflows"))

# The FEAT-001 split, as literals: the default placement must keep it.
FEAT001 = {
    site.PERSONAL: {
        "widgets": {"news", "budget", "salary", "bank", "elpris", "elforbrug",
                    "stocks", "vacation", "football", "geomap"},
        "paths": {"/news", "/budget", "/bank", "/el", "/stocks", "/vacation", "/salary",
                  "/docs/ml", "/legacy/news", "/legacy/budget"},
        "workflows": {"bank.json", "elforbrug.json"},
    },
    site.LOCAL: {
        "widgets": {"tasks", "email", "calendar", "azuredevops", "projects",
                    "aistack", "wowforever", "vault"},
        "paths": {"/ai", "/constellation", "/workflows", "/projects", "/devops", "/opslag",
                  "/poc", "/frontpage", "/today", "/maintenance", "/documents",
                  "/legacy/today", "/legacy/dashboard", "/legacy/ai", "/legacy/projects",
                  "/legacy/ado"},
        "workflows": {"ado-event-notify.json", "azuredevops.json", "calendar.json",
                      "email.json", "intake-to-ado.json", "pr-comment.json",
                      "pr-complete.json", "pr-create.json", "vault-refresh.json"},
    },
}


@pytest.fixture(autouse=True)
def _fresh():
    features.reload()
    yield
    features.reload()


def _place(monkeypatch, tmp_path, lines: dict | None, value: str | None = None) -> None:
    p = tmp_path / "features.yml"
    if lines is not None:
        p.write_text(yaml.safe_dump(lines), encoding="utf-8")
    monkeypatch.setenv("JYTTE_FEATURES_CONFIG", str(p))
    if value is None:
        monkeypatch.delenv("JYTTE_SITE", raising=False)
    else:
        monkeypatch.setenv("JYTTE_SITE", value)
    features.reload()


def _widgets() -> set[str]:
    r = WidgetRegistry(WIDGETS)
    r.discover()
    return {w.name for w in r.list()}


def _client() -> TestClient:
    return TestClient(main.app, raise_server_exceptions=False, follow_redirects=False)


def _side(active: str = "overview") -> dict[str, dict]:
    return {ln["key"]: ln for g in hreg.sidebar(active) for ln in g["links"]}


# --- AC-01 ------------------------------------------------------------

@pytest.mark.parametrize("value", [site.PERSONAL, site.LOCAL])
def test_default_placement_matches_feat001(monkeypatch, value):
    monkeypatch.delenv("JYTTE_FEATURES_CONFIG", raising=False)
    monkeypatch.setenv("JYTTE_SITE", value)
    features.reload()
    want = FEAT001[value]
    other = FEAT001[site.LOCAL if value == site.PERSONAL else site.PERSONAL]
    assert _widgets() == want["widgets"]
    assert all(features.serves(p) for p in want["paths"])
    assert not any(features.serves(p) for p in other["paths"])
    assert features.workflows_for(value) == want["workflows"]
    assert features.defaulted() == ()


# --- AC-02 / AC-03 / AC-04 --------------------------------------------

def test_budget_moved_to_local(monkeypatch, tmp_path):
    _place(monkeypatch, tmp_path, {"budget": ["local"]}, "local")
    assert "budget" in _widgets()
    assert _client().get("/budget").status_code != 404
    assert _side()["budget"]["href"] == "/budget" and not _side()["budget"]["ext"]
    monkeypatch.setenv("JYTTE_SITE", "personal")
    assert _client().get("/budget").status_code == 404
    assert "budget" not in _widgets()


@pytest.mark.parametrize("value", [site.PERSONAL, site.LOCAL])
def test_salary_on_both(monkeypatch, tmp_path, value):
    _place(monkeypatch, tmp_path, {"salary": ["personal", "local"]}, value)
    monkeypatch.setenv("JYTTE_PEER_URL", "http://peer:8080")
    assert "salary" in _widgets()
    assert features.serves("/salary") and features.serves("/frag/salary/row/x")
    assert _side()["salary"]["ext"] is False


@pytest.mark.parametrize("value", [site.PERSONAL, site.LOCAL])
def test_news_off(monkeypatch, tmp_path, value):
    _place(monkeypatch, tmp_path, {"news": []}, value)
    monkeypatch.setenv("JYTTE_PEER_URL", "http://peer:8080")
    reg = WidgetRegistry(WIDGETS)
    reg.discover()
    assert reg.get("news") is None  # no widget, so no router and no MCP tools
    monkeypatch.setattr(main, "registry", reg)
    c = _client()
    for path in ("/news", "/frag/news/row/x", "/widgets/news"):
        assert c.get(path).status_code == 404, path
    assert "news" not in _side()


# --- AC-05 ------------------------------------------------------------

def test_workflows_follow_placement(monkeypatch, tmp_path):
    _place(monkeypatch, tmp_path, {"bank": ["local"]}, "local")
    assert "bank.json" in features.workflows_for("local")
    assert "bank.json" not in features.workflows_for("personal")
    assert "bank.json" in {j["file"] for j in jobs.load(WF)["jobs"]}
    compose = REPO / "docker-compose.yml"
    if compose.exists():
        doc = yaml.safe_load(compose.read_text(encoding="utf-8"))
        have = set(doc["services"]["n8n"]["environment"]["N8N_IMPORT_ONLY"].split())
        # The compose test fails on this placement until the line is pasted.
        assert have != features.workflows_for("local")


# --- AC-06 ------------------------------------------------------------

def test_overview_cards_follow_features(monkeypatch, tmp_path):
    import asyncio
    _place(monkeypatch, tmp_path, {"budget": ["local"], "salary": ["personal"]}, "local")
    monkeypatch.setenv("JYTTE_PEER_URL", "http://peer:8080")
    sal = asyncio.run(overview.salary_card(None))
    assert sal == {"here": False, "peer": "http://peer:8080/salary"}
    assert features.on("budget")
    _place(monkeypatch, tmp_path, {"salary": []}, "local")
    assert asyncio.run(overview.salary_card(None))["peer"] == ""


# --- AC-07 / AC-08 failure modes --------------------------------------

@pytest.mark.parametrize("lines,match", [({"budgt": ["personal"]}, "unknown feature 'budgt'"),
                                         ({"budget": ["persnal"]}, "not a list of sites"),
                                         ({"budget": "both"}, "not a list of sites")])
def test_unknown_feature_or_site_raises(monkeypatch, tmp_path, lines, match):
    _place(monkeypatch, tmp_path, lines, "local")
    with pytest.raises(ValueError, match=match):
        features.placement()


def test_missing_placement_uses_default(monkeypatch, tmp_path):
    _place(monkeypatch, tmp_path, None, "local")
    assert features.defaulted() == tuple(features.CATALOG)
    assert features.placement()["budget"] == {"personal"}
    _place(monkeypatch, tmp_path, {k: list(f.default) for k, f in features.CATALOG.items()
                                   if k != "stocks"}, "local")
    assert features.defaulted() == ("stocks",)
    assert features.placement()["stocks"] == {"personal"}


# --- AC-09 / AC-10 warnings -------------------------------------------

def test_work_feature_on_personal_warns(monkeypatch, tmp_path, caplog):
    _place(monkeypatch, tmp_path, {"devops": ["personal"]}, "personal")
    with caplog.at_level(logging.WARNING, logger="jytte.features"):
        features.log_boot()
    assert any("Azure DevOps" in r.message and "work data" in r.message for r in caplog.records)
    rows, details = views.feature_rows()
    row = next(r for r in rows if r.cells[0] == "Azure DevOps")
    assert row.kinds[2] == "r" and row.cells[2] == "On here"
    assert details["feature-devops"].cmd == "devops: [personal]"


def test_soft_dependency_named(monkeypatch, tmp_path):
    _place(monkeypatch, tmp_path, {"budget": ["local"], "salary": ["personal"]}, "local")
    assert any(w["feature"] == "budget" and w["level"] == "yellow"
               for w in features.warnings())
    assert "Salary is off on this site" in views._missing("salary")
    _place(monkeypatch, tmp_path, {}, "personal")
    assert views._missing("salary") == ""


# --- AC-11 / AC-12 ----------------------------------------------------

def test_catalog_covers_everything():
    names = {(yaml.safe_load(m.read_text(encoding="utf-8")) or {}).get("name") or m.parent.name
             for m in WIDGETS.glob("*/manifest.yaml")}
    counts = Counter(w for f in features.CATALOG.values() for w in f.widgets)
    assert set(counts) == names
    assert all(n == 1 for n in counts.values()), counts
    wf = Counter(w for f in features.CATALOG.values() for w in f.workflows)
    assert set(wf) == {p.name for p in WF.glob("*.json")}
    assert all(n == 1 for n in wf.values()), wf
    for f in features.CATALOG.values():
        assert f.data in (features.WORK, features.PRIVATE), f.key
        assert set(f.needs) <= set(features.CATALOG), f.key
        assert set(f.default) <= set(site.SITES), f.key


def test_committed_file_lists_every_feature():
    doc = yaml.safe_load((REPO / "config" / "features.yml").read_text(encoding="utf-8"))
    assert list(doc) == list(features.CATALOG)


def test_unset_runs_everything(monkeypatch, tmp_path):
    _place(monkeypatch, tmp_path, {"news": []}, None)
    assert _widgets() == FEAT001[site.PERSONAL]["widgets"] | FEAT001[site.LOCAL]["widgets"]
    assert features.serves("/news")


def test_config_entries_follow_their_feature(monkeypatch, tmp_path):
    """config/apps.yml and config/schedules.yml entries: `feature:` follows
    placement, `site:` stays pinned, untagged shows on both."""
    _place(monkeypatch, tmp_path, {"bank": ["local"]}, "local")
    assert features.entry_on({"feature": "bank"})
    assert not features.entry_on({"feature": "budget"})
    assert not features.entry_on({"feature": "nosuch"})
    assert not features.entry_on({"site": "personal"})
    assert features.entry_on({})
