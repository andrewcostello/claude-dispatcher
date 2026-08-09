#!/usr/bin/env bash
# check_body_branch.sh <base> <branch> <role> [--tasks PATH --task-key KEY]
#
# Unit D1. P1 wrote this contract as a stub; P3 replaced the marked block at
# the bottom with the delegation described below. The contract is unchanged —
# only the stub's `exit 70` is gone.
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
#   Options (both or neither — half a row reference names no row):
#     --tasks PATH     a REPO-RELATIVE path to the worklist. The row is read
#                      out of <base>'s object store, never the working tree:
#                      an adjudicate row's `disputed_paths:` IS its writable
#                      set, so a branch that supplied its own row would widen
#                      its own gate by editing one line (invariant 6 again).
#     --task-key KEY   the row whose per-task facts are applied — its
#                      `immutable_paths:` addition, or, for an adjudicate
#                      branch, the `disputed_paths:` that ARE its writable
#                      set. Without them there is no per-task spec, which is
#                      right for the three deny-based roles and is exit 3 for
#                      adjudicate: the writable set lives on the row and the
#                      gate will not guess "nothing" or "anything".
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
#         the role's writable set was unavailable, the diff was empty, or —
#         when this checkout supplies the gate's own code — that code could not
#         be read out of <base> (see "provenance of the gate's own code" below,
#         the one answer this script gives without asking role_protocol).
#         FAILS CLOSED — callers must not treat 3 as a pass
#    64   usage error
#    70   not implemented. Reserved: the stub emitted it, nothing does now.
#         Kept in the table (and in role_protocol.ExitCode) so a caller that
#         still special-cases 70 keeps a defined meaning for it
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

# --- BEGIN delegation (P3) ---------------------------------------------------
# Everything below is plumbing. No rule is decided here: not the argument
# count, not the legal role words, not the exit codes, not one glob. All of
# that is role_protocol.main, so this script cannot answer differently from
# the orchestrator's post-implementer check or from a hand invocation
# (invariant 1). If you find yourself adding a `case` or an `if` that inspects
# "$@" below, that is the drift this file exists to prevent.

# The dispatcher's own `src/`, resolved from THIS SCRIPT's location — never
# from the cwd. The cwd is the checkout under judgement, and putting its `src`
# on the path would let the branch supply the code that judges it, which is
# invariant 6 by another route.
_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
_dispatcher_src="$(dirname -- "${_script_dir}")/src"

# --- provenance of the gate's own code (S1, 2026-08-09) ----------------------
#
# THE HOLE THE BASH_SOURCE RESOLUTION ABOVE DOES NOT CLOSE. Its comment is
# right that the cwd is not to be trusted, and wrong by omission: when this
# repository judges ITSELF — which is the shape CI has, and the shape every
# earlier seal lacked — the script is inside the checkout under judgement, so
# `BASH_SOURCE` resolves to a `src/` the branch wrote. Measured 2026-08-08: a
# branch that appended `FLOOR_GLOBS = ()` to its own `role_protocol.py` and
# dropped `**/.dispatcher.yaml` from the BODIES rule, then edited
# `.dispatcher.yaml`, was told `CLEAN … against the 0-glob floor`, exit 0, by
# this script. `-P` did not help: the branch did not need the cwd, it owned the
# library the wrapper pointed at.
#
# THE FIX. When the gate's own `src/` lies inside the tree under judgement, it
# is branch-supplied and is not used. The gate's code is taken instead from
# `<base>`'s git object store — the same protected base the branch is being
# measured against, and the same object store `.dispatcher.yaml` and the task
# row are already read from (design §8 / invariant 6, now applied to the code
# as well as to the policy). Nothing here compares the branch's copy to the
# base's: a comparison is a decision, and "differs" is the ordinary state of an
# honest branch that touched anything under `src/`. The base's copy is simply
# the one that runs, so a branch that rewrote the gate is judged by the real
# rules — under which rewriting the gate is itself a floor violation
# (`FLOOR_GLOBS`), reported as such, rather than a mystery.
#
# WHY THE ANCHOR HOLDS. `<base>` is a ref, and a commit on the branch cannot
# move a ref it is not on; CI fetches the base from the remote. An attacker who
# can move the protected base can merge anything anyway. Note what is NOT
# trusted here: not the working tree, not the index, not the branch's blobs —
# only objects reachable from `<base>`.
#
# WHY IT IS NOT SIMPLY ALWAYS DONE. The gate is also run against FOREIGN
# checkouts (see `test_the_ci_script_does_not_let_the_judged_checkout_supply_
# its_own_gate`, which points the real script at a repo that has no
# `claude_dispatcher` at all). There, the script's `src/` is outside the tree
# under judgement, nothing about it is branch-supplied, and `<base>` holds no
# gate to read. So the base-pinned path is entered on exactly one condition:
# the gate's code lives inside the tree it is judging.
#
# WHAT REMAINS OPEN, AND WHOSE OBLIGATION IT IS. This closes the LIBRARY, not
# the ENTRYPOINT. A branch that rewrites this file to `exit 0` owns the exit
# code, and no line written here survives the commit that deletes it — a
# self-check is deleted by the same edit it is meant to catch. The only fix is
# outside the tree: **the caller must invoke a copy of this script that the
# branch under judgement cannot write** (a pinned action, a separately fetched
# tool checkout, a container image), and must pass a `<base>` it controls. This
# repository tracks no CI configuration, so there is nowhere in-tree to pin
# that obligation; it is stated here and in the D1 report, not faked as a test.
# `scripts/check_body_branch.sh` is on `FLOOR_GLOBS`, so the rewrite is at
# least a VIOLATION whenever any trusted run reads the diff.
#
# THE ONE RULE THIS FILE DECIDES, AND WHY IT MUST. The block below can answer
# `3` (undetermined) without consulting `role_protocol`. That is the single
# exception to "no rule is decided here", and it is forced: the reason for the
# answer is that the module which owns the exit codes could not be trusted or
# could not be read, so it cannot be the thing that reports it. It fails CLOSED
# and never answers 0 or 2. It also reads `$1` as `<base>` — using the
# positional contract, not redefining it; a `$1` that is not a readable ref is
# 3, never a guess and never a delegation to code we just refused to trust.

_undetermined() {
  printf 'check_body_branch: %s\n' "$1" >&2
  printf 'check_body_branch: %s\n' \
    'UNDETERMINED is not a pass — the branch was not cleared' >&2
  exit 3
}

_judged_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
_gate_is_branch_supplied=0
if [ -n "${_judged_root}" ] && [ -d "${_dispatcher_src}" ]; then
  _judged_root="$(cd -- "${_judged_root}" && pwd -P)"
  _dispatcher_src="$(cd -- "${_dispatcher_src}" && pwd -P)"
  case "${_dispatcher_src}/" in
    "${_judged_root}"/*) _gate_is_branch_supplied=1 ;;
  esac
fi

if [ "${_gate_is_branch_supplied}" -eq 1 ]; then
  _base_ref="${1-}"
  if [ -z "${_base_ref}" ]; then
    _undetermined "this checkout supplies the gate that would judge it, and \
no <base> was given to read a trusted copy from. Nothing was checked."
  fi
  # Where the gate sits INSIDE the judged tree, so the same relative path can
  # be read out of <base>. Keeps the vendored layout working: a dispatcher at
  # `sub/project/` reads `<base>:sub/project/src`, not `<base>:src`.
  _src_rel="${_dispatcher_src#"${_judged_root}"/}"
  _trusted_root="$(mktemp -d 2>/dev/null)" \
    || _undetermined "cannot create a temporary directory to hold the \
gate's own code as <base> has it. Nothing was checked."
  trap 'rm -rf -- "${_trusted_root}"' EXIT
  # `ls-tree` + `cat-file`, not `git archive`: no tar dependency, and no
  # `.gitattributes` processing (`export-ignore` / `export-subst`) between the
  # object store and the bytes that get imported. `-z` because a path may
  # contain anything but NUL.
  if ! git ls-tree -r -z --name-only "${_base_ref}" -- "${_src_rel}" \
      > "${_trusted_root}/.listing" 2> "${_trusted_root}/.stderr"; then
    _undetermined "cannot list ${_src_rel} at ${_base_ref}, so the gate's \
own code could not be read from the protected base: \
$(tr '\n' ' ' < "${_trusted_root}/.stderr")"
  fi
  while IFS= read -r -d '' _blob_path; do
    mkdir -p -- "${_trusted_root}/$(dirname -- "${_blob_path}")" \
      || _undetermined "cannot lay out ${_blob_path} from ${_base_ref}"
    git cat-file blob "${_base_ref}:${_blob_path}" \
      > "${_trusted_root}/${_blob_path}" \
      || _undetermined "cannot read ${_base_ref}:${_blob_path}, so the \
gate's own code could not be read from the protected base"
  done < "${_trusted_root}/.listing"
  if [ ! -f "${_trusted_root}/${_src_rel}/claude_dispatcher/role_protocol.py" ]
  then
    _undetermined "${_base_ref} carries no \
${_src_rel}/claude_dispatcher/role_protocol.py, so there is no trusted gate \
to run and this checkout's own copy will not be used. Nothing was checked."
  fi
  _dispatcher_src="${_trusted_root}/${_src_rel}"
  printf 'check_body_branch: %s\n' \
    "the gate's own code lives inside the checkout under judgement; running \
${_src_rel} as ${_base_ref} has it, not as this branch wrote it" >&2
fi
# --- end provenance ----------------------------------------------------------

if [ -d "${_dispatcher_src}" ]; then
  PYTHONPATH="${_dispatcher_src}${PYTHONPATH:+:${PYTHONPATH}}"
  export PYTHONPATH
fi

# `-P` (and PYTHONSAFEPATH, its env twin) stops Python prepending the cwd to
# `sys.path`. Without it the BASH_SOURCE resolution above buys NOTHING: for
# `python -m pkg.mod`, `sys.path[0]` is the cwd and PYTHONPATH entries come
# AFTER it, so the checkout under judgement wins the import. A bodies branch
# that commits a top-level `claude_dispatcher/role_protocol.py` whose `main`
# returns 0 is then judged by its own gate — verified exploitable against this
# script before this line existed (P4, 2026-08-07): the planted gate printed
# "everything is fine" and exited 0 while the same branch added a file under
# `tests/`. Sealed by
# `test_the_ci_script_does_not_let_the_judged_checkout_supply_its_own_gate`.
# Both spellings are set: `-P` is the flag, PYTHONSAFEPATH covers a $PYTHON
# that is a wrapper swallowing argv flags. Requires CPython >= 3.11, which
# `pyproject.toml` already floors.
export PYTHONSAFEPATH=1
# Not `exec`: the EXIT trap above has to run, or a base-pinned invocation leaks
# the temporary tree holding the gate's own code. The exit code is passed
# through unchanged, which is the only thing `exec` was buying.
_rc=0
"${PYTHON:-python3}" -P -m claude_dispatcher.role_protocol "$@" || _rc=$?
exit "${_rc}"
# --- END delegation ----------------------------------------------------------
