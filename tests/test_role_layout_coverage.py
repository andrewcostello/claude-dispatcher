"""D1 seals (phase P2): the role gate must hold in the layouts the TARGETS use.

The defect these seal, measured on this branch
----------------------------------------------
A five-seat panel filed: *the SEALS deny table protects no implementation
source in the diff's own stated target repos*. Reproduced against
``built_in_policy()`` at ``9ceb6d4``::

    SEALS globs: ('**/src/**', '**/schema/**', '**/.dispatcher.yaml',
                  '**/roles/*.md', '**/reviewer_prompts/**',
                  '**/verifier_prompts/**')

    cmd/classify/main.go        WRITABLE
    internal/wallet/ledger.go   WRITABLE
    pkg/api/handler.go          WRITABLE
    web/components/Button.tsx   WRITABLE
    db/migrations/0007_*.sql    WRITABLE
    web/src/app.tsx             DENIED   <- only because the path contains /src/

``**/src/**`` is a Python/JS *layout convention*. Go implementation lives in
``cmd/``, ``internal/`` and ``pkg/``. Measured composition of the stated
targets: evenplay-mono is 2,288 Go / 996 TS+TSX / 781 SQL / 316 Java / 0
Python; awevana is 231 Go / 75 TS+TSX / 8 Python. So on the repository this
protocol exists to govern, a SEALS agent may write implementation code, and
the separation the whole scaffold-first protocol rests on — the seal author is
independent of the fixer — is unenforced for the primary language of the
primary target.

The measurement found the fault runs in BOTH directions, which is the part the
panel finding does not state and which decides the design:

  * UNDER-BLOCK — Go/TS/SQL implementation outside a ``src/`` directory is
    writable by SEALS (the rows above).
  * OVER-BLOCK — ``web/src/app.test.tsx`` and
    ``services/billing/src/test/java/InvoiceTest.java`` are *seals*, and
    ``**/src/**`` DENIES them to the seal author. A ``immutable_paths:``
    override is ADD-only and there is no negation syntax
    (:func:`validate_override`, ``_NEGATION_PREFIXES``), so nothing can buy
    them back. A seal author cannot write the TypeScript or the Maven-layout
    Java seal today.

Why this is a policy question and not another parser question
--------------------------------------------------------------
The sibling finding — the signature comparator was Python-only while the
target is Go — got a comparator registry, because "what language is this
path" has one right answer per path. This one does not decompose that way. A
deny list of implementation directories must enumerate every layout
convention that exists, forever, and this repository has now been bitten four
times by open sets where closed ones were needed
(``FORBIDDEN_DISPUTED_GLOBS``, the drift gate's artifact filter, the guard
dispatch, ``_ARTIFACT_DIRS``).

The decisive fact is co-location, and it is sealed literally below
(:func:`test_no_directory_shaped_rule_can_separate_a_go_seal_from_its_body`):
**a Go test file lives in the same directory as the implementation it
tests.** ``internal/wallet/ledger_test.go`` and ``internal/wallet/ledger.go``
share every path segment but the last. Therefore no directory-shaped deny
glob — ``**/internal/**``, ``**/cmd/**``, ``**/pkg/**`` — can deny the body
without also denying the seal, and DENY_GLOBS is monotone: overrides add, the
floor adds, and there is no carve-out syntax to subtract with. Extending the
deny list and making it repo-configurable are the same move and both fail for
the same reason.

What the seal author establishes here, and what it does NOT decide
------------------------------------------------------------------
These seals pin the PROPERTY: *a SEALS agent cannot write implementation
source, and a BODIES agent cannot write a seal, in the layouts the targets
actually use*. Whether that is reached by inverting the SEALS row to
ALLOW_ONLY_GLOBS, by extending the deny list, or by making it repo-configurable
is the body author's and P4's call. Two seals here
(:func:`test_the_delegation_marker_means_the_same_thing_in_an_allow_only_rule`,
:func:`test_an_effective_rule_never_hands_a_role_an_allow_set_that_forbids_everything`)
pin machinery gaps that are latent defects on their own terms and that an
inversion would walk straight into; they mandate no particular table.

Vacuity
-------
Every row here carries an in-test control, so each seal proves a DIFFERENCE
rather than that matching works at all. Nothing is parametrized over a
comprehension across ``DEFAULT_ROLE_RULES`` — the corpus is written out, and
its paths are target-repo shapes that appear in no constant this file checks.
The 2026-08-07 P4 measurement (18 of 28 comprehended rows caught nothing) is
the reason.

The corpus deliberately EXCLUDES two path shapes, so this file cannot be read
as ruling on them; both are in the P2 report's dispute list:

  * anything under ``docs/`` — a SEALS agent may write ``docs/adr/0007.md``
    today and ``tests/test_role_protocol_provenance.py::_STILL_WRITABLE_ROWS``
    seals that it may. Any allow-only design must carry a documentation
    allowance or it breaks that seal; this file takes no position on its shape.
  * a test-shaped path INSIDE the machine-read instruction trees, e.g.
    ``x/reviewer_prompts/testdata/g.json``. It is denied to SEALS today by
    ``**/reviewer_prompts/**`` and would become writable under an allow-only
    rule keyed on ``is_test_path``. Judged harmless (``_load_prompt`` reads
    named files, not a testdata subtree) but it is a real coverage loss and
    P4's to rule on, so no row here requires either answer.

P4 RULINGS, 2026-08-10 — inversion ACCEPTED; the three disputes
================================================================
Not one assertion in this file was amended. The ten reds stand as written; the
eight coordinated amendments this file's recommendation requires were applied to
the four sibling seal files (`test_role_protocol_table.py`,
`test_role_protocol_diff.py`, `test_role_protocol_config.py`,
`test_role_protocol_parse.py`), each with its own note. Verified in a clone: the
inverted table plus the two machinery fixes takes the whole suite — this file's
35 rows included — to GREEN, and no ninth site exists.

RULING 0 — INVERSION. `Role.SEALS` becomes `ALLOW_ONLY_GLOBS`, writable set
`(SEAL_VERIFY_TEST_PATHS, "**/docs/**")`. The alternatives were re-measured
rather than accepted: adding `**/cmd/**`, `**/internal/**` and `**/pkg/**` to
the deny row turns exactly 3 rows of
:func:`test_seals_cannot_write_implementation_source_in_the_target_layouts`
green (the three Go bodies) and exactly 4 rows of
:func:`test_seals_can_write_the_seal_that_sits_beside_the_implementation` red
(the three `_test.go` seals and `internal/wallet/testdata/ledger_golden.json`),
for a net 10 -> 11 reds. The seal author's figure is confirmed to the row.

RULING 1 — `docs/` IS IN THE WRITABLE SET, as `**/docs/**`. This was the
dispute this file left open, and the measurement closes it: a PURE
`is_test_path` inversion, with no documentation allowance, reddens EIGHT rows —
all seven of
:func:`test_seals_cannot_write_implementation_source_in_the_target_layouts`
(every one on its CONTROL, `_A_PATH_SEALS_MUST_KEEP = "docs/notes.md"`, not on
its property) and
`test_role_protocol_provenance.py::_STILL_WRITABLE_ROWS[("seals",
"docs/adr/0007.md")]`. The CRITICAL seal cannot go green without it. That is the
operator's "a false refusal has no override" made concrete, and it is decided by
this file's own control rather than by preference.

Width: `**/docs/**`, not `docs/**` and not `**/docs/**/*.md`.
  * `**/x/**` is the table's documented spelling — a leading `**/` matches zero
    directories, so one pattern covers the root and the vendored/monorepo
    `services/billing/docs/...` layout. Root-anchoring it would repeat, in
    documentation, the exact mistake `**/src/**` made in source: a convention
    written for one repository shape.
  * An extension filter would refuse `docs/slack-app-manifest.json`,
    `docs/retroactive_panel_results/panel.json` and `sweep.log` — files that
    already exist in this tree — and a false refusal has no override.
  * Narrower than the status quo in one direction worth naming: `README.md` at
    the root is NOT in `docs/` and becomes unwritable to SEALS. No seal asserts
    otherwise, and a seal author editing the README is not its job.
Accepted, unchanged risk: a unit whose DELIVERABLE is documentation would have
its body writable by the seal author. The inversion neither creates nor worsens
that — `docs/` is writable to SEALS *and* BODIES today — and the protection that
actually holds there is the mirror obligation (BODIES may not write a seal),
which is measured green in section 3 of this file.

RULING 2 — the `**/reviewer_prompts/**` testdata loss is ACCEPTED; the three
instruction globs do NOT move to the floor in this change. Verified rather than
taken on trust: `cross_family_reviewer._load_prompt` opens exactly
`{family}.md` and `_shared.md` by name and `verifier._load_prompt` exactly
`verifier.md`; nothing globs or walks either directory, so a `testdata/` file
under them is never executed. One refinement to the seal author's "harmless":
`journal.hash_tree` DOES `rglob("*")` the reviewer-prompts directory for the
`reviewer_prompts_hash` provenance field, so such a file would move that digest.
That is audit noise, not prompt injection, and it is detectable by construction.
Under the inversion SEALS still cannot write `_shared.md` itself — it is neither
a test path nor under `docs/` — so the loss is exactly one path shape.

RULING 2b — and a SEPARATE live defect, raised here and deliberately NOT bundled.
The seal author is right that "ADJUDICATE is currently stopped from writing them
by nothing at all", and it is worse than a coverage loss: measured 2026-08-10
against `built_in_policy()`, a task row of
`disputed_paths: ["src/claude_dispatcher/reviewer_prompts/_shared.md"]` yields
`effective_rule(...).globs == ("src/claude_dispatcher/reviewer_prompts/_shared.md",)`
and `evaluate_changed_paths(...) == ()`; `first_matching_glob` of that path
against `FLOOR_GLOBS` is None, as it is for `roles/reviewer.md` and
`verifier_prompts/verifier.md`. So an adjudicate branch may today rewrite the
reviewer prompt that is about to judge it. The remedy — moving `**/roles/*.md`,
`**/reviewer_prompts/**` and `**/verifier_prompts/**` onto `FLOOR_GLOBS` — is
correct on its own rationale (they are role-independent, which is why all three
deny roles carry them), but a floor has no override and binds all five roles
including LEGACY, so it would stop any dispatched task from ever improving a
reviewer prompt. That is its own unit with its own blast radius, it is not
caused by the inversion and not fixed by it, and bundling it here would put a
red row in this commit that the inversion cannot clear. Raised, measured, and
left for a separate change.

RULING 3 — `db/migrations/0007_add_bay_flags.sql` STAYS in
`_IMPLEMENTATION_PATHS`. SQL migrations are not outside the protocol's scope:
evenplay-mono is 781 SQL files, a migration is the change to the durable store
that a seed fixture or migration test pins, and a seal author who may write the
migration can make its own seal pass by exactly the route the SEALS rationale
describes. One correction to the dispute as filed: the sentence "the schema is
the sole source" is the BODIES row's rationale, not SEALS' — SEALS' rationale
speaks only of vacuous seals — so the mismatch between that sentence and
`**/schema/**` is not evidence about this row. The row's real content is that
`**/schema/**` reaches no migration path, which is the SAME layout blindness as
`**/src/**`, in SQL instead of Go; striking it would strike a second instance of
the fault this file exists to establish. Under the inversion the row needs no
special handling and no glob of its own — a migration is neither a test path nor
under `docs/`, so it is refused as an allowlist miss, and `tests/fixtures/
ledger_seed.sql` (`is_test_path` -> True) stays writable. Both were green in the
clone.
"""

from __future__ import annotations

import pytest

from claude_dispatcher.role_protocol import (
    ALLOWLIST_MISS,
    Role,
    RolePolicy,
    RoleProtocolError,
    RoleRule,
    RuleKind,
    SEAL_VERIFY_TEST_PATHS,
    PolicySource,
    TaskRoleSpec,
    built_in_policy,
    effective_rule,
    evaluate_changed_paths,
    first_matching_glob,
    role_policy_from_mapping,
)
from claude_dispatcher.seal_verify import is_test_path


# --------------------------------------------------------------------------- #
# The corpus. Written out; target-repo shapes; no comprehension over any
# constant under test.
# --------------------------------------------------------------------------- #

#: (implementation, the seal that sits beside it). Go pairs share a directory —
#: that is the whole design argument and it is asserted, not assumed.
_BODY_AND_SEAL_PAIRS: tuple[tuple[str, str], ...] = (
    ("cmd/classify/main.go", "cmd/classify/main_test.go"),
    ("internal/wallet/ledger.go", "internal/wallet/ledger_test.go"),
    ("pkg/api/handler.go", "pkg/api/handler_test.go"),
    ("web/components/Button.tsx", "web/components/Button.test.tsx"),
    ("web/src/app.tsx", "web/src/app.test.tsx"),
    (
        "services/billing/src/main/java/Invoice.java",
        "services/billing/src/test/java/InvoiceTest.java",
    ),
)

#: Implementation source in the target layouts. A SEALS agent may not write any
#: of these. Written out.
_IMPLEMENTATION_PATHS: tuple[str, ...] = (
    "cmd/classify/main.go",
    "internal/wallet/ledger.go",
    "pkg/api/handler.go",
    "web/components/Button.tsx",
    "web/src/app.tsx",
    "services/billing/src/main/java/Invoice.java",
    "db/migrations/0007_add_bay_flags.sql",
)

#: Seals in the target layouts. A SEALS agent MUST be able to write every one,
#: or the role cannot do its job and there is no override to buy it back.
_SEAL_PATHS: tuple[str, ...] = (
    "cmd/classify/main_test.go",
    "internal/wallet/ledger_test.go",
    "pkg/api/handler_test.go",
    "internal/wallet/testdata/ledger_golden.json",
    "web/components/Button.test.tsx",
    "web/src/app.test.tsx",
    "services/billing/src/test/java/InvoiceTest.java",
    "tests/fixtures/ledger_seed.sql",
)

#: The controls. A path every design must keep WRITABLE for SEALS, and one
#: every design must keep DENIED — so neither "deny everything" nor "deny
#: nothing" can satisfy a seal in this file.
_A_PATH_SEALS_MUST_KEEP = "docs/notes.md"
_A_PATH_SEALS_MUST_NOT_HAVE = "schema/merge.yaml"

#: The coherence corpus: (path, is it one of this repo's tests?). The flag is
#: cross-checked against `seal_verify.is_test_path` on every row, so this table
#: cannot drift away from the matcher it is here to agree with.
_LAYOUT_COHERENCE_ROWS: tuple[tuple[str, bool], ...] = (
    ("cmd/classify/main.go", False),
    ("cmd/classify/main_test.go", True),
    ("internal/wallet/ledger.go", False),
    ("internal/wallet/ledger_test.go", True),
    ("pkg/api/handler.go", False),
    ("pkg/api/handler_test.go", True),
    ("internal/wallet/testdata/ledger_golden.json", True),
    ("web/components/Button.tsx", False),
    ("web/components/Button.test.tsx", True),
    ("web/src/app.tsx", False),
    ("web/src/app.test.tsx", True),
    ("services/billing/src/main/java/Invoice.java", False),
    ("services/billing/src/test/java/InvoiceTest.java", True),
    ("db/migrations/0007_add_bay_flags.sql", False),
    ("tests/fixtures/ledger_seed.sql", True),
    ("roles/reviewer.md", False),
    ("schema/merge.yaml", False),
    ("src/claude_dispatcher/plan.py", False),
    (".dispatcher.yaml", False),
)

#: Directory-shaped globs someone reaching for "just extend the deny list"
#: would write for a Go repository. Written out.
_GO_LAYOUT_DIRECTORY_GLOBS: tuple[str, ...] = (
    "**/cmd/**",
    "**/internal/**",
    "**/pkg/**",
)


def _seals_rule() -> RoleRule:
    """The compiled-in SEALS rule, through the module's own lens."""
    return built_in_policy().rule_for(Role.SEALS)


def _bodies_rule() -> RoleRule:
    """The compiled-in BODIES rule, through the module's own lens."""
    return built_in_policy().rule_for(Role.BODIES)


def _denied(rule: RoleRule, paths: list[str]) -> dict[str, str]:
    """``{path: matched_glob}`` for the paths ``rule`` forbids."""
    return {v.path: v.matched_glob for v in evaluate_changed_paths(rule, paths)}


# --------------------------------------------------------------------------- #
# 1. The fact the design turns on: Go co-locates the seal with the body.
# --------------------------------------------------------------------------- #


def test_is_test_path_tells_a_go_seal_from_the_body_in_the_same_directory() -> None:
    """`seal_verify.is_test_path` already separates the pair. Establish it FIRST.

    This is the fact the whole design question turns on, and it is checked
    before anything is proposed. If the repository's one matcher for "is this a
    test file" could not tell ``internal/wallet/ledger_test.go`` from
    ``internal/wallet/ledger.go``, then delegating the seal author's writable
    set to it would be impossible and the deny list would be the only option
    left. It can: ``_TEST_PATH``'s ``_test\\.`` alternative fires on the Go
    convention.

    The controls are the bodies. A matcher that answered True for everything
    (or False for everything) fails every row, so this cannot pass by matching
    working at all — it passes only on the DIFFERENCE.

    GREEN today, and it is a fact-pin rather than a request: it is the evidence
    the P2 report cites for recommending inversion. It is not vacuous because
    it can fail — deleting ``_test\\.`` from ``seal_verify._TEST_PATH`` reddens
    the three Go rows while every glob seal in `test_role_protocol_table.py`
    stays green, since ``**/*_test.go`` is a separate spelling of the same fact.

    Falsify: drop ``_test\\.`` or ``\\.test\\.`` from `seal_verify._TEST_PATH`.
    """
    for body, seal in _BODY_AND_SEAL_PAIRS:
        assert is_test_path(seal) is True, (
            f"{seal!r} is a seal and this repo's one matcher does not say so; "
            "a writable set delegated to it would refuse the seal author its "
            "own seal"
        )
        assert is_test_path(body) is False, (
            f"{body!r} is implementation and this repo's one matcher calls it "
            "a test; a writable set delegated to it would hand the seal "
            "author the implementation"
        )

    # And the co-location itself, for the three Go pairs: same directory, so no
    # directory rule can ever separate them.
    for body, seal in _BODY_AND_SEAL_PAIRS[:3]:
        assert body.rsplit("/", 1)[0] == seal.rsplit("/", 1)[0], (body, seal)


def test_no_directory_shaped_rule_can_separate_a_go_seal_from_its_body() -> None:
    """Extending the deny list with Go's directories denies the Go seals too.

    Measured through this module's own glob lens, not a re-implementation: for
    each of ``**/cmd/**``, ``**/internal/**`` and ``**/pkg/**``, the glob that
    catches the implementation catches the ``_test.go`` beside it. That is not
    a property of these three spellings, it is a property of the LAYOUT — Go
    puts both files in one directory — so it holds for any directory glob
    anyone writes later.

    The control is the filename-shaped glob ``**/*_test.go``, which separates
    the pair perfectly. So this seal is about directory globs specifically and
    not about globs in general, and an implementation cannot satisfy it by
    breaking the matcher.

    This closes the second and third options in the design question together.
    DENY_GLOBS is monotone: ``immutable_paths:`` is ADD-only, the floor is
    ADD-only, and there is no negation syntax to carve an exception with — the
    last assertion here proves the refusal rather than citing it. So "extend
    the deny list" and "make it repo-configurable" are the same move, and both
    buy the Go body only by spending the Go seal.

    GREEN today (it is a measurement of the glob engine, not a request of the
    table). Falsify: give `risk._glob_to_regex` a negation syntax, or make
    ``immutable_paths:`` able to subtract — then a deny list becomes
    expressible for Go and this argument dies.
    """
    for glob in _GO_LAYOUT_DIRECTORY_GLOBS:
        catches_a_body = [
            body
            for body, _seal in _BODY_AND_SEAL_PAIRS
            if first_matching_glob(body, (glob,)) is not None
        ]
        assert catches_a_body, f"{glob!r} catches no Go body; wrong probe"
        for body, seal in _BODY_AND_SEAL_PAIRS:
            if first_matching_glob(body, (glob,)) is None:
                continue
            assert first_matching_glob(seal, (glob,)) is not None, (
                f"{glob!r} denies {body!r} but not {seal!r} — if a directory "
                "glob could separate them, extending the deny list would be a "
                "real option and this seal is wrong"
            )

    # The control: a filename-shaped glob DOES separate the pair.
    assert first_matching_glob("internal/wallet/ledger_test.go", ("**/*_test.go",))
    assert first_matching_glob("internal/wallet/ledger.go", ("**/*_test.go",)) is None

    # And there is no carve-out syntax to rescue a directory deny with.
    with pytest.raises(RoleProtocolError):
        role_policy_from_mapping(
            {"bodies": {"immutable_paths": ["!**/*_test.go"]}}
        )


# --------------------------------------------------------------------------- #
# 2. The CRITICAL: SEALS may write implementation source in the targets.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", _IMPLEMENTATION_PATHS)
def test_seals_cannot_write_implementation_source_in_the_target_layouts(
    path: str,
) -> None:
    """A seal author that may edit the implementation can make its own seal pass.

    That sentence is the SEALS row's own ``rationale`` in
    ``DEFAULT_ROLE_RULES``. In the layouts the stated targets use, the table
    does not deliver it: five of the seven paths below are writable today,
    including every Go path, and Go is 2,288 of evenplay-mono's files.

    The control is in the same call: ``docs/notes.md`` must stay writable, so a
    rule that denies everything cannot satisfy this row. The violation's
    ``rationale`` is asserted non-empty because a tripped gate has to tell the
    agent WHY the path is not its to touch.

    ``matched_glob`` is deliberately NOT pinned to a value: this seal states
    the property, and a deny glob and :data:`ALLOWLIST_MISS` are both honest
    answers to "why". Pinning it would pick the mechanism.

    RED today for: ``cmd/classify/main.go``, ``internal/wallet/ledger.go``,
    ``pkg/api/handler.go``, ``web/components/Button.tsx``,
    ``db/migrations/0007_add_bay_flags.sql``.
    GREEN today, by accident, for: ``web/src/app.tsx`` and
    ``services/billing/src/main/java/Invoice.java`` — both only because the
    path happens to contain a ``/src/`` segment, which is a Python/JS layout
    convention and a JS bundler directory and Maven's source root, in that
    order of intent. The accident is pinned as an accident by
    :func:`test_the_gates_two_answers_to_is_this_a_seal_agree_in_the_target_layouts`,
    which requires the same verdict for ``web/components/Button.tsx``.

    Falsify: make SEALS unrestricted — every row goes red. Make it refuse
    everything — the control goes red.
    """
    rule = _seals_rule()
    denied = _denied(rule, [path, _A_PATH_SEALS_MUST_KEEP])

    assert _A_PATH_SEALS_MUST_KEEP not in denied, (
        f"the control failed: SEALS may not write {_A_PATH_SEALS_MUST_KEEP!r}, "
        "so this seal would pass for any path at all"
    )
    assert path in denied, (
        f"a SEALS agent may write {path!r} — implementation source in a "
        "layout the target repos actually use. The seal author is not "
        "independent of the fixer, which is the separation the whole "
        "scaffold-first protocol rests on"
    )
    violation = next(
        v for v in evaluate_changed_paths(rule, [path]) if v.path == path
    )
    assert violation.matched_glob.strip(), violation
    assert violation.rationale.strip(), (
        "a violated row must print why the path is not the role's to touch"
    )


@pytest.mark.parametrize("path", _SEAL_PATHS)
def test_seals_can_write_the_seal_that_sits_beside_the_implementation(
    path: str,
) -> None:
    """The over-block half, and it is a false refusal with no override.

    ``**/src/**`` is not only too narrow, it is also too wide. A TypeScript app
    under ``web/src/`` and a Maven module under ``services/billing/src/`` both
    keep their seals inside a ``src/`` tree, and the glob denies those seals to
    the one role that exists to write them. ``immutable_paths:`` is ADD-only
    and there is no negation syntax, so a task row cannot buy them back and
    neither can ``.dispatcher.yaml``. The build simply cannot be driven for
    those units.

    The control is in the same call: ``schema/merge.yaml`` must STAY denied, so
    a rule that permits everything cannot satisfy this row. That control is the
    reason this seal cannot be read as asking to widen SEALS generally.

    RED today for ``web/src/app.test.tsx`` and
    ``services/billing/src/test/java/InvoiceTest.java`` (both denied by
    ``**/src/**``).
    GREEN today for the six others, and they are here as the regression pin:
    whatever replaces the table must not lose them. In particular
    ``internal/wallet/testdata/ledger_golden.json`` and
    ``tests/fixtures/ledger_seed.sql`` are seal artifacts, not implementation.

    Falsify: add ``**/*_test.go`` to the SEALS deny set (the naive "extend it"
    fix) — three rows go red. Deny ``**/testdata/**`` to SEALS — one more.
    """
    rule = _seals_rule()
    denied = _denied(rule, [path, _A_PATH_SEALS_MUST_NOT_HAVE])

    assert _A_PATH_SEALS_MUST_NOT_HAVE in denied, (
        f"the control failed: SEALS may write {_A_PATH_SEALS_MUST_NOT_HAVE!r}, "
        "so this seal would pass for a rule that permits everything"
    )
    assert path not in denied, (
        f"a SEALS agent may NOT write {path!r}, which is a seal. A seal author "
        "that cannot write the seal cannot do its job, and a false refusal has "
        f"no override in this system: {denied.get(path)!r} denied it"
    )


def test_the_gates_two_answers_to_is_this_a_seal_agree_in_the_target_layouts() -> None:
    """One matcher, one fact — checked in the layouts the targets actually use.

    The shape is `test_risk.test_go_table_critical_paths_are_all_authority_paths`
    and this module's own
    `test_every_seal_verify_test_path_is_denied_to_every_delegated_role`, turned
    on the SEALS role. Two independent notions of "is this a seal" that can
    disagree is invariant 5's failure mode. The gate has exactly two:

      * ``seal_verify.is_test_path`` — what the inversion gate keeps when it
        reverts a change;
      * the SEALS rule — what the seal author may write.

    They must give the same answer, because they are answering the same
    question: a path the first calls a seal and the second denies is a seal
    author refused its own seal, and a path the first calls implementation and
    the second permits is a seal author writing the code it is judging.

    Every row's ``is_test`` flag is cross-checked against the live matcher
    before it is used, so this table cannot quietly drift away from the thing
    it is here to agree with — and if `is_test_path` changed underneath, this
    reddens instead of silently re-baselining.

    Non-vacuity: the corpus carries 12 implementation rows and 7 seal rows, so
    neither "deny everything" nor "deny nothing" passes. Nothing here is
    derived from ``DEFAULT_ROLE_RULES``.

    RED today, both directions, 7 disagreements:
      * writable but not a seal: ``cmd/classify/main.go``,
        ``internal/wallet/ledger.go``, ``pkg/api/handler.go``,
        ``web/components/Button.tsx``, ``db/migrations/0007_add_bay_flags.sql``
      * denied but IS a seal: ``web/src/app.test.tsx``,
        ``services/billing/src/test/java/InvoiceTest.java``

    Falsify: flip any row's flag — the row's own cross-check goes red first.
    """
    rule = _seals_rule()
    paths = [path for path, _flag in _LAYOUT_COHERENCE_ROWS]
    denied = _denied(rule, paths)

    seal_rows = [p for p, flag in _LAYOUT_COHERENCE_ROWS if flag]
    body_rows = [p for p, flag in _LAYOUT_COHERENCE_ROWS if not flag]
    assert len(seal_rows) >= 5 and len(body_rows) >= 5, (
        "the corpus must exercise both directions or this seal is one-sided"
    )

    disagreements: list[str] = []
    for path, is_seal in _LAYOUT_COHERENCE_ROWS:
        assert is_test_path(path) is is_seal, (
            f"the corpus says is_test_path({path!r}) is {is_seal}, the matcher "
            f"says {is_test_path(path)}. Fix the row, not the matcher"
        )
        if is_seal and path in denied:
            disagreements.append(
                f"{path} is one of this repo's tests and SEALS is denied it "
                f"by {denied[path]!r} — the seal author cannot write its seal"
            )
        if not is_seal and path not in denied:
            disagreements.append(
                f"{path} is implementation and SEALS may write it — the seal "
                "author can make its own seal pass"
            )
    assert not disagreements, (
        "the gate's two answers to 'is this a seal' disagree in the target "
        "layouts:\n  " + "\n  ".join(disagreements)
    )


# --------------------------------------------------------------------------- #
# 3. The mirror: BODIES must not be able to write a seal in those same layouts.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", _SEAL_PATHS)
def test_bodies_cannot_write_a_seal_in_the_target_layouts(path: str) -> None:
    """The mirror obligation, measured rather than assumed.

    GREEN today, all eight rows, and that is the finding: BODIES does NOT have
    the layout blindness SEALS has. The reason is structural and worth stating,
    because it is the diagnosis for the SEALS defect: the BODIES rule denies by
    FILE SHAPE (``**/*_test.go``, ``**/*.test.*``, ``**/testdata/**``) plus the
    ``seal_verify.is_test_path`` delegation, and a filename convention travels
    with the language. The SEALS rule denies by DIRECTORY LAYOUT
    (``**/src/**``), and a directory convention does not. One rule was written
    per language, the other was written for one ecosystem.

    It is a regression pin, not a request, and it can fail — but MEASURED, not
    asserted, because the first falsification this docstring claimed was wrong
    and the measurement is the correction:

      * deleting ``**/*_test.go`` from the BODIES row reddens NOTHING here.
        The three Go rows stay denied by the ``seal_verify.is_test_path``
        delegation, with ``matched_glob`` changing from ``**/*_test.go`` to
        :data:`SEAL_VERIFY_TEST_PATHS`. That is the delegation working as
        designed — ``built_in_policy`` appends the marker precisely so a glob
        gap is backstopped — and that single-glob deletion is caught where it
        belongs, by this pair's row in `test_role_protocol_table.py`.
      * deleting ``Role.BODIES`` from ``TEST_PATH_DELEGATED_ROLES`` reddens the
        Maven row (``services/billing/src/test/java/InvoiceTest.java``), which
        the globs do not reach.
      * deleting BOTH reddens four rows: the three Go rows and the Maven row.

    The asymmetry that measurement exposes IS the finding of this section.
    BODIES is defended in depth — a filename glob AND the delegation, either
    alone sufficient for the Go layout. SEALS has neither: no delegation, and a
    single directory glob written for one ecosystem. The two roles were not
    given the same care, and only one of them is load-bearing for the primary
    target's primary language.

    Falsify: remove the test-shaped globs from the BODIES row AND the
    delegation.
    """
    rule = _bodies_rule()
    denied = _denied(rule, [path, _A_PATH_SEALS_MUST_KEEP])
    assert _A_PATH_SEALS_MUST_KEEP not in denied, (
        f"the control failed: BODIES may not write {_A_PATH_SEALS_MUST_KEEP!r}"
    )
    assert path in denied, (
        f"a BODIES agent may write {path!r}, which is a seal. A body author "
        "that can edit the seal makes it pass by editing it, which is the "
        "vacuous-seal shape the protocol exists to remove"
    )


@pytest.mark.parametrize("path", _IMPLEMENTATION_PATHS)
def test_bodies_can_still_write_the_implementation_the_seal_pins(
    path: str,
) -> None:
    """The upper bound on the row above, and the reason it is not vacuous.

    BODIES exists to write implementation. A fix that reached for "deny every
    Go file to BODIES" would satisfy the mirror seal and make the protocol
    undrivable, with no override. These rows say so.

    GREEN today, all seven. Falsify: deny ``**/*.go`` or ``**/internal/**`` to
    BODIES — every Go row goes red while the mirror seal stays green, which is
    exactly the failure this row exists to catch.
    """
    denied = _denied(_bodies_rule(), [path])
    assert path not in denied, (
        f"a BODIES agent may no longer write {path!r}, which is the "
        f"implementation it exists to write: denied by {denied[path]!r}"
    )


# --------------------------------------------------------------------------- #
# 4. Machinery. Two latent defects in their own right, and the two an
#    inversion would walk into. Neither mandates a table.
# --------------------------------------------------------------------------- #


def test_the_delegation_marker_means_the_same_thing_in_an_allow_only_rule() -> None:
    """:data:`SEAL_VERIFY_TEST_PATHS` is a FACT; the rule's KIND is the verdict.

    The marker is documented as "a property of the rule (data), not of the role
    (a hardcode a caller-supplied policy could not switch off)", and its meaning
    is fixed: *this repo's test files*. But
    :func:`evaluate_changed_paths` reads it in the DENY_GLOBS branch only. In
    the ALLOW_ONLY_GLOBS branch it falls through to
    ``first_matching_glob``, which — as that function's own docstring says —
    matches nothing on the marker because it contains no wildcard. So a rule
    that says "the writable set is this repo's test files" silently means "the
    writable set is empty", and denies every path including the seals.

    That is a fail-shape on its own terms, independent of what the SEALS table
    becomes: the module has one marker with one meaning and one of its two
    consumers ignores it. It is also precisely what an inversion needs, which
    is why it is sealed here rather than assumed.

    Two controls make this non-vacuous. A non-test path under the same rule
    must still be a violation carrying :data:`ALLOWLIST_MISS`, so "allow
    everything when the marker is present" fails. And the DENY side is asserted
    in the same test on the same two paths with the opposite verdict, so an
    implementation that made the marker mean the same THING in both kinds —
    rather than the same FACT — fails too.

    RED today: ``internal/wallet/ledger_test.go`` is a violation under the
    allow-only rule.
    Falsify: make the marker match paths in `first_matching_glob` — the DENY
    half's ``matched_glob`` assertions in `test_role_protocol_table.py` change
    meaning and this test's control goes red.
    """
    allow_only = RoleRule(
        role=Role.SEALS,
        kind=RuleKind.ALLOW_ONLY_GLOBS,
        globs=(SEAL_VERIFY_TEST_PATHS,),
        rationale="probe: the writable set is this repo's test files",
    )
    seal = "internal/wallet/ledger_test.go"
    body = "internal/wallet/ledger.go"
    assert is_test_path(seal) and not is_test_path(body)

    allowed = _denied(allow_only, [seal, body])
    # The control first: a non-test path is still outside the writable set.
    assert body in allowed, (
        "the control failed: an allow-only rule carrying the marker let a "
        "non-test path through, so it allows everything"
    )
    assert allowed[body] == ALLOWLIST_MISS, allowed[body]
    assert seal not in allowed, (
        "an ALLOW_ONLY rule whose writable set is the delegation marker "
        f"denies {seal!r} — one of this repo's tests. The marker names a fact "
        "and the KIND decides whether that fact allows or denies; today the "
        "allow-only branch cannot read it at all, so such a rule refuses every "
        "path in the repository"
    )

    # The same marker, the same fact, the opposite kind — asserted here so the
    # two branches cannot be given two meanings.
    deny = RoleRule(
        role=Role.BODIES,
        kind=RuleKind.DENY_GLOBS,
        globs=(SEAL_VERIFY_TEST_PATHS,),
        rationale="probe: the deny set is this repo's test files",
    )
    denied = _denied(deny, [seal, body])
    assert seal in denied and denied[seal] == SEAL_VERIFY_TEST_PATHS
    assert body not in denied


def test_an_effective_rule_never_hands_a_role_an_allow_set_that_forbids_everything() -> (
    None
):
    """:func:`effective_rule` discards an ALLOW_ONLY role's POLICY globs.

    The ALLOW_ONLY branch is written to ADJUDICATE's semantics and applied to
    the kind: ``built = replace(rule, globs=tuple(spec.disputed_paths))``. For
    ADJUDICATE that is right — its writable set is per-task data and
    ``disputed_paths:`` is required. For any OTHER role that ever holds an
    allow-only rule it is a silent total refusal: ``disputed_paths`` is empty
    (it is a typed error on every role but ADJUDICATE), the policy's own allow
    set is thrown away, and :func:`validate_rule` permits an empty ALLOW_ONLY
    tuple, so nothing raises. The role is handed a rule under which every path
    in the repository is a violation.

    This is the fail-shape ``RuleKind.UNRESTRICTED``'s own docstring names,
    seen from the other end: "an accidentally-emptied deny list can never read
    as a pass" is sealed, and "an accidentally-emptied ALLOW list reads as a
    refusal of everything" is not. It fails closed, but a false refusal has no
    override in this system, so the build stops with no way past it.

    The control is the ADJUDICATE path in the same test: a spec that DOES carry
    ``disputed_paths`` must still get exactly those, and must still be denied
    everything else. So this cannot be satisfied by ignoring ``disputed_paths``,
    which would break the role the branch was written for.

    RED today: the first assertion. ``tests/test_x.py`` is a violation under a
    policy that explicitly allows ``**/tests/**``.
    Falsify: make the ALLOW_ONLY branch return ``spec.disputed_paths``
    unconditionally again — the first assertion goes red. Make it ignore
    ``disputed_paths`` — the ADJUDICATE control goes red.
    """
    allow_only = RoleRule(
        role=Role.SEALS,
        kind=RuleKind.ALLOW_ONLY_GLOBS,
        globs=("**/tests/**",),
        rationale="probe: the policy names this role's writable set",
    )
    adjudicate = built_in_policy().rule_for(Role.ADJUDICATE)
    legacy = built_in_policy().rule_for(Role.LEGACY)
    scaffold = built_in_policy().rule_for(Role.SCAFFOLD)
    bodies = built_in_policy().rule_for(Role.BODIES)
    policy = RolePolicy(
        rules=(scaffold, allow_only, bodies, adjudicate, legacy),
        source=PolicySource.BUILT_IN_DEFAULTS,
    )

    spec = TaskRoleSpec(task_key="U-1", role=Role.SEALS)
    built = effective_rule(spec, policy)
    assert _denied(built, ["tests/test_x.py"]) == {}, (
        "the effective rule discarded the policy's allow set, so every path in "
        "the repository is a violation for this task — a total false refusal "
        f"with no override. Built globs: {built.globs!r}"
    )
    # And it must still be an allowlist, not silently widened.
    assert _denied(built, ["internal/wallet/ledger.go"]), (
        "the effective rule stopped being an allowlist"
    )

    # The control: ADJUDICATE's per-task writable set must be untouched.
    disputed = TaskRoleSpec(
        task_key="U-2",
        role=Role.ADJUDICATE,
        disputed_paths=("docs/adr/0007.md",),
    )
    ruled = effective_rule(disputed, policy)
    assert _denied(ruled, ["docs/adr/0007.md"]) == {}
    assert _denied(ruled, ["tests/test_x.py"]), (
        "ADJUDICATE's writable set must come from its own disputed_paths"
    )
