"""Host grouping and degraded-run rendering (large inventories, unreachable
hosts, plays matching no hosts). Grouping behavior was verified against a
real 15-host run (testdata/inventory-large.ini)."""
import json

import pytest

from playcheck.parse import parse_events
from playcheck.render import render
from playcheck.render_md import render_markdown

from test_parse import FIXTURE


def _fixture_lines():
    return FIXTURE.read_text(encoding="utf-8").splitlines()


def _with_cloned_host(lines, src="db-01", clones=("db-02", "db-03")):
    out = list(lines)
    for line in lines:
        if f'"{src}"' in line:
            for clone in clones:
                out.append(line.replace(f'"{src}"', f'"{clone}"'))
    return out


@pytest.fixture(scope="module")
def grouped_report():
    return parse_events(_with_cloned_host(_fixture_lines()))


def test_identical_hosts_render_once(grouped_report):
    out = render(grouped_report, color=False)
    assert "db-01, db-02, db-03" in out
    assert "changes each" in out
    assert "= identical on: db-01 db-02 db-03" in out
    # The db config diff must appear exactly once despite three hosts.
    assert out.count("+max_connections=200") == 1


def test_differing_hosts_do_not_group(grouped_report):
    out = render(grouped_report, color=False)
    # web-01 has different results and must stay its own section.
    assert "web-01  " in out


def test_markdown_grouping(grouped_report):
    md = render_markdown(grouped_report)
    assert "Identical on 3 hosts: db-01, db-02, db-03" in md
    assert md.count("+max_connections=200") == 1


def test_unreachable_host_rendering():
    events = _fixture_lines() + [
        json.dumps(
            {
                "event": "result",
                "status": "unreachable",
                "host": "dead-01",
                "task": "Write nginx config",
                "action": "ansible.builtin.copy",
                "changed": False,
                "msg": "Failed to connect to the host via ssh",
            }
        )
    ]
    out = render(parse_events(events), color=False)
    assert "dead-01  0 changes · unreachable" in out
    assert "UNREACHABLE" in out


def test_partial_no_hosts_matched_keeps_report():
    events = _fixture_lines() + ['{"event": "no_hosts_matched"}']
    out = render(parse_events(events), color=False)
    # One play matching nothing must not replace the whole report.
    assert "SUMMARY" in out and "web-01" in out
    assert "matched no hosts" in out


def test_total_no_hosts_matched_short_circuits():
    report = parse_events(['{"event": "no_hosts_matched"}'])
    out = render(report, color=False)
    assert "No hosts matched" in out
    md = render_markdown(report)
    assert "No hosts matched" in md
