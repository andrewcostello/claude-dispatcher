#!/usr/bin/env bash
# verify_agy_pipe.sh — smoke test for the agy (Antigravity CLI) --print path.
#
# WHY THIS EXISTS
#   antigravity-cli#76: `agy --print` can silently drop its response when
#   stdout is a non-TTY pipe — which is exactly how the cross-family reviewer
#   panel consumes it (subprocess.run with capture_output). If the bug is live
#   on this machine's agy build, the Gemini-family reviewer would return
#   nothing useful. This script reproduces the panel's invocation shape
#   (prompt on stdin, `--print ""`, stdout redirected to a pipe/file) and
#   asserts the output is non-empty.
#
# USAGE
#   tools/verify_agy_pipe.sh
#
# EXIT CODES
#   0  PASS — agy produced non-empty stdout over a non-TTY pipe.
#   1  FAIL — empty stdout (suspected antigravity-cli#76) or non-zero exit.
#   2  SKIP — agy binary not found on PATH (cannot run the check).
#
# Runnable standalone and from CI-ish checks. No arguments.

# `set -u` (unset-var guard) + `pipefail` (so $? reflects agy, the last
# pipeline element). Deliberately NOT `set -e`: agy's non-zero exit is a
# FAIL we report ourselves with exit 1 — `set -e` would abort before the
# RC capture and leak agy's raw exit code, breaking the 0/1/2 contract.
set -u
set -o pipefail

AGY_BIN="${AGY_BIN:-agy}"
PRINT_TIMEOUT="${AGY_PRINT_TIMEOUT:-60s}"
# A trivial, deterministic prompt. We only assert non-empty output, not the
# exact text — models vary — but the instruction nudges toward a short reply.
PROMPT='Reply with exactly the single word: PONG'

pass() { echo "PASS: $*"; exit 0; }
fail() { echo "FAIL: $*"; exit 1; }
skip() { echo "SKIP: $*"; exit 2; }

if ! command -v "$AGY_BIN" >/dev/null 2>&1; then
  skip "agy binary not found on PATH (set AGY_BIN to override)"
fi

AGY_VERSION="$("$AGY_BIN" --version 2>/dev/null | head -1 || true)"
echo "agy binary:  $(command -v "$AGY_BIN")"
echo "agy version: ${AGY_VERSION:-unknown}"

# Capture stdout to a file. Redirecting to a file (not a terminal) is the
# non-TTY condition that triggers antigravity-cli#76; it mirrors how
# subprocess.run captures the reviewer's output.
OUT_FILE="$(mktemp -t agy_pipe_smoke.XXXXXX)" || fail "mktemp failed (no writable tmpdir?)"
ERR_FILE="$(mktemp -t agy_pipe_smoke_err.XXXXXX)" || { rm -f "$OUT_FILE"; fail "mktemp failed (no writable tmpdir?)"; }
trap 'rm -f "$OUT_FILE" "$ERR_FILE"' EXIT

printf '%s' "$PROMPT" | "$AGY_BIN" --print "" --print-timeout "$PRINT_TIMEOUT" \
  >"$OUT_FILE" 2>"$ERR_FILE"
RC=$?

BYTES=$(wc -c <"$OUT_FILE" | tr -d ' ')
# Strip whitespace to decide "empty" the same way the adapter does.
CONTENT="$(tr -d '[:space:]' <"$OUT_FILE")"

echo "exit code:   $RC"
echo "stdout bytes: $BYTES"

if [ "$RC" -ne 0 ]; then
  echo "--- stderr (tail) ---"
  tail -5 "$ERR_FILE" >&2 || true
  fail "agy exited non-zero ($RC) over a pipe"
fi

if [ -z "$CONTENT" ]; then
  fail "empty stdout with exit 0 (suspected antigravity-cli#76) — agy dropped its response over a non-TTY pipe"
fi

echo "--- stdout (first line) ---"
head -1 "$OUT_FILE"
pass "agy produced non-empty stdout (${BYTES} bytes) over a non-TTY pipe"
