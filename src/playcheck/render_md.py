"""Render a RunReport as GitHub-flavored markdown for PR comments."""
from __future__ import annotations

from typing import List

from .model import Category, HostGroup, RunReport, TaskResult, group_identical_hosts
from .render import _diff_lines, _short_action

MARKER = "<!-- playcheck-report -->"


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fence(lines: List[str]) -> List[str]:
    # Four backticks so diff content containing ``` cannot break out.
    return ["````diff"] + lines + ["````"]


def _task_md(r: TaskResult) -> List[str]:
    name = f"**{_esc(r.task)}** (`{_short_action(r.action)}`)"
    if r.category is Category.CHANGED:
        out = [f"- 🟡 {name}"]
        diff_lines: List[str] = []
        for entry in r.diff:
            diff_lines.extend(_diff_lines(entry))
        if diff_lines:
            out.append("")
            out.extend("  " + l for l in _fence(diff_lines))
            out.append("")
        return out
    if r.category is Category.CHANGED_DIFF_HIDDEN:
        reason = "diff censored (`no_log`)" if r.censored else "diff hidden by task setting (`diff: false`)"
        return [f"- 🟡 {name} — would change, {reason}"]
    if r.category is Category.NOT_PREVIEWABLE:
        note = _esc(r.msg) if r.msg else "module does not support check mode"
        return [f"- 🚫 {name} — **NOT previewed**: {note}"]
    if r.category is Category.RAN_FOR_REAL:
        return [f"- ⚡ {name} — **executed for real** despite `--check` (`check_mode: false`)"]
    if r.category in (Category.FAILED, Category.UNREACHABLE):
        label = "unreachable" if r.category is Category.UNREACHABLE else "failed"
        suffix = " (ignored)" if r.ignore_errors else ""
        msg = f": {_esc(r.msg)}" if r.msg else ""
        return [f"- ❌ {name} — **{label}**{suffix}{msg}"]
    return []


def _host_md(g: HostGroup, open_details: bool) -> List[str]:
    h = g.report
    changes = h.count(Category.CHANGED, Category.CHANGED_DIFF_HIDDEN)
    blind = h.count(Category.NOT_PREVIEWABLE)
    failed = h.count(Category.FAILED)
    unreachable = h.count(Category.UNREACHABLE)
    each = " each" if len(g.hosts) > 1 else ""
    bits = [f"{changes} change{'s' if changes != 1 else ''}{each}"]
    if blind:
        bits.append(f"🚫 {blind} not previewable")
    if failed:
        bits.append(f"❌ {failed} failed")
    if unreachable:
        bits.append("❌ unreachable")
    ran = h.count(Category.RAN_FOR_REAL)
    if ran:
        bits.append(f"⚡ {ran} ran for real")

    out = [
        f"<details{' open' if open_details else ''}>",
        f"<summary><b>{_esc(g.label())}</b> — {_esc(' · '.join(bits))}</summary>",
        "",
    ]
    if len(g.hosts) > 1:
        out += [f"_Identical on {len(g.hosts)} hosts: {_esc(', '.join(g.hosts))}_", ""]
    interesting = (
        Category.CHANGED,
        Category.CHANGED_DIFF_HIDDEN,
        Category.NOT_PREVIEWABLE,
        Category.RAN_FOR_REAL,
        Category.FAILED,
        Category.UNREACHABLE,
    )
    for r in h.results:
        if r.category in interesting:
            out.extend(_task_md(r))
    quiet_ok = h.count(Category.OK)
    quiet_skip = h.count(Category.SKIPPED)
    quiet = []
    if quiet_ok:
        quiet.append(f"{quiet_ok} ok (no change)")
    if quiet_skip:
        quiet.append(f"{quiet_skip} skipped by condition")
    if quiet:
        out.append(f"- ⚪ {', '.join(quiet)}")
    out += ["", "</details>", ""]
    return out


def render_markdown(report: RunReport) -> str:
    out: List[str] = [MARKER, "## Playcheck — `ansible --check --diff` preview", ""]

    if report.no_hosts_matched and not report.hosts:
        out.append("> ❌ **No hosts matched the play pattern — nothing was checked.**")
        return "\n".join(out) + "\n"

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

    headline = f"**{hosts_changed} of {hosts_total} hosts would change · {changed} tasks would change**"
    if hidden:
        headline += f" ({hidden} with hidden diffs)"
    out += [headline, ""]

    if failed:
        out.append(f"> ❌ **{failed} task run{'s' if failed != 1 else ''} failed during the check.**")
    if ran:
        out.append(f"> ⚡ **{ran} task{'s' if ran != 1 else ''} executed for real despite `--check`** (`check_mode: false`).")
    if blind:
        out.append(
            f"> 🚫 **{blind} task{'s were' if blind != 1 else ' was'} NOT simulated** "
            "(module does not support check mode) — the real run may change more than shown."
        )
    else:
        out.append("> ✅ Every task could be previewed.")
    out.append("")

    groups = group_identical_hosts(report.hosts)
    for group in groups:
        out.extend(_host_md(group, open_details=len(groups) <= 3))

    return "\n".join(out) + "\n"
