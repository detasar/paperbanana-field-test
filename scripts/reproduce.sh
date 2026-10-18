#!/usr/bin/env bash
# Re-run the field test for all papers in inputs/ (or the ones named).
# Expected cost with the defaults: about USD 1.50-1.60 and 10 minutes per paper.
#
# Usage: scripts/reproduce.sh [paper-name ...]
# Requires OPENAI_API_KEY in your shell and a prior run of scripts/setup.sh.
# Extra options for run_paperbanana.py can be passed via RUNNER_ARGS, e.g.
#   RUNNER_ARGS="--candidates 2" scripts/reproduce.sh qcp-multioutput-conformal
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"
UPSTREAM_DIR="${UPSTREAM_DIR:-${REPO_ROOT}/upstream/PaperBanana}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/runs}"
read -r -a extra_args <<< "${RUNNER_ARGS:-}"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "error: set OPENAI_API_KEY in your shell first." >&2
  exit 2
fi
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "error: virtual environment not found; run scripts/setup.sh first." >&2
  exit 2
fi

if [[ $# -gt 0 ]]; then
  papers=("$@")
else
  papers=()
  for dir in "${REPO_ROOT}"/inputs/*/; do
    papers+=("$(basename "${dir}")")
  done
fi

for paper in "${papers[@]}"; do
  input_dir="${REPO_ROOT}/inputs/${paper}"
  if [[ ! -f "${input_dir}/method.txt" ]]; then
    echo "error: no inputs for '${paper}' in ${REPO_ROOT}/inputs" >&2
    exit 2
  fi
  echo ">>> ${paper}"
  "${VENV_DIR}/bin/python" "${REPO_ROOT}/run_paperbanana.py" \
    --name "${paper}" \
    --method-file "${input_dir}/method.txt" \
    --caption-file "${input_dir}/caption.txt" \
    --out-dir "${OUTPUT_ROOT}/${paper}" \
    --upstream-dir "${UPSTREAM_DIR}" \
    ${extra_args[@]+"${extra_args[@]}"}
done
