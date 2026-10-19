"""Tests for the /jobs loader.

Pure stdlib, so this runs on the host without pytest installed in the
image:

    python -m pytest tests/test_jobs.py

The cron cases are the point of the file. `human_cron` is allowed to
say "I do not know" and must never guess a cadence, because a guessed
interval is exactly what makes a stalled job look healthy - the same
rule tests/test_poc_triage.py pins for the Systemmonitor.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import jobs  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

# On the host the workflow JSONs sit in the repo. Inside the container
# only `app/` is baked in, and the same files arrive on the read-only
# bind mount the page itself reads. Resolve both so one suite covers
# `python -m pytest tests/` in either place.
WF = REPO / "deploy" / "n8n" / "workflows"
if not WF.is_dir():
    WF = Path(os.getenv("JYTTE_N8N_WORKFLOWS_PATH", "/jytte/n8n-workflows"))


# --- cron ------------------------------------------------------------

def test_minute_steps():
    assert jobs.human_cron("*/5 * * * *") == ("hvert 5. minut", 5)
    assert jobs.human_cron("*/15 * * * *") == ("hvert 15. minut", 15)


def test_hour_step_keeps_the_minute_offset():
    # The bank job runs at minute 7 so it never collides with every
    # other cron on the hour. Dropping that offset would misreport it.
    assert jobs.human_cron("7 */6 * * *") == ("hver 6. time, minut 07", 360)


def test_daily():
    assert jobs.human_cron("30 6 * * *") == ("dagligt 06:30", 1440)


def test_hourly():
    assert jobs.human_cron("0 * * * *") == ("hver time, minut 00", 60)


def test_every_minute():
    assert jobs.human_cron("* * * * *") == ("hvert minut", 1)


def test_weekly():
    text, mins = jobs.human_cron("0 9 * * 1")
    assert mins == 7 * 24 * 60
    assert "ugentligt" in text


def test_unknown_shape_never_guesses_a_cadence():
    """The contract: an expression this parser does not understand
    prints as itself and reports no cadence. A plausible default here
    would let a dead job read as alive."""
    for expr in ("1,15,45 * * * *", "0 0 1 */3 *", "nonsense", ""):
        text, mins = jobs.human_cron(expr)
        assert mins is None, f"{expr!r} was given a cadence"
        assert text == expr.strip()


def test_six_field_cron_drops_the_seconds():
    assert jobs.human_cron("0 */5 * * * *") == ("hvert 5. minut", 5)


# --- trigger ---------------------------------------------------------

def _node(t, **params):
    return {"type": f"n8n-nodes-base.{t}", "parameters": params}


def test_error_trigger_is_not_the_trigger():
    """A workflow with a schedule and an error branch is a scheduled
    job. Reading errorTrigger as the trigger would describe every
    fetch job in this repo as error-driven."""
    nodes = [_node("errorTrigger"),
             _node("scheduleTrigger",
                   rule={"interval": [{"field": "cronExpression",
                                       "expression": "*/5 * * * *"}]})]
    t = jobs._trigger(nodes)
    assert t["kind"] == "plan" and t["minutes"] == 5


def test_webhook_detail_includes_method_path_and_auth():
    t = jobs._trigger([_node("webhook", httpMethod="POST", path="pr-create",
                             authentication="basicAuth")])
    assert t["kind"] == "hook"
    assert "POST" in t["detail"] and "pr-create" in t["detail"]
    assert "basicAuth" in t["detail"]


def test_ui_written_interval_is_read_too():
    """n8n writes minutesInterval instead of a cron when you pick the
    interval from its dropdown. Both shapes have to parse."""
    t = jobs._trigger([_node("scheduleTrigger",
                             rule={"interval": [{"field": "minutes",
                                                 "minutesInterval": 20}]})])
    assert t["minutes"] == 20


def test_no_trigger_node_is_manual_not_scheduled():
    t = jobs._trigger([_node("set")])
    assert t["kind"] == "manual" and t["minutes"] is None


# --- credential types ------------------------------------------------

def test_only_credential_types_are_exposed():
    """Types are schema and safe to print. Names and values are not,
    and must not leak into the page. Pinned because this table is the
    one surface that renders anything from a credential block."""
    nodes = [{"credentials": {"microsoftOutlookOAuth2Api":
                              {"id": "abc123", "name": "Nichlas Outlook"}}}]
    assert jobs._cred_types(nodes) == ["microsoftOutlookOAuth2Api"]


# --- load ------------------------------------------------------------

def test_missing_directory_is_not_an_empty_table():
    out = jobs.load(REPO / "does-not-exist")
    assert out["ready"] is False
    assert out["jobs"] == []
    assert "monteret" in out["reason"]


def test_loads_the_real_workflow_folder():
    out = jobs.load(WF)
    assert out["ready"] is True
    names = [j["name"] for j in out["jobs"]]
    assert "bank" in names and "pr-create" in names
    assert out["counts"]["total"] == len(list(WF.glob("*.json")))
    assert out["counts"]["active"] + out["counts"]["inactive"] == out["counts"]["total"]


def test_inactive_jobs_sort_first():
    """The list exists to answer "what is switched off". Burying that
    under the healthy rows would defeat the page."""
    out = jobs.load(WF)
    actives = [j["active"] for j in out["jobs"]]
    assert actives == sorted(actives), "an active job sorted above an inactive one"


def test_every_job_has_a_deep_link():
    """A workflow without a top-level id cannot be linked: n8n opens a
    blank canvas, which reads as "deleted". Two commits have already
    gone in to add these ids; this keeps them."""
    out = jobs.load(WF)
    missing = [j["file"] for j in out["jobs"] if not j["href"]]
    assert not missing, f"no top-level id in: {missing}"


def test_description_comes_from_the_file_not_from_us():
    out = jobs.load(WF)
    bank = next(j for j in out["jobs"] if j["name"] == "bank")
    raw = json.loads((WF / "bank.json").read_text(encoding="utf-8"))
    assert bank["desc"] == raw["meta"]["notes"].strip()


def test_long_description_is_split_for_the_cell():
    out = jobs.load(WF)
    bank = next(j for j in out["jobs"] if j["name"] == "bank")
    assert bank["desc_short"].endswith("...")
    assert bank["desc_long"] == bank["desc"]
