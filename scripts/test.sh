#!/usr/bin/env bash
# The ONE mechanical test gate — invoked by BOTH .dispatcher.yaml's test:
# command and `make test`, so the two definitions cannot drift. Exit 0 = green.
#
# Interpreter: scripts/python.sh (the single resolution ladder — no
# per-developer absolute paths; export DISPATCHER_TEST_PYTHON to override).
# Environment matrix for the T26 doc lint:
#   peer checkout present  → full checks, citations REQUIRED
#   peer checkout absent   → degraded: every doc-local check still enforced,
#                            citations skipped with a loud stderr notice;
#                            NEVER a hard failure on peer absence alone.
# The predicate is t26_lint's own --probe-peer, so the shell, the lint and
# the pytest seal cannot disagree about which environment this is.
set -e
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
PY="$(bash scripts/python.sh)"

PYTHONPATH=src "$PY" -m pytest tests/ -q --tb=line

if "$PY" tools/t26_lint.py --probe-peer >/dev/null 2>&1; then
  "$PY" tools/t26_lint.py
else
  echo "test.sh: claude-workflow peer checkout absent — running t26_lint in" \
       "degraded mode (doc-local checks only; set CLAUDE_WORKFLOW_REPO for" \
       "the full check)" >&2
  "$PY" tools/t26_lint.py --no-citations
fi
