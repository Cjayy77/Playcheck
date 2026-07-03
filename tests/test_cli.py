"""CLI exit-code behavior, with the ansible invocation stubbed out."""
from pathlib import Path

import pytest

import playcheck.cli as cli
from playcheck.runner import RunOutcome

from test_parse import FIXTURE


@pytest.fixture()
def stub_run(monkeypatch):
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()

    def fake_run(playbook, inventories, extra_args, **kwargs):
        return RunOutcome(returncode=0, stdout_lines=lines, stderr="")

    monkeypatch.setattr(cli, "run", fake_run)


BASE = ["run", "site.yml", "-i", "inv.ini", "--no-color", "--quiet"]


def test_default_exit_mirrors_ansible(stub_run, capsys):
    assert cli.main(BASE) == 0
    assert "SUMMARY" in capsys.readouterr().out


def test_fail_on_changes_exits_3(stub_run, capsys):
    assert cli.main(BASE + ["--fail-on-changes"]) == 3


def test_fail_on_unpreviewable_exits_4(stub_run, capsys):
    assert cli.main(BASE + ["--fail-on-unpreviewable"]) == 4


def test_changes_gate_takes_precedence(stub_run, capsys):
    assert cli.main(BASE + ["--fail-on-changes", "--fail-on-unpreviewable"]) == 3


def test_ansible_failure_wins_over_gates(monkeypatch, capsys):
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    monkeypatch.setattr(
        cli,
        "run",
        lambda *a, **k: RunOutcome(returncode=2, stdout_lines=lines, stderr=""),
    )
    assert cli.main(BASE + ["--fail-on-changes"]) == 2


def test_markdown_format(stub_run, capsys):
    assert cli.main(BASE + ["--format", "markdown"]) == 0
    assert capsys.readouterr().out.startswith("<!-- playcheck-report -->")
