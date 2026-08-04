#!/usr/bin/env bash
# check_body_branch.sh <base> <branch> <role>
#
# STUB (unit D1, phase P1). Exits non-zero with a not-implemented message.
# P3 replaces the marked block with the delegation described below.
#
# WHAT IT IS FOR
# The build protocol (implementation-plan §2a) gives each phase of a unit a
# role, and each role a set of paths that are not its to touch: bodies may not
# edit the seals that judge them, seals may not edit the implementation they
# seal. Self-reporting that ("I didn't touch tests/") is exactly the honour
# system that produced 24 vacuous seals, so the rule is checked mechanically
# against the branch's actual diff.
#
# This is the SECOND of two independent enforcement points. The first is
# plan-time (role_protocol.validate, via plan.load_tasks): it refuses an
# illegal worklist before any agent runs. This one refuses an illegal diff.
# Both exist because a check that only fires at PR time has already let a whole
# build cycle burn.
#
# CONTRACT
#   Arguments (all three required, positional):
#     base    a git ref — the protected base the branch is measured against
#     branch  a git ref — the branch under judgement
#     role    one of: scaffold | seals | bodies | adjudicate
#             ("legacy" is NOT accepted: a role-less task has no immutable
#             paths, and accepting the word here would let a caller disable
#             the gate by passing it.)
#
#   Runs in the checkout to be judged (cwd = repo root), as CI does.
#
#   Exit codes — distinct per outcome, because a CI job that cannot tell
#   "violation" from "could not check" will treat one as the other:
#     0   clean: the diff was read, was non-empty, and every changed path is
#         this role's to touch (and, for bodies, no scaffolded signature
#         changed)
#     2   violation: at least one forbidden path or changed signature. Every
#         one is printed with the glob that forbade it and that rule's
#         rationale
#     3   undetermined: the diff or the base-pinned policy could not be read,
#         the role's writable set was unavailable, or the diff was empty.
#         FAILS CLOSED — callers must not treat 3 as a pass
#    64   usage error
#    70   not implemented (this stub)
#
#   The policy is read from `.dispatcher.yaml` in <base>'s object store, never
#   from the working tree: a branch may not supply the policy that judges it
#   (design §8 / invariant 6).
#
# P3: replace the block below with a delegation to the single Python
# entrypoint — role_protocol.check_branch via its CLI face — so that this
# script, the orchestrator's post-implementer check and CI cannot disagree
# (invariant 1). Something of the shape:
#
#     exec "${PYTHON:-python3}" -m claude_dispatcher.role_protocol "$@"
#
# with PYTHONPATH=src when the package is not installed. Do NOT reimplement
# the path matching in bash: the glob semantics live in risk.py and the rule
# table in role_protocol.py, and a bash second opinion would drift from both.

set -euo pipefail

# --- BEGIN not-implemented stub (P3 replaces this block) ---------------------
echo "check_body_branch.sh: NOT IMPLEMENTED (unit D1 phase P3 fills it)." >&2
echo "  Called with: ${*:-<no arguments>}" >&2
echo "  Until it lands, a role's immutable paths are enforced only at plan" >&2
echo "  time (role_protocol.validate); a branch's diff is NOT checked, so do" >&2
echo "  not report this as a pass." >&2
exit 70
# --- END not-implemented stub ------------------------------------------------
