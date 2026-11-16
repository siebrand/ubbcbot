#!/usr/bin/env bash
# Run the same static analysis checks as CI (.github/workflows/static-analysis.yml).
#
# Usage:
#   scripts/static-analysis.sh [check ...]
#
# Checks: ruff, format, mypy, bandit, audit, compile. With no arguments all run.
# Exit code is non-zero if any check fails.
set -u

cd "$(dirname "$0")/.." || exit 1

# Use ./test_env when no virtualenv is active, and keep it in sync with the pins.
if [ -z "${VIRTUAL_ENV:-}" ] && [ -d test_env/bin ]; then
  export PATH="$PWD/test_env/bin:$PATH"
fi
scripts/sync-venv.sh || echo "sync-venv failed; continuing with the installed tools"

PYTHON="${PYTHON:-python3}"
ALL_CHECKS=(ruff format mypy bandit audit compile)
CHECKS=("${@:-${ALL_CHECKS[@]}}")

missing=()
for tool in ruff mypy bandit pip-audit; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing tools: ${missing[*]}"
  echo "Install them with: pip install -r src/requirements.txt -r tests/requirements.txt"
  exit 2
fi

failed=()

run() {
  local name="$1"
  shift
  echo
  echo "==> $name: $*"
  if "$@"; then
    echo "OK   $name"
  else
    echo "FAIL $name"
    failed+=("$name")
  fi
}

for check in "${CHECKS[@]}"; do
  case "$check" in
    ruff) run ruff ruff check . ;;
    format) run format ruff format --check . ;;
    mypy) run mypy mypy src ;;
    bandit) run bandit bandit -q -r src -c pyproject.toml ;;
    audit) run audit pip-audit -r src/requirements.txt -r tests/requirements.txt --progress-spinner off ;;
    compile) run compile "$PYTHON" -m compileall -q src ;;
    *)
      echo "Unknown check: $check (valid: ${ALL_CHECKS[*]})"
      exit 2
      ;;
  esac
done

echo
if [ ${#failed[@]} -gt 0 ]; then
  echo "Failed: ${failed[*]}"
  exit 1
fi
echo "All checks passed."
