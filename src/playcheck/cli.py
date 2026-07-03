"""playcheck CLI entry point."""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from . import __version__
from .model import Category
from .parse import parse_events
from .render import render
from .runner import AnsibleNotFound, run


def _want_color(no_color_flag: bool) -> bool:
    if no_color_flag or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="playcheck",
        description=(
            "Run ansible-playbook --check --diff and reformat the result into a "
            "readable per-host preview, flagging tasks that cannot be simulated."
        ),
    )
    parser.add_argument("--version", action="version", version=f"playcheck {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser(
        "run",
        help="preview a playbook",
        description=(
            "Everything after `--` is passed through to ansible-playbook "
            "unchanged (e.g. playcheck run site.yml -i hosts -- -l web -t nginx)."
        ),
    )
    run_p.add_argument("playbook", help="playbook to preview")
    run_p.add_argument(
        "-i",
        "--inventory",
        action="append",
        default=[],
        help="inventory file or host list (repeatable)",
    )
    run_p.add_argument("-l", "--limit", help="limit to matching hosts")
    run_p.add_argument("-t", "--tags", help="only run tasks tagged with these values")
    run_p.add_argument(
        "--format",
        choices=("terminal", "markdown"),
        default="terminal",
        help="output format: terminal (default) or markdown for PR comments",
    )
    run_p.add_argument("--no-color", action="store_true", help="disable colored output")
    run_p.add_argument(
        "--fail-on-changes",
        action="store_true",
        help="exit 3 if any task would change (CI gating)",
    )
    run_p.add_argument(
        "--fail-on-unpreviewable",
        action="store_true",
        help="exit 4 if any task could not be previewed (CI gating)",
    )
    run_p.add_argument("--quiet", action="store_true", help="no live progress while ansible runs")
    run_p.add_argument(
        "--ansible-playbook-bin",
        default="ansible-playbook",
        help="path to the ansible-playbook executable",
    )
    run_p.add_argument(
        "ansible_args",
        nargs="*",
        help="extra arguments after `--` are passed to ansible-playbook",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # argparse swallows `--`; split passthrough args off manually first.
    passthrough: List[str] = []
    if "--" in argv:
        idx = argv.index("--")
        argv, passthrough = argv[:idx], argv[idx + 1 :]

    args = _build_parser().parse_args(argv)

    extra = list(passthrough) + list(args.ansible_args or [])
    if args.limit:
        extra += ["-l", args.limit]
    if args.tags:
        extra += ["-t", args.tags]

    try:
        outcome = run(
            args.playbook,
            args.inventory,
            extra,
            ansible_playbook_bin=args.ansible_playbook_bin,
            progress=not args.quiet,
        )
    except AnsibleNotFound as exc:
        print(f"playcheck: {exc}", file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        print("playcheck: interrupted", file=sys.stderr)
        return 130

    report = parse_events(outcome.stdout_lines)

    if not report.hosts and outcome.returncode != 0:
        # ansible died before producing results (syntax error, bad inventory...)
        sys.stderr.write(outcome.stderr)
        for line in report.unparsed_lines:
            print(line, file=sys.stderr)
        print(
            f"playcheck: ansible-playbook exited with {outcome.returncode} "
            "before any host produced results",
            file=sys.stderr,
        )
        return outcome.returncode or 1

    if outcome.stderr.strip():
        sys.stderr.write(outcome.stderr)

    if args.format == "markdown":
        from .render_md import render_markdown

        print(render_markdown(report), end="")
    else:
        print(render(report, color=_want_color(args.no_color)), end="")

    if outcome.returncode != 0:
        return outcome.returncode
    if args.fail_on_changes and report.count(
        Category.CHANGED, Category.CHANGED_DIFF_HIDDEN
    ):
        return 3
    if args.fail_on_unpreviewable and report.count(Category.NOT_PREVIEWABLE):
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
