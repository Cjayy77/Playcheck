"""Render a RunReport for the terminal.

Layout goals, in priority order:
1. Tasks that could NOT be previewed are impossible to miss.
2. Per-host grouping with change counts readable in ten seconds.
3. Colored add/remove diffs instead of raw unified-diff walls.
"""
from __future__ import annotations

import difflib
import json
from typing import Any, Dict, List

from .model import (
    Category,
    HostGroup,
    HostReport,
    RunReport,
    TaskResult,
    group_identical_hosts,
)


class Palette:
    def __init__(self, color: bool):
        c = color
        self.reset = "\x1b[0m" if c else ""
        self.bold = "\x1b[1m" if c else ""
        self.dim = "\x1b[2m" if c else ""
        self.red = "\x1b[31m" if c else ""
        self.green = "\x1b[32m" if c else ""
        self.yellow = "\x1b[33m" if c else ""
        self.magenta = "\x1b[35m" if c else ""
        self.cyan = "\x1b[36m" if c else ""

    def paint(self, text: str, *styles: str) -> str:
        if not any(styles):
            return text
        return "".join(styles) + text + self.reset


def _short_action(action: str) -> str:
    return action.rsplit(".", 1)[-1]


def _diff_lines(entry: Dict[str, Any]) -> List[str]:
    """Turn one ansible diff entry into displayable diff lines."""
    if entry.get("prepared"):
        return str(entry["prepared"]).splitlines()

    before, after = entry.get("before"), entry.get("after")
    if before is None and after is None:
        return []
    if not isinstance(before, str) or not isinstance(after, str):
        # Some modules (e.g. file) diff attribute dicts, not file content.
        before = json.dumps(before, indent=2, sort_keys=True, default=str)
        after = json.dumps(after, indent=2, sort_keys=True, default=str)

    from_header = str(entry.get("before_header") or "before")
    to_header = str(entry.get("after_header") or "after")
    lines = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=from_header,
            tofile=to_header,
            lineterm="",
        )
    )
    return lines


def _render_diff(result: TaskResult, p: Palette, indent: str) -> List[str]:
    out: List[str] = []
    for entry in result.diff:
        for line in _diff_lines(entry):
            if line.startswith(("+++", "---")):
                out.append(indent + p.paint(line, p.dim))
            elif line.startswith("@@"):
                out.append(indent + p.paint(line, p.cyan))
            elif line.startswith("+"):
                out.append(indent + p.paint(line, p.green))
            elif line.startswith("-"):
                out.append(indent + p.paint(line, p.red))
            else:
                out.append(indent + line)
    return out


_HIDDEN_REASON = {
    True: "diff censored (no_log)",
    False: "diff hidden by task setting (diff: false)",
}


def _host_headline(g: HostGroup, p: Palette) -> str:
    h = g.report
    changes = h.count(Category.CHANGED, Category.CHANGED_DIFF_HIDDEN)
    blind = h.count(Category.NOT_PREVIEWABLE)
    failed = h.count(Category.FAILED)
    unreachable = h.count(Category.UNREACHABLE)
    each = " each" if len(g.hosts) > 1 else ""
    parts = [f"{changes} change{'s' if changes != 1 else ''}{each}"]
    if blind:
        parts.append(p.paint(f"{blind} not previewable", p.magenta, p.bold))
    if failed:
        parts.append(p.paint(f"{failed} failed", p.red, p.bold))
    if unreachable:
        parts.append(p.paint("unreachable", p.red, p.bold))
    ran = h.count(Category.RAN_FOR_REAL)
    if ran:
        parts.append(p.paint(f"{ran} ran for real", p.yellow))
    return f"{p.paint(g.label(), p.bold, p.cyan)}  {' · '.join(parts)}"


def _render_task(r: TaskResult, p: Palette) -> List[str]:
    name = f"{r.task} ({_short_action(r.action)})"
    lines: List[str] = []
    if r.category is Category.CHANGED:
        lines.append("  " + p.paint("~ " + name, p.yellow))
        lines.extend(_render_diff(r, p, "      "))
    elif r.category is Category.CHANGED_DIFF_HIDDEN:
        reason = _HIDDEN_REASON[r.censored]
        lines.append(
            "  " + p.paint("~ " + name, p.yellow) + "  " + p.paint(f"[{reason}]", p.dim)
        )
    elif r.category is Category.NOT_PREVIEWABLE:
        note = r.msg or "module does not support check mode"
        lines.append(
            "  "
            + p.paint("! " + name, p.magenta, p.bold)
            + "  "
            + p.paint(f"NOT PREVIEWED — {note}", p.magenta)
        )
    elif r.category is Category.RAN_FOR_REAL:
        lines.append(
            "  "
            + p.paint("» " + name, p.yellow)
            + "  "
            + p.paint("[executed for real: check_mode: false]", p.dim)
        )
    elif r.category in (Category.FAILED, Category.UNREACHABLE):
        suffix = " (ignored)" if r.ignore_errors else ""
        label = "UNREACHABLE" if r.category is Category.UNREACHABLE else "FAILED"
        lines.append("  " + p.paint(f"✗ {name}  {label}{suffix}", p.red, p.bold))
        if r.msg:
            lines.append("      " + p.paint(r.msg, p.red))
    return lines


def render(report: RunReport, color: bool = True) -> str:
    p = Palette(color)
    out: List[str] = []
    out.append(p.paint("Playcheck", p.bold) + p.paint(" — ansible --check --diff preview", p.dim))
    out.append("")

    if report.no_hosts_matched and not report.hosts:
        out.append(p.paint("No hosts matched the play pattern — nothing was checked.", p.red, p.bold))
        return "\n".join(out) + "\n"

    interesting = (
        Category.CHANGED,
        Category.CHANGED_DIFF_HIDDEN,
        Category.NOT_PREVIEWABLE,
        Category.RAN_FOR_REAL,
        Category.FAILED,
        Category.UNREACHABLE,
    )

    for group in group_identical_hosts(report.hosts):
        h = group.report
        out.append(_host_headline(group, p))
        if len(group.hosts) > 1:
            names = " ".join(group.hosts[:20])
            if len(group.hosts) > 20:
                names += f" … (+{len(group.hosts) - 20} more)"
            out.append("  " + p.paint(f"= identical on: {names}", p.dim))
        shown = [r for r in h.results if r.category in interesting]
        for r in shown:
            out.extend(_render_task(r, p))
        quiet_ok = h.count(Category.OK)
        quiet_skip = h.count(Category.SKIPPED)
        quiet_bits = []
        if quiet_ok:
            quiet_bits.append(f"{quiet_ok} ok (no change)")
        if quiet_skip:
            quiet_bits.append(f"{quiet_skip} skipped by condition")
        if quiet_bits:
            out.append("  " + p.paint("· " + ", ".join(quiet_bits), p.dim))
        out.append("")

    # -- top-line summary ---------------------------------------------------
    hosts_total = len(report.hosts)
    hosts_changed = sum(
        1
        for h in report.hosts.values()
        if h.count(Category.CHANGED, Category.CHANGED_DIFF_HIDDEN)
    )
    changed = report.count(Category.CHANGED, Category.CHANGED_DIFF_HIDDEN)
    hidden = report.count(Category.CHANGED_DIFF_HIDDEN)
    blind = report.count(Category.NOT_PREVIEWABLE)
    ran = report.count(Category.RAN_FOR_REAL)
    failed = report.count(Category.FAILED, Category.UNREACHABLE)

    out.append(p.paint("SUMMARY", p.bold))
    host_line = f"  hosts: {hosts_changed} of {hosts_total} would change"
    out.append(host_line)
    if report.no_hosts_matched:
        out.append("  " + p.paint("⚠ one or more plays matched no hosts in this inventory", p.yellow))
    task_line = f"  tasks: {changed} would change"
    if hidden:
        task_line += f" ({hidden} with hidden diffs)"
    out.append(task_line)
    if failed:
        out.append("  " + p.paint(f"✗ {failed} task run{'s' if failed != 1 else ''} failed — see above", p.red, p.bold))
    if ran:
        out.append("  " + p.paint(f"» {ran} task{'s' if ran != 1 else ''} executed for real despite --check (check_mode: false)", p.yellow))
    if blind:
        out.append(
            "  "
            + p.paint(
                f"⚠ {blind} task{'s were' if blind != 1 else ' was'} NOT simulated "
                "(module does not support check mode) — the real run may change more than shown.",
                p.magenta,
                p.bold,
            )
        )
    else:
        out.append("  " + p.paint("✓ every task could be previewed", p.green))
    return "\n".join(out) + "\n"
