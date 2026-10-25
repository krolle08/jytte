"""FEAT-001: one codebase, two sites.

`JYTTE_SITE=personal` is the home server (money, news, household),
`JYTTE_SITE=local` is the work machine (Home, AI, Work, POC), unset runs
everything. These tests pin which half owns what, so a new page or
workflow cannot silently land on both or neither.

Needs the app's dependencies, so run it where they are installed (the
image, with pytest added):

    python -m pytest tests/test_site_split.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import jobs, nav, site  # noqa: E402
from app import main  # noqa: E402
from app.registry import WidgetRegistry  # noqa: E402

WIDGETS = REPO / "app" / "widgets"
WF = REPO / "deploy" / "n8n" / "workflows"
if not WF.is_dir():
    WF = Path(os.getenv("JYTTE_N8N_WORKFLOWS_PATH", "/jytte/n8n-workflows"))

PERSONAL_WIDGETS = {"news", "budget", "salary", "bank", "elpris", "elforbrug",
                    "stocks", "vacation", "football", "geomap"}
LOCAL_WIDGETS = {"tasks", "email", "calendar", "azuredevops", "projects",
                 "aistack", "wowforever", "vault"}

# Top-level routes both sites answer. Anything else must be owned.
SHARED = {"/health", "/legacy", "/chat", "/events",
          "/widgets/{name}", "/widgets/{name}/refresh",
          "/widgets/{name}/state", "/widgets/{name}/error"}


def _registry(monkeypatch, value: str | None) -> WidgetRegistry:
    if value is None:
        monkeypatch.delenv("JYTTE_SITE", raising=False)
    else:
        monkeypatch.setenv("JYTTE_SITE", value)
    r = WidgetRegistry(WIDGETS)
    r.discover()
    return r


def _client(monkeypatch, value: str) -> TestClient:
    monkeypatch.setenv("JYTTE_SITE", value)
    # No `with`: the lifespan (scheduler, watchers, DB) is not needed to
    # see what the gate answers, and the gate runs before any handler.
    return TestClient(main.app, raise_server_exceptions=False,
                      follow_redirects=False)


# --- AC-01 / AC-02 / AC-03 registry ------------------------------------

def test_registry_personal(monkeypatch):
    names = {w.name for w in _registry(monkeypatch, "personal").list()}
    assert names == PERSONAL_WIDGETS


def test_registry_local(monkeypatch):
    names = {w.name for w in _registry(monkeypatch, "local").list()}
    assert names == LOCAL_WIDGETS


def test_registry_unset_loads_all(monkeypatch):
    names = {w.name for w in _registry(monkeypatch, None).list()}
    assert names == PERSONAL_WIDGETS | LOCAL_WIDGETS


def test_every_manifest_has_site():
    for m in sorted(WIDGETS.glob("*/manifest.yaml")):
        tag = (yaml.safe_load(m.read_text(encoding="utf-8")) or {}).get("site")
        assert tag in site.SITES, f"{m.parent.name}: site is {tag!r}"


# --- AC-04 / AC-05 / AC-06 routes --------------------------------------

def test_every_route_is_owned_or_shared():
    """A new page that nobody assigned would be served on both sites."""
    for r in main.app.routes:
        if not isinstance(r, APIRoute):
            continue
        if r.path.startswith("/widgets/") and r.path not in SHARED:
            # Widget routers (/widgets/<name>/...) belong to their widget,
            # which the registry already filters.
            continue
        assert (site.path_site(r.path) is not None or r.path in SHARED
                or r.path in site.SHARED_PATHS or _hub_shared(r.path)), r.path


def _hub_shared(path: str) -> bool:
    """FEAT-002: a hub fragment or action is shared when its page is."""
    for pre in ("/frag/", "/act/"):
        if path.startswith(pre):
            seg = path[len(pre):].split("/", 1)[0]
            return (seg == "{seg}" or seg in site.HUB_SHARED_SEGMENTS
                    or "/" + seg in site.SHARED_PATHS)
    return False


def test_hub_fragments_follow_their_page():
    assert site.path_site("/frag/bank/row/tx1") == site.PERSONAL
    assert site.path_site("/act/maintenance/x/done") == site.LOCAL
    assert site.path_site("/frag/jobs/row/x") is None
    assert site.path_site("/") is None


@pytest.mark.parametrize("path", ["/budget", "/bank", "/bank/callback", "/salary",
                                  "/el", "/legacy/budget", "/docs/ml", "/stocks",
                                  "/news", "/frag/bank/row/x"])
def test_routes_gated_local(monkeypatch, path):
    assert _client(monkeypatch, "local").get(path).status_code == 404


@pytest.mark.parametrize("path", ["/ai", "/devops", "/poc", "/poc/systems",
                                  "/legacy/today", "/frontpage/box/now", "/today",
                                  "/maintenance", "/documents"])
def test_routes_gated_personal(monkeypatch, path):
    assert _client(monkeypatch, "personal").get(path).status_code == 404


@pytest.mark.parametrize("value,path", [("local", "/ai"), ("local", "/jobs"),
                                        ("personal", "/budget"), ("personal", "/bank")])
def test_own_routes_pass_the_gate(monkeypatch, value, path):
    # Without the lifespan a handler may fail for want of templates, but
    # it must not be the gate's 404.
    assert _client(monkeypatch, value).get(path).status_code != 404


@pytest.mark.parametrize("value", ["personal", "local"])
def test_shared_routes(monkeypatch, value):
    assert _client(monkeypatch, value).get("/health").status_code == 200
    monkeypatch.setenv("JYTTE_SITE", value)
    owners = {p["site"] for p in nav.legacy_pages()}
    assert owners == {value}


def test_legacy_unset_lists_all(monkeypatch):
    monkeypatch.delenv("JYTTE_SITE", raising=False)
    assert len(nav.legacy_pages()) == len(nav.LEGACY_PAGES)


@pytest.mark.parametrize("value", ["personal", "local"])
def test_root_is_shared(monkeypatch, value):
    """FEAT-002: `/` is the Home Hub overview on both sites. It used to
    send the personal site to /budget."""
    assert _client(monkeypatch, value).get("/").status_code != 404


# --- AC-07 / AC-NF-02 nav -----------------------------------------------

def _hrefs(groups: list[dict], label: str) -> list[str]:
    for g in groups:
        if g["label"] == label:
            return [it.href for it in g["links"]]
    return []


def test_nav_peer_links():
    groups = nav._groups(site.LOCAL, "http://server:8080")
    assert _hrefs(groups, "Personal")
    assert all(h.startswith("http://server:8080/") for h in _hrefs(groups, "Personal"))
    for label in ("Overview", "AI", "Work", "Legacy", "POC'S"):
        assert all(h.startswith("/") for h in _hrefs(groups, label)), label
    # Own groups keep the 1..9 keys; peer links get none.
    personal = next(g for g in groups if g["label"] == "Personal")
    assert all(it.idx == 0 for it in personal["links"])
    own = [it.idx for g in groups if g["label"] != "Personal" for it in g["links"] if it.idx]
    assert own == list(range(1, len(own) + 1))


def test_nav_personal_keys_start_at_one():
    groups = nav._groups(site.PERSONAL, "")
    assert groups[0]["label"] == "Personal"
    assert groups[0]["links"][0].idx == 1


def test_nav_without_peer():
    labels = [g["label"] for g in nav._groups(site.LOCAL, "")]
    assert "Personal" not in labels
    assert "AI" in labels


def test_home_budget_tile(monkeypatch):
    import asyncio
    from app import home

    class _Empty:
        def get(self, name):
            return None

        def list(self):
            return []

    monkeypatch.setenv("JYTTE_SITE", "local")
    monkeypatch.delenv("JYTTE_PEER_URL", raising=False)
    tiles = asyncio.run(home.build(_Empty()))["tiles"]
    assert not any(t["label"] == "Budget" for t in tiles)

    monkeypatch.setenv("JYTTE_PEER_URL", "http://server:8080/")
    tiles = asyncio.run(home.build(_Empty()))["tiles"]
    assert [t["href"] for t in tiles if t["label"] == "Budget"] == ["http://server:8080/budget"]


# --- AC-08 / AC-09 workflows ------------------------------------------

def _import_only(compose: str) -> set[str]:
    doc = yaml.safe_load((REPO / compose).read_text(encoding="utf-8"))
    return set(doc["services"]["n8n"]["environment"]["N8N_IMPORT_ONLY"].split())


def test_workflow_lists_partition():
    if not (REPO / "docker-compose.personal.yml").exists():
        pytest.skip("compose files are not in the image")
    files = {p.name for p in WF.glob("*.json")}
    personal = _import_only("docker-compose.personal.yml")
    local = _import_only("docker-compose.yml")
    assert not personal & local
    assert personal | local == files
    assert personal == {f for f, s in site.WORKFLOWS.items() if s == site.PERSONAL}
    assert local == {f for f, s in site.WORKFLOWS.items() if s == site.LOCAL}


def test_jobs_filtered(monkeypatch):
    monkeypatch.setenv("JYTTE_SITE", "local")
    files = {j["file"] for j in jobs.load(WF)["jobs"]}
    assert "bank.json" not in files and "elforbrug.json" not in files
    assert {f for f, s in site.WORKFLOWS.items() if s == site.LOCAL} <= files


# --- AC-10 personal compose ------------------------------------------

def test_personal_compose_no_windows_paths():
    p = REPO / "docker-compose.personal.yml"
    if not p.exists():
        pytest.skip("compose files are not in the image")
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert doc["services"]["jytte"]["environment"]["JYTTE_SITE"] == "personal"
    for svc in doc["services"].values():
        for v in svc.get("volumes", []):
            src = v["source"] if isinstance(v, dict) else v.split(":", 1)[0]
            assert not src.upper().startswith("C:"), src


# --- AC-NF-01 / AC-NF-03 failure modes --------------------------------

def test_invalid_site_raises(monkeypatch):
    monkeypatch.setenv("JYTTE_SITE", "persnal")
    with pytest.raises(ValueError, match="personal, local"):
        site.current()


def test_unloaded_widget_routes_404(monkeypatch):
    local = _registry(monkeypatch, "local")
    monkeypatch.setattr(main, "registry", local)
    monkeypatch.setenv("JYTTE_INTERNAL_SECRET", "test-only-secret")
    c = _client(monkeypatch, "local")
    assert c.get("/widgets/budget").status_code == 404
    r = c.post("/widgets/bank/state", json={"x": 1},
               headers={"X-Jytte-Internal-Secret": "test-only-secret"})
    assert r.status_code == 404


# --- review fixes ------------------------------------------------------

def test_nav_peer_groups_keep_order():
    """POC'S stays last: the money pages must not sit below the WIP group."""
    labels = [g["label"] for g in nav._groups(site.LOCAL, "http://server:8080")]
    assert labels == [g.label for g in nav.GROUPS]
    assert labels[-1] == "POC'S"


def test_misspelt_site_loads_nowhere(monkeypatch, tmp_path):
    import shutil
    for name in ("vacation",):
        shutil.copytree(WIDGETS / name, tmp_path / name)
    m = tmp_path / "vacation" / "manifest.yaml"
    m.write_text(m.read_text(encoding="utf-8").replace("site: personal", "site: persnal"),
                 encoding="utf-8")
    for value in ("personal", "local"):
        monkeypatch.setenv("JYTTE_SITE", value)
        r = WidgetRegistry(tmp_path)
        r.discover()
        assert r.list() == [], value
