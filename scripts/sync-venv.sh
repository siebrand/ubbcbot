#!/usr/bin/env bash
# Bring the local virtualenv in line with the pinned requirements.
#
# Used by scripts/static-analysis.sh (before every run) and by the pre-commit
# post-merge / post-rewrite hooks (after git pull, merge, rebase), so a merged
# Dependabot PR reaches the venv without a manual pip install.
#
# Venv selection: the active one ($VIRTUAL_ENV), else ./test_env. If neither
# exists the script does nothing, so it never touches the system Python.
# Set SKIP_VENV_SYNC=1 to disable.
set -eu

cd "$(dirname "$0")/.."

[ "${SKIP_VENV_SYNC:-0}" = "1" ] && exit 0

if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/pip" ]; then
  PIP="$VIRTUAL_ENV/bin/pip"
elif [ -x test_env/bin/pip ]; then
  PIP="test_env/bin/pip"
else
  echo "sync-venv: no virtualenv found (activate one or create test_env); skipping"
  exit 0
fi

REQS=(-r src/requirements.txt -r tests/requirements.txt)

# A dry run is quick when everything is already satisfied and prints
# "Would install ..." when a pin changed.
if "$PIP" install --dry-run --disable-pip-version-check "${REQS[@]}" 2>/dev/null | grep -q "Would install"; then
  echo "sync-venv: requirements changed, updating $(dirname "$(dirname "$PIP")")"
  "$PIP" install --disable-pip-version-check --quiet "${REQS[@]}"
else
  echo "sync-venv: virtualenv is up to date"
fi
