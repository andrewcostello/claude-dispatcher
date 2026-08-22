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
echo "test.sh: interpreter $PY ($("$PY" --version 2>&1))"

# Known-red register (D-68). The dispatcher exports DISPATCHER_KNOWN_RED_FILE
# pointing at NEWLINE-separated pytest node ids — rows another unit's seals task
# committed RED by design, which this task has no way to green and must not be
# failed by. Empty or unset on almost every run, and then the pytest command
# below is byte-identical to what it was before the register existed.
#
# `IFS= read -r` preserves a row verbatim, which is what keeps a PARAMETRISED id
# intact: ids routinely contain spaces (`test_seal[a plain property]`) and any
# split on the default IFS would tear one row into several arguments that
# deselect nothing.
set --
if [ -n "${DISPATCHER_KNOWN_RED_FILE:-}" ] && [ -f "${DISPATCHER_KNOWN_RED_FILE}" ]; then
  while IFS= read -r row; do
    [ -n "$row" ] && set -- "$@" --deselect "$row"
  done < "${DISPATCHER_KNOWN_RED_FILE}"
  echo "test.sh: known-red register active ($(( $# / 2 )) row(s) deselected)" >&2
fi

PYTHONPATH=src "$PY" -m pytest tests/ -q --tb=line "$@"

probe_out="$("$PY" tools/t26_lint.py --probe-peer 2>&1)" && probe_rc=0 || probe_rc=$?
if [ "$probe_rc" = 0 ]; then
  "$PY" tools/t26_lint.py
elif [ "$probe_rc" != 1 ]; then
  # exit 1 means "peer absent"; anything else is the probe itself failing,
  # which must not be reported to the operator as a missing checkout.
  echo "test.sh: --probe-peer failed (exit $probe_rc): $probe_out" >&2
  exit "$probe_rc"
else
  # --probe-peer exits 1 for exactly one reason: the peer is unresolvable.
  echo "test.sh: claude-workflow peer checkout absent — running t26_lint in" \
       "degraded mode (doc-local checks only; set CLAUDE_WORKFLOW_REPO for" \
       "the full check). CI's citations job covers the other arm." >&2
  "$PY" tools/t26_lint.py --no-citations
fi
