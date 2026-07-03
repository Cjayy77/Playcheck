#!/usr/bin/env bash
# Version-drift guard: run the real testdata playbook through playcheck's
# callback on several ansible-core versions, then re-run the parser test
# suite against each fresh capture. Requires uv (https://docs.astral.sh/uv/).
#
# Usage: scripts/version_matrix.sh [core:python ...]
# Default matrix covers oldest-commonly-deployed through current.
set -euo pipefail
cd "$(dirname "$0")/.."

MATRIX=("$@")
[ ${#MATRIX[@]} -eq 0 ] && MATRIX=(2.15:3.11 2.17:3.12 2.19:3.13)
UV="${UV:-uv}"
FAILED=()

for pair in "${MATRIX[@]}"; do
  core="${pair%%:*}"; py="${pair##*:}"
  venv="/tmp/pcx-venv-${core}"
  capture="/tmp/pcx-capture-${core}.jsonl"
  echo "=== ansible-core ${core} (python ${py}) ==="
  "$UV" venv --clear --python "$py" "$venv" >/dev/null
  "$UV" pip install --python "$venv/bin/python" --quiet "ansible-core==${core}.*"
  "$venv/bin/ansible-playbook" --version | head -1

  if ANSIBLE_STDOUT_CALLBACK=playcheck_jsonl \
     ANSIBLE_CALLBACK_PLUGINS=src/playcheck/_ansible/callback_plugins \
     "$venv/bin/ansible-playbook" testdata/site.yml -i testdata/inventory.ini \
       --check --diff > "$capture" 2>"/tmp/pcx-stderr-${core}.txt" \
     && PLAYCHECK_FIXTURE="$capture" PYTHONPATH=src python3 -m pytest tests/ -q; then
    echo "--- ${core}: OK"
  else
    echo "--- ${core}: FAILED (stderr follows)"
    cat "/tmp/pcx-stderr-${core}.txt" || true
    FAILED+=("$core")
  fi
done

if [ ${#FAILED[@]} -gt 0 ]; then
  echo "FAILED versions: ${FAILED[*]}"
  exit 1
fi
echo "All versions passed."
