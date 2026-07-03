"""Tests against real captured ansible-core 2.21 --check --diff output.

tests/fixtures/jsonl_output.jsonl was produced by an actual ansible-playbook
run of testdata/site.yml through the playcheck_jsonl callback — not
hand-written. Regenerate it with a real run if the callback changes.
"""
import os
from pathlib import Path

import pytest

from playcheck.model import Category
from playcheck.parse import parse_events
from playcheck.render import render

# The version-matrix runner points PLAYCHECK_FIXTURE at output freshly
# captured from other ansible-core versions and reruns this same suite.
FIXTURE = Path(
    os.environ.get(
        "PLAYCHECK_FIXTURE", Path(__file__).parent / "fixtures" / "jsonl_output.jsonl"
    )
)


@pytest.fixture(scope="module")
def report():
    return parse_events(FIXTURE.read_text(encoding="utf-8").splitlines())


def _by_task(report, name_fragment):
    matches = [r for r in report.all_results() if name_fragment in r.task]
    assert matches, f"no task result matching {name_fragment!r}"
    return matches[0]


def test_hosts_and_plays(report):
    assert set(report.hosts) == {"web-01", "db-01"}
    assert report.plays == ["Configure web servers", "Configure db servers"]


def test_shell_and_command_flagged_not_previewable(report):
    for fragment in ("Restart nginx", "Run migration script", "Vacuum database"):
        r = _by_task(report, fragment)
        assert r.category is Category.NOT_PREVIEWABLE, fragment


def test_raw_flagged_even_without_any_skip_message(report):
    # Verified against ansible-core 2.21: raw is skipped in check mode with
    # no msg and no skip_reason at all. Only the fail-safe default catches it.
    r = _by_task(report, "Bootstrap agent")
    assert r.category is Category.NOT_PREVIEWABLE


def test_loop_task_merges_item_diffs(report):
    r = _by_task(report, "Write tuning files")
    assert r.category is Category.CHANGED
    rendered = "\n".join(str(d) for d in r.diff)
    assert len(r.diff) == 2
    assert "shared_buffers" in rendered and "work_mem" in rendered


def test_handlers_are_reported(report):
    flag = _by_task(report, "Write restart flag")
    assert flag.category is Category.CHANGED
    reload_h = _by_task(report, "Reload db (shell handler")
    assert reload_h.category is Category.NOT_PREVIEWABLE


def test_conditional_skip_is_not_flagged(report):
    r = _by_task(report, "Skipped by condition")
    assert r.category is Category.SKIPPED


def test_unattributable_skip_defaults_to_not_previewable():
    # Fail-safe bias: any skip without a recognized conditional reason must be
    # flagged, even if the message is unfamiliar.
    events = [
        '{"event": "result", "status": "skipped", "host": "h", "task": "t",'
        ' "action": "a", "changed": false, "msg": "some future skip text"}'
    ]
    report = parse_events(events)
    assert report.all_results()[0].category is Category.NOT_PREVIEWABLE


def test_changed_with_diff(report):
    r = _by_task(report, "Write nginx config")
    assert r.category is Category.CHANGED
    assert r.diff and "server_name example.com" in r.diff[0]["after"]


def test_diff_false_hides_content(report):
    r = _by_task(report, "Write secret config")
    assert r.category is Category.CHANGED_DIFF_HIDDEN
    assert r.diff == []


def test_no_log_censored(report):
    r = _by_task(report, "Write API token")
    assert r.category is Category.CHANGED_DIFF_HIDDEN
    assert r.censored


def test_check_mode_false_flagged_as_ran_for_real(report):
    r = _by_task(report, "Gather versions")
    assert r.category is Category.RAN_FOR_REAL


def test_failed_task_with_ignore_errors(report):
    r = _by_task(report, "Failing assertion")
    assert r.category is Category.FAILED
    assert r.ignore_errors


def test_no_change_task_is_ok(report):
    r = _by_task(report, "Already correct file")
    assert r.category is Category.OK


def test_dict_shaped_diff_from_lineinfile(report):
    # lineinfile returns a single dict diff, not a list.
    r = _by_task(report, "Ensure line in hosts-like file")
    assert r.category is Category.CHANGED
    assert r.diff[0]["after"].startswith("10.0.0.5")


@pytest.mark.parametrize("color", [True, False])
def test_rendered_output_never_leaks_secrets(report, color):
    out = render(report, color=color)
    assert "supersecret" not in out
    assert "abc123" not in out


def test_rendered_output_headline_content(report):
    out = render(report, color=False)
    assert "NOT PREVIEWED" in out
    assert "5 tasks were NOT simulated" in out
    assert "executed for real despite --check" in out
    assert "web-01" in out and "db-01" in out


def test_garbage_lines_collected_not_fatal():
    report = parse_events(["not json", '{"event": "stats", "stats": {}}'])
    assert report.unparsed_lines == ["not json"]
