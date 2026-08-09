"""D1 seals (P2, self-authorization wave): the gate's own provenance.

Why this file exists
--------------------
D1 is the unit built to remove one defect class: *a gate whose authorization is
writable by the thing it gates*. A five-seat panel found three more instances
**inside D1 itself**, which makes six in this effort after `risk.py`'s
config-defined floors, ADJUDICATE's self-widening (sealed in
`test_role_protocol_floor.py`) and the genesis actor allowlist.

  * **S1 — the judged branch supplies its own judge.** An earlier fix closed the
    *cwd* vector with `-P` / `PYTHONSAFEPATH=1`, and its comment correctly
    explains why the cwd is unsafe. It does not notice that
    `scripts/check_body_branch.sh` resolves `src/` from `BASH_SOURCE` — and the
    script itself lives in the checkout under judgement. So in CI the branch
    supplies BOTH the entrypoint and the library that judges it.
  * **S2 — the entrypoint is off the floor.** `scripts/check_body_branch.sh` is
    on no role's deny list and on no floor glob, so every role may edit the
    script that judges it.
  * **S3 — the floor protects the config file but not the code.**
    `.dispatcher.yaml` is on `FLOOR_GLOBS`; `src/claude_dispatcher/
    role_protocol.py`, which *implements* every rule the config merely tunes,
    is not.
  * **S4 — SCAFFOLD may rewrite the machine-read reviewer/verifier prompts.**
    SEALS and BODIES are denied `**/roles/*.md`, `**/reviewer_prompts/**` and
    `**/verifier_prompts/**`. SCAFFOLD is denied none of them, and `src/**` is
    the one tree SCAFFOLD exists to write in — which is where both prompt
    directories live.

What each seal pins, and what it does not
-----------------------------------------
The fixer chooses the mechanism. These seals pin the observable consequence, so
that a *different* mechanism than the one the author imagined still satisfies
them. In particular nothing here asserts the presence of `-P`, of a digest, of a
particular floor glob string, or of a particular rationale text. See the S1
section header for the explicit statement of what its seals can and cannot
detect — it is the one place where the limit is interesting.

Vacuity discipline
------------------
The P4 lesson from this unit is obeyed literally: **a seal parametrized over a
comprehension across the constant it pins is vacuous**, because deleting an
entry from the constant deletes the test row instead of reddening it (18 of 28
such rows caught nothing on a sibling unit). Every table below is written out by
hand and the live constants are checked *against* the written list, never
derived from it.

Every refusal row is paired with a control that must STAY green, so "refuse
everything" cannot satisfy this file:

  * S1: `test_the_gate_still_clears_an_untampered_legal_branch_from_either_entrypoint`
  * S2/S3: `_STILL_WRITABLE_ROWS`
  * S4: `test_scaffold_still_writes_everything_that_is_not_a_machine_read_instruction`

and the S1 seals additionally use the strongest control shape available here —
the **same tree judged twice**, once from a trusted entrypoint and once from the
branch's own, so the seal proves the *difference* rather than an absolute.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import cross_family_reviewer, verifier as verifier_mod
from claude_dispatcher.role_protocol import (
    FLOOR_RATIONALE,
    DiffVerdict,
    ExitCode,
    PolicySource,
    Role,
    RolePolicy,
    RoleRule,
    RuleKind,
    TaskRoleSpec,
    built_in_policy,
    check_branch,
    first_matching_glob,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The gate's two halves, as git spells them. Written out; nothing here reads
#: them off `FLOOR_GLOBS`.
GATE_ENTRYPOINT = "scripts/check_body_branch.sh"
GATE_LIBRARY = "src/claude_dispatcher/role_protocol.py"


# --------------------------------------------------------------------------- #
# S1 — the judged branch supplies its own judge
#
# WHAT THESE SEALS CAN DETECT
#   That a branch which rewrites the gate's own code and then commits a change
#   the real gate forbids does NOT get exit 0 out of the entrypoint that ships
#   inside that same branch. Two attack shapes on the LIBRARY are exercised: a
#   wholesale replacement of `role_protocol.py` with a `main` that returns 0,
#   and a DATA edit (drop one glob from the BODIES rule, empty `FLOOR_GLOBS`)
#   that leaves every signature intact and every other rule working.
#
# WHAT THESE SEALS CANNOT DETECT
#   * The third attack shape — the branch rewriting the SHELL SCRIPT itself to
#     `exit 0` — is measured but deliberately NOT asserted against the
#     in-checkout invocation, because no change to this repository could make
#     that assertion pass: if CI executes a file the branch owns, the branch
#     owns the exit code, and a self-check written in the script is deleted by
#     the same commit. This repository tracks no CI configuration (measured:
#     `git ls-files` matches no workflow, Makefile or pipeline definition), so
#     there is nothing in-tree to seal the caller's obligation against. What is
#     sealed instead is that the edit is a VIOLATION when a trusted run reads
#     the diff — see
#     `test_rewriting_the_entrypoint_is_itself_refused_by_a_trusted_run`.
#   * They cannot check "the gate ran trusted code" from the inside. A test that
#     runs from this checkout cannot bootstrap a trusted oracle for this
#     checkout, so no assertion here inspects what the gate imported.
#   * They therefore cannot distinguish a PRECISE fix (verify provenance, then
#     judge) from a BLUNT one (refuse to run at all when the entrypoint lives in
#     the tree under judgement, forcing CI to invoke a trusted copy). Both make
#     the attack rows green. That is deliberate — the blunt fix is one of the
#     shapes the ruling names — and it is why the in-checkout arm of every seal
#     accepts UNDETERMINED (3) but never OK (0).
#   * They cannot detect a fix that is defeated by an attacker who ALSO forges
#     whatever the fix checks (a digest committed on the branch, a pin the
#     branch can edit). A fix whose anchor is writable by the branch would pass
#     every row here. Anchoring the check in the protected base is the fixer's
#     obligation and is not observable from a single checkout.
#   * `_ci_checkout_template` copies the repo's tracked files but SKIPS
#     symlinks, so `.claude/workflow` (a tracked symlink into a sibling repo) is
#     absent from the fixture checkouts. No seal depends on it.
# --------------------------------------------------------------------------- #


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, timeout=60
    )


@pytest.fixture(scope="session")
def ci_checkout_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A one-commit git repo holding a copy of this repo's tracked files.

    This is the shape CI actually has and the shape every seal in this unit has
    so far lacked: a checkout that contains BOTH `scripts/check_body_branch.sh`
    and `src/claude_dispatcher/`. The existing gate-evasion seal
    (`test_role_protocol_diff.py::test_the_ci_script_does_not_let_the_judged_
    checkout_supply_its_own_gate`) runs the REAL repo's script against a tiny
    foreign checkout, so the script's own directory is outside the tree under
    judgement — which is exactly the configuration in which the S1 hole is
    invisible.

    Session-scoped and cloned per test (`git clone --local` is ~20ms), so the
    copy is paid once.
    """
    template = tmp_path_factory.mktemp("ci-checkout-template") / "repo"
    template.mkdir()
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    ).stdout
    copied = 0
    for rel in listing.split("\0"):
        if not rel:
            continue
        src = REPO_ROOT / rel
        # Symlinks (`.claude/workflow`) point outside the repo and would dangle.
        if src.is_symlink() or not src.is_file():
            continue
        dst = template / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    assert (template / GATE_ENTRYPOINT).is_file(), "the fixture has no gate script"
    assert (template / GATE_LIBRARY).is_file(), "the fixture has no gate library"
    assert copied > 50, f"the fixture copied only {copied} files; it is not a repo"

    _git(["init", "-q", "-b", "main", "."], template)
    _git(["config", "user.email", "seal@example.invalid"], template)
    _git(["config", "user.name", "D1 seal"], template)
    _git(["add", "-A"], template)
    _git(["commit", "-q", "-m", "base: the protected checkout"], template)
    return template


def _checkout(template: Path, tmp_path: Path) -> Path:
    """A fresh clone of the template, on `main`, ready to branch."""
    dst = tmp_path / "checkout"
    subprocess.run(
        ["git", "clone", "-q", "--local", str(template), str(dst)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    _git(["config", "user.email", "branch@example.invalid"], dst)
    _git(["config", "user.name", "the branch"], dst)
    _git(["checkout", "-q", "-b", "feat/x"], dst)
    return dst


def _commit(checkout: Path, message: str) -> None:
    _git(["add", "-A"], checkout)
    _git(["commit", "-q", "-m", message], checkout)


def _run_gate(script: Path, checkout: Path) -> subprocess.CompletedProcess:
    """Invoke the gate for `feat/x` with cwd = the checkout, as CI does.

    `PYTHONPATH` is stripped: the question is precisely which `src/` the wrapper
    puts on the path by itself, and handing it the real one would answer that
    question for it.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHON"] = sys.executable
    return subprocess.run(
        ["bash", str(script), "main", "feat/x", "bodies"],
        cwd=str(checkout),
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


def _trusted_script() -> Path:
    """The entrypoint from a location the branch under judgement cannot write.

    This checkout's own `scripts/` — which, for a fixture checkout created under
    `tmp_path`, is a different tree entirely.
    """
    return REPO_ROOT / "scripts" / "check_body_branch.sh"


def _assert_in_checkout_run_is_not_a_pass(
    proc: subprocess.CompletedProcess, *, attack: str
) -> None:
    """The S1 property, stated once so all three attack rows cannot drift.

    Not `rc == 2`: a fix that refuses to trust an entrypoint shipped by the
    branch may legitimately answer UNDETERMINED (3) instead of judging. What it
    may never answer is 0.
    """
    assert proc.returncode != ExitCode.OK.value, (
        f"{attack}: the branch rewrote the gate and the gate — invoked from "
        "that same branch, as CI invokes it — cleared the branch.\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "check_body_branch: CLEAN" not in proc.stdout, (
        f"{attack}: the report announced CLEAN.\nstdout={proc.stdout}"
    )
    assert proc.returncode != ExitCode.NOT_IMPLEMENTED.value, (
        f"{attack}: the gate reported not-implemented; nothing was checked"
    )


def _assert_tampered_module_is_live(checkout: Path) -> None:
    """Prove the branch's edit really changed the rules, before judging anything.

    Imports the branch's `role_protocol` in a subprocess (`-P`, PYTHONPATH set to
    the checkout's own `src`) and reads the two things the tamper claims to have
    changed. Without this the seal could pass on a tamper that silently did
    nothing — the fixture-is-stale failure mode, which is what a text splice into
    a constant's spelling actually produces.
    """
    probe = subprocess.run(
        [
            sys.executable,
            "-P",
            "-c",
            "import claude_dispatcher.role_protocol as m;"
            "bodies = next(r for r in m.DEFAULT_ROLE_RULES "
            "if r.role is m.Role.BODIES);"
            "print(len(m.FLOOR_GLOBS), '**/.dispatcher.yaml' in bodies.globs)",
        ],
        cwd=str(checkout),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(checkout / "src")},
        timeout=120,
    )
    assert probe.returncode == 0, (
        f"the tampered gate library does not import: {probe.stderr}"
    )
    assert probe.stdout.strip() == "0 False", (
        "the tamper did not take effect — the branch's own copy still carries "
        f"a floor and/or the config deny: {probe.stdout!r}"
    )


def test_a_branch_that_replaces_the_gate_module_cannot_clear_itself(
    ci_checkout_template: Path, tmp_path: Path
) -> None:
    """The blatant attack: the branch commits its own `role_protocol.py`.

    The `-P` / `PYTHONSAFEPATH` fix closed the *cwd* vector — a top-level
    `claude_dispatcher/` package planted at the repo root no longer wins the
    import. It does nothing about this one, because the script does not find its
    library through the cwd: it finds it through `BASH_SOURCE`, and in CI
    `BASH_SOURCE` is inside the branch.

    The control in the same body is the whole strength of this seal: the SAME
    tree, judged by the SAME script from a location the branch cannot write,
    must be a VIOLATION. So the assertion below is not "some verdict changed" —
    it is that two invocations of one gate over one tree disagree, and that the
    branch's own copy is the one that says yes.

    Red now (measured against the built worktree): the in-checkout run prints
    `HOSTILE GATE: everything is fine` and exits 0, while the trusted run exits
    2 and names `tests/test_planted_seal.py`.
    Green when: the in-checkout run is anything but 0 — it verified its own
    provenance and refused, or it was made to run the trusted library.
    Falsify: revert the fix — this goes red on the exit code and on the marker.
    """
    checkout = _checkout(ci_checkout_template, tmp_path)
    (checkout / GATE_LIBRARY).write_text(
        "import sys\n"
        "def main(argv):\n"
        "    print('HOSTILE GATE: everything is fine')\n"
        "    return 0\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    # ...and the forbidden edit the planted gate exists to hide.
    (checkout / "tests" / "test_planted_seal.py").write_text(
        "def test_x():\n    pass\n", encoding="utf-8"
    )
    _commit(checkout, "a seal, and a gate that approves it")

    # The control: the branch's diff really is a violation, and the gate really
    # can see that — from a trusted entrypoint. Without this the seal below
    # could be satisfied by a gate that is simply broken.
    trusted = _run_gate(_trusted_script(), checkout)
    assert trusted.returncode == ExitCode.VIOLATION.value, (
        "the trusted entrypoint failed to refuse a branch that added a seal "
        f"file; the fixture, not the gate, is wrong\nstdout={trusted.stdout}\n"
        f"stderr={trusted.stderr}"
    )
    assert "tests/test_planted_seal.py" in trusted.stdout

    judged_by_itself = _run_gate(checkout / GATE_ENTRYPOINT, checkout)
    assert "HOSTILE GATE" not in judged_by_itself.stdout, (
        "the checkout under judgement supplied the module that judged it: "
        f"{judged_by_itself.stdout}"
    )
    _assert_in_checkout_run_is_not_a_pass(
        judged_by_itself, attack="a planted role_protocol.main"
    )


def test_a_branch_that_edits_the_deny_table_cannot_clear_itself(
    ci_checkout_template: Path, tmp_path: Path
) -> None:
    """The attack a reviewer would not notice: two DATA edits, no new file.

    The branch deletes one glob from the BODIES rule and empties `FLOOR_GLOBS`,
    then writes `.dispatcher.yaml` — the file the floor exists to protect. Every
    scaffolded signature is unchanged, `seal_verify`'s test-path delegation
    still runs, every other rule still fires. Only the two lines that would have
    refused this branch are gone, and the branch is the thing that removed them.

    This row matters beyond S1: it is the reason S3 is a defect at all. The
    floor protects `.dispatcher.yaml` and the floor's own definition lives in a
    file the same branch may rewrite, so the floor is exactly as strong as the
    weakest role's write permission on `src/`.

    The tamper is appended rather than spliced into the literals, and this is
    not a stylistic choice: the first draft rewrote the source line
    `FLOOR_GLOBS: tuple[str, ...] = ("**/.dispatcher.yaml",)`, and any fix for
    S2/S3 necessarily reformats that line — so the seal would have died of a
    stale fixture on the very commit that fixed it. Appending a rebinding says
    what the tamper MEANS ("this branch's floor is empty") in a way no
    reformatting can invalidate, and `_assert_tampered_module_is_live` proves
    the rebinding took effect before the gate is ever run.

    Red now (measured): the in-checkout run prints `CLEAN` and `against the
    0-glob floor`, and exits 0; the trusted run exits 2 naming `.dispatcher.yaml`
    and the floor's rationale.
    Green when: the in-checkout run is not 0.
    Falsify: revert the fix — this goes red on the exit code.
    """
    checkout = _checkout(ci_checkout_template, tmp_path)
    library = checkout / GATE_LIBRARY
    text = library.read_text(encoding="utf-8")
    guard = 'if __name__ == "__main__":'
    assert guard in text, "the gate library has no script face to insert before"
    amendment = (
        "\n# --- the branch's own amendment to the rules it is judged by\n"
        "FLOOR_GLOBS = ()\n"
        "DEFAULT_ROLE_RULES = tuple(\n"
        "    dataclasses.replace(\n"
        "        _rule,\n"
        "        globs=tuple(\n"
        "            _g for _g in _rule.globs if _g != '**/.dispatcher.yaml'\n"
        "        ),\n"
        "    )\n"
        "    for _rule in DEFAULT_ROLE_RULES\n"
        ")\n\n"
    )
    # BEFORE the script face, not appended: `python -m pkg.mod` runs the module
    # top to bottom and the `__main__` guard calls `main()` and raises
    # SystemExit, so anything after it never executes. An appended rebinding
    # tampers with the IMPORTED module and not with the one the gate runs —
    # measured, and it made this seal pass while the exploit was wide open.
    text = text.replace(guard, amendment + guard, 1)
    library.write_text(text, encoding="utf-8")
    assert text.index(amendment) < text.index(guard)
    _assert_tampered_module_is_live(checkout)

    with (checkout / ".dispatcher.yaml").open("a", encoding="utf-8") as handle:
        handle.write("\n# and now the policy file is mine\n")
    _commit(checkout, "delete the floor, then walk through it")

    trusted = _run_gate(_trusted_script(), checkout)
    assert trusted.returncode == ExitCode.VIOLATION.value, (
        "the trusted entrypoint failed to refuse a branch that wrote "
        f"`.dispatcher.yaml`; the fixture is wrong\nstdout={trusted.stdout}\n"
        f"stderr={trusted.stderr}"
    )
    assert ".dispatcher.yaml" in trusted.stdout

    judged_by_itself = _run_gate(checkout / GATE_ENTRYPOINT, checkout)
    _assert_in_checkout_run_is_not_a_pass(
        judged_by_itself, attack="an emptied FLOOR_GLOBS"
    )


def test_rewriting_the_entrypoint_is_itself_refused_by_a_trusted_run(
    ci_checkout_template: Path, tmp_path: Path
) -> None:
    """The third shape, end-to-end, and the one place this file states a limit
    instead of a property.

    The branch leaves `role_protocol.py` untouched and edits ONLY
    `check_body_branch.sh`, replacing the delegation with `exit 0`. Measured
    (2026-08-08): invoked as `bash scripts/check_body_branch.sh …` from that
    checkout, it exits 0 and prints nothing.

    **That measurement is deliberately not asserted, because no change to this
    repository could make it false.** If CI executes a file the branch owns, the
    branch decides the exit code; a provenance check written inside the script
    is deleted by the same commit. The only fixes are outside the tree — CI
    invoking a copy the branch cannot write — and this repository tracks no CI
    configuration at all (measured: `git ls-files` matches no workflow, Makefile
    or pipeline definition), so there is nothing here to seal it against. It is
    reported as an obligation on the caller, not pinned as a test that would
    then have to be deleted.

    What IS sealed is the half that lives in the tree: rewriting the entrypoint
    must be a VIOLATION when a trusted run looks at the diff. That is the whole
    of S2 stated end-to-end — the unit-level rows are in `_GATE_ROWS`, and this
    one proves the same thing through the real script, real git and a real
    checkout, so a fix that only changes a constant nothing reads would not
    satisfy it.

    Red now (measured): the trusted run exits 0 and reports CLEAN — the script
    that judges every branch is on no role's deny list and on no floor glob, so
    replacing it is an ordinary edit.
    Green when: the trusted run is a VIOLATION naming the entrypoint.
    """
    checkout = _checkout(ci_checkout_template, tmp_path)
    (checkout / GATE_ENTRYPOINT).write_text(
        "#!/usr/bin/env bash\n"
        "# the branch's own opinion of itself\n"
        "exit 0\n",
        encoding="utf-8",
    )
    _commit(checkout, "the gate agrees with me")

    trusted = _run_gate(_trusted_script(), checkout)
    assert GATE_ENTRYPOINT in trusted.stdout, (
        "the fixture did not change the entrypoint at all\n"
        f"stdout={trusted.stdout}\nstderr={trusted.stderr}"
    )
    assert trusted.returncode == ExitCode.VIOLATION.value, (
        "a bodies branch replaced the script that judges every branch with "
        f"`exit 0`, and the gate cleared it\nstdout={trusted.stdout}\n"
        f"stderr={trusted.stderr}"
    )
    assert f"FORBIDDEN {GATE_ENTRYPOINT}" in trusted.stdout, (
        "the report must name the entrypoint as the forbidden path, or the "
        f"refusal came from something else\nstdout={trusted.stdout}"
    )


def test_the_gate_still_clears_an_untampered_legal_branch_from_either_entrypoint(
    ci_checkout_template: Path, tmp_path: Path
) -> None:
    """The control for all three attacks above, and the reason they are a
    narrowing rather than a refusal.

    An untampered branch doing exactly what BODIES exists to do — adding a file
    under `src/` — must still be cleared. Two arms, deliberately asymmetric:

      * from the TRUSTED entrypoint the answer must be CLEAN / 0, under every
        mechanism. If a fix cannot clear a legal branch from a trusted copy, the
        gate is not fixed, it is broken.
      * from the branch's OWN entrypoint the answer must be 0 or 3, never 2. A
        fix that refuses to trust an entrypoint shipped by the branch is
        allowed to answer "I did not check"; it is not allowed to invent a
        violation, which would make every legal branch look guilty and train
        every reader to ignore the gate.

    Green now, and it must STILL be green afterwards.
    Falsify: implement S1 as "the in-checkout invocation always fails" with a
    violation exit code — the second arm goes red. Implement it as "the gate
    always refuses" — the first arm goes red.
    """
    checkout = _checkout(ci_checkout_template, tmp_path)
    (checkout / "src" / "claude_dispatcher" / "brand_new_module.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    _commit(checkout, "an ordinary bodies commit")

    trusted = _run_gate(_trusted_script(), checkout)
    assert trusted.returncode == ExitCode.OK.value, (
        "a legal bodies branch was not cleared by the trusted entrypoint\n"
        f"stdout={trusted.stdout}\nstderr={trusted.stderr}"
    )
    assert "check_body_branch: CLEAN" in trusted.stdout

    from_the_branch = _run_gate(checkout / GATE_ENTRYPOINT, checkout)
    assert from_the_branch.returncode in (
        ExitCode.OK.value,
        ExitCode.UNDETERMINED.value,
    ), (
        "the gate invoked from inside an UNTAMPERED checkout reported "
        f"rc={from_the_branch.returncode}; a legal branch must be cleared or "
        "honestly declared unchecked, never called a violation\n"
        f"stdout={from_the_branch.stdout}\nstderr={from_the_branch.stderr}"
    )


# --------------------------------------------------------------------------- #
# S2 + S3 — the gate's own two halves are not on the floor
#
# Both are stated the same way and are therefore tabled together: a changed path
# that IS the gate must not produce a clean verdict for ANY role, including
# LEGACY (the state a row acquires by deleting one line) and including
# ADJUDICATE with a task row that explicitly declares the path as its writable
# set (the shape that defeated the deny table in the first place).
# --------------------------------------------------------------------------- #

#: A rationale nothing in the module can produce, so a violation can be proven
#: to have come from the gate's own reason and not from the injected rule.
_STRIPPED_RATIONALE = "injected policy with the gate deliberately unprotected"


def _policy_that_protects_nothing() -> RolePolicy:
    """A complete, well-formed policy under which every probe below is writable.

    Models the two things an unlowerable protection must survive: a base-pinned
    `roles:` section from a repo that does not carry it, and a caller-supplied
    policy (`check_branch(..., policy=...)`, which the contract says wins
    verbatim). Each row asserts the probe is writable under this policy BEFORE
    it asserts the refusal, so a pass can only come from a tier the policy
    cannot reach.
    """
    rules: list[RoleRule] = []
    for role in Role:
        if role is Role.LEGACY:
            rules.append(
                RoleRule(Role.LEGACY, RuleKind.UNRESTRICTED, (), _STRIPPED_RATIONALE)
            )
        elif role is Role.ADJUDICATE:
            rules.append(
                RoleRule(
                    Role.ADJUDICATE,
                    RuleKind.ALLOW_ONLY_GLOBS,
                    (),
                    _STRIPPED_RATIONALE,
                )
            )
        else:
            rules.append(
                RoleRule(
                    role,
                    RuleKind.DENY_GLOBS,
                    ("**/never-touched/**",),
                    _STRIPPED_RATIONALE,
                )
            )
    return RolePolicy(
        rules=tuple(rules), source=PolicySource.BASE_PINNED_CONFIG, base_ref="main"
    )


class _RunResult(tuple):
    def __new__(cls, rc: int, out: str = "", err: str = "") -> "_RunResult":
        return super().__new__(cls, (rc, out, err))

    @property
    def returncode(self) -> int:
        return self[0]

    @property
    def stdout(self) -> str:
        return self[1]

    @property
    def stderr(self) -> str:
        return self[2]


#: What every blob read below answers, at BOTH revisions. Identical text at base
#: and branch means `compare_signatures` reports CHECKED with no changes, so the
#: scaffolded-signature half of the BODIES gate is switched off deliberately and
#: visibly: these seals are about PATHS, and a row that came out non-clean
#: because a signature moved would be a row proving the wrong thing.
_UNCHANGED_BLOB = "VALUE = 1\n"


def _run_stub(changed: list[str]):
    """A git seam answering the diff read and blob reads; anything else raises,
    so a seal cannot pass on a code path it never modelled.

    The blob answer matters for `Role.BODIES`: `check_branch` compares
    scaffolded signatures over every changed `*.py`, and a seam that could not
    answer would make every BODIES row UNDETERMINED. UNDETERMINED is not a pass,
    so the refusal rows would go green without any protection existing — the
    exact vacuity this file is written against.
    """

    def run(cmd, *_args, **_kwargs):
        argv = [str(c) for c in cmd]
        if "diff" in argv:
            return _RunResult(0, "".join(p + "\n" for p in changed), "")
        if "ls-tree" in argv:
            # `repo_config.blob_text_at` refuses anything that is not a
            # regular-file blob, so the entry has to be well-formed.
            path = argv[-1]
            return _RunResult(0, f"100644 blob 0123456789abcdef\t{path}\0", "")
        if "cat-file" in argv:
            return _RunResult(0, _UNCHANGED_BLOB, "")
        raise AssertionError(f"unscripted git command: {argv}")

    return run


def _check(role: Role, changed: list[str], **kwargs):
    kwargs.setdefault("policy", built_in_policy())
    return check_branch("/x", "main", "feat/x", role, run=_run_stub(changed), **kwargs)


def _spec(role: Role, *disputed: str) -> TaskRoleSpec:
    return TaskRoleSpec(
        task_key="D1-SELFAUTH", role=role, disputed_paths=tuple(disputed)
    )


#: (role, changed path). WRITTEN OUT, one row per pair — five roles times the
#: four probes of the gate's two halves. Derived from nothing: not from `Role`,
#: not from `FLOOR_GLOBS`, not from a product comprehension. The nested probes
#: follow the precedent `test_role_protocol_floor.py` set for
#: `sub/project/.dispatcher.yaml`: the repo can be vendored inside another tree
#: and one pattern must cover both layouts, which is the reason
#: `DEFAULT_ROLE_RULES` spells its globs `**/x/**` rather than `x/**`.
_GATE_ROWS: tuple[tuple[str, str], ...] = (
    ("scaffold", "scripts/check_body_branch.sh"),
    ("scaffold", "sub/project/scripts/check_body_branch.sh"),
    ("scaffold", "src/claude_dispatcher/role_protocol.py"),
    ("scaffold", "sub/project/src/claude_dispatcher/role_protocol.py"),
    ("seals", "scripts/check_body_branch.sh"),
    ("seals", "sub/project/scripts/check_body_branch.sh"),
    ("seals", "src/claude_dispatcher/role_protocol.py"),
    ("seals", "sub/project/src/claude_dispatcher/role_protocol.py"),
    ("bodies", "scripts/check_body_branch.sh"),
    ("bodies", "sub/project/scripts/check_body_branch.sh"),
    ("bodies", "src/claude_dispatcher/role_protocol.py"),
    ("bodies", "sub/project/src/claude_dispatcher/role_protocol.py"),
    ("adjudicate", "scripts/check_body_branch.sh"),
    ("adjudicate", "sub/project/scripts/check_body_branch.sh"),
    ("adjudicate", "src/claude_dispatcher/role_protocol.py"),
    ("adjudicate", "sub/project/src/claude_dispatcher/role_protocol.py"),
    ("legacy", "scripts/check_body_branch.sh"),
    ("legacy", "sub/project/scripts/check_body_branch.sh"),
    ("legacy", "src/claude_dispatcher/role_protocol.py"),
    ("legacy", "sub/project/src/claude_dispatcher/role_protocol.py"),
)


@pytest.mark.parametrize("role_value, changed", _GATE_ROWS)
def test_no_role_gets_a_clean_verdict_for_editing_the_gate(
    role_value: str, changed: str
) -> None:
    """S2 and S3, stated as one property: the gate is not a role's to edit.

    The two halves are one artifact. Protecting `role_protocol.py` while leaving
    `check_body_branch.sh` writable protects nothing (the branch replaces the
    entrypoint), and protecting the entrypoint while leaving the library
    writable protects nothing either (the entrypoint faithfully executes the
    branch's rules). So both are tabled, for all five roles.

    LEGACY is a row for the same reason the floor covers it: LEGACY is not
    granted to anyone, it is what a row IS when the `role:` key is absent, so a
    protection LEGACY escapes is bypassed by deleting one line — and here the
    deleted line would buy the right to rewrite the judge.

    ADJUDICATE is a row because it is the role that already defeated the deny
    table once: `effective_rule` builds its writable set out of the task's own
    `disputed_paths:`, so the row below DECLARES the gate as the disputed
    artifact and is asserted to genuinely be granted it before the refusal is
    checked. An adjudication over the gate's source is exactly how the most
    privileged role would grant itself the gate.

    The policy handed in mentions none of these paths, and each row proves that
    first. So this cannot be satisfied by a repo `roles:` addition or by
    `built_in_policy`'s table alone: it requires a tier no supplied policy can
    lower, which is what `FLOOR_GLOBS` is for.

    Red now (measured against the built worktree): all twenty rows return
    `DiffVerdict.CLEAN` with `violations == ()`.
    Green when: each returns a VIOLATION naming exactly the changed path.
    Falsify: add these paths to `DEFAULT_ROLE_RULES` instead of to the floor —
    the rows stay red, because the injected policy replaces that table.
    """
    role = Role(role_value)
    policy = _policy_that_protects_nothing()
    rule = policy.rule_for(role)

    # The fixture exhibits the defect: nothing in the supplied policy protects
    # this path, so a violation can only come from a tier above the policy.
    assert first_matching_glob(changed, rule.globs) is None, (
        "the injected policy already denies the probe; this row would then "
        "pass without any floor existing"
    )
    spec = _spec(role, changed) if role is Role.ADJUDICATE else None
    if spec is not None:
        assert first_matching_glob(changed, spec.disputed_paths) == changed, (
            "the adjudicate declaration does not grant the probe, so this row "
            "would pass on an allowlist miss rather than on the floor"
        )
    if role is Role.LEGACY:
        assert rule.kind is RuleKind.UNRESTRICTED, rule.kind

    result = _check(role, [changed], policy=policy, spec=spec)

    assert [v.path for v in result.violations] == [changed], (
        f"role {role_value} rewrote {changed!r} — the gate that judges it — "
        f"and the verdict was {result.verdict.value}"
    )
    assert result.verdict is DiffVerdict.VIOLATION
    violation = result.violations[0]
    assert violation.matched_glob.strip(), (
        "a violation must say what forbade the path, or the agent cannot act "
        "on the report"
    )
    assert violation.rationale.strip(), "a violation must print why"
    assert violation.rationale != _STRIPPED_RATIONALE, (
        "the violation printed the injected policy's rationale, so it came "
        "from the policy — the one thing a caller can replace wholesale"
    )


@pytest.mark.parametrize(
    "role_value, changed",
    _GATE_ROWS,
    ids=[f"{r}-{c}" for r, c in _GATE_ROWS],
)
def test_the_gate_is_refused_under_the_policy_the_gate_actually_runs_with(
    role_value: str, changed: str
) -> None:
    """The same twenty rows under `built_in_policy()` — the policy CI has.

    The seal above proves unlowerability by stripping the policy; this one
    proves the protection is actually reachable on the path production takes. It
    is a separate function on purpose: an implementation that put the paths only
    in a caller-supplied default would satisfy one and not the other.

    Two rows are already VIOLATION today for an unrelated reason — SEALS is
    denied `**/src/**`, which covers both `role_protocol.py` probes — and that
    is fine: this file's job is that no role gets CLEAN, not that every row gets
    there by a new mechanism. The eighteen others are the measurement.

    Red now (measured): eighteen of the twenty return CLEAN.
    Green when: all twenty are VIOLATION naming the path.
    """
    role = Role(role_value)
    spec = _spec(role, changed) if role is Role.ADJUDICATE else None
    result = _check(role, [changed], spec=spec)
    assert [v.path for v in result.violations] == [changed], (
        f"under the built-in policy, role {role_value} may write {changed!r}"
    )
    assert result.verdict is DiffVerdict.VIOLATION


def test_a_floor_violation_on_the_gate_reports_the_floors_own_reason() -> None:
    """One row, separate from the table, for the report an agent has to read.

    `FLOOR_RATIONALE` explains a refusal that no role rule can explain — for
    ADJUDICATE the role's own rationale says the writable set IS
    `disputed_paths:`, which is the one sentence that cannot explain refusing a
    path that is in `disputed_paths:`. This is stated once rather than in every
    row so the table stays about the verdict.

    Red now: CLEAN, so there is no violation to inspect.
    Green when: the violation carries the floor's own reason.
    Falsify: implement the protection by appending to each role's `globs` — the
    ADJUDICATE row then prints "its writable set is the task's disputed_paths:"
    and this goes red.
    """
    spec = _spec(Role.ADJUDICATE, GATE_LIBRARY)
    result = _check(Role.ADJUDICATE, [GATE_LIBRARY], spec=spec)
    assert result.verdict is DiffVerdict.VIOLATION
    assert result.violations[0].rationale == FLOOR_RATIONALE, (
        "the gate's source is protected by something other than the floor, or "
        "the floor's reason was not carried to the report: "
        f"{result.violations[0].rationale!r}"
    )


#: (role, changed path) pairs that must STAY clean. Written out. Without these,
#: "deny `scripts/**`", "deny `src/**` to everyone" and "refuse every diff" all
#: satisfy the table above, and each of those would make the protocol unusable:
#: BODIES exists to write under `src/`, and SCAFFOLD exists to write the stubs.
_STILL_WRITABLE_ROWS: tuple[tuple[str, str], ...] = (
    ("scaffold", "src/claude_dispatcher/plan.py"),
    ("scaffold", "src/claude_dispatcher/brand_new_unit.py"),
    ("scaffold", "scripts/some_other_helper.sh"),
    ("scaffold", "docs/adr/0007.md"),
    ("bodies", "src/claude_dispatcher/plan.py"),
    ("bodies", "src/claude_dispatcher/brand_new_unit.py"),
    ("bodies", "scripts/some_other_helper.sh"),
    ("bodies", "docs/adr/0007.md"),
    ("legacy", "src/claude_dispatcher/plan.py"),
    ("legacy", "src/claude_dispatcher/brand_new_unit.py"),
    ("legacy", "scripts/some_other_helper.sh"),
    ("legacy", "docs/adr/0007.md"),
    ("seals", "tests/test_role_protocol_provenance.py"),
    ("seals", "docs/adr/0007.md"),
)


@pytest.mark.parametrize("role_value, changed", _STILL_WRITABLE_ROWS)
def test_protecting_the_gate_costs_the_rest_of_the_tree_nothing(
    role_value: str, changed: str
) -> None:
    """The upper bound on S2 and S3.

    `scripts/some_other_helper.sh` and `src/claude_dispatcher/plan.py` are the
    rows that matter: the protection is about TWO named artifacts, not about the
    directories they live in. A fix reaching for `**/scripts/**` or
    `**/src/claude_dispatcher/**` would stop BODIES doing its job and would make
    every legitimate change to the dispatcher unplannable, with no override,
    because a floor has no override.

    Green now, and it must STILL be green afterwards.
    Falsify: protect the directory instead of the file — these go red while the
    table above stays green.
    """
    result = _check(Role(role_value), [changed])
    assert result.verdict is DiffVerdict.CLEAN, (
        f"role {role_value} may no longer write {changed!r}: "
        f"{[(v.path, v.matched_glob) for v in result.violations]}"
    )
    assert result.violations == ()


# --------------------------------------------------------------------------- #
# S4 — SCAFFOLD may rewrite the instructions that judge its own branch
#
# The panel named `**/roles/*.md` + `**/reviewer_prompts/**` +
# `**/verifier_prompts/**`. That list is checked here by MEASUREMENT rather than
# taken on trust, and the measurement changed the answer twice:
#
#   * `**/roles/*.md` matches NO file this repo tracks. The role file the code
#     names — `preflight.DEFAULT_ROLE_FILE = ".claude/workflow/roles/tasker.md"`
#     — lives behind `.claude/workflow`, a tracked SYMLINK into a sibling
#     repository. Git never reports a path under it as changed here, so the glob
#     protects nothing in this tree today. It is still sealed below, as a
#     path-shape row: it is what SEALS and BODIES already carry, the symlink can
#     become a directory, and a glob that protects nothing today is not the same
#     claim as a glob that is absent.
#   * The reviewer prompt directory holds FIVE files, not four. `_shared.md` is
#     concatenated into every family's prompt by `_load_prompt`, so it is the
#     one file that reaches every reviewer seat — and it is the file a list
#     written from the family names would miss.
# --------------------------------------------------------------------------- #

#: (repo-relative path, the function that reads it). WRITTEN OUT. Verified
#: against the loaders by `test_the_prompt_files_this_file_pins_are_the_ones_the
#: _loaders_read`, which also fails when a NEW prompt file appears with no row.
_MACHINE_READ_PROMPTS: tuple[tuple[str, str], ...] = (
    (
        "src/claude_dispatcher/reviewer_prompts/_shared.md",
        "cross_family_reviewer._load_prompt",
    ),
    (
        "src/claude_dispatcher/reviewer_prompts/claude.md",
        "cross_family_reviewer._load_prompt",
    ),
    (
        "src/claude_dispatcher/reviewer_prompts/codex.md",
        "cross_family_reviewer._load_prompt",
    ),
    (
        "src/claude_dispatcher/reviewer_prompts/gemini.md",
        "cross_family_reviewer._load_prompt",
    ),
    (
        "src/claude_dispatcher/reviewer_prompts/grok.md",
        "cross_family_reviewer._load_prompt",
    ),
    (
        "src/claude_dispatcher/verifier_prompts/verifier.md",
        "verifier._load_prompt",
    ),
)

#: The reviewer families whose prompt `_load_prompt` renders. Written out rather
#: than globbed off the directory, for the usual reason.
_REVIEWER_FAMILIES: tuple[str, ...] = ("claude", "codex", "gemini", "grok")


def test_the_prompt_files_this_file_pins_are_the_ones_the_loaders_read() -> None:
    """The measurement S4 rests on, run rather than asserted from the panel's
    list.

    Three things are established:

      1. every written row names a file that exists at the path the loader
         computes (`_PROMPTS_DIR`), so the repo-relative strings in the table
         are the strings git would report;
      2. the loader's OUTPUT actually contains that file's bytes — a file in the
         prompt directory that nothing concatenates is not machine-read, and
         sealing it would be sealing a guess;
      3. no `*.md` under either prompt directory is missing from the table, so a
         new reviewer family cannot arrive unsealed.

    Green now: it is a measurement, not a gate. Its value is (3): the day a
    seventh prompt file lands, this reddens instead of the protection silently
    not covering it.
    Falsify: add `reviewer_prompts/mystery.md` — this goes red naming it.
    """
    reviewer_dir = Path(cross_family_reviewer._PROMPTS_DIR)
    verifier_dir = Path(verifier_mod._PROMPTS_DIR)

    written = {path for path, _reader in _MACHINE_READ_PROMPTS}
    for path, _reader in _MACHINE_READ_PROMPTS:
        assert (REPO_ROOT / path).is_file(), (
            f"{path} is pinned by this file but does not exist; the table is "
            "stale"
        )

    # (1) the loaders' directories are the ones the written paths name. Compared
    # by tail and by content rather than by absolute equality, so the seal still
    # holds when the package is imported from an install rather than from `src`.
    assert reviewer_dir.as_posix().endswith(
        "claude_dispatcher/reviewer_prompts"
    ), reviewer_dir
    assert verifier_dir.as_posix().endswith(
        "claude_dispatcher/verifier_prompts"
    ), verifier_dir
    for path, _reader in _MACHINE_READ_PROMPTS:
        loaded = (
            reviewer_dir if "reviewer_prompts" in path else verifier_dir
        ) / Path(path).name
        assert loaded.is_file(), f"the loader's directory has no {path}"
        assert (
            loaded.read_bytes() == (REPO_ROOT / path).read_bytes()
        ), (
            f"{path} in the repo and the copy the loader reads have diverged; "
            "the repo-relative string this file seals is not the file the "
            "reviewer executes"
        )

    # (2) the bytes really reach a prompt.
    shared = (reviewer_dir / "_shared.md").read_text(encoding="utf-8")
    for family in _REVIEWER_FAMILIES:
        rendered = cross_family_reviewer._load_prompt(family)
        family_text = (reviewer_dir / f"{family}.md").read_text(encoding="utf-8")
        assert family_text.strip() in rendered, family
        assert shared.strip() in rendered, (
            f"_shared.md is not concatenated into the {family} prompt; the "
            "table's claim about it is wrong"
        )
    assert (
        (verifier_dir / "verifier.md").read_text(encoding="utf-8")
        == verifier_mod._load_prompt()
    )

    # (3) nothing in either directory is unsealed.
    found = {
        (p.relative_to(REPO_ROOT)).as_posix()
        for directory in (reviewer_dir, verifier_dir)
        for p in directory.glob("*.md")
    }
    unsealed = sorted(found - written)
    assert not unsealed, (
        "machine-read prompt files with no row in _MACHINE_READ_PROMPTS and "
        f"therefore no seal: {unsealed}"
    )


#: The instruction files SCAFFOLD must not be able to rewrite. WRITTEN OUT, one
#: literal row per path.
#:
#: The last two rows are the `**/roles/*.md` shape. No such file is tracked here
#: (see the section header), so they are path-shape rows: they pin that the
#: protection SCAFFOLD gets is the same one SEALS and BODIES already carry, and
#: they redden if a fix covers only the two prompt directories. Nothing about
#: them depends on the file existing — `check_branch` judges the strings git
#: reports.
_SCAFFOLD_MUST_NOT_WRITE: tuple[str, ...] = (
    "src/claude_dispatcher/reviewer_prompts/_shared.md",
    "src/claude_dispatcher/reviewer_prompts/claude.md",
    "src/claude_dispatcher/reviewer_prompts/codex.md",
    "src/claude_dispatcher/reviewer_prompts/gemini.md",
    "src/claude_dispatcher/reviewer_prompts/grok.md",
    "src/claude_dispatcher/verifier_prompts/verifier.md",
    "roles/tasker.md",
    ".claude/workflow/roles/tasker.md",
)


@pytest.mark.parametrize("changed", _SCAFFOLD_MUST_NOT_WRITE)
def test_scaffold_cannot_rewrite_the_instructions_that_judge_its_own_branch(
    changed: str
) -> None:
    """S4: the reviewer and the verifier read these files, and SCAFFOLD's whole
    job is writing under `src/` — which is where both prompt directories live.

    A scaffold branch that edits `reviewer_prompts/_shared.md` edits the
    instructions the panel executes over that same branch's diff. That is the
    self-authorization shape, with the reviewer standing in for the gate: the
    thing being judged writes the judge's instructions.

    Nothing here is asserted about SEALS or BODIES; those are the control below,
    and they are already denied these paths. The asymmetry has no stated reason
    in `DEFAULT_ROLE_RULES` — the comment on the `**/roles/*.md` entry gives the
    rationale ("machine-read instructions that the review gate executes, so
    editing them edits the reviewer that is about to judge the change") and that
    rationale is not role-specific.

    Red now (measured against the built worktree): all eight rows return
    `DiffVerdict.CLEAN` with `violations == ()`.
    Green when: each returns a VIOLATION naming the path.
    Falsify: deny SCAFFOLD only `**/reviewer_prompts/**` — the verifier row and
    the two `roles/` rows stay red.
    """
    result = _check(Role.SCAFFOLD, [changed])
    assert [v.path for v in result.violations] == [changed], (
        f"a scaffold branch rewrote {changed!r} — an instruction file the "
        "review gate executes over that same branch — and the verdict was "
        f"{result.verdict.value}"
    )
    assert result.verdict is DiffVerdict.VIOLATION
    assert result.violations[0].rationale.strip(), (
        "a violation must print why; a scaffold agent that trips this needs to "
        "learn that these files judge it"
    )


#: (role, path) pairs that are ALREADY refused today, written out literally.
#: These are the evidence that the probes above are real paths under the real
#: glob lens rather than strings that happen to match nothing — and they are the
#: regression guard for the fix: extending SCAFFOLD must not disturb the two
#: roles that already carry these globs.
_ALREADY_REFUSED_ROWS: tuple[tuple[str, str], ...] = (
    ("seals", "src/claude_dispatcher/reviewer_prompts/_shared.md"),
    ("seals", "src/claude_dispatcher/reviewer_prompts/claude.md"),
    ("seals", "src/claude_dispatcher/reviewer_prompts/codex.md"),
    ("seals", "src/claude_dispatcher/reviewer_prompts/gemini.md"),
    ("seals", "src/claude_dispatcher/reviewer_prompts/grok.md"),
    ("seals", "src/claude_dispatcher/verifier_prompts/verifier.md"),
    ("seals", "roles/tasker.md"),
    ("seals", ".claude/workflow/roles/tasker.md"),
    ("bodies", "src/claude_dispatcher/reviewer_prompts/_shared.md"),
    ("bodies", "src/claude_dispatcher/reviewer_prompts/claude.md"),
    ("bodies", "src/claude_dispatcher/reviewer_prompts/codex.md"),
    ("bodies", "src/claude_dispatcher/reviewer_prompts/gemini.md"),
    ("bodies", "src/claude_dispatcher/reviewer_prompts/grok.md"),
    ("bodies", "src/claude_dispatcher/verifier_prompts/verifier.md"),
    ("bodies", "roles/tasker.md"),
    ("bodies", ".claude/workflow/roles/tasker.md"),
)


@pytest.mark.parametrize("role_value, changed", _ALREADY_REFUSED_ROWS)
def test_seals_and_bodies_keep_the_protection_they_already_have(
    role_value: str, changed: str
) -> None:
    """Green now and green afterwards.

    Two jobs. First, it proves the eight probes in `_SCAFFOLD_MUST_NOT_WRITE`
    are genuinely matched by the module's glob lens — so when the SCAFFOLD rows
    are red, they are red because SCAFFOLD is unprotected and not because the
    probe strings are wrong. Second, it is the regression guard: the natural fix
    edits `DEFAULT_ROLE_RULES`, and an edit that moved these globs to SCAFFOLD
    instead of adding them reddens here.
    """
    result = _check(Role(role_value), [changed])
    assert [v.path for v in result.violations] == [changed], (
        f"role {role_value} lost its protection on {changed!r}"
    )
    assert result.verdict is DiffVerdict.VIOLATION


def test_scaffold_still_writes_everything_that_is_not_a_machine_read_instruction(
) -> None:
    """The control for S4, and the reason it is a narrowing.

    SCAFFOLD's entire job is landing typed stubs under `src/`, and a fix that
    reached for `**/src/**` or `**/*.md` would end the role. The probes are the
    two things it must keep: ordinary source, and ordinary prose.

    Green now, and it must STILL be green afterwards.
    Falsify: deny SCAFFOLD `**/*.md` — the doc rows go red. Deny it `**/src/**`
    — the module rows go red.
    """
    result = _check(
        Role.SCAFFOLD,
        [
            "src/claude_dispatcher/brand_new_unit.py",
            "src/claude_dispatcher/plan.py",
            "docs/adr/0007.md",
            "README.md",
            "features/d1/notes.md",
        ],
    )
    assert result.verdict is DiffVerdict.CLEAN, [
        (v.path, v.matched_glob) for v in result.violations
    ]
    assert result.violations == ()
