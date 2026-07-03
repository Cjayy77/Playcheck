# Internal stdout callback used by playcheck. Emits one JSON object per line
# so the playcheck CLI can parse results without scraping human output.
from __future__ import annotations

import json
import sys

from ansible.plugins.callback import CallbackBase

DOCUMENTATION = """
    name: playcheck_jsonl
    type: stdout
    short_description: JSON Lines output for playcheck
    version_added: "2.9"
    description:
        - Internal callback plugin for the playcheck CLI.
        - Emits one JSON object per event on stdout.
"""


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "stdout"
    CALLBACK_NAME = "playcheck_jsonl"

    def _emit(self, obj):
        sys.stdout.write(json.dumps(obj, default=str) + "\n")
        sys.stdout.flush()

    # -- playbook structure ------------------------------------------------

    def v2_playbook_on_play_start(self, play):
        self._emit({"event": "play_start", "play": play.get_name().strip()})

    def v2_playbook_on_task_start(self, task, is_conditional):
        self._emit(
            {
                "event": "task_start",
                "task": task.get_name().strip(),
                "action": task.action,
                "uuid": task._uuid,
            }
        )

    def v2_playbook_on_handler_task_start(self, task):
        self._emit(
            {
                "event": "task_start",
                "task": task.get_name().strip(),
                "action": task.action,
                "uuid": task._uuid,
                "is_handler": True,
            }
        )

    def v2_playbook_on_no_hosts_matched(self):
        self._emit({"event": "no_hosts_matched"})

    def v2_playbook_on_stats(self, stats):
        hosts = sorted(stats.processed.keys())
        self._emit(
            {"event": "stats", "stats": {h: stats.summarize(h) for h in hosts}}
        )

    # -- per-host results ---------------------------------------------------

    def _result_fields(self, result):
        # result._result has already had no_log censoring applied by the
        # TaskExecutor before it reaches callbacks; keep only what we need.
        r = result._result
        task = result._task
        fields = {
            "host": result._host.get_name(),
            "task": task.get_name().strip(),
            "action": task.action,
            "uuid": task._uuid,
            "changed": bool(r.get("changed", False)),
            "censored": "censored" in r,
            "diff_disabled": task.diff is False,
            "check_mode_bypassed": task.check_mode is False,
        }
        for key in ("msg", "skip_reason", "skipped", "diff", "results"):
            if key in r:
                fields[key] = r[key]
        return fields

    def _emit_result(self, status, result, **extra):
        fields = self._result_fields(result)
        fields.update(extra)
        fields["event"] = "result"
        fields["status"] = status
        self._emit(fields)

    def v2_runner_on_ok(self, result):
        self._emit_result("changed" if result.is_changed() else "ok", result)

    def v2_runner_on_skipped(self, result):
        self._emit_result("skipped", result)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self._emit_result("failed", result, ignore_errors=ignore_errors)

    def v2_runner_on_unreachable(self, result):
        self._emit_result("unreachable", result)

    def v2_runner_item_on_ok(self, result):
        self._emit_result(
            "item_changed" if result.is_changed() else "item_ok", result
        )

    def v2_runner_item_on_skipped(self, result):
        self._emit_result("item_skipped", result)

    def v2_runner_item_on_failed(self, result):
        self._emit_result("item_failed", result)
