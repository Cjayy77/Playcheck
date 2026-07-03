# CLAUDE.md — Playcheck

This file is ground truth for working on Playcheck in this repo. Read it before making implementation decisions. `README.md` is the user-facing statement of what the tool does and doubles as the project brief; if this file and the README diverge on product intent, reconcile them rather than guessing.

## What this project is

Ansible's `--check --diff` mode simulates a playbook run and shows what *would* change, but the raw terminal output is an unstructured scroll with no per-host summary and no visibility into which tasks were silently skipped because their module doesn't support check mode (`shell`, `command`, `raw`, etc.).

Playcheck is a CLI that runs `ansible-playbook <playbook> --check --diff -i <inventory>`, parses the output, and reformats it into something readable in ten seconds:

- Per-host grouping ("web-01: 2 changes, db-01: 0 changes")
- Rendered diffs (GitHub-style colored add/remove, not raw unified diff)
- Explicit flagging of tasks that couldn't be previewed — this is the core value prop, not a nice-to-have. Silently missing this defeats the tool's purpose.
- Top-line summary: hosts affected, tasks that would change, tasks that couldn't be previewed

Later (optional, CI phase): a GitHub Action that posts the formatted output as a PR comment, `terraform plan`-style.

Later still (only with real free-tier adoption): a paid hosted dashboard for teams. Not to be pulled forward early.

## Build order — do not skip ahead

1. **CLI formatter only.** `playcheck run <playbook> -i <inventory>`. Shippable and useful standalone. Get this right before touching CI.
2. **Edge cases**: modules without check-mode support, `diff: false` tasks (must not leak secrets), multi-play playbooks, large host counts.
3. **CI wrapper**: GitHub Action first (most common target). GitLab CI later.
4. **Polish**: config for host/tag filtering, comment formatting, failure thresholds.
5. **Hosted dashboard**: only if there's real demand for the free tier first.

## Ground rules

- **No hands-on Ansible experience yet.** Before writing implementation code for any given Ansible behavior (especially check-mode quirks and which modules skip cleanly vs. noisily), verify it against a real test run against actual servers/VMs — don't guess. This matters more here than it would on a project with prior domain familiarity.
- **This project is secondary to Chuchote.** Pick it up once Chuchote has real progress, or if a genuine independent need for Ansible tooling comes up.
- **The "skipped tasks" trap is the whole point.** People assume no diff shown means no change — that's false, and silently mishandling this in the formatter defeats the tool's purpose. Treat correctness here as higher priority than breadth of features.
- **New feature requests**: check whether they make the free CLI formatter more correct/complete, or whether they're a hosted-tier idea getting pulled forward too early. Bias toward the former.
- **Stay in CLI/CI terms throughout.** The target audience (devops engineers) works in terminals and pipelines, not GUIs — don't build a GUI prematurely.
- **Re-check market fit periodically.** Before investing further, search for whether Ansible core, `ansible-lint`, or another community tool has shipped a proper visual/PR-friendly diff view since this space could close. Last checked 2026-07-03: space still open (nothing on PyPI or the GitHub Marketplace does check-mode previews with unpreviewable-task flagging).
- **Version drift guard.** Skip-message text and callback behavior vary across ansible-core versions. Any change to the callback plugin or classifier must pass `scripts/version_matrix.sh` (real runs on 2.15/2.17/2.19 via uv); CI runs the same matrix on every push. Never key classification on exact message text — the fail-safe is "any skip not attributable to a `when:` conditional gets flagged as not previewable" (real example: `raw` skips with no message at all).

## License / distribution (context, not implementation-relevant day to day)

License decision deferred as of 2026-07-03 (owner reconsidering MIT vs. alternatives for commercial reasons; repo currently declares no license, i.e. all rights reserved). Original plan was MIT open core — free CLI permissive, paid hosted dashboard closed-source. **A license must be chosen before any visibility push or PyPI publish**; unlicensed repos get no adoption. GitHub Sponsors for funding. Visibility push (r/devops, r/ansible, Ansible forums/Discord, Show HN) only once the CLI actually works well — no parallel marketing before that.

## When returning to this project in a new session

1. Confirm what step of the build order (above) is actually current — check repo state, don't assume.
2. If touching new Ansible behavior, verify against a real test run first.
3. Sanity-check any new feature ask against the "free CLI correctness vs. hosted-tier scope creep" rule above.
