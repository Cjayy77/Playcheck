"""Data model for a parsed --check --diff run."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class Category(enum.Enum):
    """What a task result means for the person reading the preview."""

    CHANGED = "changed"                    # would change, diff available
    CHANGED_DIFF_HIDDEN = "diff_hidden"    # would change, diff suppressed (diff: false / no_log)
    NOT_PREVIEWABLE = "not_previewable"    # skipped because check mode is unsupported
    RAN_FOR_REAL = "ran_for_real"          # check_mode: false — executed despite --check
    OK = "ok"                              # no change
    SKIPPED = "skipped"                    # skipped by condition — would also skip in a real run
    FAILED = "failed"
    UNREACHABLE = "unreachable"


@dataclass
class TaskResult:
    host: str
    task: str
    action: str
    play: str
    category: Category
    changed: bool = False
    msg: Optional[str] = None
    diff: List[Dict[str, Any]] = field(default_factory=list)
    censored: bool = False
    ignore_errors: bool = False


@dataclass
class HostReport:
    host: str
    results: List[TaskResult] = field(default_factory=list)

    def count(self, *categories: Category) -> int:
        return sum(1 for r in self.results if r.category in categories)


@dataclass
class RunReport:
    plays: List[str] = field(default_factory=list)
    hosts: Dict[str, HostReport] = field(default_factory=dict)
    stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    no_hosts_matched: bool = False
    unparsed_lines: List[str] = field(default_factory=list)

    def add(self, result: TaskResult) -> None:
        self.hosts.setdefault(result.host, HostReport(result.host)).results.append(result)

    def all_results(self) -> List[TaskResult]:
        return [r for h in self.hosts.values() for r in h.results]

    def count(self, *categories: Category) -> int:
        return sum(1 for r in self.all_results() if r.category in categories)
