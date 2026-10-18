#!/usr/bin/env bash
# Clone PaperBanana at the pinned commit, create a virtual environment and
# download the PaperBananaBench reference set (~240 MB) used by the Retriever.
#
# Usage: scripts/setup.sh
# Environment overrides:
#   PYTHON           Python interpreter used to create the venv (default: python3)
#   UPSTREAM_DIR     Checkout location (default: <repo>/upstream/PaperBanana)
#   VENV_DIR         Virtual environment location (default: <repo>/.venv)
set -euo pipefail

readonly UPSTREAM_URL="https://github.com/dwzhu-pku/PaperBanana.git"
readonly UPSTREAM_COMMIT="491fa29b950cb6befbbd611133cf5cd5e0cb4dd3"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
UPSTREAM_DIR="${UPSTREAM_DIR:-${REPO_ROOT}/upstream/PaperBanana}"
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"

if [[ ! -d "${UPSTREAM_DIR}/.git" ]]; then
  echo "Cloning ${UPSTREAM_URL} into ${UPSTREAM_DIR}"
  git clone --quiet "${UPSTREAM_URL}" "${UPSTREAM_DIR}"
fi
git -C "${UPSTREAM_DIR}" fetch --quiet origin "${UPSTREAM_COMMIT}" || true
git -C "${UPSTREAM_DIR}" -c advice.detachedHead=false checkout --quiet "${UPSTREAM_COMMIT}"
echo "PaperBanana pinned at ${UPSTREAM_COMMIT}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Creating virtual environment in ${VENV_DIR}"
  "${PYTHON}" -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${UPSTREAM_DIR}/requirements.txt"

if [[ ! -f "${UPSTREAM_DIR}/data/PaperBananaBench/diagram/ref.json" ]]; then
  echo "Downloading PaperBananaBench (diagram split)"
  (cd "${UPSTREAM_DIR}" && "${VENV_DIR}/bin/python" scripts/prepare_bench.py --tasks diagram)
fi
echo "Setup complete."
