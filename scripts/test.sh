#!/usr/bin/env bash
# The ONE mechanical test gate — invoked by BOTH .dispatcher.yaml's test:
# command and `make test`, so the two definitions cannot drift (PR0 panel
# finding). Exit 0 = green.
#
# Interpreter resolution: main-checkout .venv preferred; worktrees share the
# git root metadata but usually lack their own .venv, so we honour
# DISPATCHER_TEST_PYTHON and fall back to python3.
set -e
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
if [ -n "${DISPATCHER_TEST_PYTHON:-}" ] && [ -x "${DISPATCHER_TEST_PYTHON}" ]; then
  PY="${DISPATCHER_TEST_PYTHON}"
elif [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
elif [ -x /Users/andrewcostello/Projects/claude-dispatcher/.venv/bin/python ]; then
  PY=/Users/andrewcostello/Projects/claude-dispatcher/.venv/bin/python
elif [ -x /home/andrew/Project/claude-dispatcher/.venv/bin/python ]; then
  PY=/home/andrew/Project/claude-dispatcher/.venv/bin/python
else
  PY=python3
fi

PYTHONPATH=src "$PY" -m pytest tests/ -q --tb=line

# The design doc's own lint (T26). The citation half needs the
# claude-workflow peer checkout; a dispatched-task worktree may not have one
# (container layout mounts under /worktrees), so the doc-local checks always
# run and the citation check runs whenever the peer is resolvable. The FULL
# check (citations required) is `make verify-t26` / CI.
if [ -n "${CLAUDE_WORKFLOW_REPO:-}" ] || [ -d "$ROOT/../claude-workflow/.git" ]; then
  "$PY" tools/t26_lint.py
else
  echo "test.sh: claude-workflow peer checkout absent — t26_lint runs doc-local checks only"
  "$PY" tools/t26_lint.py --no-citations
fi
