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
if [ -n "${DISPATCHER_TEST_PYTHON:-}" ]; then
  # An explicit override is intent: if it is unusable, say so loudly rather
  # than silently falling through to a different interpreter.
  if [ -x "${DISPATCHER_TEST_PYTHON}" ]; then
    echo "${DISPATCHER_TEST_PYTHON}"
  else
    echo "python.sh: DISPATCHER_TEST_PYTHON='${DISPATCHER_TEST_PYTHON}' is not" \
         "executable — refusing to silently use a different interpreter" >&2
    exit 1
  fi
elif [ -x "$ROOT/.venv/bin/python" ]; then
  echo "$ROOT/.venv/bin/python"
else
  echo python3
fi
