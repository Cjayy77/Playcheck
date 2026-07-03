from pathlib import Path

import pytest

from playcheck.parse import parse_events
from playcheck.render_md import MARKER, render_markdown

from test_parse import FIXTURE


@pytest.fixture(scope="module")
def md():
    report = parse_events(FIXTURE.read_text(encoding="utf-8").splitlines())
    return render_markdown(report)


def test_marker_present_for_comment_updates(md):
    assert md.startswith(MARKER)


def test_headline_and_warning(md):
    assert "hosts would change" in md
    assert "NOT simulated" in md


def test_hosts_in_details_blocks(md):
    assert "<summary><b>web-01</b>" in md
    assert "<summary><b>db-01</b>" in md


def test_diff_rendered_in_fence(md):
    assert "````diff" in md
    assert "+server {" in md


def test_no_secret_leak(md):
    assert "supersecret" not in md
    assert "abc123" not in md


def test_not_previewed_tasks_called_out(md):
    assert md.count("🚫") >= 5  # 5 unpreviewable tasks + summary line
