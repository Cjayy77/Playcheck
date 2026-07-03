"""Parse JSONL events emitted by the playcheck_jsonl callback into a RunReport.

Classification rules were verified against real ansible-core 2.21 --check --diff
runs (see tests/fixtures/jsonl_output.jsonl):

- A task skipped because its module cannot run in check mode arrives as
  status "skipped" with a msg (e.g. "Command would have run if not in check
  mode") and NO skip_reason.
- A task skipped by a `when:` condition arrives with
  skip_reason "Conditional result was False" and no msg.

Any skip we cannot positively attribute to a conditional is flagged as
NOT_PREVIEWABLE. Over-flagging is acceptable; silently missing an
unpreviewable task defeats the tool's purpose.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from .model import Category, RunReport, TaskResult

_CONDITIONAL_SKIP_REASONS = ("conditional result was false",)


def _normalize_diff(diff: Any) -> List[Dict[str, Any]]:
    """Ansible modules return diffs as a dict, a list of dicts, or nothing."""
    if not diff:
        return []
    if isinstance(diff, dict):
        return [diff]
    if isinstance(diff, list):
        return [d for d in diff if isinstance(d, dict)]
    return []


def _is_conditional_skip(event: Dict[str, Any]) -> bool:
    reason = event.get("skip_reason")
    if not reason or event.get("msg"):
        return False
    return str(reason).strip().lower() in _CONDITIONAL_SKIP_REASONS


def _classify(event: Dict[str, Any]) -> Category:
    status = event["status"]
    if status == "failed":
        return Category.FAILED
    if status == "unreachable":
        return Category.UNREACHABLE
    if status == "skipped":
        if _is_conditional_skip(event):
            return Category.SKIPPED
        return Category.NOT_PREVIEWABLE
    # status is "ok" or "changed"
    if event.get("check_mode_bypassed"):
        return Category.RAN_FOR_REAL
    if status == "changed":
        if event.get("censored") or event.get("diff_disabled") or not _collect_diffs(event):
            return Category.CHANGED_DIFF_HIDDEN
        return Category.CHANGED
    return Category.OK


def _collect_diffs(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    diffs = _normalize_diff(event.get("diff"))
    # Loop tasks carry per-item results, each possibly with its own diff.
    for item in event.get("results") or []:
        if isinstance(item, dict):
            diffs.extend(_normalize_diff(item.get("diff")))
    return diffs


def parse_events(lines: Iterable[str]) -> RunReport:
    report = RunReport()
    current_play = ""
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except ValueError:
            report.unparsed_lines.append(raw)
            continue
        if not isinstance(event, dict):
            report.unparsed_lines.append(raw)
            continue
        kind = event.get("event")
        if kind == "play_start":
            current_play = event.get("play", "")
            report.plays.append(current_play)
        elif kind == "no_hosts_matched":
            report.no_hosts_matched = True
        elif kind == "stats":
            report.stats = event.get("stats", {})
        elif kind == "result":
            status = event.get("status", "")
            if status.startswith("item_"):
                # Per-item loop events; the aggregate task result follows and
                # carries the item results, so avoid double counting.
                continue
            msg = event.get("msg")
            report.add(
                TaskResult(
                    host=event.get("host", "?"),
                    task=event.get("task", ""),
                    action=event.get("action", ""),
                    play=current_play,
                    category=_classify(event),
                    changed=bool(event.get("changed")),
                    msg=str(msg) if msg is not None else None,
                    diff=_collect_diffs(event),
                    censored=bool(event.get("censored")),
                    ignore_errors=bool(event.get("ignore_errors")),
                )
            )
    return report
