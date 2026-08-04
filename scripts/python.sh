#!/usr/bin/env bash
# THE interpreter-resolution definition. Every caller — scripts/test.sh, the
# Makefile, .dispatcher.yaml — sources this one ladder, so no two of them can
# drift (panel round 2).
#
# Order: DISPATCHER_TEST_PYTHON (explicit override, e.g. hosts whose main
# checkout is elsewhere) → the repo's own .venv → python3. Worktrees share
# the git root metadata but usually lack their own .venv, which is why the
# override exists and why there are no per-developer absolute paths here.
set -e
ROOT="$(git rev-parse --show-toplevel)"
if [ -n "${DISPATCHER_TEST_PYTHON:-}" ] && [ -x "${DISPATCHER_TEST_PYTHON}" ]; then
  echo "${DISPATCHER_TEST_PYTHON}"
elif [ -x "$ROOT/.venv/bin/python" ]; then
  echo "$ROOT/.venv/bin/python"
else
  echo python3
fi
