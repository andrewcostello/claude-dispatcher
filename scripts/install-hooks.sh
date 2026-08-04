#!/usr/bin/env bash
# Install the repo-local pre-push hook. Git hooks are not versioned, so this
# is opt-in per clone — run it once:
#
#     bash scripts/install-hooks.sh
#
# The hook runs `make verify` (boundary seals + the citations-REQUIRED T26
# lint). PR0's comments call `make verify` the pre-push gate; before this
# script existed there was no mechanism behind that claim (panel round 3).
set -e
ROOT="$(git rev-parse --show-toplevel)"
# git rev-parse --git-path resolves the real hooks directory for BOTH a
# main clone and a linked worktree (where .git is a FILE, not a directory —
# the same layout t26_lint handles for peer detection).
HOOK="$(git rev-parse --git-path hooks/pre-push)"
mkdir -p "$(dirname "$HOOK")"

cat > "$HOOK" <<'HOOK_BODY'
#!/usr/bin/env bash
# Installed by scripts/install-hooks.sh — PR0's pre-push gate.
set -e
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
echo "pre-push: make verify (boundary seals + T26 with citations required)"
if ! make verify; then
  echo "pre-push: BLOCKED — 'make verify' failed. Fix, or push with" \
       "--no-verify if you have a reason and will say what it is." >&2
  exit 1
fi
HOOK_BODY

chmod +x "$HOOK"
echo "installed: $HOOK"
echo "it runs 'make verify'; bypass with 'git push --no-verify'"
