"""Invoke ansible-playbook --check --diff with the playcheck callback plugin."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

PLUGIN_DIR = Path(__file__).parent / "_ansible" / "callback_plugins"


@dataclass
class RunOutcome:
    returncode: int
    stdout_lines: List[str] = field(default_factory=list)
    stderr: str = ""


class AnsibleNotFound(Exception):
    pass


def build_command(
    playbook: str,
    inventories: List[str],
    extra_args: List[str],
    ansible_playbook_bin: str = "ansible-playbook",
) -> List[str]:
    cmd = [ansible_playbook_bin, playbook, "--check", "--diff"]
    for inv in inventories:
        cmd += ["-i", inv]
    cmd += extra_args
    return cmd


def build_env(base_env: Optional[dict] = None) -> dict:
    env = dict(base_env if base_env is not None else os.environ)
    env["ANSIBLE_STDOUT_CALLBACK"] = "playcheck_jsonl"
    plugin_path = str(PLUGIN_DIR)
    existing = env.get("ANSIBLE_CALLBACK_PLUGINS")
    env["ANSIBLE_CALLBACK_PLUGINS"] = (
        plugin_path + os.pathsep + existing if existing else plugin_path
    )
    # Our callback owns stdout; ansible color codes would corrupt the JSONL.
    env.pop("ANSIBLE_FORCE_COLOR", None)
    env["ANSIBLE_NOCOLOR"] = "1"
    return env


def run(
    playbook: str,
    inventories: List[str],
    extra_args: List[str],
    ansible_playbook_bin: str = "ansible-playbook",
    progress: bool = True,
) -> RunOutcome:
    cmd = build_command(playbook, inventories, extra_args, ansible_playbook_bin)
    try:
        proc = subprocess.Popen(
            cmd,
            env=build_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        raise AnsibleNotFound(
            f"could not find '{ansible_playbook_bin}' on PATH. "
            "Is Ansible installed in this environment?"
        )

    lines: List[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.append(line)
        if progress:
            _echo_progress(line)
    _, stderr = proc.communicate()
    return RunOutcome(returncode=proc.returncode, stdout_lines=lines, stderr=stderr or "")


def _echo_progress(line: str) -> None:
    """Show a lightweight live trace on stderr while ansible runs."""
    import json

    try:
        event = json.loads(line)
    except ValueError:
        return
    kind = event.get("event")
    if kind == "play_start":
        sys.stderr.write(f"PLAY {event.get('play', '')}\n")
    elif kind == "task_start":
        sys.stderr.write(f"  · {event.get('task', '')}\n")
    sys.stderr.flush()
