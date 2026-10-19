"""Severity logic for the systemmonitor POC.

The whole value of a monitor is that it is wrong in the safe direction:
it may call a healthy system suspicious, it must never call a stopped
one stable. These tests pin that asymmetry, and pin the one case the
POC exists to expose - that an n8n-pushed widget's cadence is unknown
and must not be guessed into looking fine.

No third-party imports, so this suite runs on the host as well as in
the container.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.poc.systems import CRIT_FAILURES, pulse, triage  # noqa: E402


def test_fresh_and_quiet_is_stable():
    t = triage(age_min=5, expected_min=30, failures=0)
    assert t["level"] == "stabil"
    assert t["dot"] == "aqua"


def test_slightly_late_is_observation_not_critical():
    # 1.5x to 3x the interval: late enough to show, not enough to shout.
    t = triage(age_min=60, expected_min=30, failures=0)
    assert t["level"] == "observation"


def test_clearly_stopped_is_critical():
    t = triage(age_min=200, expected_min=30, failures=0)
    assert t["level"] == "kritisk"
    assert "30 min" in t["why"]


def test_one_failure_shows_before_the_clock_runs_out():
    # Fresh data, but the last attempt failed. A monitor that waits for
    # the interval to lapse hides a failure that is already known.
    t = triage(age_min=1, expected_min=30, failures=1)
    assert t["level"] == "observation"


def test_three_failures_is_critical_regardless_of_freshness():
    t = triage(age_min=0, expected_min=30, failures=CRIT_FAILURES)
    assert t["level"] == "kritisk"


def test_never_delivered_is_unknown_not_stable():
    # The dangerous default: a widget that has never pushed has no age,
    # and "no age" must not read as "nothing wrong".
    t = triage(age_min=None, expected_min=None, failures=0, ever_succeeded=False)
    assert t["level"] == "ukendt"
    assert "aldrig" in t["why"]


def test_unknown_cadence_is_never_reported_as_stable():
    # This is the POC's own finding. An n8n-pushed widget has no
    # knowable interval, so even a recent push cannot be called healthy
    # without inventing the number that would prove it.
    t = triage(age_min=3, expected_min=None, failures=0,
               cadence_note="kadence ejes af n8n-workflowet, kan ikke læses herfra")
    assert t["level"] == "ukendt"
    assert "n8n" in t["why"]


def test_unknown_cadence_quotes_the_caller_not_a_hardcoded_reason():
    # The first bug this page found was in itself: a file watcher was
    # told its cadence was owned by n8n, which it is not. The reason
    # belongs to the caller, so two systems with different causes must
    # not get the same sentence.
    pushed = triage(age_min=1, expected_min=None, cadence_note="ejes af n8n")
    watched = triage(age_min=1, expected_min=None, cadence_note="watcher uden interval")
    assert pushed["level"] == watched["level"] == "ukendt"
    assert pushed["why"] != watched["why"]
    assert "n8n" not in watched["why"]


def test_severity_ranks_sort_worst_first():
    rows = [
        triage(age_min=1, expected_min=30),                       # stabil
        triage(age_min=1, expected_min=30, failures=5),           # kritisk
        triage(age_min=1, expected_min=None),                     # ukendt
        triage(age_min=60, expected_min=30),                      # observation
    ]
    order = [r["level"] for r in sorted(rows, key=lambda r: r["rank"])]
    assert order == ["kritisk", "observation", "stabil", "ukendt"]


def test_pulse_marks_one_missed_slot_per_elapsed_interval():
    p = pulse(age_min=95, expected_min=30, slots=12)
    assert len(p) == 12
    assert sum(1 for x in p if x["state"] == "missed") == 3
    # Most recent slot is the rightmost, so the misses are at the end.
    assert p[-1]["state"] == "missed"
    assert p[0]["state"] == "ok"


def test_pulse_without_a_known_cadence_is_all_unknown():
    assert all(x["state"] == "unknown" for x in pulse(10, None))
    assert all(x["state"] == "unknown" for x in pulse(None, 30))


def test_pulse_never_reports_more_misses_than_it_has_slots():
    p = pulse(age_min=100000, expected_min=1, slots=12)
    assert len(p) == 12
    assert all(x["state"] == "missed" for x in p)


def test_escalate_raises_severity_but_never_lowers_it():
    # A second signal may make a system look worse than the clock did.
    # It must never argue a known failure back down to green.
    from app.poc.systems import _escalate
    stable = triage(age_min=1, expected_min=30)
    worse = _escalate(stable, "observation", "widget melder ready: false")
    assert worse["level"] == "observation"
    assert "ready: false" in worse["why"]

    critical = triage(age_min=1, expected_min=30, failures=9)
    unchanged = _escalate(critical, "observation", "mindre vigtigt signal")
    assert unchanged["level"] == "kritisk"
    assert unchanged["why"] == critical["why"]


# ---------------------------------------------------------------------
# Self-declared cadence. A pushed widget can be judged only if it says
# how often it expects to run, because its cron lives in n8n and Jytte
# cannot read it. These pin that the declaration is used when present
# and never fabricated when absent.
# ---------------------------------------------------------------------

def test_declared_cadence_is_read_from_the_payload():
    from app.poc.systems import _declared_cadence
    d = _declared_cadence({"ready": True, "expected_minutes": 1440,
                           "stale_after_minutes": 1560})
    assert d == {"expected": 1440.0, "stale_after": 1560.0}


def test_garbled_cadence_is_treated_as_absent_not_coerced():
    # A confident wrong verdict is worse than an honest unknown.
    from app.poc.systems import _declared_cadence
    for bad in ({"expected_minutes": 0}, {"expected_minutes": -5},
                {"expected_minutes": "snart"}, {"expected_minutes": None}, {}):
        assert "expected" not in _declared_cadence(bad)
    assert _declared_cadence(None) == {}
    assert _declared_cadence("nope") == {}


def test_declared_cadence_makes_a_pushed_widget_judgeable():
    # 1440 min cadence, pushed 20 minutes ago: healthy, and no longer
    # stuck on "ukendt".
    t = triage(age_min=20, expected_min=1440, cadence_note="kadence oplyst i payload")
    assert t["level"] == "stabil"


def test_stale_after_beats_the_global_factor():
    # A daily job is late at 26 h. WARN_FACTOR alone would wait 36 h,
    # because no single multiplier suits both a 10-minute inbox poll
    # and a nightly batch.
    late = 27 * 60
    assert triage(age_min=late, expected_min=1440)["level"] == "stabil"
    assert triage(age_min=late, expected_min=1440,
                  stale_after_min=26 * 60)["level"] == "observation"


def test_two_missed_windows_is_critical():
    t = triage(age_min=53 * 60, expected_min=1440, stale_after_min=26 * 60)
    assert t["level"] == "kritisk"
