"""FEAT-002 Azure DevOps rework tests.

Covers work-item field extension (sprint / due / urgency), the enable gate
(disabled instances are never contacted), and the multi-instance MCP tools.
Uses asyncio.run() so only plain pytest is needed.
"""

import asyncio

from app.widgets.azuredevops import ado
from app.widgets.azuredevops import fetch as f
from app.widgets.azuredevops import mcp as ado_mcp
from app.widgets.azuredevops.ado import ADOConfig


def _wi(fields):
    return {"id": 7, "fields": fields}


def test_workitem_fields():
    cfg = ADOConfig(slug="primary", org="Trustworks", project="App", pat="x", user_email="e")
    item = ado._normalize_workitem(_wi({
        "System.Title": "Do the thing",
        "System.WorkItemType": "Task",
        "System.State": "Active",
        "System.IterationPath": "App\\Sprint 12",
        "System.AssignedTo": {"displayName": "Nichlas"},
        "System.Description": "<p>desc</p>",
        "Microsoft.VSTS.Common.Priority": 2,
        "Microsoft.VSTS.Scheduling.DueDate": "2026-08-01T00:00:00Z",
    }), cfg)
    assert item["title"] == "Do the thing"
    assert item["assignee"] == "Nichlas"
    assert item["sprint"] == "Sprint 12"
    assert item["due_date"] == "2026-08-01T00:00:00Z"
    assert item["urgency"] == "high"
    # A list-fetch normalized item must NOT carry comments (they load lazily).
    assert "comments" not in item


def test_derive_urgency():
    assert ado._derive_urgency({"Microsoft.VSTS.Common.Priority": 1}) == "critical"
    assert ado._derive_urgency({"Microsoft.VSTS.Common.Priority": 4}) == "low"
    assert ado._derive_urgency({"Microsoft.VSTS.Common.Severity": "1 - Critical"}) == "critical"
    assert ado._derive_urgency({}) == "normal"


def test_target_date_fallback():
    cfg = ADOConfig(slug="primary", org="o", project="p", pat="x", user_email="e")
    item = ado._normalize_workitem(_wi({
        "Microsoft.VSTS.Scheduling.TargetDate": "2026-09-09T00:00:00Z",
    }), cfg)
    assert item["due_date"] == "2026-09-09T00:00:00Z"


def test_env_enabled(monkeypatch):
    monkeypatch.delenv("AZDO_ENABLED", raising=False)
    assert ado._env_enabled("") is True          # absent = enabled
    monkeypatch.setenv("AZDO_ENABLED_DAGROFA", "false")
    assert ado._env_enabled("_DAGROFA") is False
    monkeypatch.setenv("AZDO_ENABLED_DAGROFA", "true")
    assert ado._env_enabled("_DAGROFA") is True


def test_disabled_instance_not_contacted(monkeypatch):
    cfg = ADOConfig(slug="dagrofa", org="Dagrofa", project="P", pat="x",
                    user_email="e", enabled=False)
    monkeypatch.setattr(f, "discover_configs", lambda: [cfg])

    async def _boom(c):
        raise AssertionError("disabled instance was contacted")

    monkeypatch.setattr(f, "_safely_fetch_instance", _boom)
    data = asyncio.run(f.fetch())
    inst = data["instances"][0]
    assert inst["awaiting_activation"] is True
    assert inst["enabled"] is False
    assert inst["prs"] is None


class _FakeMcp:
    def __init__(self):
        self.tools = {}

    def tool(self, name, description):
        def deco(fn):
            self.tools[name] = fn
            return fn
        return deco


class _FakeWidget:
    def __init__(self, data):
        self._data = data

    async def latest(self):
        return {"data": self._data}


def test_mcp_reads_instances():
    data = {
        "ready": True, "fetched_at": "t",
        "instances": [
            {"slug": "primary", "label": "Trustworks / App", "awaiting_activation": False,
             "tasks": {"items": [{"id": 1, "title": "a"}], "iteration": {"name": "S12"}},
             "section_errors": {}},
            {"slug": "dagrofa", "label": "Dagrofa", "awaiting_activation": True,
             "tasks": None, "section_errors": {}},
        ],
    }
    mcp, widget = _FakeMcp(), _FakeWidget(data)
    ado_mcp.register(mcp, widget)
    out = asyncio.run(mcp.tools["ado_my_tasks"]())
    assert len(out["items"]) == 1
    assert out["items"][0]["instance"] == "primary"
    assert out["items"][0]["instance_label"] == "Trustworks / App"
    assert "primary" in out["iterations"]
    # dagrofa is dark -> contributes nothing
    assert all(it["instance"] != "dagrofa" for it in out["items"])


def test_comment_normalize():
    c = ado._normalize_comment({
        "id": 3, "text": "<p>looks good</p>",
        "createdBy": {"displayName": "Reviewer"},
        "createdDate": "2026-07-20T12:00:00Z",
    })
    assert c["author"] == "Reviewer"
    assert c["text"] == "<p>looks good</p>"
    assert c["created"] == "2026-07-20T12:00:00Z"
