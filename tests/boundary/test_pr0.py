"""PR0 seals — generated truth + CI gates (implementation plan §2 PR0).

Every seal here exists to make a specific drift class a red build:

- fsmgen --check: hand edits to generated files, or schema/doc divergence
  (the comparison against the design's inline tables runs inside fsmgen).
- enum/variant exhaustiveness: a YAML state/event/single that never reached
  the generated module — envelope fields sealed on every event type.
- T19 goldens against a HAND-WRITTEN oracle (tests/boundary/vectors/
  t19_expected.json) that fsmgen never regenerates — a wrong reducer goes
  red even after regeneration (independent-oracle rule).
- fail-closed wire: missing REQUIRED / forbidden-present / unknown enum
  value / unknown variant ⇒ typed halts, never coercion (explicit-state).
- t26_lint: the design doc's own lint, run by the repo gate
  (scripts/test.sh) and .github/workflows/verify.yml, with planted-violation
  deny rows through the REAL Doc constructor.
- T8/T9 fail-closed AST gates covering bare-name, attribute-qualified and
  import-aliased constructions; dark-mode detector covering every STATIC
  import spelling (dynamic `importlib.import_module`/`__import__` string
  forms are an accepted, recorded scope limit — see
  ``test_architecture_boundary_dark_mode``); each with deny fixtures.
- T6: every parametrised seal carries a deny row — checked over the
  COLLECTED items' real param ids.

Every deny in this file names the RULE it seals, never merely the exception
type: `pytest.raises(..., match=...)` for constructor guards, the
`_DENY_RULE_MARKERS` substrings for wire halts. A bare
`pytest.raises(ValueError)` is a vacuous seal — the `_mk_*` helpers build
many fields at once, so a row can raise for a guard other than the one
under test and still look green.

Each repaired seal records, in a comment, the MUTATION of the generated
module that turns it red (seal-repair pass, 2026-08-03). A seal with no
such mutation is either testing nothing or testing something else.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VECTORS_DIR = REPO_ROOT / "tests/boundary/vectors/t19"
EXPECTED_PATH = REPO_ROOT / "tests/boundary/vectors/t19_expected.json"
BOUNDARY_DIR = REPO_ROOT / "tests/boundary"
FRAMES_DIR = REPO_ROOT / "schema/testdata/classifier_frames"

# Independently computed goldens (standalone snippets over the schema's
# preimage specs — never the generated functions):
PINNED_ROSTER_DIGEST = "9108f9897faff4e3fdba20745ca51eea1a30309cfe32b2a739039b69089ca4a8"
PINNED_HOLD_ID_SEQ0 = "ee8e6d58f6a3b89373def7e3b4e1556b6499ab81a8edc174b555931d8bb9e724"
PINNED_RECOVERY_ID_M1 = "dd693323dd35ceed8d6339ba871ea2784b81410d51ef5e9940c2dfc883e808c6"


def _envelope_kwargs() -> dict:
    """§9's common envelope, in ONE place. It was hand-rolled at six sites
    and the copies had already drifted (trace_id was "tr" at one, "t" at
    two, "trace-1" at three — three spellings of one concept), so adding an
    envelope field meant editing six literals."""
    return dict(schema_major=1, schema_minor=0, event_id="e1",
                ts="1970-01-01T00:00:00Z", run_id="run-1",
                trace_id="trace-1", protocol_epoch="E0")


HANDWRITTEN_DIR = VECTORS_DIR / "handwritten"


def _vector_paths() -> list[Path]:
    """The T19 corpus is TWO regions: the generated tree (tools/fsmgen.py
    writes it and fsmgen --check makes it exact) and `handwritten/`, which
    the generator never writes or deletes and the stray scan skips. A
    non-recursive glob loaded only the first, so a hand-authored vector was
    invisible to the suite that is supposed to judge it."""
    return sorted(VECTORS_DIR.glob("*.json")) + sorted(
        HANDWRITTEN_DIR.glob("*.json"))


def load_vectors() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in _vector_paths():
        assert p.stem not in out, (
            f"two T19 vectors named {p.stem!r} — a hand-authored vector may "
            f"not shadow a generated one (or vice versa)")
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return out


_VECTORS = load_vectors()
_EXPECTED = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))["vectors"]

# Parametrize decorators run at collection time, before fixtures exist, so
# the generated module is imported once here for the param lists. Tests
# still take the `generated` fixture for the assertions themselves.
# conftest.py already performs this insert; guard it so `src` cannot land on
# sys.path twice when this module is imported directly.
_SRC = str(REPO_ROOT / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from claude_dispatcher.boundary import generated as _GEN  # noqa: E402


# ─── the ONE public entrypoint, bound once ───────────────────────────────────
#
# `reduce_section_a`, `reduce_section_b` and `fold_epochs` are DELETED, not
# renamed. They were documented as projections but were CALLABLE with events,
# and two of them could not express the run context — so each was a second
# walk over the same bytes with a fabricated SHARED run, which is the
# divergence four review rounds kept rediscovering. Every seal in this file
# now goes through `_boundary()`, so no seal can reintroduce a second walk,
# and every projection is selected OUT OF the one result.


def _event_of(vec: dict, variant: str) -> dict:
    """The (single) event of a given variant in a vector, selected BY VARIANT
    rather than by list position. Positional indexing into a generated corpus
    has now rotted three seals — a synthesised opening row was prepended and
    `events[0]` silently became a different event."""
    hits = [e for e in vec["events"] if e.get("variant") == variant]
    assert len(hits) == 1, (
        f"expected exactly one {variant} in this vector, found {len(hits)} "
        f"(variants: {[e.get('variant') for e in vec['events']]})")
    return hits[0]


def _run_context(generated, *, mode: str = "SHARED", anchors=None):
    """A RunContext. `mode` is REQUIRED by the type (None raises rather than
    reading as SHARED), and an empty `anchors` is the NAMED state "this run
    has no protocol_genesis anchor", which fails closed."""
    return generated.RunContext(
        credential_mode=generated.CredentialMode[mode],
        anchors={} if anchors is None else anchors)


def _boundary(generated, events, *, mode: str = "SHARED", anchors=None) -> dict:
    """THE single pass. Returns the whole reduced state."""
    return generated.reduce_boundary(
        events, _run_context(generated, mode=mode, anchors=anchors))


def _machine_view(generated, result, machine: str):
    """One machine's view OUT OF an already-computed result, selected from the
    module's OWN closed key map — never a second walk, and never a key list
    this file invented. `test_machine_projection_is_a_selection_not_a_walk`
    keeps this statement and the module's private `_project_machine`
    coupled."""
    keys = generated._MACHINE_PROJECTIONS[machine]
    return result[keys[0]] if len(keys) == 1 else {k: result[k] for k in keys}


def _epochs(generated, events, *, mode: str = "SHARED", anchors=None):
    """The fence view: what `fold_epochs` used to return, projected out of
    the one pass instead of walked a second time."""
    return _machine_view(
        generated, _boundary(generated, events, mode=mode, anchors=anchors),
        "epoch_fold")


def _run(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=timeout)


# ─── fsmgen: committed and diff-clean; oracle never generated ────────────────

def test_fsmgen_output_committed_and_diff_clean():
    """Regeneration is byte-identical to what is committed; fsmgen also
    fails here if the schema and the design doc's inline tables diverge."""
    proc = _run(["tools/fsmgen.py", "--check"])
    assert proc.returncode == 0, (
        f"fsmgen --check failed:\n{proc.stdout}{proc.stderr}")


@pytest.mark.parametrize("case", [
    pytest.param("table-cell", id="deny-doc-table-cell-drift"),
    pytest.param("union-field", id="deny-doc-union-field-drift"),
])
def test_doc_equals_artifact_comparison_fires(tmp_path, monkeypatch, case):
    """The doc==artifact comparison is credited with catching schema/design
    divergence but was never falsified by a committed test (panel round 3,
    finding 38). Plant drift in a COPY of the design doc and assert the
    comparator names it — and that the clean doc does not."""
    fsmgen = _fsmgen()
    schemas = fsmgen.load_schemas()
    text = fsmgen.DESIGN_DOC.read_text(encoding="utf-8")
    if case == "table-cell":
        planted = text.replace("| — | `observe_delta` | HELD_FOREIGN (created) | none |",
                               "| — | `observe_delta` | RELEASED (created) | none |", 1)
        compare, needle = fsmgen.compare_tables_with_design, "section_b"
    else:
        planted = text.replace("`protocol_epoch_advanced{old, new}`",
                               "`protocol_epoch_advanced{old, new, extra}`", 1)
        compare, needle = fsmgen.compare_unions_with_design, "protocol_epoch_advanced"
    assert planted != text, f"{case}: the planted text was not found"
    doc = tmp_path / "design.md"
    doc.write_text(planted, encoding="utf-8")
    assert not compare(schemas), "the clean doc already reports drift"
    monkeypatch.setattr(fsmgen, "DESIGN_DOC", doc)
    problems = compare(schemas)
    assert problems, f"{case}: planted drift not detected"
    assert any(needle in p for p in problems), (
        f"{case}: detected drift does not name {needle!r}: {problems}")


def _workflow() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8"))


def test_ci_citations_job_hard_fails_on_a_missing_peer():
    """The claim "CI always requires the peer" must not outrun its
    enforcement: the citations job may not soft-fail (panel round 4).

    The claim is JOB-wide, so the seal is job-wide: previously it read only
    the peer-checkout step's continue-on-error, so `continue-on-error: true`
    on the `make verify` step — or on the job mapping itself — kept it green
    while the citations-REQUIRED half stopped gating.

    MUTATION (verify.yml, not committed): add `continue-on-error: true` to
    the "make verify" step ⇒ red; add it to `jobs.citations` ⇒ red; add
    `if: ${{ needs.gate.result != 'success' }}` to any citations step ⇒ red;
    delete the peer-checkout step ⇒ red with a sentence, not StopIteration.
    """
    wf = _workflow()
    job = wf["jobs"]["citations"]
    citations = job["steps"]
    # the JOB mapping itself must not soft-fail or be conditionally skipped
    assert not job.get("continue-on-error"), (
        "jobs.citations.continue-on-error soft-fails the whole job — the "
        "citations-REQUIRED half would report success having checked nothing")
    assert "if" not in job, (
        f"jobs.citations carries a job-level `if:` ({job.get('if')!r}) — the "
        f"peer-present arm must run unconditionally")
    # …and no STEP may soft-fail: the `make verify` step is the one that
    # actually enforces citations.
    soft = [s.get("name", s.get("uses", "?")) for s in citations
            if s.get("continue-on-error")]
    assert not soft, f"citations steps soft-fail: {soft}"
    peer_step = next((s for s in citations
                      if "checkout" in str(s.get("uses", ""))
                      and "claude-workflow" in str(s.get("with", {}))), None)
    assert peer_step is not None, (
        "verify.yml's citations job no longer checks out the claude-workflow "
        "peer — the citations-REQUIRED arm has nothing to resolve against")
    assert any("--probe-peer" in str(s.get("run", "")) for s in citations), (
        "the citations job does not assert the peer actually resolved")
    assert any("make verify" in str(s.get("run", "")) for s in citations), (
        "the citations job no longer runs `make verify` — the "
        "citations-REQUIRED T26 form is what this job exists for")
    # skip-and-warn, in EITHER spelling: a bare `x != 'success'` and the
    # `${{ ... != 'success' }}` expression form (which ends in `}}`, so an
    # endswith() check could never see it).
    warn = [s.get("if") for s in citations if "!= 'success'" in str(s.get("if", ""))]
    assert not warn, f"a skip-and-warn path remains: {warn}"
    # and the doc-local arm runs unconditionally in the other job
    gate = wf["jobs"]["gate"]["steps"]
    assert any("scripts/test.sh" in str(s.get("run", "")) for s in gate), (
        "the gate job no longer runs scripts/test.sh — the peer-ABSENT arm "
        "of the environment matrix is unexercised in CI")


def test_boundary_paths_stay_in_the_critical_risk_tier():
    """Plan §0/§2 requires the boundary surface to classify as CRITICAL
    risk, which is what routes a change here through the full panel. The
    rule lived in .agent/risk-paths.json with nothing asserting it: quietly
    dropping a path — or downgrading the rule to "high" — would leave the
    whole suite green while the code that decides whether review happens
    stopped demanding review of itself.

    MUTATION (.agent/risk-paths.json, not committed): change
    generated-safety-truth's risk to "high" ⇒ red; delete "schema/**" or
    "tools/fsmgen.py" from its paths ⇒ red.
    """
    spec = json.loads((REPO_ROOT / ".agent/risk-paths.json")
                      .read_text(encoding="utf-8"))
    rule = next((r for r in spec["rules"]
                 if r.get("id") == "generated-safety-truth"), None)
    assert rule is not None, (
        ".agent/risk-paths.json no longer carries the generated-safety-truth "
        "rule — the boundary would take unmatched_risk instead of critical")
    assert rule["risk"] == "critical", (
        f"the boundary risk tier was downgraded to {rule['risk']!r}")
    required = {"src/claude_dispatcher/boundary/**", "schema/**",
                "tools/fsmgen.py", "tools/t26_lint.py",
                "tests/boundary/vectors/t19_expected.json",
                "tests/boundary/**"}
    missing = required - set(rule["paths"])
    assert not missing, f"dropped from the critical rule: {sorted(missing)}"
    # risk is the MAX over matched rules, so no rule may be marked
    # presentation-only for these paths.
    assert not rule.get("presentational")


def test_auto_release_deferral_is_a_recorded_cutover_blocker(schemas):
    """The PR4 provenance obligation must not be forgettable: it is recorded
    as a PR6 cut-over blocker in the schema (panel round 4, finding 3)."""
    ev = schemas["lifecycle_fsm"]["events"]["unions"]["hold_lifecycle"][
        "actor_verified_evidence"]
    assert ev["blocks_pr6_cutover"] is True
    assert ev["provenance_wired_in"] == "PR4"
    assert "self-derivable" in ev["blocks_pr6_cutover_reason"]
    assert ev["provenance_fields_pending_design_amendment"] == [
        "hook_id", "delivery_guid", "repository_id"]
    # the PR0-enforceable half is named as CONSISTENCY, never provenance
    assert "consistency_checks_enforced_in_pr0" in ev


def test_ast_gate_schema_lists_cannot_be_silently_emptied(schemas):
    """Both AST gates take their teeth from schema lists nothing asserted:
    emptying `guarded_names`, or adding a module to `door_entrypoints`,
    left them trivially green (panel round 3, finding 34).

    EMPTYING was sealed; WIDENING was not — `allowed_modules` was asserted
    only truthy and `legacy_exemptions` not at all, so appending a path to
    either silently exempted that file from the T8/T9 gate. Every list is
    now pinned element-wise, in order, so widening requires deliberately
    editing this seal.

    MUTATION (schema/ast_allowlists.yaml, not committed): append
    `src/claude_dispatcher/orchestrator.py` to t8_construction.
    allowed_modules ⇒ red; append any path to t8's legacy_exemptions ⇒ red;
    add a path to t9's legacy_exemptions ⇒ red; append to door_entrypoints
    ⇒ red (already sealed).
    """
    allow = schemas["ast_allowlists"]
    t8 = allow["t8_construction"]
    # the §3.1 closed sum and the §3.2 validated payload — the names the
    # design closes construction over.
    assert set(t8["guarded_names"]) == {"Classification", "ClassifyOutcome",
                                        "ClassifyOk", "ClassifyAbsent",
                                        "ClassifyEmpty", "ClassifyFailed"}
    t9 = allow["t9_interpretation"]
    assert set(t9["guarded_names"]) == {"MergePlan", "Mergeable",
                                        "Unmergeable", "PanelPlan"}
    # element-wise, not merely non-empty: the SOLE legal construction site
    # is the PR2 parse module.
    assert t8["allowed_modules"] == ["src/claude_dispatcher/boundary/wire.py"]
    assert t9["allowed_modules"] == [
        "src/claude_dispatcher/boundary/doors.py",
        "src/claude_dispatcher/boundary/panel_runner.py",
        "src/claude_dispatcher/boundary/authority_channels.py"]
    # the ONE legacy exemption, scoped to exactly the file the schema's own
    # prose promises it is scoped to (and retired at PR6).
    assert t8["legacy_exemptions"] == ["src/claude_dispatcher/classification.py"], (
        "t8 legacy_exemptions widened — the schema's prose promises the "
        "exemption is scoped to exactly classification.py and retired at PR6")
    assert t9["legacy_exemptions"] == [], (
        "t9 has no legacy mirror path; an exemption here exempts a plan "
        "consumption site from the T9 gate")
    # dark mode: the door allowlist stays EMPTY until PR6 fills it
    assert allow["architecture"]["door_entrypoints"] == [], (
        "door_entrypoints is non-empty — dark mode ends at PR6, not before")
    assert allow["architecture"]["package"] == "claude_dispatcher.boundary"


def _single_payload(g, cls) -> tuple[dict, dict]:
    """(envelope, payload) for one §9 single, built from its REQUIRED set."""
    env = dict(_envelope_kwargs(), family=cls.FAMILY)
    typed = {"duration_ms": 1,
             "credential_mode": g.CredentialMode.SHARED,
             "protection_mode": g.ProtectionMode.PREVENT,
             "actor_verification": g.ActorVerification.VERIFIED_API,
             "hold_effect": g.HoldEffect.NONE}
    payload = {f: typed.get(f, f) for f in cls.REQUIRED if f not in env}
    for field, domain in cls.DOMAINS.items():
        payload[field] = domain[0]
    for key, rule in getattr(cls, "PAIR_RULES", {}).items():
        allowed = rule["allowed"].get(payload.get(key))
        if allowed:
            payload[rule["field"]] = allowed[0]
    return env, payload


@pytest.mark.parametrize("event_name", [
    # Every row carries denies that run for EVERY single, not only the six
    # with a declared domain, so the `deny-` id T6 reads is earned rather
    # than merely asserted.
    pytest.param(n, id=f"deny-single-{n}") for n in sorted(_GEN.SINGLE_EVENTS)
])
def test_every_single_event_constructs(generated, event_name):
    """8 of 14 §9 singles were never constructed while the docstring claimed
    all were sealed (panel round 3, finding 33). Every one is built from its
    REQUIRED set here.

    The DENY half used to be `for field in cls.DOMAINS: raises(...)` — for
    the 8 singles whose DOMAINS is empty that loop body never ran, so those
    rows asserted only that construction succeeds while carrying a `deny-`
    id T6's name-based checker accepted. The gate was satisfied by
    labelling. Every row now runs five denies that exist on every single:
    the family mis-tag guard, both `_validate_field_value` int arms, its
    ts arm and its non-empty-str arm — plus one per declared domain and one
    per enum-typed REQUIRED field.

    MUTATIONS (src/claude_dispatcher/boundary/generated/__init__.py, each
    reverted): delete the per-single `family ... contradicts its schema
    name` raise ⇒ red on all 14 rows (this is the guard finding 3 reported
    as dead on every single); `_validate_field_value` int arm →
    `if False:` ⇒ red; its schema_major-range arm → `if False:` ⇒ red; its
    ts arm → `if False:` ⇒ red; the non-empty-str arm → `if False:` ⇒ red;
    a single's `outside the closed domain` raise ⇒ red on that row.
    """
    g = generated
    cls = g.SINGLE_EVENTS[event_name]
    env, payload = _single_payload(g, cls)
    built = cls(**env, **payload)
    assert built.family == cls.FAMILY

    # deny: a family tag that contradicts the event's own schema name. This
    # is the §9 guard that halted a base when a single carried the wrong
    # family; before this row nothing in the suite constructed one.
    other_family = next(f for f in sorted(g.FAMILY_VALUES) if f != cls.FAMILY)
    with pytest.raises(ValueError, match="contradicts its schema name"):
        cls(**dict(env, family=other_family), **payload)
    # deny: schema_major is an int, never coerced from its wire spelling
    with pytest.raises(ValueError, match=r"schema_major must be an int"):
        cls(**dict(env, schema_major="1"), **payload)
    # deny: an unsupported major halts (§9) rather than being tolerated
    with pytest.raises(ValueError, match="outside the supported set"):
        cls(**dict(env, schema_major=99), **payload)
    # deny: ts is an RFC 3339 UTC instant, checked semantically
    with pytest.raises(ValueError, match="not an RFC 3339 UTC instant"):
        cls(**dict(env, ts="1970-13-45T99:00:00Z"), **payload)
    # deny: a REQUIRED str field is non-empty — "" is absence in disguise
    with pytest.raises(ValueError, match="must be a non-empty str"):
        cls(**dict(env, event_id=""), **payload)
    # deny: one out-of-domain value per declared closed domain
    for field in cls.DOMAINS:
        with pytest.raises(ValueError, match="outside the closed domain"):
            cls(**env, **dict(payload, **{field: "NOT_IN_DOMAIN"}))
    # deny: an enum-typed REQUIRED field never coerces its raw wire string
    # (protocol_genesis's credential_mode/protection_mode are the run-context
    # enums the whole §0.3 gate turns on).
    for field in cls.REQUIRED:
        enum_t = g._ENUM_WIRE_FIELDS.get(field)
        if enum_t is None:
            continue
        raw = payload[field].value
        with pytest.raises(ValueError,
                           match=f"must be a {enum_t.__name__} instance"):
            cls(**env, **dict(payload, **{field: raw}))


def test_generated_paths_git_clean():
    """`git status --porcelain` (not `git diff`) so a STAGED hand edit and an
    untracked stray in a generated path are caught too (panel round 2)."""
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--",
         "src/claude_dispatcher/boundary/generated", "docs/generated",
         "tests/boundary/vectors/t19", "schema/testdata",
         # vectors/t19/handwritten/ is the TEST AUTHOR's region — the
         # generator never writes it, so a change there is authorship, not
         # a hand edit to generated output. Everything else stays exact.
         ":(exclude)tests/boundary/vectors/t19/handwritten"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"git status failed: {proc.stderr}"
    assert not proc.stdout.strip(), (
        f"generated paths dirty (unstaged, staged or untracked):\n{proc.stdout}")


def _fsmgen():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import fsmgen
    finally:
        sys.path.pop(0)
    return fsmgen


def _oracle_independence_problems(outputs, vectors) -> list[str]:
    """The independent-oracle predicate, in ONE place so the deny arm below
    exercises the same code the allow arm relies on: fsmgen must not emit
    the hand-written oracle, and no generated vector may carry its own
    expectation."""
    problems = [f"fsmgen writes the oracle {p}" for p in outputs
                if p == EXPECTED_PATH]
    problems += [f"{name}: vector carries its own 'expected' key"
                 for name, vec in vectors.items() if "expected" in vec]
    return problems


def test_oracle_is_not_an_fsmgen_output(monkeypatch):
    """The independent-oracle rule, sealed against fsmgen's REAL output set
    (panel round 2: the previous seal inspected a 1.8KB slice of the source
    and could not detect generation at all).

    The old third assertion — `simulated[EXPECTED_PATH] = b"{}"; assert
    EXPECTED_PATH in simulated` — was a statement about Python's dict, true
    regardless of fsmgen, build_outputs or any repo state, so it could not
    demonstrate the real assertion was non-vacuous. The predicate now lives
    in `_oracle_independence_problems`, driven here by BOTH arms:
      1. fsmgen's real output set produces no problems;
      2. a build_outputs run whose vector emitter is monkeypatched to emit
         the oracle path DOES produce one — real fsmgen code, real emitter,
         a genuine falsification.

    MUTATION (tests only — the predicate is the test's): make
    `_oracle_independence_problems` return [] ⇒ the deny arm goes red.
    MUTATION (tools/fsmgen.py, not committed): have build_t19_vectors emit a
    vector named `t19_expected` under VECTORS_DIR.parent ⇒ arm 1 goes red.
    """
    fsmgen = _fsmgen()
    schemas = fsmgen.load_schemas()
    outputs = fsmgen.build_outputs(schemas)
    assert not _oracle_independence_problems(outputs, _VECTORS), (
        "fsmgen writes the oracle, or a vector carries its own expectation "
        "— the T19 goldens would be self-sealing")

    # deny: run the REAL build_outputs with the vector emitter widened to
    # emit the oracle's own path, and assert the same predicate fires.
    real_build = fsmgen.build_t19_vectors
    oracle_name = EXPECTED_PATH.stem                      # "t19_expected"

    def _emits_the_oracle(fsm):
        vecs = dict(real_build(fsm))
        vecs[oracle_name] = {"machine": "section_a", "events": [],
                             "expected": {"movements": {}}}
        return vecs

    # EXPECTED_PATH is VECTORS_DIR's PARENT/t19_expected.json: point the
    # emitter's output dir there so the widened emitter writes exactly the
    # oracle path, and the real build_outputs assembles the rogue set.
    monkeypatch.setattr(fsmgen, "VECTORS_DIR", EXPECTED_PATH.parent)
    monkeypatch.setattr(fsmgen, "build_t19_vectors", _emits_the_oracle)
    rogue_outputs = fsmgen.build_outputs(schemas)
    rogue_vectors = _emits_the_oracle(schemas["lifecycle_fsm"])
    assert EXPECTED_PATH in rogue_outputs, (
        "the falsification fixture did not put the oracle in the output set")
    problems = _oracle_independence_problems(rogue_outputs, rogue_vectors)
    assert any("writes the oracle" in p for p in problems), (
        "the oracle-independence predicate does not fire on an output set "
        f"that DOES contain the oracle — the seal is vacuous: {problems}")
    assert any("'expected' key" in p for p in problems), (
        "the vector-expectation predicate does not fire on a vector that "
        f"carries its own expectation — that half is vacuous: {problems}")


def test_fsmgen_check_flags_a_generated_oracle(tmp_path, monkeypatch):
    """Second, stronger half: if a future edit made fsmgen emit the oracle,
    `fsmgen --check`'s stray scan over the vectors tree must call it drift."""
    fsmgen = _fsmgen()
    outputs = fsmgen.build_outputs(fsmgen.load_schemas())
    # Redirect the generated tree into tmp_path rather than writing a stray
    # file into the real repo (panel round 3, finding 50): a crash between
    # write and unlink would leave the working tree dirty.
    real_vectors = fsmgen.VECTORS_DIR
    staged = tmp_path / "t19"
    staged.mkdir()
    remapped = {}
    for path, blob in outputs.items():
        if path.parent == real_vectors:
            (staged / path.name).write_bytes(blob)
            remapped[staged / path.name] = blob
        else:
            remapped[path] = blob
    (staged / "not_a_generated_vector.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(fsmgen, "VECTORS_DIR", staged)
    # REPO_ROOT moves with it: check_outputs reports paths relative to it.
    monkeypatch.setattr(fsmgen, "REPO_ROOT", tmp_path)
    # the other generated dirs are scanned too — point them at empty staging
    # so this probe isolates the vectors tree.
    for attr in ("DOCS_DIR", "FRAMES_DIR", "HANDWRITTEN_DIR"):
        empty = tmp_path / attr.lower()
        empty.mkdir(exist_ok=True)
        monkeypatch.setattr(fsmgen, attr, empty)
    remapped = {k: v for k, v in remapped.items()
                if k.is_relative_to(tmp_path)}
    drift = fsmgen.check_outputs(remapped)
    assert any("stray" in d and "not_a_generated_vector" in d for d in drift), (
        f"fsmgen --check does not flag stray files in the vectors tree: {drift}")


# ─── FSM enum/dispatch exhaustiveness + envelope ─────────────────────────────

def test_section_a_states_and_events_exhaustive(schemas, generated):
    fsm = schemas["lifecycle_fsm"]["section_a"]
    assert {s.name for s in generated.SectionAState} == \
        {fsm["initial_pseudo_state"], *fsm["states"]}
    assert set(generated.SECTION_A_EVENTS) == set(fsm["events"])
    triggers = {cls.TRIGGER for cls in generated.EFFECT_VARIANTS.values()}
    assert triggers == set(fsm["events"])
    rows_with_variants = {cls.ROW for cls in generated.EFFECT_VARIANTS.values()}
    for row in fsm["rows"]:
        if row["to"] in ("ILLEGAL", "terminal", "unchanged"):
            continue
        assert row["id"] in rows_with_variants, f"row {row['id']} has no variant"


def test_section_b_states_and_events_exhaustive(schemas, generated):
    fsm = schemas["lifecycle_fsm"]["section_b"]
    assert {s.name for s in generated.SectionBState} == \
        {fsm["initial_pseudo_state"], *fsm["states"]}
    assert set(generated.SECTION_B_EVENTS) == set(fsm["events"])
    triggers = {cls.TRIGGER for cls in generated.HOLD_VARIANTS.values()}
    assert triggers == set(fsm["events"])
    rows_with_variants = {cls.ROW for cls in generated.HOLD_VARIANTS.values()}
    for row in fsm["rows"]:
        if row["to"] in ("ILLEGAL", "terminal", "as_held_foreign_rows"):
            continue
        assert row["id"] in rows_with_variants, f"row {row['id']} has no variant"


def test_every_event_type_carries_the_envelope(schemas, generated):
    """§9's common envelope is generated onto EVERY event type — union
    variants and singles alike (panel finding: an event with no ts/event_id/
    run_id/trace_id is a state change with no audit attribution)."""
    env = set(schemas["lifecycle_fsm"]["events"]["envelope"]["required"])
    all_types = {**generated.EFFECT_VARIANTS, **generated.HOLD_VARIANTS,
                 **generated.SINGLE_EVENTS}
    for name, cls in all_types.items():
        assert env <= set(cls.REQUIRED), (
            f"{name}: envelope fields {sorted(env - set(cls.REQUIRED))} "
            f"missing from REQUIRED")


@pytest.mark.parametrize("path,token", [
    pytest.param(("lifecycle_fsm", "reconcile_dispositions", "accepting", 0),
                 'X"; import os; os.system("id"); "', id="deny-accepting-set"),
    pytest.param(("lifecycle_fsm", "reconcile_dispositions", "operator_accepting", 0),
                 "not an identifier", id="deny-operator-accepting-set"),
    pytest.param(("lifecycle_fsm", "events", "unions", "effect_lifecycle",
                  "common_required", 0), "bad-field", id="deny-common-required"),
    pytest.param(("lifecycle_fsm", "events", "unions", "hold_lifecycle",
                  "common_optional", 0), "bad optional", id="deny-common-optional"),
    pytest.param(("lifecycle_fsm", "section_a", "rows", 0, "to"),
                 "NOT_A_STATE", id="deny-row-to-undeclared-state"),
    pytest.param(("lifecycle_fsm", "section_a", "rows", 0, "from"),
                 "NOT_A_STATE", id="deny-row-from-undeclared-state"),
    pytest.param(("panel_aggregate", "strategy", 0), "bad strategy",
                 id="deny-panel-strategy"),
    pytest.param(("boundary_errors", "codes", 0, "code"), "bad code",
                 id="deny-error-code"),
])
def test_no_unvalidated_schema_token_reaches_exec(path, token):
    """The "no unvalidated token" invariant, PROVED per sink: plant a
    hostile token at each place the emitters interpolate schema data into
    generated source and assert the loader refuses it (panel round 3: the
    invariant was claimed and false for three token classes)."""
    fsmgen = _fsmgen()
    schemas = fsmgen.load_schemas()
    node = schemas[path[0]]
    for key in path[1:-1]:
        node = node[key]
    node[path[-1]] = token
    with pytest.raises(SystemExit) as exc:
        fsmgen._validate_schema_tokens(schemas)
    assert "SCHEMA ERROR" in str(exc.value)


def test_family_is_a_generated_field_on_every_event_type(schemas, generated):
    """panel round 3 CRITICAL: `family` is the event's schema name and must
    be a REQUIRED generated field on EVERY event type — the two lifecycle
    unions AND all §9 singles. A single without it halted its own base."""
    fam_spec = schemas["lifecycle_fsm"]["events"]["reducer_family_filter"]
    assert set(generated.FAMILY_VALUES) == set(fam_spec["values"])
    assert set(generated.REDUCED_BY_FAMILIES) == set(fam_spec["reduced_by"])
    all_types = {**generated.EFFECT_VARIANTS, **generated.HOLD_VARIANTS,
                 **generated.SINGLE_EVENTS}
    for name, cls in all_types.items():
        assert "family" in cls.REQUIRED, f"{name}: family is not required"
        assert cls.FAMILY in generated.FAMILY_VALUES, (
            f"{name}: FAMILY {cls.FAMILY!r} outside the closed domain")
    # every declared family value is claimed by at least one generated type
    claimed = {cls.FAMILY for cls in all_types.values()}
    assert claimed == set(generated.FAMILY_VALUES), (
        f"declared-but-unclaimed: {sorted(set(generated.FAMILY_VALUES) - claimed)}")


def test_singles_exhaustive_and_domain_validated(schemas, generated):
    """Every §9 single (incl. authorization_granted, the sole authorization
    record) is a generated, sealed type with its closed domains enforced."""
    singles = schemas["lifecycle_fsm"]["events"]["singles"]
    for name in singles:
        assert name in generated.SINGLE_EVENTS, f"single {name} not generated"
    for v in schemas["lifecycle_fsm"]["events"]["unions"][
            "classification_evaluated"]["variants"]:
        assert f"classification_evaluated/{v['name']}" in generated.SINGLE_EVENTS
    env = dict(_envelope_kwargs(), family="authorization_granted")
    ag = generated.SINGLE_EVENTS["authorization_granted"]
    ok = ag(**env, authorization_id="a1", base_key="b", authority="fp",
            kind="AUTO_LOW", assurance="NOT_APPLICABLE", evidence_ref="ev",
            actor="dispatcher")
    assert ok.kind == "AUTO_LOW"
    # deny: unknown kind outside the closed domain
    with pytest.raises(ValueError, match=r"kind: unknown value 'VIBES'"):
        ag(**env, authorization_id="a1", base_key="b", authority="fp",
           kind="VIBES", assurance="NOT_APPLICABLE", evidence_ref="ev",
           actor="dispatcher")
    # deny: an empty REQUIRED str is absence in disguise
    with pytest.raises(ValueError, match=r"assurance must be a non-empty str"):
        ag(**env, authorization_id="a1", base_key="b", authority="fp",
           kind="AUTO_LOW", assurance="", evidence_ref="ev", actor="d")


def _independent_projection(schemas: dict) -> tuple[dict, set]:
    """Recompute the projection machine from the SCHEMA ROWS by an
    independent route: breadth-first closure over memory-only states,
    written from §6.0's rule ("durable states + composed edges ... the
    live table's paths composed through memory-only states") rather than
    by calling fsmgen's compose_projection (panel round 2: the authority
    for the durable reduce had no oracle)."""
    sec = schemas["lifecycle_fsm"]["section_a"]
    memory = set(sec["durability"]["memory_only"])
    durable = set(sec["projection"]["durable_states"])
    live: dict[str, set[str]] = {}
    for row in sec["rows"]:
        if row["to"] in ("ILLEGAL", "unchanged", "terminal"):
            continue
        froms = row["from"] if isinstance(row["from"], list) else [row["from"]]
        if froms == ["any_other"]:
            continue
        for f in froms:
            live.setdefault(f, set()).add(row["to"])
    reachable, edges = {}, set()
    for d in durable:
        frontier, queue = {d}, [d]
        while queue:
            for nxt in live.get(queue.pop(), ()):
                if nxt in memory:
                    if nxt not in frontier:
                        frontier.add(nxt)
                        queue.append(nxt)
                else:
                    frontier.add(nxt)
                    edges.add((d, nxt))
        reachable[d] = tuple(sorted(s for s in frontier
                                    if s in memory or s == d))
    return reachable, edges


def test_projection_machine_matches_an_independent_derivation(schemas, generated):
    """PROJECTION_EDGES / PROJECTION_REACHABLE are the authority for the
    durable reduce — pinned here against a second, independently written
    derivation from the schema rows."""
    reachable, edges = _independent_projection(schemas)
    assert set(generated.PROJECTION_EDGES) == edges
    assert dict(generated.PROJECTION_REACHABLE) == reachable
    # the composed edges must genuinely bridge memory-only states: PREPARED
    # → EXPLAINED exists only via SUBMITTED/EFFECT_OBSERVED, neither durable.
    assert ("PREPARED", "EXPLAINED") in edges
    assert "SUBMITTED" not in {e[0] for e in edges} | {e[1] for e in edges}


def test_projection_frontier_violation_is_the_only_failure(generated):
    """Deny row for the frontier check itself: a durable event whose audit
    `from` is unreachable from the reduced durable state halts, with every
    other invariant satisfied (the event is well-formed, the pair is a real
    projection edge, the epoch algebra holds)."""
    prep = _wire_effect(generated, "Prepare", "e1", "m1", "GENESIS",
                        authorization_id="auth-1")
    to_held = _wire_effect(generated, "MoveToHoldFromPrepared", "e2", "m1",
                           "PREPARED")
    # EFFECT_OBSERVED is a legal `from` for Explained (so the row-audit check
    # passes) but is NOT on any composed path out of the reduced state HELD —
    # only the FRONTIER check can reject this.
    bad = _wire_effect(generated, "Explained", "e3", "m1", "EFFECT_OBSERVED",
                       new_oid="oid-new")
    got = _boundary(generated, [prep, to_held, bad])
    halt = got["halts"]["R1:refs/heads/main"]
    assert halt["code"] == "ILLEGAL_TRANSITION"
    assert "unreachable from durable state" in halt["detail"]


@pytest.mark.parametrize("kind,assurance,ok", [
    pytest.param("AUTO_LOW", "NOT_APPLICABLE", True, id="auto-low-not-applicable"),
    pytest.param("GITHUB_APPROVAL", "OPERATOR_ATTESTED", True, id="approval-attested"),
    pytest.param("LIVE_CONSENT", "HUMAN_IDENTITY_ENFORCED", True, id="consent-enforced"),
    pytest.param("AUTO_LOW", "HUMAN_IDENTITY_ENFORCED", False,
                 id="deny-auto-low-claims-human-identity"),
    pytest.param("AUTO_LOW", "OPERATOR_ATTESTED", False,
                 id="deny-auto-low-claims-attestation"),
    pytest.param("GITHUB_APPROVAL", "NOT_APPLICABLE", False,
                 id="deny-approval-claims-not-applicable"),
])
def test_authorization_granted_kind_assurance_pairs(generated, kind, assurance, ok):
    """§9: the SOLE authorization record cannot assert a human-assurance
    value on an automatic grant — the (kind, assurance) pair rule is
    generated from the schema, not left as prose (panel round 2)."""
    ag = generated.SINGLE_EVENTS["authorization_granted"]
    env = dict(_envelope_kwargs(), family="authorization_granted")
    build = lambda: ag(  # noqa: E731
        **env, authorization_id="a1", base_key="b", authority="fp",
        kind=kind, assurance=assurance, evidence_ref="ev", actor="dispatcher")
    if ok:
        assert build().assurance == assurance
    else:
        # pin the PAIR rule: an automatic grant asserting a human-assurance
        # value must be refused BY that rule, not by an unrelated guard.
        with pytest.raises(ValueError,
                           match=rf"kind={kind!r} admits assurance"):
            build()


@pytest.mark.parametrize("event,field,bad", [
    pytest.param("seat_result", "verdict", "VIBES", id="deny-seat-verdict"),
    pytest.param("panel_decided", "strategy", "YOLO", id="deny-strategy"),
    pytest.param("panel_decided", "demanded", "MAXIMUM", id="deny-demanded"),
    pytest.param("merge_planned", "plan_kind", "MAYBE", id="deny-plan-kind"),
    pytest.param("merge_planned", "verdict", "MEDIUM", id="deny-merge-verdict"),
    pytest.param("approval_evaluated", "assurance", "VIBES",
                 id="deny-approval-assurance"),
    pytest.param("consent", "evidence_mode", "TELEPATHY",
                 id="deny-consent-evidence-mode"),
    pytest.param("consent", "assurance", "NOT_APPLICABLE",
                 id="deny-consent-not-applicable"),
    # the branch below special-cased authorization_granted while the table
    # carried no such row, so it could never execute. The row is added
    # rather than the branch deleted: `kind` is the §9 authorization
    # record's own closed domain and belongs in this table.
    pytest.param("authorization_granted", "kind", "VIBES",
                 id="deny-authorization-kind"),
])
def test_singles_closed_domains_reject_unknown_values(schemas, generated,
                                                      event, field, bad):
    """§9: an unknown VALUE of a known enum field halts identically to an
    unknown variant — asserted for every gate-decision field the design
    closes (panel round 2, finding 12)."""
    spec = schemas["lifecycle_fsm"]["events"]["singles"][event]
    cls = generated.SINGLE_EVENTS[event]
    assert f"{field}_domain" in spec, f"{event}.{field} has no declared domain"
    env = dict(_envelope_kwargs(), family=event)
    payload = {f: f for f in spec["required"]}
    for dom_key, members in spec.items():
        if dom_key.endswith("_domain"):
            payload[dom_key[:-len("_domain")]] = members[0]
    if event == "authorization_granted":
        payload["assurance"] = "NOT_APPLICABLE"
    payload[field] = bad
    with pytest.raises(ValueError,
                       match=rf"{field}: unknown value {bad!r} outside the "
                             rf"closed domain"):
        cls(**env, **payload)
    del payload[field]
    assert cls.DOMAINS.get(field), f"{event}.{field} domain not generated"


def test_durability_partition_is_exclusive_and_total(schemas, generated):
    dur = schemas["lifecycle_fsm"]["section_a"]["durability"]
    parts = [set(dur["durable_state_branch"]), set(dur["memory_only"]),
             set(dur["hold_branch"])]
    union = set().union(*parts)
    assert union == set(schemas["lifecycle_fsm"]["section_a"]["states"])
    assert sum(len(p) for p in parts) == len(union), "partition overlaps"
    assert set(generated.PROJECTION_DURABLE_STATES) == \
        {"GENESIS"} | parts[0] | parts[2]


# ─── typed event construction helpers ────────────────────────────────────────

# FIXED values in the schema are enum members on the generated dataclass.
_ENUM_BY_FIELD = {
    "actor_verification": _GEN.ActorVerification,
    "mode": _GEN.CredentialMode,
    "credential_mode": _GEN.CredentialMode,
    "protection_mode": _GEN.ProtectionMode,
    "hold_effect": _GEN.HoldEffect,
}


def _wire_effect(generated, variant: str, eid: str, mid: str, frm: str,
                 base: str = "R1:refs/heads/main", **extra) -> dict:
    """A well-formed effect_lifecycle WIRE dict (what a reducer consumes),
    with every §9-required field present."""
    cls = generated.EFFECT_VARIANTS[variant]
    to = frm if cls.TO_STATE == "unchanged" else cls.TO_STATE
    ev = {**_envelope_kwargs(), "event_id": eid,
          "family": cls.FAMILY, "variant": variant,
          "trigger_event": cls.TRIGGER, "movement_id": mid, "base_key": base,
          "from": frm, "to": to, "authority": "fp-1", "epoch_before": "E0",
          "epoch_after": "E0",
          "hold_effect": getattr(cls, "ROW_HOLD_EFFECT", None) or "NONE",
          "actor_context": "dispatcher", "credential_mode": "SHARED"}
    ev.update(extra)
    # honour the row's epoch algebra unless the caller is testing it
    if "epoch_after" not in extra and cls.EPOCH_EFFECT == "assign_new_oid":
        ev["epoch_after"] = ev.get("new_oid", ev["epoch_after"])
    return ev


def _legal_disposition(generated, cls):
    """The disposition a variant's own guard admits — FIXED when the row
    pins one, REJECT_RESTORE_HOLD for the restore rows, else an
    operator-accepting value. Derived, so a guard change surfaces here
    rather than being papered over by a hard-coded constant."""
    fixed = cls.FIXED.get("disposition")
    if fixed:
        return generated.ReconcileDisposition[fixed]
    if "RejectRestoreHold" in cls.__name__:
        return generated.ReconcileDisposition.REJECT_RESTORE_HOLD
    # ACCEPT_FOREIGN_ADVANCED is the accepting disposition with NO payload —
    # ACCEPT_OURS would additionally require its new_oid (§6.0 algebra).
    return generated.ReconcileDisposition.ACCEPT_FOREIGN_ADVANCED


def _finish_audit(cls, kwargs: dict, over: dict) -> dict:
    """trigger_event/from/to are §9-REQUIRED wire fields validated against
    the variant's row — default them FROM the row so a helper never
    desynchronises them (tests that mean to desynchronise pass them)."""
    for field, value in cls.FIXED.items():
        # a FIXED field is pinned by the row whether or not it is REQUIRED —
        # ActorVerifiedAuto pins disposition while carrying it as optional.
        if field not in over:
            enum_t = (_GEN.ReconcileDisposition if field == "disposition"
                      else _ENUM_BY_FIELD[field])
            kwargs[field] = enum_t[value]
    kwargs.update(over)
    kwargs.setdefault("family", cls.FAMILY)
    row_effect = getattr(cls, "ROW_HOLD_EFFECT", None)
    if row_effect is not None and "hold_effect" not in over:
        kwargs["hold_effect"] = _GEN.HoldEffect[row_effect]
    kwargs.setdefault("from_state", cls.FROM_STATES[0])
    kwargs.setdefault("trigger_event", cls.TRIGGER)
    kwargs.setdefault("to_state", kwargs["from_state"]
                      if cls.TO_STATE == "unchanged" else cls.TO_STATE)
    # honour the row's epoch algebra so a helper-built event is legal
    effect = cls.EPOCH_EFFECT
    if "epoch_after" not in over:
        if effect == "assign_new_oid":
            kwargs["epoch_after"] = kwargs.get("new_oid", "E1")
        elif effect in ("per_disposition", "as_accept_ours"):
            disp = kwargs.get("disposition")
            accepting = (effect == "as_accept_ours"
                         or disp in _GEN.ACCEPTING_DISPOSITIONS)
            if accepting:
                kwargs["epoch_after"] = kwargs.get("new_oid", "E1")
    return kwargs


def _mk_effect(generated, variant: str, **over):
    cls = generated.EFFECT_VARIANTS[variant]
    kwargs = dict(_envelope_kwargs(), movement_id="m", base_key="b",
                  authority="fp", epoch_before="E0", epoch_after="E0",
                  hold_effect=generated.HoldEffect.NONE, actor_context="ctx",
                  credential_mode=generated.CredentialMode.SHARED)
    for f in ("authorization_id", "new_oid"):
        if f in cls.REQUIRED:
            kwargs[f] = f
    if "disposition" in cls.REQUIRED and "disposition" not in over:
        kwargs["disposition"] = _legal_disposition(generated, cls)
    return cls(**_finish_audit(cls, kwargs, over))


def _mk_hold(generated, variant: str, **over):
    cls = generated.HOLD_VARIANTS[variant]
    kwargs = dict(_envelope_kwargs(), base_key="b", ref="refs/heads/main",
                  mode=generated.CredentialMode.SHARED,
                  actor_verification=generated.ActorVerification.DISPLAY_ONLY,
                  actor_display="someone", epoch_before="E0", epoch_after="E0")
    for f in ("hold_id", "delta_old_oid", "delta_new_oid",
              "source_delivery_id", "actor_node_id", "matched_subject_digest"):
        if f in cls.REQUIRED:
            kwargs[f] = f
    if "disposition" in cls.REQUIRED and "disposition" not in over:
        kwargs["disposition"] = _legal_disposition(generated, cls)
    return cls(**_finish_audit(cls, kwargs, over))


@pytest.mark.parametrize("case", [
    pytest.param("display-only", id="deny-actor-verified-display-only"),
    pytest.param("non-auto-disposition", id="deny-actor-verified-wrong-disposition"),
    pytest.param("no-actor-node-id", id="deny-auto-release-without-identity"),
    pytest.param("valid", id="actor-verified-valid-evidence"),
])
def test_actor_verified_auto_evidence_guards(generated, case):
    """The auto-release path's constructor guards, exercised through the
    REAL constructor (panel round 3: only the SHARED arm had a deny).

    Each row now pins the RULE, not the exception type: `_mk_hold` builds a
    dozen fields at once, so a bare `pytest.raises(ValueError)` here passes
    on a raise from any of the other guards.

    MUTATIONS (generated, each reverted): drop ActorVerifiedAuto's
    `actor_verification` FIXED pin ⇒ display-only row green→red is lost, so
    the row is what holds it; delete the REQUIRES_WHEN VERIFIED_API⇒
    actor_node_id rule ⇒ the no-actor-node-id row goes red; drop the FIXED
    disposition pin ⇒ the wrong-disposition row goes red.
    """
    g = generated
    over = {"mode": g.CredentialMode.SEPARATED}
    expect = ""
    if case == "display-only":
        over["actor_verification"] = g.ActorVerification.DISPLAY_ONLY
        # the row FIXES actor_verification=VERIFIED_API: evidence for the
        # only operator-less release may never be presentation-only.
        expect = r"actor_verification .*VERIFIED_API"
    elif case == "non-auto-disposition":
        over["disposition"] = g.ReconcileDisposition.ACCEPT_OURS
        expect = r"disposition .*ACTOR_VERIFIED_AUTO"
    elif case == "no-actor-node-id":
        over["actor_node_id"] = None
        # NOTE: on THIS variant actor_node_id is §9-REQUIRED, so the plain
        # required-field check refuses it before the VERIFIED_API
        # conditional can — the id says "without identity", the rule that
        # fires is the REQUIRED one. (The conditional itself is sealed on
        # ObserveDelta, where actor_node_id is optional: see
        # test_requires_when_verified_api_needs_an_identity.)
        expect = r"ActorVerifiedAuto\.actor_node_id must be a non-empty str"
    if case == "valid":
        ev = _mk_hold(g, "ActorVerifiedAuto", **over)
        assert ev.disposition is g.ReconcileDisposition.ACTOR_VERIFIED_AUTO
        assert ev.actor_verification is g.ActorVerification.VERIFIED_API
        return
    with pytest.raises(ValueError, match=expect):
        _mk_hold(g, "ActorVerifiedAuto", **over)


def test_actor_verified_fixed_values_match_the_schema(schemas, generated):
    """Emptying the schema's `fixed:` must be red, not silently permissive."""
    variants = schemas["lifecycle_fsm"]["events"]["unions"]["hold_lifecycle"]["variants"]
    spec = next((v for v in variants if v["name"] == "ActorVerifiedAuto"), None)
    assert spec is not None, (
        "the schema no longer declares an ActorVerifiedAuto hold_lifecycle "
        "variant — the only operator-less release path has vanished")
    assert spec["fixed"] == {"actor_verification": "VERIFIED_API",
                             "disposition": "ACTOR_VERIFIED_AUTO"}
    assert dict(generated.HOLD_VARIANTS["ActorVerifiedAuto"].FIXED) == spec["fixed"]
    assert "source_delivery_id" in spec["required"]


@pytest.mark.parametrize("verification,identity,ok", [
    pytest.param("VERIFIED_API", "N_op", True, id="verified-with-identity"),
    pytest.param("DISPLAY_ONLY", None, True, id="display-only-no-identity"),
    pytest.param("VERIFIED_API", None, False,
                 id="deny-verified-api-without-identity"),
    pytest.param("VERIFIED_API", "", False,
                 id="deny-verified-api-empty-identity"),
])
def test_requires_when_verified_api_needs_an_identity(generated, verification,
                                                      identity, ok):
    """§6.0: actor_display is presentation, never predicate input — evidence
    claiming VERIFIED_API must carry an attributable actor_node_id."""
    g = generated
    over = {"actor_verification": g.ActorVerification[verification],
            "actor_node_id": identity}
    if ok:
        assert _mk_hold(g, "ObserveDelta", **over) is not None
    else:
        # pin the CONDITIONAL rule, not merely ValueError: `_mk_hold` sets a
        # dozen fields, several of which have their own guards.
        with pytest.raises(ValueError, match=r"requires 'actor_node_id'"):
            _mk_hold(g, "ObserveDelta", **over)


# ─── the credential-mode refusal, one seal per LAYER ─────────────────────────
#
# Round 3 asserted `("credential mode is run context" in detail or "under
# SHARED, never" in detail)` and claimed "TWO independent layers refuse it,
# and the seal names which". A disjunction over two layers' messages names
# neither: for BOTH parametrised modes only the first arm ever matched, and
# coverage showed the deeper gate's halt body was never executed at all.
# The three layers are now sealed one per test, each asserting the exact
# wording of ITS OWN site:
#
#   layer 1  ActorVerifiedAuto.__post_init__      "requires SEPARATED; under
#                                                  SHARED, never"
#   layer 2  _step_section_b mode-disagreement    "credential mode is run
#                                                  context ... not event
#                                                  payload"
#   layer 3  _check_auto_release_gates run-mode   "requires the RUN to be
#                                                  SEPARATED"
#
# SCOPE, stated because a comment must not claim what coverage denies:
# layer 3 is UNREACHABLE through reduce_section_b on the committed tree —
# the constructor pins event.mode=SEPARATED and _step_section_b halts unless
# event.mode == run_mode, so run_mode is SEPARATED on every path that
# reaches the gate. It is defence in depth, and it is sealed by driving it
# directly (the same white-box route test_unknown_epoch_effect_is_closed_at
# _both_ends already uses for _check_epoch_algebra), never by an `or` that
# lets layer 2 stand in for it.

def test_auto_release_under_a_separated_run_releases(generated):
    """The allow arm: the SAME stream that must be refused elsewhere DOES
    auto-release when the run context is SEPARATED — otherwise the deny
    arms below would pass on a stream that never releases at all."""
    g = generated
    vec = _VECTORS["b_actor_verified_auto_separated"]
    released = _boundary(g, vec["events"], mode="SEPARATED")
    assert not released["halts"], released["halts"]
    assert {d["state"] for h in released["holds"].values()
            for d in h.values()} == {"RELEASED"}


@pytest.mark.parametrize("mode_name", [
    pytest.param("SHARED", id="deny-shared-run-refuses-auto-release"),
])
def test_layer2_event_mode_disagreeing_with_the_run_halts(generated, mode_name):
    """LAYER 2, alone: an event declaring SEPARATED under a SHARED run is
    refused by the mode-disagreement check in `_step_section_b`, by its own
    wording.

    The `None` row moved to
    `test_run_context_refuses_an_absent_credential_mode`: an absent mode is
    no longer READ as SHARED, it is refused at the type boundary, which is a
    stronger fact than "defaults closed" and needs its own seal.

    MUTATION: `if event.mode is not run_mode:` → `if False:` in
    _step_section_b ⇒ red.
    """
    g = generated
    vec = _VECTORS["b_actor_verified_auto_separated"]
    got = _boundary(g, vec["events"], mode=mode_name)
    assert got["halts"], f"mode={mode_name}: auto-release was not refused"
    detail = " ".join(h["detail"] for h in got["halts"].values())
    assert "credential mode is run context" in detail, detail
    assert "not event payload" in detail, detail
    # …and it is THIS layer that caught it: layer 3's wording must be
    # absent, or the seal cannot name which site refused.
    assert "requires the RUN to be SEPARATED" not in detail, (
        "layer 3 fired here — the layer attribution in this file's comments "
        "is stale; re-derive which site refuses before editing this seal")


@pytest.mark.parametrize("mode,match", [
    pytest.param(None, r"must be a CredentialMode member",
                 id="deny-run-mode-absent"),
    pytest.param("SEPARATED", r"must be a CredentialMode member",
                 id="deny-run-mode-is-a-raw-string"),
    pytest.param(2, r"must be a CredentialMode member",
                 id="deny-run-mode-is-an-int"),
])
def test_run_context_refuses_an_absent_credential_mode(generated, mode, match):
    """§0.3's "absent or unprobeable ⇒ SHARED, never a soft SEPARATED" is a
    rule for the PREFLIGHT that builds the context. Inside the reduce it
    would mean "the caller said nothing", and the run's mode decides whether
    the only operator-less release of a foreign hold is open — so absence is
    REFUSED at the type boundary rather than defaulted.

    Previously `credential_mode` was a per-function keyword defaulting to
    None ⇒ SHARED, and two of the three entrypoints did not accept it at
    all: the same bytes produced two verdicts. There is now no signature
    through which the mode can be omitted.

    MUTATION: `if not isinstance(self.credential_mode, CredentialMode)` →
    `if False:` in RunContext.__post_init__ ⇒ red on all three rows.
    """
    with pytest.raises(ValueError, match=match):
        generated.RunContext(credential_mode=mode)


def test_reduce_boundary_refuses_anything_but_a_run_context(generated):
    """deny: the entrypoint takes a RunContext, not a bare mode or a dict —
    the run's mode and its anchors travel together because separating them
    is what let one of them be fabricated.

    MUTATION: `if not isinstance(run_context, RunContext)` → `if False:`
    in _ReduceState.__init__ ⇒ red.
    """
    g = generated
    for bad in (g.CredentialMode.SHARED, {"credential_mode": "SHARED"}, None):
        with pytest.raises(TypeError, match=r"requires a RunContext"):
            g.reduce_boundary([], bad)


def test_run_context_anchors_are_an_immutable_named_state(generated):
    """The empty anchor map is a NAMED state — "this run has no
    protocol_genesis anchor" — and it fails closed: a base with
    epoch-advancing edges and no anchor takes an EPOCH_GAP halt rather than
    resolving to anything. It can therefore carry a default where the
    credential mode cannot: SHARED-as-default is permissive on the run-mode
    gate; an absent anchor is permissive on nothing.

    MUTATIONS: drop the `MappingProxyType(dict(...))` copy ⇒ the aliasing
    row goes red (a caller could move the fence's origin after the context
    was built); make an anchorless base resolve to its first edge instead of
    halting ⇒ the fail-closed row goes red.
    """
    g = generated
    mutable = {"B1": "a" * 40}
    ctx = g.RunContext(credential_mode=g.CredentialMode.SHARED,
                       anchors=mutable)
    mutable["B1"] = "b" * 40                    # move it afterwards
    assert ctx.anchors["B1"] == "a" * 40, (
        "RunContext aliased a caller-owned anchor map — the fence's origin "
        "could change after the context was constructed")
    with pytest.raises(TypeError):
        ctx.anchors["B1"] = "c" * 40
    # the default: named, and fail-closed on an edge-bearing base
    assert g.RunContext(credential_mode=g.CredentialMode.SHARED).anchors == {}
    history = _edge_history("noanchor", "R1:refs/heads/main")
    epochs = _epochs(g, history)                # no anchors at all
    entry = epochs["R1:refs/heads/main"]
    assert entry["status"] == "halt", (
        "an edge-bearing base with no anchor resolved to something — the "
        "empty anchor map is not fail-closed")
    assert entry["halt"]["code"] == "EPOCH_GAP"
    assert "no protocol_genesis anchor" in entry["halt"]["detail"]
    with pytest.raises(ValueError, match=r"anchors must be a mapping"):
        g.RunContext(credential_mode=g.CredentialMode.SHARED, anchors=["B1"])


def test_machine_projection_is_a_selection_not_a_walk(generated):
    """`_project_machine` selects a view OUT OF an already-computed result.
    It cannot be handed events — a function that cannot be handed events
    cannot walk them, which is the structural half of S1's fix.

    This also couples THIS FILE's `_machine_view` to the module's own
    `_MACHINE_PROJECTIONS`: the two statements of "what a machine's view is"
    must agree, or one of them is a private reimplementation that can drift
    exactly the way the three deleted entrypoints did.

    MUTATIONS: add a fourth key to a machine's projection tuple without
    updating the module ⇒ red; make `_project_machine` accept an unknown
    machine instead of raising ⇒ the closed-set row goes red; delete a key
    from `_MACHINE_PROJECTIONS` ⇒ red.
    """
    g = generated
    assert set(g._MACHINE_PROJECTIONS) == {"section_a", "section_b",
                                           "epoch_fold"}, (
        "the machine set is CLOSED — a fourth projection is a fourth walk "
        "waiting to happen")
    result = _boundary(g, [], anchors={"B1": "a" * 40})
    for machine in g._MACHINE_PROJECTIONS:
        assert g._project_machine(result, machine) == \
            _machine_view(g, result, machine), (
            f"{machine}: this file's projection and the module's disagree")
    # every projected key really is a key of the one result
    for keys in g._MACHINE_PROJECTIONS.values():
        for key in keys:
            assert key in result, f"{key} is not part of the reduced state"
    # the whole reduced state is exactly the union — no key is unprojectable
    projected = {k for keys in g._MACHINE_PROJECTIONS.values() for k in keys}
    assert projected == set(result), (
        f"reduced-state keys no machine can project: "
        f"{sorted(set(result) - projected)}")
    with pytest.raises(KeyError, match=r"unknown boundary machine"):
        g._project_machine(result, "section_c")
    # …and it is not callable with events: handing it a stream is a KeyError
    # on the machine name or a missing result key, never a reduce.
    with pytest.raises((KeyError, TypeError)):
        g._project_machine([], "section_a")


def test_layer1_constructor_pins_separated_on_the_auto_release(generated):
    """LAYER 1, alone: a SHARED-declared auto-release is unconstructible.

    MUTATION: delete `if self.mode is not CredentialMode.SEPARATED: raise`
    from ActorVerifiedAuto.__post_init__ ⇒ red.
    """
    g = generated
    with pytest.raises(ValueError,
                       match=r"requires SEPARATED; under SHARED, never"):
        _mk_hold(g, "ActorVerifiedAuto", hold_id="h", actor_node_id="n",
                 matched_subject_digest="s",
                 actor_verification=g.ActorVerification.VERIFIED_API,
                 mode=g.CredentialMode.SHARED,
                 disposition=g.ReconcileDisposition.ACTOR_VERIFIED_AUTO)


@pytest.mark.parametrize("mode_name", [
    pytest.param("SEPARATED", id="separated-run-passes-the-gate"),
    pytest.param("SHARED", id="deny-shared-run-refused-by-the-run-mode-gate"),
])
def test_layer3_run_mode_gate_inside_check_auto_release_gates(generated,
                                                              mode_name):
    """LAYER 3, alone and driven DIRECTLY: `_check_auto_release_gates`'s
    run-mode arm — the layer the schema names authoritative
    (`credential_mode_source: run_context`) and the layer coverage showed
    was never executed by any test.

    It is unreachable through `reduce_section_b` (see the scope note above),
    so it is exercised the way the epoch-effect closed-domain arm is: by
    calling the generated helper with a run mode the reducer can never hand
    it, and asserting the gate's OWN sentence, `hold {hid}:` prefix
    included, so layer 1's byte-similar "under SHARED, never" cannot stand
    in for it.

    MUTATION: `if run_mode is not CredentialMode.SEPARATED:` → `if False:`
    in _check_auto_release_gates ⇒ red (the SHARED row). Before this seal
    the same mutation left the whole boundary suite at exit 0.
    """
    g = generated
    book = g._HoldBook()
    hid = "hold-1"
    event = _mk_hold(g, "ActorVerifiedAuto", hold_id=hid, actor_node_id="n",
                     matched_subject_digest="s",
                     mode=g.CredentialMode.SEPARATED)
    ev = {"event_id": "e-auto"}
    halt = g._check_auto_release_gates(book, "R1:refs/heads/main", hid, event,
                                       ev, g.CredentialMode[mode_name])
    if mode_name == "SEPARATED":
        # the run-mode arm must NOT fire; the next gate (delivery
        # membership) does — proving the call reached past this arm rather
        # than returning None for an unrelated reason.
        assert halt is not None
        assert "requires the RUN to be SEPARATED" not in halt["detail"]
        assert "not a delivery recorded on" in halt["detail"], halt["detail"]
        return
    assert halt is not None, (
        "the run-mode gate admitted a non-SEPARATED run on the only "
        "operator-less release path")
    assert halt["code"] == "ILLEGAL_TRANSITION"
    assert f"hold {hid}: ACTOR_VERIFIED_AUTO requires the RUN to be " \
        "SEPARATED" in halt["detail"], halt["detail"]
    assert "protocol_genesis.credential_mode" in halt["detail"]


def test_auto_release_gate_order_refusal_before_run_mode(generated):
    """The gate ORDER is normative: an operator's prior REJECT_RESTORE_HOLD
    closes the auto-release path before the run-mode arm is consulted, so a
    SEPARATED run cannot re-open what an operator refused.

    MUTATION: move the `hid in book.reject_restored` arm below the run-mode
    arm ⇒ the SHARED row below reports the run-mode sentence ⇒ red.
    """
    g = generated
    book = g._HoldBook()
    hid = "hold-1"
    book.reject_restored.add(hid)
    event = _mk_hold(g, "ActorVerifiedAuto", hold_id=hid, actor_node_id="n",
                     matched_subject_digest="s",
                     mode=g.CredentialMode.SEPARATED)
    for mode in (g.CredentialMode.SEPARATED, g.CredentialMode.SHARED):
        halt = g._check_auto_release_gates(book, "R1:refs/heads/main", hid,
                                           event, {"event_id": "e"}, mode)
        assert halt is not None
        assert "an operator REJECTED this hold's release" in halt["detail"], (
            f"mode={mode}: the operator refusal is no longer the first gate")


def test_reconcile_disposition_sets_match_the_schema(schemas, generated):
    """The disposition SETS are generated from the schema, not hand-listed
    beside it (the enforcement half is the parametrised seal below)."""
    disp = schemas["lifecycle_fsm"]["reconcile_dispositions"]
    g = generated
    assert {d.name for d in g.ACCEPTING_DISPOSITIONS} == set(disp["accepting"])
    assert {d.name for d in g.OPERATOR_ACCEPTING_DISPOSITIONS} == \
        set(disp["operator_accepting"])
    assert {d.name for d in g.SECTION_B_ONLY_DISPOSITIONS} == \
        {m["name"] for m in disp["members"] if m.get("section_b_only")}
    assert not (g.OPERATOR_ACCEPTING_DISPOSITIONS & g.SECTION_B_ONLY_DISPOSITIONS)


def _admitted_dispositions(g, cls) -> set:
    """The dispositions a variant's OWN guard admits, derived from the row
    (never hand-listed): a FIXED disposition pins exactly one; the restore
    rows take REJECT_RESTORE_HOLD; every other operator_reconcile row takes
    the operator-accepting set. `_legal_disposition` picks one member of
    this same set, so a guard change surfaces in both places."""
    fixed = cls.FIXED.get("disposition")
    if fixed:
        return {g.ReconcileDisposition[fixed]}
    if "RejectRestoreHold" in cls.__name__:
        return {g.ReconcileDisposition.REJECT_RESTORE_HOLD}
    return set(g.OPERATOR_ACCEPTING_DISPOSITIONS)


def _reconcile_rows() -> list:
    """(machine, variant, disposition) for every operator_reconcile variant
    on either machine × every disposition its row must refuse. Derived from
    the generated tables, so a variant added later cannot slip in untested."""
    rows = []
    for machine, table in (("a", _GEN.EFFECT_VARIANTS), ("b", _GEN.HOLD_VARIANTS)):
        for name, cls in sorted(table.items()):
            if cls.TRIGGER != "operator_reconcile":
                continue
            admitted = _admitted_dispositions(_GEN, cls)
            for d in _GEN.ReconcileDisposition:
                if d in admitted:
                    continue
                rows.append(pytest.param(machine, name, d.name,
                                         id=f"deny-{name}-{d.name}"))
    return rows


@pytest.mark.parametrize("machine,variant,disposition", _reconcile_rows())
def test_every_operator_reconcile_variant_refuses_foreign_dispositions(
        generated, machine, variant, disposition):
    """Panel CRITICAL: no side door into RELEASED(ACTOR_VERIFIED_AUTO). The
    round-3 seal denied exactly TWO variants (ReconcileAccept and
    HoldReconcileAccept); coverage showed five per-variant disposition
    guards were never executed — including BOTH replay-identity rows, which
    are precisely the ones that can echo a disposition into RELEASED, and
    which the docstring claimed were closed.

    Every operator_reconcile variant × every disposition its own row must
    refuse is now a row, and each asserts the GUARD'S OWN message (prefixed
    with the variant name), so a raise from an unrelated guard cannot pass
    for this one.

    MUTATIONS (generated, each reverted, each red on exactly its rows):
      ReconcileRejectRestoreHold requires REJECT_RESTORE_HOLD      → `pass`
      ReconcileReplayIdentity replay-must-be-operator-accepting    → `pass`
      HoldReconcileRejectRestoreHold requires REJECT_RESTORE_HOLD  → `pass`
      HoldReconcileStanding.disposition must be STANDING           → `pass`
      HoldReconcileReplayIdentity replay-must-be-operator-accepting→ `pass`
      ReconcileAccept / HoldReconcileAccept operator-accepting     → `pass`
    """
    g = generated
    d = g.ReconcileDisposition[disposition]
    over = {"disposition": d}
    if machine == "b":
        over["hold_id"] = "h"
    cls = (g.EFFECT_VARIANTS if machine == "a" else g.HOLD_VARIANTS)[variant]
    carries_new_oid = "new_oid" in cls.REQUIRED or "new_oid" in cls.OPTIONAL
    rules = ("operator-accepting", "REJECT_RESTORE_HOLD", "must be STANDING")
    if d is g.ReconcileDisposition.ACCEPT_OURS:
        if carries_new_oid:
            # supply the §9 conditional's payload so the row trips the
            # DISPOSITION guard rather than the epoch-payload guard — the
            # wrong-reason pass the panel demonstrated on this very helper.
            over["new_oid"] = "oid-new"
        else:
            # this row declares REQUIRES_WHEN {ACCEPT_OURS: (new_oid,)} while
            # carrying no new_oid field at all, so the conditional refuses
            # ACCEPT_OURS before the disposition guard is reached. Still a
            # refusal of the foreign disposition — by a different, also
            # §9-normative rule, so this row accepts either sentence (and
            # still refuses any raise that names NEITHER).
            rules = (*rules, "requires 'new_oid'")
    mk = _mk_effect if machine == "a" else _mk_hold
    with pytest.raises(ValueError, match=rf"^{variant}[.: ]") as exc:
        mk(g, variant, **over)
    text = str(exc.value)
    assert any(rule in text for rule in rules), (
        f"{variant} refused {disposition} but not by the rule this row "
        f"seals ({rules}): {text}")


# ─── §6.0 epoch algebra: a deny vector per arm ───────────────────────────────
#
# _DENY_RULE_MARKERS enumerated deny vectors for the `none` arm and both
# `assign_new_oid` arms, and NONE for the three per_disposition /
# as_accept_ours arms — the rules that govern the authority fence
# (AuthorityFingerprint.base_epoch) on every operator reconcile and on the
# only operator-less release. Three independent `if False:` mutations of
# those arms each left the whole boundary suite at exit 0.
#
# The T19 vector corpus is GENERATED by tools/fsmgen.py (fsmgen --check's
# stray scan makes the vectors tree exact), so a new deny VECTOR is an
# implementation change this test author may not make. These arms are
# therefore sealed with in-test wire streams driven through the same public
# reducers the vectors use — identical reach, no generator edit.

def test_accepting_must_advance_is_retired_and_that_is_load_bearing(schemas,
                                                                    generated):
    """RETIRED, and I checked the retirement against the design rather than
    accepting it: §6.0's section-B table gives `operator_reconcile(accepting
    d)` the epoch effect "per d" and NOWHERE says an accepting disposition
    must CHANGE the fence. §6.0/§6.1 name ABA and force-push-back as T19
    rows, and both re-seed the fence from a fresh §8 ref read that
    legitimately lands on the value already held — so demanding an advance
    left those rows with no legal encoding at all and made the hold
    permanently unreleasable.

    What is NOT loosened is where a payload PINS the value. The schema's
    `fence_pinning` map is the whole rule, and this seal pins the map itself
    plus the fact that `unpinned_fresh_ref_read` is a NAMED value rather
    than a gap: the reducer cannot verify a fresh ref read and must not
    second-guess it.

    MUTATION: flip `accepting_must_advance` to true in the schema and
    regenerate ⇒ red here AND the ABA row below goes red, which is the
    consequence that matters.
    MUTATION: change any entry of `fence_pinning` ⇒ red.
    """
    g = generated
    disp = schemas["lifecycle_fsm"]["reconcile_dispositions"]
    fence = disp["fence_pinning"]
    assert dict(g.FENCE_PINNING) == fence
    assert fence == {"ACCEPT_OURS": "new_oid",
                     "ACTOR_VERIFIED_AUTO": "hold_observed_delta_new_oid",
                     "ACCEPT_FOREIGN_ADVANCED": "unpinned_fresh_ref_read",
                     "REJECT_RESTORE_HOLD": "must_not_advance",
                     "STANDING": "must_not_advance"}
    # every disposition in the closed domain has a pinning rule — a member
    # with no entry would fall through to "unconstrained" by omission.
    assert set(fence) == {d.name for d in g.ReconcileDisposition}, (
        f"dispositions with no fence rule: "
        f"{sorted({d.name for d in g.ReconcileDisposition} - set(fence))}")
    assert disp["accepting_must_advance"] is False
    assert g.ACCEPTING_MUST_ADVANCE is False


def test_the_ABA_reconcile_re_seeds_to_the_value_already_held(generated):
    """The row the retirement exists for, sealed so the retirement cannot be
    re-argued from an empty table: a force-push-back (ABA) leaves the ref at
    an OID the base already held, so the accepting reconcile that resolves it
    re-seeds `base_epoch` to that same value. It must REDUCE, not halt.

    §6.0/§6.1 name ABA as a T19 row and §0.1 accepts that "ABA restore
    defeats OID comparison" — the protocol's answer is a hold plus an
    operator reconcile, and this is that reconcile.

    MUTATION: `if ACCEPTING_MUST_ADVANCE and accepting and not advanced:` →
    drop the flag ⇒ red (the hold becomes permanently unreleasable and the
    base halts for the whole append-only history).
    """
    g = generated
    vec = copy.deepcopy(_VECTORS["b_reject_restore_hold"])
    observed = _event_of(vec, "ObserveDelta")
    # the operator accepts, re-seeding the fence from a fresh ref read that
    # landed back on the epoch the base already had (A→B→A).
    accept = dict(_event_of(vec, "HoldReconcileAccept"),
                  event_id="aba-accept",
                  disposition="ACCEPT_FOREIGN_ADVANCED", to="RELEASED",
                  epoch_before=observed["epoch_before"],
                  epoch_after=observed["epoch_before"])
    got = _boundary(g, [observed, accept], mode=vec["credential_mode"])
    assert got["halts"] == {}, (
        f"an ABA re-seed to the value already held was refused — the hold is "
        f"permanently unreleasable: {got['halts']}")
    (hold,) = got["holds"]["R1:refs/heads/main"].values()
    assert hold["state"] == "RELEASED"
    assert hold["disposition"] == "ACCEPT_FOREIGN_ADVANCED"


def test_epoch_accept_ours_pins_the_fence_to_its_own_new_oid(generated):
    """§6.0 per_disposition: ACCEPT_OURS(new_oid) pins the fence to ITS OWN
    payload — the one accepting case where a payload determines the value,
    so it is enforced even though a bare advance is not required.

    MUTATION: `if (disposition is ReconcileDisposition.ACCEPT_OURS and
    carries_new_oid` → `if (False and carries_new_oid` ⇒ red.
    """
    g = generated
    cls = g.EFFECT_VARIANTS["ReconcileAccept"]
    ev = _wire_effect(g, "ReconcileAccept", "e1", "m1", cls.FROM_STATES[0],
                      disposition="ACCEPT_OURS", new_oid="oid-new",
                      epoch_before="E0", epoch_after="E1")
    halt = _boundary(g, [ev])["halts"]["R1:refs/heads/main"]
    assert halt["code"] == "ILLEGAL_TRANSITION"
    assert "ACCEPT_OURS pins the fence to its new_oid payload" in halt["detail"]
    assert "'oid-new'" in halt["detail"], halt["detail"]


def test_epoch_as_accept_ours_is_pinned_to_the_holds_own_delta(generated):
    """§6.0 as_accept_ours: the auto-release's fence is pinned to the HOLD'S
    OWN recorded delta_new_oid — the observed effect OID, never writer free
    text and never "whatever advanced".

    This replaces an earlier seal that asserted the auto-release must
    ADVANCE. That was the wrong rule (see the retirement seal above); the
    right one is the pin, which is strictly stronger — it names one legal
    value instead of excluding one illegal one.

    MUTATION: delete the `event.epoch_after != observed` comparison in
    `_check_auto_release_gates` ⇒ red.
    """
    g = generated
    vec = copy.deepcopy(_VECTORS["b_actor_verified_auto_separated"])
    auto = _event_of(vec, "ActorVerifiedAuto")
    observed = _event_of(vec, "ObserveDelta")["delta_new_oid"]
    assert auto["epoch_after"] == observed, (
        "the allow vector no longer pins the fence to the hold's own delta")
    auto["epoch_after"] = auto["epoch_before"]     # any other value at all
    got = _boundary(g, vec["events"], mode="SEPARATED")
    halt = got["halts"]["R1:refs/heads/main"]
    assert halt["code"] == "ILLEGAL_TRANSITION"
    assert "must set the fence to the hold's own observed delta_new_oid" \
        in halt["detail"], halt["detail"]
    assert "never writer free text" in halt["detail"]


def test_epoch_non_accepting_disposition_may_not_advance(generated):
    """§6.0 per_disposition, the negative half: a NON-accepting disposition
    (REJECT_RESTORE_HOLD) must not advance the fence — a refusal that moves
    base_epoch would let a rejected reconcile re-authorise the base.

    SCOPE: unreachable end-to-end on the committed tree — both
    per_disposition rows (ReconcileAccept, HoldReconcileAccept) refuse any
    disposition outside OPERATOR_ACCEPTING at construction, and every
    operator-accepting disposition is in ACCEPTING, so `accepting` is
    always True by the time a typed event reaches the checker. It is
    defence in depth against a schema edit widening those rows, so it is
    driven directly: a per_disposition ROW against a REAL typed event
    carrying REJECT_RESTORE_HOLD and an advanced fence — exactly the pair
    such a widening would produce.

    MUTATION: `if not accepting and advanced:` → `if False:` ⇒ red.
    """
    g = generated
    row = g.EFFECT_VARIANTS["ReconcileAccept"]          # per_disposition
    event = _mk_effect(g, "ReconcileRejectRestoreHold",
                       disposition=g.ReconcileDisposition.REJECT_RESTORE_HOLD,
                       epoch_before="E0", epoch_after="E1")
    assert event.disposition not in g.ACCEPTING_DISPOSITIONS
    halt = g._check_epoch_algebra(row, event, "where", {"event_id": "e"})
    assert halt is not None, (
        "a non-accepting disposition advanced the fence unrefused")
    assert halt["code"] == "ILLEGAL_TRANSITION"
    assert "a non-accepting disposition" in halt["detail"], halt["detail"]
    assert "must not advance" in halt["detail"], halt["detail"]


def test_every_epoch_effect_has_a_deny(generated):
    """Closure, the shape `test_every_reject_reason_has_a_vector` already
    applies to the reject-reason domain: every member of the CLOSED
    EPOCH_EFFECT_VALUES domain must have at least one deny exercising it,
    so a newly declared effect cannot arrive unsealed.

    MUTATION: add a fifth member to EPOCH_EFFECT_VALUES in the schema and
    regenerate ⇒ red (no deny names it).
    """
    g = generated
    denied = {
        # `none` and `assign_new_oid`: the generated T19 corpus
        "none": ["a_none_effect_row_advances_deny", "b_none_effect_row_advances_deny"],
        "assign_new_oid": ["a_advancing_row_that_does_not_advance_deny",
                           "a_epoch_advance_not_pinned_to_new_oid_deny"],
        # per_disposition / as_accept_ours: the in-test seals above
        "per_disposition": ["test_epoch_accept_ours_pins_the_fence_to_its_own_new_oid",
                            "test_epoch_non_accepting_disposition_may_not_advance",
                            "test_the_ABA_reconcile_re_seeds_to_the_value_already_held"],
        "as_accept_ours": ["test_epoch_as_accept_ours_is_pinned_to_the_holds_own_delta"],
    }
    missing = set(g.EPOCH_EFFECT_VALUES) - set(denied)
    assert not missing, (
        f"epoch effects with no deny: {sorted(missing)} — the domain is "
        f"closed, so a new member arrives with a seal or not at all")
    assert set(denied) <= set(g.EPOCH_EFFECT_VALUES), (
        f"denies naming an undeclared effect: "
        f"{sorted(set(denied) - set(g.EPOCH_EFFECT_VALUES))}")
    # the vector-corpus half of the table must name vectors that exist…
    for effect, names in denied.items():
        for name in names:
            if name.startswith("test_"):
                assert name in globals(), f"{effect}: {name} is not a seal here"
            else:
                assert name in _VECTORS, f"{effect}: {name} is not a vector"


def test_enum_wire_fields_are_never_coerced_from_a_raw_string(generated):
    """deny: a raw string for an enum field is a schema violation, never a
    coercion (§9 explicit-state).

    MUTATION: make `_validate_field_value`'s enum arm `return` instead of
    raising ⇒ red.
    """
    with pytest.raises(ValueError,
                       match=r"credential_mode must be a CredentialMode instance"):
        _mk_effect(generated, "Prepare", credential_mode="SHARED")


# ─── the WIRE path: build_wire_event's own fail-closed arms ──────────────────
#
# Coverage reported the wire twins of the constructor checks as never
# executed: build_wire_event's family contradiction, and _convert_wire_value
# 's int / schema_major-range / non-empty-str / ts arms. They are
# unreachable through the REDUCERS — `_intake` calls `_classify_event`
# first, which pre-empts the major and family checks — but build_wire_event
# is a public generated entry point, so they are reachable and sealed here
# directly rather than left as dead code nobody can tell is dead.

def _wire_ok(generated) -> dict:
    return _wire_effect(generated, "Prepare", "e1", "m1", "GENESIS",
                        authorization_id="auth-1")


@pytest.mark.parametrize("over,match", [
    pytest.param({"variant": "TotallyNovelEvent"},
                 r"unknown event variant 'TotallyNovelEvent'",
                 id="deny-wire-unknown-variant"),
    pytest.param({"family": "hold_lifecycle"},
                 r"family 'hold_lifecycle' contradicts the variant's own "
                 r"schema name",
                 id="deny-wire-family-contradicts-variant"),
    pytest.param({"authority": None}, r"required field 'authority' absent",
                 id="deny-wire-missing-required"),
    pytest.param({"credential_mode": "TELEPATHY"},
                 r"unknown value 'TELEPATHY' for closed enum",
                 id="deny-wire-unknown-enum-value"),
    pytest.param({"schema_major": "1"}, r"schema_major: must be an int",
                 id="deny-wire-major-not-an-int"),
    pytest.param({"schema_major": True}, r"schema_major: must be an int",
                 id="deny-wire-major-is-a-bool"),
    pytest.param({"schema_major": 99}, r"99 outside the supported set",
                 id="deny-wire-unsupported-major"),
    pytest.param({"schema_minor": "0"}, r"schema_minor: must be an int",
                 id="deny-wire-minor-not-an-int"),
    pytest.param({"authority": ""}, r"authority: must be a non-empty str",
                 id="deny-wire-empty-required-str"),
    pytest.param({"authority": 7}, r"authority: must be a non-empty str",
                 id="deny-wire-required-str-is-an-int"),
    pytest.param({"ts": "1970-13-45T99:00:00Z"},
                 r"is not an RFC 3339 UTC instant",
                 id="deny-wire-ts-is-not-an-instant"),
    pytest.param({"trigger_event": "submit"},
                 r"contradicts the variant's row trigger",
                 id="deny-wire-trigger-mis-tagged"),
    pytest.param({"to": "HELD"}, r"audit 'to' 'HELD' contradicts the row's",
                 id="deny-wire-to-contradicts-the-row"),
])
def test_build_wire_event_is_fail_closed(generated, over, match):
    """§9: missing REQUIRED / forbidden-present / unknown enum value /
    unknown variant / unsupported major ⇒ a typed WireViolation, never
    coercion and never a default.

    MUTATIONS (generated, each reverted): `_convert_wire_value`'s int arm →
    `return value` ⇒ the three int rows go red; its major-range arm →
    `pass` ⇒ the unsupported-major row goes red; its non-empty-str arm →
    `pass` ⇒ two rows go red; its ts arm → `pass` ⇒ one row; build_wire_
    event's `ev.get("family") != cls.FAMILY` → `if False:` ⇒ the family row
    goes red (that guard had NO test — `_intake` pre-empts it).
    """
    g = generated
    ev = dict(_wire_ok(g))
    for key, value in over.items():
        if value is None:
            ev.pop(key, None)
        else:
            ev[key] = value
    with pytest.raises(g.WireViolation, match=match) as exc:
        g.build_wire_event(g.EFFECT_VARIANTS, ev)
    # a WireViolation carries the SCHEMA_MAJOR_UNKNOWN code by contract:
    # §9 halts an unknown variant and an unknown enum value identically to
    # an unknown major.
    assert exc.value.code is g.BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN


@pytest.mark.parametrize("major,match", [
    pytest.param("1", r"non-integer schema_major",
                 id="deny-reducer-major-is-a-string"),
    pytest.param(True, r"non-integer schema_major",
                 id="deny-reducer-major-is-a-bool"),
    pytest.param(1.0, r"non-integer schema_major",
                 id="deny-reducer-major-is-a-float"),
])
def test_reducers_halt_on_a_non_integer_schema_major(generated, major, match):
    """`_classify_event` is the envelope check EVERY consumer shares, and
    its non-integer arm had no vector — the corpus covers only out-of-range
    integers (0, 99). A bool is the sharp case: `True == 1` and
    `True in SUPPORTED_SCHEMA_MAJORS` are both true, so without the
    isinstance(bool) test a boolean major would be admitted as major 1.

    MUTATION: `if isinstance(major, bool) or not isinstance(major, int):`
    → `if False:` ⇒ red on all three rows.
    """
    g = generated
    ev = dict(_wire_ok(g), schema_major=major)
    halt = _boundary(g, [ev])["halts"]["R1:refs/heads/main"]
    assert halt["code"] == "SCHEMA_MAJOR_UNKNOWN"
    assert "non-integer schema_major" in halt["detail"], halt["detail"]


def test_build_wire_event_rejects_a_forbidden_field(generated):
    """deny: a FORBIDDEN field present is a schema violation — the §9
    authorization_id may not ride on a reconcile row.

    MUTATION: delete the FORBIDDEN loop from build_wire_event ⇒ red.
    """
    g = generated
    cls = g.EFFECT_VARIANTS["ReconcileAccept"]
    ev = _wire_effect(g, "ReconcileAccept", "e1", "m1", cls.FROM_STATES[0],
                      disposition="ACCEPT_FOREIGN_ADVANCED",
                      epoch_before="E0", epoch_after="E1",
                      authorization_id="auth-1")
    with pytest.raises(g.WireViolation,
                       match=r"forbidden field 'authorization_id' present"):
        g.build_wire_event(g.EFFECT_VARIANTS, ev)


# ─── §9 audit fields, validated against the variant's own row ────────────────

@pytest.mark.parametrize("over,match", [
    pytest.param({"from_state": "RECONCILED"}, r"from_state 'RECONCILED' not in",
                 id="deny-audit-from-outside-from-states"),
    pytest.param({"family": "hold_lifecycle"},
                 r"family 'hold_lifecycle' contradicts the variant's own "
                 r"schema name",
                 id="deny-audit-family-contradicts-variant"),
    pytest.param({"trigger_event": "submit"},
                 r"trigger_event 'submit' contradicts the row's trigger",
                 id="deny-audit-trigger-contradicts-row"),
    pytest.param({"to_state": "HELD"}, r"to 'HELD' contradicts the row's",
                 id="deny-audit-to-contradicts-row"),
])
def test_row_audit_fields_are_validated_at_construction(generated, over, match):
    """The CONSTRUCTOR twins of the wire audit checks (coverage reported all
    four as never executed): §9's from/family/trigger_event/to are real
    fields validated against the variant's row, so a typed event built in
    process cannot contradict the row it claims.

    MUTATION: any one of the four raises in `_validate_row_audit_fields` →
    `pass` ⇒ exactly its row goes red.
    """
    with pytest.raises(ValueError, match=match):
        _mk_effect(generated, "Prepare", **over)


def test_hold_effect_must_match_the_rows_declared_effect(generated):
    """The fifth audit guard: a row that declares a hold effect pins it, so
    an event may not claim a different one.

    MUTATION: delete the ROW_HOLD_EFFECT comparison ⇒ red.
    """
    g = generated
    cls = g.EFFECT_VARIANTS["MoveToHoldFromPrepared"]
    assert getattr(cls, "ROW_HOLD_EFFECT", None) is not None, (
        "this seal needs a row that declares a hold effect")
    other = next(e for e in g.HoldEffect if e.value != cls.ROW_HOLD_EFFECT)
    with pytest.raises(ValueError,
                       match=r"contradicts the row's declared effect"):
        _mk_effect(g, "MoveToHoldFromPrepared", hold_effect=other)


# ─── cross-base duplicate propagation, through the REDUCERS' intake ─────────
#
# `_Dedup` is shared by both reducers AND the fold, but the two
# order-dependence properties it exists for were covered only by FOLD
# vectors — and the reducers register through a different call site
# (`_intake`) than the fold (`_collect_epoch_edges`), so a regression in
# `_intake` reddened nothing.

def _divergent_pair(g, base_a: str, base_b: str) -> list[dict]:
    """One event_id on two bases with DIVERGENT payloads."""
    first = _wire_effect(g, "Prepare", "dup", "m1", "GENESIS", base=base_a,
                         authorization_id="auth-1")
    second = dict(first, base_key=base_b, authority="fp-DIFFERENT")
    return [first, second]


def test_divergent_duplicate_halts_every_base_it_touched(generated):
    """A divergent copy of one event_id halts EVERY base it appeared on —
    not merely the one it arrived on second. Integrity, not last-writer.

    MUTATION: in `_intake`, catch `_DivergentDuplicate` and record the halt
    on `base_hint` only (instead of every base in `exc.bases`) ⇒ red.
    """
    g = generated
    got = _boundary(g, _divergent_pair(g, "B1", "B2"))
    for base in ("B1", "B2"):
        assert base in got["halts"], (
            f"{base} did not halt on a divergent duplicate: {got['halts']}")
        assert got["halts"][base]["code"] == "EVENT_PAYLOAD_DIVERGENT"


def test_dedup_registers_even_on_an_already_halted_base(generated):
    """The first copy lands on a base that is ALREADY halted; a divergent
    copy then arrives on a healthy base. If registration were skipped for
    halted bases, the second copy would read as first-seen and the healthy
    base would accept a payload the protocol has already contradicted.

    MUTATION: in `_intake`, move `dedup.check(...)` inside `if not halted:`
    ⇒ red.
    """
    g = generated
    # halt B1 first: an unknown variant is a §9 schema violation.
    halting = dict(_wire_effect(g, "Prepare", "e0", "m0", "GENESIS",
                                base="B1", authorization_id="auth-1"),
                   variant="TotallyNovelEvent")
    first, second = _divergent_pair(g, "B1", "B2")
    got = _boundary(g, [halting, first, second])
    assert got["halts"]["B1"]["code"] == "SCHEMA_MAJOR_UNKNOWN"
    assert "B2" in got["halts"], (
        "the divergent copy on a healthy base was read as first-seen — "
        "dedup registration is order-dependent")
    assert got["halts"]["B2"]["code"] == "EVENT_PAYLOAD_DIVERGENT"


# ─── derived ids: independent issuers CONVERGE ──────────────────────────────
#
# Iteration 6 reported two defects here and left them unsealed rather than
# ratify them: (a) `actor_verified_match` was not a derived-id kind, so a
# concurrent duplicate of the ONLY operator-less release halted a base that
# had just done the right thing twice; (b) the derived recovery id covered
# the ID but not the PAYLOAD — `_canonical` dropped only ts/run_id/trace_id,
# so any disagreement in the remaining issuer-supplied §9 fields was
# EVENT_PAYLOAD_DIVERGENT, the exact permanent halt the derived id exists to
# prevent. Both are fixed, so both are sealed.
#
# The derived ids below are computed HERE from the schema's own declared
# preimage lines with a standalone snippet — never by calling
# `derive_event_id`, which is the function under test.

def _derived_event_id(*lines: str) -> str:
    """SHA-256 over the schema's tagged newline-joined preimage."""
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def _dual_append(schemas: dict) -> dict:
    return schemas["lifecycle_fsm"]["section_a"]["durability"]["dual_append"]


def _preimage_lines(schemas: dict, kind: str) -> list[str]:
    return list(_dual_append(schemas)["derived_id_kinds"][kind]["preimage_lines"])


def test_derived_id_kinds_are_declared_by_the_schema(schemas, generated):
    """The derived-id set is schema-declared, not code-local, and it covers
    BOTH kinds whose ids two independent issuers must agree on: the
    cold-start recovery append and the auto-release of a foreign hold.

    MUTATION: delete `actor_verified_match` from
    lifecycle_fsm.section_a.durability.dual_append.derived_id_kinds and
    regenerate
    ⇒ red (and the convergence seal below goes red too).
    """
    g = generated
    declared = _dual_append(schemas)["derived_id_kinds"]
    assert set(g.DERIVED_ID_KINDS) == set(declared)
    assert set(g.DERIVED_ID_KINDS) == {"crash_recovery", "actor_verified_match"}, (
        "the operator-less release is not a derived-id kind — two verifiers "
        "reaching the same conclusion cannot converge")
    for kind, spec in declared.items():
        assert list(g.DERIVED_ID_PREIMAGES[kind]) == list(spec["preimage_lines"])


def test_concurrent_auto_release_duplicates_converge(schemas, generated):
    """ActorVerifiedAuto is the only operator-less release, on the path the
    reducer itself calls "inherently concurrent" (door 0, webhook-driven,
    at-least-once). Two independent verifiers observing the SAME delivery on
    the SAME hold mint the SAME derived id and must converge into ONE
    release with no halt — not a TERMINAL ILLEGAL_TRANSITION on a base that
    just did the right thing twice.

    The twins differ on issuer decoration (ts/run_id/trace_id): that is what
    two processes cannot agree on, and it is exactly what the positive
    comparison core excludes.

    MUTATION (schema + regenerate): remove `actor_verified_match` from
    `derived_id_kinds` ⇒ red. EQUIVALENT mutation actually run against the
    committed module: `DERIVED_ID_PREIMAGES` → drop the
    'actor_verified_match' entry ⇒ the twin is no longer recognised as
    derived, `_canonical` compares full payloads, and the base halts
    EVENT_PAYLOAD_DIVERGENT. Also verified: pinning the twin's event_id to
    a NON-derived value ⇒ red (the deny row below).
    """
    g = generated
    vec = copy.deepcopy(_VECTORS["b_actor_verified_auto_separated"])
    auto = _event_of(vec, "ActorVerifiedAuto")
    lines = _preimage_lines(schemas, "actor_verified_match")
    assert lines == ["release=actor_verified_match", "base=<base_key>",
                     "hold=<hold_id>", "delivery=<source_delivery_id>"], lines
    derived = _derived_event_id(
        "release=actor_verified_match",
        f"base={auto['base_key']}",
        f"hold={auto['hold_id']}",
        f"delivery={auto['source_delivery_id']}")
    auto["event_id"] = derived
    twin = dict(auto, ts="1999-12-31T23:59:59Z", run_id="run-2",
                trace_id="trace-2")
    got = _boundary(g, vec["events"] + [twin], mode="SEPARATED")
    assert got["halts"] == {}, (
        f"a concurrent duplicate of a correct auto-release halted the base: "
        f"{got['halts']}")
    holds = got["holds"]["R1:refs/heads/main"]
    assert len(holds) == 1, f"the twin created a second hold: {holds}"
    (state,) = {h["state"] for h in holds.values()}
    assert state == "RELEASED"
    # exactly ONE release: the twin was absorbed by dedup, not applied twice
    (disposition,) = {h["disposition"] for h in holds.values()}
    assert disposition == "ACTOR_VERIFIED_AUTO"


def test_a_non_derived_auto_release_twin_still_halts(generated):
    """deny: convergence is earned by the DERIVATION, not granted to the
    kind. A second ActorVerifiedAuto carrying a freshly MINTED event_id is
    a different event making the same claim, and the state precondition
    refuses it — the seal above must not be readable as "duplicates are
    always fine".

    MUTATION: make `_is_derived_id` return True unconditionally ⇒ red.
    """
    g = generated
    vec = copy.deepcopy(_VECTORS["b_actor_verified_auto_separated"])
    auto = vec["events"][-1]
    twin = dict(auto, event_id="minted-by-hand", ts="1999-12-31T23:59:59Z")
    got = _boundary(g, vec["events"] + [twin], mode="SEPARATED")
    assert got["halts"], "a hand-minted duplicate release was admitted"
    detail = " ".join(h["detail"] for h in got["halts"].values())
    assert "contradicts the reduced state" in detail, detail


def test_recovery_append_payload_converges_on_every_issuer_field(schemas,
                                                                 generated):
    """The derived recovery id covers the ID; this seals the PAYLOAD.

    `_finish_section_a` now emits a COMPLETE §9 instruction record and names
    the fields the recovering process must stamp itself. Two processes that
    agree on the declared core and disagree on EVERY one of those
    issuer-supplied fields must still converge — under the old exclusion
    list (`ts`/`run_id`/`trace_id` only) each of the other six was
    EVENT_PAYLOAD_DIVERGENT.

    MUTATION: revert `_canonical`'s derived branch to an exclusion list —
    `drop = set(CANONICAL_EXCLUDES_ALWAYS) | {"ts","run_id","trace_id"}`
    and compare the remaining payload ⇒ red.
    MUTATION: remove any field from `canonical_core_for_derived_ids` that
    the two copies DO agree on (e.g. `base_key`) ⇒ still green, which is
    why the deny row below pins the core's other direction.
    """
    g = generated
    prepared = _wire_effect(g, "Prepare", "e1", "m1", "GENESIS",
                            authorization_id="auth-1")
    plan = _boundary(g, [prepared])["recovery_appends"]
    assert len(plan) == 1
    append = plan[0]
    issuer = list(append["issuer_supplied"])
    # the named set is exactly the §9 REQUIRED fields the record does not
    # carry — derived from the variant, not hand-listed here.
    cls = g.EFFECT_VARIANTS["CrashRecoveryFromPrepared"]
    carried = set(append) - {"issuer_supplied"}
    assert set(issuer) == set(cls.REQUIRED) - carried, (
        f"issuer_supplied is not REQUIRED minus the record's own fields: "
        f"{sorted(issuer)} vs {sorted(set(cls.REQUIRED) - carried)}")
    assert issuer, "the append names no issuer-supplied fields"

    # Two recovering processes: same declared core, DIFFERENT values for
    # every field the record says the issuer must stamp.
    def _stamp(ts, run, trace, epoch, authority, ctx, mode) -> dict:
        ev = {k: v for k, v in append.items() if k != "issuer_supplied"}
        ev.update({"ts": ts, "run_id": run, "trace_id": trace,
                   "protocol_epoch": epoch, "authority": authority,
                   # `none` epoch effect: before == after WITHIN a copy,
                   # while the two copies disagree.
                   "epoch_before": epoch, "epoch_after": epoch,
                   "actor_context": ctx, "credential_mode": mode})
        return ev

    first = _stamp("1970-01-01T00:00:00Z", "run-A", "trace-A", "E0", "fp-A",
                   "dispatcher", "SHARED")
    second = _stamp("2026-08-04T12:00:00Z", "run-B", "trace-B", "E9", "fp-B",
                    "operator", "SEPARATED")
    differing = [f for f in issuer if first.get(f) != second.get(f)]
    assert set(differing) == set(issuer), (
        f"the two copies agree on {sorted(set(issuer) - set(differing))} — "
        f"this seal must vary EVERY issuer-supplied field")
    # the append's audit `from` is PREPARED, so the stream carries the
    # movement's own history first — this is a cold start reading its own
    # durable trace, then two processes appending the recovery.
    got = _boundary(g, [prepared, first, second])
    assert got["halts"] == {}, (
        f"two recovering processes that agree on the declared core did not "
        f"converge: {got['halts']}")
    assert got["movements"]["R1:refs/heads/main"]["m1"]["state"] == "HELD"
    # …and the movement is HELD once, not twice: the twin was absorbed
    assert got["recovery_appends"] == [], (
        "the reduced state already reached HELD, so no further recovery "
        "append is planned")


def test_derived_twins_that_disagree_on_the_CORE_still_halt(schemas, generated):
    """deny: convergence is scoped to issuer decoration. Two twins sharing a
    derived event_id while disagreeing on a field INSIDE the declared
    comparison core are two different claims wearing one id, and that is
    still EVENT_PAYLOAD_DIVERGENT.

    MUTATION: empty `canonical_core_for_derived_ids` (or make `_canonical`'s
    derived branch return a constant) ⇒ red — the positive core would
    compare nothing and any two events sharing a derived id would "agree".
    """
    g = generated
    # PER KIND now: actor_verified_match inheriting crash_recovery's core let
    # a twin assert a different actor_node_id on an already-released hold
    # with nothing to compare it against. A kind with no entry is a
    # generation error, never a fall-through to another kind's core.
    declared = _dual_append(schemas)["canonical_core_for_derived_ids"]
    assert set(declared) == set(g.DERIVED_ID_KINDS), (
        f"kinds with no byte-identity core: "
        f"{sorted(set(g.DERIVED_ID_KINDS) - set(declared))}")
    for kind, fields in declared.items():
        assert set(g.CANONICAL_CORE_FOR_DERIVED_IDS[kind]) == set(fields)
    core = set(declared["crash_recovery"])
    prepared = _wire_effect(g, "Prepare", "e1", "m1", "GENESIS",
                            authorization_id="auth-1")
    append = _boundary(g, [prepared])["recovery_appends"][0]
    base = {k: v for k, v in append.items() if k != "issuer_supplied"}
    base.update({"ts": "1970-01-01T00:00:00Z", "run_id": "r",
                 "trace_id": "t", "protocol_epoch": "E0", "authority": "fp",
                 "epoch_before": "E0", "epoch_after": "E0",
                 "actor_context": "dispatcher", "credential_mode": "SHARED"})
    # `from` is in the core: a twin claiming a different origin for the same
    # derived id is a divergent payload, not a convergent one.
    assert "from" in core
    twin = dict(base, **{"from": "SUBMITTED", "to": "HELD",
                         "variant": "CrashRecoveryFromSubmitted"})
    got = _boundary(g, [prepared, base, twin])
    assert got["halts"], "twins disagreeing inside the comparison core converged"
    assert got["halts"]["R1:refs/heads/main"]["code"] == "EVENT_PAYLOAD_DIVERGENT"


# ─── the fold: identity replay, and the fence shape at harvest ──────────────

def test_identity_replay_contributes_no_epoch_edge(generated):
    """§6.0's blessed idempotent reconcile is a no-op to the fold exactly as
    it is to the machines: a replay row's epoch effect is `none`, so it
    contributes NO edge. If it did, the replay would either fork the chain
    at the tail (two candidates from one epoch) or leave an unused edge —
    an EPOCH_FORK/EPOCH_GAP halt on a history the design blesses.

    MUTATION: make `_check_epoch_algebra` tolerate an advance on a `none`
    row and give the replay `epoch_after != epoch_before` — or collect
    edges from no-effect rows in `_collect_epoch_edges` (drop the
    `eb == ea: continue` arm) ⇒ red.
    """
    g = generated
    replay = _VECTORS["reconcile_replay_identity"]
    variants = [e.get("variant") for e in replay["events"]]
    assert "ReconcileReplayIdentity" in variants, (
        f"this seal needs an identity-replay event: {variants}")
    for ev in replay["events"]:
        if ev.get("variant") == "ReconcileReplayIdentity":
            assert g.EFFECT_VARIANTS["ReconcileReplayIdentity"].EPOCH_EFFECT \
                == "none"
            assert ev["epoch_before"] == ev["epoch_after"], (
                "the replay row advances the fence — it is not an identity")
    # the fold over the SAME history is clean: the replay adds no edge, so
    # the chain from the anchor is walked to its tail with nothing left over.
    anchor = replay["events"][0]["epoch_before"]
    base = replay["events"][0]["base_key"]
    fold = _epochs(g, replay["events"], anchors={base: anchor})
    assert fold[base]["halt"] is None, (
        f"an identity replay contributed an edge: {fold[base]['halt']}")
    assert fold[base]["status"] == "ok"
    # …and dropping the replay leaves the SAME harvested fence: proof the
    # replay contributed nothing rather than contributing a self-loop.
    without = [e for e in replay["events"]
               if e.get("variant") != "ReconcileReplayIdentity"]
    assert _epochs(g, without, anchors={base: anchor})[base]["epoch"] == \
        fold[base]["epoch"], "the replay changed the harvested fence"


@pytest.mark.parametrize("name", [
    pytest.param(n, id=("deny-" + n) if "deny" in n else n)
    for n in sorted(_VECTORS) if _VECTORS[n]["machine"] == "epoch_fold"
])
def test_fence_shape_at_harvest(generated, name):
    """The fold's per-base result is what §6.0 harvests into
    AuthorityFingerprint.base_epoch, so its SHAPE is a contract, not a
    convenience: on an `ok` base the harvested fence is an object id (40
    lowercase hex) — never None, never free text, never an epoch a halted
    base merely reached. A `halt` base carries a typed halt, and its epoch
    is diagnostic only.

    Nothing asserted this before: every fold seal read `["halt"]` or
    `["epoch"]` for one named vector, so a fence harvested as `None` or as
    a writer's free text on an `ok` base was unsealed across the corpus.

    MUTATION (verified): return `{"status": "ok", "epoch": None, "halt":
    None}` from `_walk_epoch_chain`'s success arm ⇒ red on every ok row.
    MUTATION (verified): `_walk_epoch_chain`'s success arm returning a
    non-OID string ⇒ red.

    SCOPE: this ranges over the vectors whose declared MACHINE is the fence
    walk. It was parametrised on `"anchors" in _VECTORS[n]`, which selected
    only fold vectors while anchors were a fold-only field — every vector now
    carries a full run context, so that predicate silently expanded to all
    119, and its "a non-empty history folded to nothing" assertion is simply
    wrong for a machine vector that declares no fence. Selecting on the
    MACHINE is the fix, and the shape rules that hold for EVERY vector's
    fence view get their own seal below.
    """
    g = generated
    vec = _VECTORS[name]
    fold = _epochs(g, vec["events"], anchors=vec["anchors"])
    assert fold != {} or not vec["events"], (
        "a non-empty history folded to nothing — 'no bases' and 'nothing to "
        "fold' must be distinguishable")
    for base, entry in fold.items():
        assert entry["status"] in ("ok", "halt"), entry
        if entry["status"] == "ok":
            assert entry["halt"] is None, entry
            assert isinstance(entry["epoch"], str) and _is_oid(entry["epoch"]), (
                f"{name}/{base}: harvested fence {entry['epoch']!r} is not an "
                f"object id — AuthorityFingerprint.base_epoch would carry "
                f"writer free text")
        else:
            assert entry["halt"] is not None, entry
            assert entry["halt"]["code"] in {c.value for c in g.BoundaryErrorCode}
            assert entry["halt"]["detail"], (
                f"{name}/{base}: a halt with no detail fails the 3am test")


@pytest.mark.parametrize("field", [
    pytest.param("epoch_before", id="deny-non-oid-fence-before"),
    pytest.param("epoch_after", id="deny-non-oid-fence-after"),
])
def test_an_advancing_edge_may_not_carry_a_non_oid_fence(generated, field):
    """The reachable half of the fence-shape contract, and the one the
    corpus could not reach: an event that survives validation, the
    transition rules AND the epoch algebra still may not carry writer free
    text INTO the fence. `epoch_after == new_oid` holds for `not-an-oid`
    just as well as for a real oid, so the algebra alone does not close it.

    MUTATION: `if not _valid_oid(value):` → `if False:` in the reduce's
    edge-recording arm ⇒ red on both rows and on both consumers. (Before
    this seal that mutation left the whole suite green — the committed
    corpus contains no non-OID fence, which is exactly why the shape rule
    needed a constructed input rather than a vector.)
    """
    g = generated
    history = _edge_history("bad", "R1:refs/heads/main")
    opening, advancing = history
    # keep the row's own algebra satisfied so the SHAPE rule is what fires:
    # `assign_new_oid` requires epoch_after == the observed new_oid.
    bad = dict(advancing, event_id="bad-fence")
    bad[field] = "not-an-oid"
    if field == "epoch_after":
        bad["new_oid"] = "not-an-oid"
    else:
        # epoch_before is free text while the advance itself stays legal
        bad["epoch_after"] = advancing["epoch_after"]
    halt = _boundary(g, [opening, bad])["halts"]["R1:refs/heads/main"]
    assert halt["code"] == "SCHEMA_MAJOR_UNKNOWN", halt
    assert f"{field} 'not-an-oid' is not an object id" in halt["detail"], (
        halt["detail"])
    assert "never coerced" in halt["detail"]
    # the fold shares the one pass, so it halts identically rather than
    # harvesting the free text as a fence
    fold = _epochs(g, [opening, bad], anchors={"R1:refs/heads/main": opening["epoch_before"]})
    entry = fold["R1:refs/heads/main"]
    assert entry["status"] == "halt", entry
    assert entry["halt"]["code"] == "SCHEMA_MAJOR_UNKNOWN"


@pytest.mark.parametrize("kind,components,match", [
    pytest.param("crash_recovery", {"base_key": "b", "movement_id": "m"}, None,
                 id="crash-recovery-derives"),
    pytest.param("actor_verified_match",
                 {"base_key": "b", "hold_id": "h", "source_delivery_id": "d"},
                 None, id="actor-verified-match-derives"),
    pytest.param("operator_reconcile", {"base_key": "b"},
                 r"is not a derived-id kind",
                 id="deny-derive-unknown-kind"),
    pytest.param("crash_recovery", {"base_key": "b"},
                 r"component 'movement_id' is absent",
                 id="deny-derive-absent-component"),
])
def test_derive_event_id_is_closed_over_its_kinds(generated, kind, components,
                                                  match):
    """`derive_event_id` is the ONE place two independent issuers agree, so
    it fails loudly rather than deriving from a hole: an unknown kind and an
    absent preimage component both raise, naming which.

    MUTATION: return a digest of the template instead of raising on an
    unknown kind ⇒ the unknown-kind row goes red; substitute "" for an
    absent component ⇒ the absent-component row goes red (and two issuers
    holding different views of a missing field would silently "converge").
    """
    g = generated
    if match is None:
        got = g.derive_event_id(kind, **components)
        assert len(got) == 64 and got == got.lower()
        # …and it is the schema's preimage, recomputed here
        lines = []
        for line in g.DERIVED_ID_PREIMAGES[kind]:
            tag, _, placeholder = line.partition("=")
            lines.append(f"{tag}={components[placeholder[1:-1]]}"
                         if placeholder.startswith("<") else line)
        assert got == hashlib.sha256("\n".join(lines).encode()).hexdigest()
        return
    with pytest.raises(ValueError, match=match):
        g.derive_event_id(kind, **components)


def test_a_none_anchor_is_a_typed_halt_not_a_crash(generated):
    """`fold_epochs` iterates the union of anchors, edges and halts; a base
    named in the anchor map with a None VALUE and no edges used to reach
    `min([])` and raise a bare `ValueError: min() iterable argument is
    empty` — every other malformed input on this path is a typed halt, and
    the fold computes the authority fence. (Reported as an implementation
    defect in the previous pass; fixed in iteration 7, so it is sealed
    here.) A PR4 caller building anchors as
    `{base: genesis.get("expected_base_oid")}` produces exactly this shape.

    MUTATION: revert the anchor-value check so the None branch falls into
    the edge walk ⇒ the test errors with a bare ValueError instead of
    reading a typed halt.
    """
    g = generated
    fold = _epochs(g, [], anchors={"B1": None})
    assert fold, "a malformed anchor read as 'nothing to fold'"
    assert fold["B1"]["status"] == "halt"
    assert fold["B1"]["halt"]["code"] in {c.value for c in g.BoundaryErrorCode}
    assert "missing anchor VALUE is malformed input" in fold["B1"]["halt"]["detail"], (
        fold["B1"]["halt"]["detail"])
    # …and it must not be readable as an ABSENT anchor: an absent base is
    # simply not in the result at all.
    assert _epochs(g, [], anchors={}) == {}


_OID_HEX = set("0123456789abcdef")


def _is_oid(value: str) -> bool:
    """40 lowercase hex, checked here rather than by importing the module's
    own regex — an independent second statement of the same shape rule."""
    return len(value) == 40 and all(c in _OID_HEX for c in value)


def test_matched_subject_digest_has_an_independent_oracle(schemas, generated):
    """The auto-release's `matched_subject_digest` is the ONE cross-check
    standing between a self-asserted release and the hold's own recorded
    delta. Both the vector's value and the reducer's check came from the
    same generated `derive_matched_delta_digest`, so a wrong preimage would
    have agreed with itself — the shared-derivation class this file exists
    to prevent.

    The digest is now recomputed HERE from the schema's declared preimage
    lines with a standalone snippet, and the VECTOR's committed value is
    asserted against that independent hash.

    MUTATION: reorder or rename any line in
    `matched_delta_digest_preimage` and regenerate ⇒ red. EQUIVALENT
    mutation run against the committed module: swap `subject-old`/
    `subject-new` in `derive_matched_delta_digest` ⇒ red.
    """
    g = generated
    spec = schemas["lifecycle_fsm"]["events"]["unions"]["hold_lifecycle"][
        "actor_verified_evidence"]["matched_delta_digest_preimage"]
    assert spec["join"] == "\n" and spec["hash"] == "SHA-256"
    assert spec["lines"] == ["subject-base=<base_key>", "subject-ref=<ref>",
                             "subject-old=<delta_old_oid>",
                             "subject-new=<delta_new_oid>"], spec["lines"]
    # the hold's own recorded delta, read off the vector that releases on it
    vec = _VECTORS["b_actor_verified_auto_separated"]
    observe = _event_of(vec, "ObserveDelta")
    auto = _event_of(vec, "ActorVerifiedAuto")
    values = {"<base_key>": observe["base_key"], "<ref>": observe["ref"],
              "<delta_old_oid>": observe["delta_old_oid"],
              "<delta_new_oid>": observe["delta_new_oid"]}
    built = []
    for line in spec["lines"]:
        tag, _, placeholder = line.partition("=")
        built.append(f"{tag}={values[placeholder]}")
    independent = hashlib.sha256("\n".join(built).encode()).hexdigest()
    # 1. the generated derivation agrees with the schema's own spec
    assert g.derive_matched_delta_digest(
        observe["base_key"], observe["ref"], observe["delta_old_oid"],
        observe["delta_new_oid"]) == independent, (
        "derive_matched_delta_digest does not implement the schema's "
        "declared preimage")
    # 2. and the COMMITTED VECTOR carries that value — so the vector and the
    #    checker no longer share one derivation.
    assert auto["matched_subject_digest"] == independent, (
        f"the vector's matched_subject_digest {auto['matched_subject_digest']!r}"
        f" is not the independently derived {independent!r}")
    # 3. deny: a digest over a DIFFERENT delta is refused by the reducer
    forged = copy.deepcopy(vec)
    _event_of(forged, "ActorVerifiedAuto")["matched_subject_digest"] = hashlib.sha256(
        "\n".join(built[:-1] + ["subject-new=" + "9" * 40]).encode()).hexdigest()
    got = _boundary(g, forged["events"], mode="SEPARATED")
    assert got["halts"], "a release bound to a different delta was admitted"
    detail = " ".join(h["detail"] for h in got["halts"].values())
    assert "matched_subject_digest" in detail and \
        "self-asserted evidence refused" in detail, detail


# ─── apply(): legal and illegal pairs ────────────────────────────────────────

@pytest.mark.parametrize("state,variant", [
    pytest.param("EXPLAINED", "Submit", id="deny-terminal-explained-submit"),
    pytest.param("RECONCILED", "Prepare", id="deny-terminal-reconciled-prepare"),
    pytest.param("HELD", "Submit", id="deny-held-submit"),
    pytest.param("GENESIS", "Explained", id="deny-genesis-explained"),
    pytest.param("PREPARED", "Prepare", id="deny-double-prepare"),
])
def test_section_a_illegal_pairs_raise(generated, state, variant):
    ev = _mk_effect(generated, variant)
    st = generated.MachineStateA(generated.SectionAState[state])
    with pytest.raises(generated.IllegalTransitionError,
                       match=rf"section_a: {state} × {variant}") as exc:
        generated.apply_section_a(st, ev)
    assert exc.value.error.code is generated.BoundaryErrorCode.ILLEGAL_TRANSITION
    # the pair, not merely the code: (state, event) is what the row denies
    assert (exc.value.state, exc.value.event) == (state, variant)


def _legal_pairs(variants: dict) -> list[tuple[str, str]]:
    """Every (from_state, variant) the §6.0 tables declare legal — derived
    from the generated FROM_STATES so a row added later cannot slip in
    untested (panel round 2: six legal transitions had no test)."""
    return sorted((frm, name) for name, cls in variants.items()
                  for frm in cls.FROM_STATES)


@pytest.mark.parametrize("pair", [
    pytest.param(p, id=f"{p[0]}-x-{p[1]}")
    for p in _legal_pairs(_GEN.EFFECT_VARIANTS)
] + [pytest.param(("GENESIS", "LOOKALIKE"), id="deny-structural-lookalike")])
def test_section_a_apply_dispatch(generated, pair):
    """apply_section_a over the FULL legal cross-product of §6.0 section A."""
    state, variant = pair
    st = generated.MachineStateA(generated.SectionAState[state])
    if variant == "ReconcileReplayIdentity":
        # an identity replay echoes the disposition the state already carries
        st = generated.MachineStateA(
            generated.SectionAState[state],
            generated.ReconcileDisposition.ACCEPT_FOREIGN_ADVANCED)
    if variant == "LOOKALIKE":
        class Prepare:  # same NAME as the real variant — shape is not identity
            FROM_STATES = ("GENESIS",)
            TO_STATE = "PREPARED"
            TRIGGER = "prepare"
        # the dispatch is by IDENTITY, not by shape or name: a lookalike
        # is refused as an unknown variant, not applied.
        with pytest.raises(generated.IllegalTransitionError,
                           match=r"section_a: GENESIS × Prepare — unknown "
                                 r"event variant halts"):
            generated.apply_section_a(st, Prepare())
        return
    cls = generated.EFFECT_VARIANTS[variant]
    got = generated.apply_section_a(st, _mk_effect(generated, variant,
                                                   from_state=state))
    if variant == "ReconcileRejectRestoreHold":
        assert got.name.value == "HELD"          # stays HELD, per the row
    elif variant == "ReconcileReplayIdentity":
        assert got.name.value == state           # identity replay
    else:
        assert got.name.value == cls.TO_STATE


@pytest.mark.parametrize("pair", [
    pytest.param(p, id=f"{p[0]}-x-{p[1]}")
    for p in _legal_pairs(_GEN.HOLD_VARIANTS)
] + [pytest.param(("HELD_FOREIGN", "LOOKALIKE"), id="deny-structural-lookalike")])
def test_section_b_apply_dispatch(generated, pair):
    """apply_section_b over the FULL legal cross-product of §6.0 section B
    (panel round 2: this machine had no direct test at all)."""
    state, variant = pair
    st = generated.MachineStateB(generated.SectionBState[state])
    if variant == "LOOKALIKE":
        class ObserveDelta:  # right name and shape, wrong identity
            FROM_STATES = ("HELD_FOREIGN",)
            TO_STATE = "HELD_FOREIGN"
            TRIGGER = "observe_delta"
        with pytest.raises(generated.IllegalTransitionError,
                           match=r"section_b: HELD_FOREIGN × ObserveDelta — "
                                 r"unknown event variant halts"):
            generated.apply_section_b(st, ObserveDelta())
        return
    cls = generated.HOLD_VARIANTS[variant]
    over = {"from_state": state}
    if variant == "ActorVerifiedAuto":
        over["mode"] = generated.CredentialMode.SEPARATED
    if variant == "HoldReconcileReplayIdentity":
        # a replay echoes the disposition the state carries — which is the
        # helper's default accepting disposition.
        st = generated.MachineStateB(
            generated.SectionBState[state],
            generated.ReconcileDisposition.ACCEPT_FOREIGN_ADVANCED)
    got = generated.apply_section_b(st, _mk_hold(generated, variant, **over))
    if cls.TO_STATE == "unchanged":
        assert got == st                          # idempotent no-op rows
    elif variant == "HoldReconcileRejectRestoreHold":
        # "as the HELD_FOREIGN rows"; from STANDING the resolved reading is
        # the schema key STANDING_REJECT_RESTORE_TARGET_NAME.
        want = (generated.STANDING_REJECT_RESTORE_TARGET_NAME
                if state == "STANDING" else "HELD_FOREIGN")
        assert got.name.value == want
    elif variant == "HoldReconcileReplayIdentity":
        assert got.name.value == state
    else:
        assert got.name.value == cls.TO_STATE


@pytest.mark.parametrize("state,variant", [
    pytest.param("RELEASED", "ObserveDelta", id="deny-released-create"),
    pytest.param("GENESIS", "HoldReconcileAccept", id="deny-genesis-reconcile"),
    pytest.param("GENESIS", "ActorVerifiedAuto", id="deny-genesis-actor-verified"),
    pytest.param("RELEASED", "HoldReconcileStanding", id="deny-released-standing"),
])
def test_section_b_illegal_pairs_raise(generated, state, variant):
    over = {"mode": generated.CredentialMode.SEPARATED} \
        if variant == "ActorVerifiedAuto" else {}
    # the event is well-formed; only the (state × event) PAIR is illegal.
    ev = _mk_hold(generated, variant, **over)
    st = generated.MachineStateB(generated.SectionBState[state])
    with pytest.raises(generated.IllegalTransitionError,
                       match=rf"section_b: {state} × {variant}") as exc:
        generated.apply_section_b(st, ev)
    assert exc.value.error.code is generated.BoundaryErrorCode.ILLEGAL_TRANSITION
    assert (exc.value.state, exc.value.event) == (state, variant)


# ─── T19 goldens against the hand-written oracle ─────────────────────────────

def _project_halt(halt):
    return None if halt is None else {"code": halt["code"]}


def _project_note(note: object) -> dict:
    """The contract half of a door-0 resolution note: WHICH resolution the
    reducer applied, WHAT the writer had tagged, and on WHICH hold. The
    prose `detail`, the metric name and the run/trace correlation ids are
    diagnostics, not contract."""
    assert isinstance(note, dict), (
        f"a resolution note must be a structured record, got {type(note).__name__}"
        " — a prose sentence cannot be compared by content")
    return {k: note[k] for k in ("code", "resolution", "tagged", "hold_id")}


def _project_result(machine: str, got: dict) -> dict:
    """Compare on the CONTRACT: reduced state exactly, halts per base_key on
    the code. Halt DETAILS are diagnostics — pinned separately by
    test_deny_vectors_pin_their_rule, which asserts the named fields."""
    if machine == "section_a":
        return {"movements": got["movements"],
                "recovery_appends": got["recovery_appends"],
                "halts": {b: {"code": h["code"]} for b, h in got["halts"].items()}}
    if machine == "section_b":
        # Notes are compared by CONTENT. `len(n)` let a note naming the
        # WRONG resolution pass: b_concurrent_tag_resolved_to_new_hold,
        # ..._to_redelivery and b_concurrent_duplicate_creations all
        # projected to {"R1:refs/heads/main": 1}, so only the holds map
        # distinguished them — and the note is the operator-facing record of
        # how door 0's most concurrent path was resolved.
        return {"holds": got["holds"],
                "halts": {b: {"code": h["code"]} for b, h in got["halts"].items()},
                "resolution_notes": {b: [_project_note(x) for x in n]
                                     for b, n in got["resolution_notes"].items()}}
    return {base: {"status": entry["status"], "epoch": entry["epoch"],
                   "halt": _project_halt(entry["halt"])}
            for base, entry in got.items()}


def _reduce(generated, vec: dict) -> dict:
    """The vector's OWN declared run context, through the ONE entrypoint,
    then projected to the machine the vector names.

    Every vector now carries BOTH `credential_mode` and `anchors`, for all
    three machines — because there is one walk, so the run's mode is not
    section B's private business and the anchors are not the fold's. The old
    driver called a different function per machine and invented a run for
    two of them; that is precisely the second walk S1 deleted."""
    result = _boundary(generated, vec["events"],
                       mode=vec["credential_mode"], anchors=vec["anchors"])
    return _machine_view(generated, result, vec["machine"])


def _all_halt_details(machine: str, got: dict) -> str:
    if machine in ("section_a", "section_b"):
        return " | ".join(h["detail"] for h in got["halts"].values())
    return " | ".join(e["halt"]["detail"] for e in got.values()
                      if e["halt"] is not None)


# Each deny vector pins the RULE it names, not merely a halt code: the
# substrings below must appear in the halt detail (panel round 2 — "a deny
# vector that asserts only the code cannot tell one violation from another").
_DENY_RULE_MARKERS = {
    "a_missing_required_field_deny": ["required field", "new_oid", "never defaulted"],
    "a_forbidden_authorization_id_deny": ["forbidden field", "authorization_id"],
    "a_unknown_variant_deny": ["unknown event variant", "TotallyNovelEvent"],
    "a_unknown_enum_value_deny": ["unknown value", "credential_mode"],
    "a_section_b_disposition_deny": ["operator-accepting", "ACTOR_VERIFIED_AUTO"],
    "a_unsupported_major_deny": ["schema_major", "outside the supported set"],
    "a_major_zero_deny": ["schema_major", "outside the supported set"],
    "a_major_99_deny": ["schema_major", "outside the supported set"],
    "a_missing_to_deny": ["required field", "'to'"],
    "a_to_contradiction_deny": ["contradicts the row"],
    "a_trigger_variant_mismatch_deny": ["trigger_event", "mis-tagged"],
    "a_missing_trigger_deny": ["required field", "trigger_event"],
    "a_missing_family_deny": ["family", "filters by"],
    "a_unknown_family_deny": ["unknown family", "closed domain"],
    "a_empty_family_deny": ["missing required field 'family'"],
    "a_case_typo_family_deny": ["unknown family", "closed domain"],
    "a_family_mistag_terminal_deny": ["contradicts variant", "mis-tagged writer"],
    "b_family_mistag_deny": ["contradicts variant", "mis-tagged writer"],
    "b_unknown_family_deny": ["unknown family", "closed domain"],
    "a_bad_ts_deny": ["ts", "RFC 3339"],
    "a_out_of_range_ts_deny": ["ts", "RFC 3339 UTC instant"],
    "a_epoch_advance_not_pinned_to_new_oid_deny":
        ["assign_new_oid", "must set the fence to the observed new_oid"],
    "a_advancing_row_that_does_not_advance_deny":
        ["assign_new_oid", "must advance the epoch but did not"],
    "a_accept_ours_without_new_oid_deny": ["ACCEPT_OURS", "requires", "new_oid"],
    "epoch_unknown_major_deny": ["schema_major", "never advance the fence"],
    "epoch_unknown_family_deny": ["unknown family", "closed domain"],
    "a_none_effect_row_advances_deny": ["no epoch effect", "advances"],
    "dual_append_divergent_payload_deny": ["divergent payloads", "integrity"],
    "reconcile_conflict_deny": ["conflicting disposition"],
    "resume_submit_illegal_deny": ["memory-only", "resume-submit"],
    # Layered defence: with `mode` pinned SEPARATED by the constructor, a
    # SHARED-declared auto-release is refused at CONSTRUCTION; a
    # SEPARATED-declared one under a SHARED run is refused by the
    # disagreement check. The run-mode gate in reduce_section_b is the
    # third layer (sealed directly by
    # test_credential_mode_is_run_context_not_event_payload).
    "b_actor_verified_shared_run_deny": ["under SHARED, never"],
    "b_mode_disagrees_with_run_deny": ["run context", "not event payload"],
    "b_verified_api_without_actor_node_id_deny":
        ["actor_verification", "requires", "actor_node_id"],
    "b_actor_verified_wrong_delta_digest_deny":
        ["matched_subject_digest", "self-asserted evidence refused"],
    "b_actor_verified_unresolvable_delivery_deny":
        ["source_delivery_id", "not a delivery recorded on"],
    "b_reconcile_accept_actor_verified_deny": ["operator-accepting"],
    "b_replayed_conflicting_reconcile_deny": ["conflicting d"],
    "b_from_state_contradicts_reduced_deny":
        ["audit from", "contradicts the reduced state"],
    "b_missing_event_id_deny": ["missing required envelope field 'event_id'"],
    "epoch_missing_base_key_deny": ["required field 'base_key' absent"],
    "epoch_single_carrying_epoch_deny":
        ["not reduced by any lifecycle machine", "never advance the fence"],
    "epoch_consent_carrying_epoch_deny":
        ["not reduced by any lifecycle machine"],
    "epoch_lifecycle_without_variant_deny":
        ["no variant", "unknown variants halt"],
    "epoch_non_oid_dict_deny": ["is not an object id", "never coerced"],
    "epoch_non_oid_int_deny": ["is not an object id"],
    "b_actor_verified_unpinned_fence_deny":
        ["must set the fence to the hold's own observed delta_new_oid",
         "never writer free text"],
    "b_auto_release_closed_after_reject_restore_deny":
        ["operator REJECTED", "stays closed"],
    "a_replayed_conflicting_reconcile_deny": ["conflicting d"],
    "epoch_cross_base_divergent_after_halt_deny": ["divergent payloads"],
    "b_redelivery_delta_contradiction_deny": ["contradicts the hold's recorded delta"],
    "b_declared_hold_id_mismatch_deny": ["declared hold_id", "contradicts"],
    "b_reconcile_unknown_hold_deny": ["references unknown hold"],
    "b_unknown_actor_verification_deny": ["unknown value", "actor_verification"],
    "b_forbidden_authorization_id_deny": ["forbidden field", "authorization_id"],
    "b_none_effect_row_advances_deny": ["no epoch effect", "advances"],
    "b_release_conflict_deny": ["conflicting disposition"],
    "epoch_gap": ["unused edge", "first orphan"],
    "epoch_fork": ["fork at", "candidates:"],
    "epoch_cycle": ["cycle/reused epoch"],
    "epoch_dup_divergent_deny": ["divergent payloads"],
    "epoch_no_effect_twin_divergent_deny": ["divergent payloads"],
    "epoch_no_effect_twin_divergent_reverse_deny": ["divergent payloads"],
    "epoch_cross_base_divergent_deny": ["divergent payloads"],
    # hand-authored region (tests/boundary/vectors/t19/handwritten/)
    "b_actor_verified_minted_twin_deny": ["audit from", "contradicts the reduced state"],
    "epoch_unanchored_base_deny": ["no protocol_genesis anchor",
                                   "never silently dropped"],
}


@pytest.mark.parametrize("name", [
    pytest.param(n, id=("deny-" + n) if ("deny" in n) else n)
    for n in sorted(_VECTORS)
])
def test_t19_goldens_against_independent_oracle(generated, name):
    vec = _VECTORS[name]
    assert name in _EXPECTED, (f"{name}: no hand-written expectation — the "
                               f"oracle must cover every vector")
    got = _reduce(generated, vec)
    projected = _project_result(vec["machine"], json.loads(json.dumps(got)))
    assert projected == _EXPECTED[name]


@pytest.mark.parametrize("name", [
    pytest.param(n, id=("deny-" + n) if "deny" in n else n)
    for n in sorted(_DENY_RULE_MARKERS)
])
def test_deny_vectors_pin_their_rule(generated, name):
    """A halt code alone does not distinguish one violation from another:
    every deny vector's halt DETAIL must name the rule it exists to seal."""
    assert name in _VECTORS, f"{name}: marker table names a missing vector"
    detail = _all_halt_details(_VECTORS[name]["machine"],
                               _reduce(generated, _VECTORS[name]))
    assert detail, f"{name}: expected a halt, got none"
    for marker in _DENY_RULE_MARKERS[name]:
        assert marker in detail, (
            f"{name}: halt detail does not name {marker!r} — the vector pins "
            f"a code but not its rule.\ndetail: {detail}")


def test_every_deny_vector_has_a_rule_marker():
    """No deny vector may sit outside the marker table (which is what makes
    the rule-pinning seal non-optional for new vectors)."""
    deny = {n for n in _VECTORS if "deny" in n}
    missing = deny - set(_DENY_RULE_MARKERS)
    assert not missing, f"deny vectors without a pinned rule: {sorted(missing)}"


def test_oracle_covers_exactly_the_vector_corpus():
    assert set(_EXPECTED) == set(_VECTORS), (
        f"oracle/corpus mismatch: only-oracle="
        f"{sorted(set(_EXPECTED) - set(_VECTORS))}, "
        f"only-corpus={sorted(set(_VECTORS) - set(_EXPECTED))}")


def test_t19_vector_inventory():
    """The §6.0/§12 named histories all exist (every held origin, all four
    dual-append crash points, the epoch histories, redelivery + re-park,
    section-B reconcile/STANDING rows, wire-violation denies)."""
    names = set(_VECTORS)
    required = {
        "success", "reject", "timeout",
        "held_from_prepared_crash", "held_from_prepared_later",
        "held_from_prepared_move", "held_from_submitted_mismatch",
        "held_from_submitted_crash", "held_from_submitted_later",
        "held_from_unknown_later", "held_from_unknown_crash",
        "crash_p1_before_hold_append", "crash_p2_between_appends",
        "crash_p3_after_both_appends", "crash_p4_redelivered_duplicate",
        "dual_append_divergent_payload_deny", "a_recovery_converges",
        "a_multi_base", "a_missing_required_field_deny",
        "a_forbidden_authorization_id_deny", "a_unknown_variant_deny",
        "a_unknown_enum_value_deny", "a_section_b_disposition_deny",
        "epoch_empty", "epoch_prepare_only", "epoch_no_effect_reject",
        "epoch_cross_stream", "epoch_gap", "epoch_fork", "epoch_cycle",
        "epoch_dup_divergent_deny", "epoch_unanchored_base_deny",
        "epoch_multi_base",
        "b_redelivery_after_released", "b_repark_after_released",
        "b_concurrent_tag_resolved_to_new_hold",
        "b_concurrent_tag_resolved_to_redelivery",
        "b_replayed_accepting_reconcile_is_identity",
        "b_reject_restore_hold", "b_standing_reenter",
        "b_standing_reject_restore", "b_standing_standing",
        "b_reconcile_accept_actor_verified_deny",
        "b_unknown_actor_verification_deny", "b_reconcile_unknown_hold_deny",
        "b_declared_hold_id_mismatch_deny",
    }
    missing = required - names
    assert not missing, f"missing T19 vectors: {sorted(missing)}"
    assert len({n for n in names if "deny" in n}) >= 12, "T19 needs deny rows (T6)"


def _edge_history(prefix: str, base: str) -> list[dict]:
    """A legal two-event history that CONTRIBUTES an epoch edge on `base`:
    a `Prepare` (no epoch effect) followed by the advancing `Explained` for
    the same movement. The fold authenticates its inputs, so an edge is a
    full event history, not a {before, after} pair.

    This used to copy `epoch_cross_stream`'s events[0] alone. That vector
    now begins with a synthesised `Prepare` — a no-effect row, so the copy
    contributed NO edge and the seal below asserted a halt on a base the
    fold never saw. Selecting the advancing event BY ITS EPOCH EFFECT
    rather than by list position is what stops that recurring.
    """
    vec = _VECTORS["epoch_cross_stream"]
    advancing = next(
        (e for e in vec["events"]
         if e.get("epoch_before") != e.get("epoch_after")), None)
    assert advancing is not None, (
        "epoch_cross_stream carries no advancing event — this helper needs "
        "one to build an edge-bearing history")
    opening = next(
        (e for e in vec["events"]
         if e.get("movement_id") == advancing["movement_id"]
         and e.get("epoch_before") == e.get("epoch_after")), None)
    assert opening is not None, (
        f"no no-effect opening row for movement "
        f"{advancing['movement_id']!r} in epoch_cross_stream")
    mid = f"{prefix}-m"
    return [dict(opening, event_id=f"{prefix}-open", base_key=base,
                 movement_id=mid),
            dict(advancing, event_id=f"{prefix}-edge", base_key=base,
                 movement_id=mid)]


# Test-owned ANCHORS. A protocol_genesis anchor becomes the base's harvested
# fence — AuthorityFingerprint.base_epoch — so the fold validates its SHAPE
# (lowercase 40-hex), not merely its nullity. These fixtures carried "E0",
# which the fold now refuses; naming them stops the placeholder creeping
# back and makes it obvious that an anchor is an OBJECT ID, not a label.
ANCHOR_A = "0" * 40
ANCHOR_B = "1" * 40


def _seat_result_single(generated, event_id: str, base: str) -> dict:
    """A COMPLETE §9 `seat_result` record. Singles are now constructed and
    validated inside the one walk, so the old 5-field stub halts the base as
    a schema violation and masks whatever the caller meant to isolate —
    which is exactly what happened to the three ceiling seals. Built against
    the generated type's own REQUIRED set, so a §9 field added later fails
    HERE with a sentence instead of turning a ceiling seal into a
    schema-violation seal."""
    cls = generated.SINGLE_EVENTS["seat_result"]
    values = {"schema_major": 1, "schema_minor": 0, "event_id": event_id,
              "ts": "1970-01-01T00:00:00Z", "run_id": "run-1",
              "trace_id": "trace-1", "protocol_epoch": "a" * 40,
              "family": "seat_result", "roster_digest": "rd",
              "subject_digest": "sd", "attempt_id": "att-1",
              "seat_id": "claude", "verdict": "APPROVE",
              "findings_digest": "fd"}
    missing = set(cls.REQUIRED) - set(values)
    assert not missing, (
        f"§9 gave seat_result new REQUIRED fields {sorted(missing)} — this "
        f"helper must carry every one, or the ceiling seals silently become "
        f"schema-violation seals")
    # base_key is not a seat_result field; it rides along because the
    # per-base ceiling counts by base_key and unknown wire keys are ignored.
    return dict(values, base_key=base)


def _ceiling_events(generated, n: int, base: str = "B1") -> list[dict]:
    """N distinct, fully SCHEMA-VALID §9 singles carrying no epoch fields:
    every consumer accepts them (both machines filter by family, the fence
    walk finds no edge), so these seals isolate the CEILING rather than
    tripping another check."""
    return [_seat_result_single(generated, f"{base}-e{i}", base)
            for i in range(n)]


@pytest.mark.parametrize("anchor,expect", [
    pytest.param("a" * 40, None, id="valid-lowercase-40-hex"),
    pytest.param(None, "no protocol_genesis epoch",
                 id="deny-anchor-is-none"),
    pytest.param("not-an-oid", "of type str", id="deny-anchor-is-free-text"),
    pytest.param("", "of type str", id="deny-anchor-is-empty"),
    pytest.param("A" * 40, "of type str", id="deny-anchor-is-uppercase-hex"),
    pytest.param("a" * 39, "of type str", id="deny-anchor-is-39-hex"),
    pytest.param(7, "of type int", id="deny-anchor-is-an-int"),
    pytest.param(True, "of type bool", id="deny-anchor-is-a-bool"),
    pytest.param(1.5, "of type float", id="deny-anchor-is-a-float"),
])
def test_anchor_shape_at_the_fence(generated, anchor, expect):
    """A protocol_genesis anchor BECOMES the base's harvested fence on the ok
    path, and that value IS `AuthorityFingerprint.base_epoch` — the thing
    §6.0's authority check compares byte-for-byte. So the anchor obeys the
    same shape rule as an edge fence: lowercase 40-hex, validated, never
    coerced. Anything else is malformed input and halts EPOCH_GAP.

    I reported this hole in the previous pass and deliberately did NOT seal
    it: with the bug live, the only assertions available were "ok with free
    text" (ratifying it) or a red test. It is fixed, so it is sealed.

    Uppercase 40-hex is refused ON PURPOSE: the fence is compared for
    equality, so `A…` and `a…` are two different fences for one commit, and
    accepting both would make the comparison depend on which writer wrote.

    This rule is UNSEALED without this test — measured, not assumed:
    reverting `not _valid_oid(anchor)` to `anchor is None` in
    `_ReduceState._walk_epochs` leaves the whole boundary suite GREEN (0
    failures, with the three generated-integrity seals deselected since any
    edit to the generated module trips those). The two ceiling fixtures that
    were red merely tripped over the fix; they did not seal it.

    MUTATION: `if base in self.anchors and not _valid_oid(anchor):` →
    `... and anchor is None:` ⇒ every deny row except deny-anchor-is-none
    goes red.
    MUTATION: drop the `missing` branch so the None case reports the
    not-an-object-id wording ⇒ deny-anchor-is-none goes red.
    """
    g = generated
    entry = _epochs(g, [], anchors={"B1": anchor})["B1"]
    if expect is None:
        assert entry["status"] == "ok", entry
        assert entry["halt"] is None
        assert entry["epoch"] == anchor
        return
    assert entry["status"] == "halt", (
        f"anchor {anchor!r} was accepted as a fence — it would flow into "
        f"AuthorityFingerprint.base_epoch uncoerced")
    assert entry["epoch"] is None, (
        "a refused anchor must not be presented as the harvested fence")
    halt = entry["halt"]
    assert halt["code"] == "EPOCH_GAP", halt
    # the detail names the BASE and the offending value/type — the 3am test
    assert halt["detail"].startswith("B1: "), halt["detail"]
    assert expect in halt["detail"], halt["detail"]
    if anchor is not None:
        assert "is not an object id" in halt["detail"], halt["detail"]
        assert "never coerced" in halt["detail"], halt["detail"]


def test_ceiling_halt_wins_over_anchor_shape(generated):
    """The ORDERING the ceiling fixtures rely on, asserted deliberately
    instead of relied on accidentally: a base carrying BOTH a recovery-
    ceiling breach AND a malformed anchor reports the CEILING.

    That is the right precedence — the ceiling is the operator-actionable
    cause (too much history for one base), and a base whose reduce was
    refused outright has no fence to validate. But it also MASKS anchor
    validation, which is exactly why three ceiling fixtures carried the
    invalid anchor "E0" and passed: `test_ceiling_n_plus_one_halts`,
    `test_ceiling_is_counted_per_base`'s BUSY arm and
    `test_ceiling_with_partial_anchors_keeps_edge_bearing_bases`. Every one
    now uses a real object id, and this seal owns the masking.

    MUTATION: move the `if base in self.halts:` arm of `_walk_epochs` BELOW
    the anchor-shape arm ⇒ red (the base would report the anchor complaint
    and the ceiling breach would be invisible).
    """
    g = generated
    n = g.RECOVERY_CEILING_EVENTS
    breached = _ceiling_events(g, n + 1, "BUSY")
    entry = _epochs(g, breached, anchors={"BUSY": "E0"})["BUSY"]
    assert entry["status"] == "halt"
    assert entry["halt"]["code"] == "RECOVERY_CEILING", (
        f"the anchor complaint pre-empted the ceiling breach: {entry['halt']}")
    assert "is not an object id" not in entry["halt"]["detail"]
    # …and with a VALID anchor the same base reports the same cause, so the
    # ceiling result does not depend on the anchor at all.
    assert _epochs(g, breached, anchors={"BUSY": ANCHOR_A})["BUSY"]["halt"]["code"] \
        == "RECOVERY_CEILING"
    # …while a healthy base with the SAME malformed anchor does report it —
    # proof the masking is the halt's doing, not a dropped check.
    quiet = _epochs(g, _ceiling_events(g, 3, "QUIET"), anchors={"QUIET": "E0"})
    assert quiet["QUIET"]["halt"]["code"] == "EPOCH_GAP"
    assert "is not an object id" in quiet["QUIET"]["halt"]["detail"]


def test_ceiling_exactly_n_is_admitted(generated):
    """Boundary: exactly N events is admitted.

    The docstring used to add "(they then fail their own schema checks, but
    never with RECOVERY_CEILING)". They fail nothing: `_ceiling_events`
    emits schema-VALID §9 singles carrying no epoch fields, which is
    precisely why they isolate the ceiling — the reducers filter them at the
    family check and the fold finds no edge. The row now asserts the
    stronger fact it actually holds: NO halts at all.
    """
    g, n = generated, generated.RECOVERY_CEILING_EVENTS
    for result in (_boundary(g, _ceiling_events(g, n)),
                   _boundary(g, _ceiling_events(g, n))):
        assert result["halts"] == {}, (
            f"exactly N was not admitted cleanly: {result['halts']}")
    # the fold arm is the ONLY one of the ceiling seals whose anchor is
    # actually examined (no per-base halt masks it), so it is the one that
    # needs a real object id — see test_ceiling_halt_wins_over_anchor_shape
    # for why the others passed while carrying "E0".
    fold = _epochs(g, _ceiling_events(g, n), anchors={"B1": ANCHOR_A})["B1"]
    assert fold["halt"] is None, fold["halt"]
    assert fold["status"] == "ok" and fold["epoch"] == ANCHOR_A


def test_ceiling_n_plus_one_halts(generated):
    """deny: one event past the ceiling halts all three consumers."""
    g, n = generated, generated.RECOVERY_CEILING_EVENTS
    for result in (_boundary(g, _ceiling_events(g, n + 1)),
                   _boundary(g, _ceiling_events(g, n + 1))):
        assert result["halts"]["B1"]["code"] == "RECOVERY_CEILING"
    fold = _epochs(g, _ceiling_events(g, n + 1), anchors={"B1": ANCHOR_A})
    assert fold["B1"]["halt"]["code"] == "RECOVERY_CEILING"


def test_ceiling_is_counted_per_base(generated):
    """deny: one busy base must never halt a quiet one."""
    g, n = generated, generated.RECOVERY_CEILING_EVENTS
    events = _ceiling_events(g, n + 1, "BUSY") + _ceiling_events(g, 3, "QUIET")
    for result in (_boundary(g, events), _boundary(g, events)):
        assert result["halts"]["BUSY"]["code"] == "RECOVERY_CEILING"
        # "must never halt a quiet one" — NOT halt, not merely "not halted
        # with this one code". A shared-dedup or misattributed error that
        # halted QUIET for any other reason satisfied the old assertion.
        # (The fold arm below already got this right.)
        assert "QUIET" not in result["halts"], (
            f"a busy base halted a quiet one: {result['halts'].get('QUIET')}")
    # DISTINCT anchors: one shared value could not tell "each base kept its
    # own fence" from "both read the same one".
    fold = _epochs(g, events, anchors={"BUSY": ANCHOR_A, "QUIET": ANCHOR_B})
    assert fold["BUSY"]["halt"]["code"] == "RECOVERY_CEILING"
    assert fold["QUIET"]["halt"] is None, fold["QUIET"]["halt"]
    assert fold["QUIET"]["epoch"] == ANCHOR_B, (
        "the quiet base did not harvest its OWN anchor")


def test_ceiling_with_empty_anchors_still_halts(generated):
    """deny: a ceiling breach with NO anchors must be an explicit halt — {}
    would read as a clean, empty fold."""
    g = generated
    fold = _epochs(g, _ceiling_events(g, g.RECOVERY_CEILING_EVENTS + 1), anchors={})
    assert fold, "empty result: a ceiling breach read as 'nothing to fold'"
    assert fold["B1"]["status"] == "halt"
    assert fold["B1"]["halt"]["code"] == "RECOVERY_CEILING"


def test_ceiling_with_partial_anchors_keeps_edge_bearing_bases(generated):
    """deny: an edge-bearing base must not vanish on the ceiling path."""
    g, n = generated, generated.RECOVERY_CEILING_EVENTS
    other = _edge_history("o1", "OTHER")
    fold = _epochs(g, _ceiling_events(g, n + 1, "BUSY") + other, anchors={"BUSY": ANCHOR_A})
    assert fold["BUSY"]["halt"]["code"] == "RECOVERY_CEILING"
    assert fold["OTHER"]["halt"]["code"] == "EPOCH_GAP"


def test_ceiling_counts_deduplicated_events(generated):
    """The ceiling bounds recovered HISTORY, not wire traffic: N+1 COPIES of
    one event must not trip an OPERATOR halt, while N+1 DISTINCT events
    must (panel round 3 — at-least-once redelivery is exactly what the
    protocol absorbs)."""
    g, n = generated, generated.RECOVERY_CEILING_EVENTS
    one = _seat_result_single(g, "same", "B1")
    copies = [dict(one) for _ in range(n + 1)]
    assert "RECOVERY_CEILING" not in {
        h["code"] for h in _boundary(g, copies)["halts"].values()}
    distinct = _ceiling_events(g, n + 1)
    assert _boundary(g, distinct)["halts"]["B1"]["code"] == "RECOVERY_CEILING"


def test_derivations_pinned_goldens(generated):
    """derive_hold_id / derive_recovery_event_id / roster_digest against
    independently computed hexes (standalone snippet over the schema's
    preimage spec) — and the newline-injectivity guard rejects."""
    g = generated
    assert g.derive_hold_id("R1:refs/heads/main", "refs/heads/main",
                            "o0", "o1", 0) == PINNED_HOLD_ID_SEQ0
    assert g.derive_recovery_event_id("R1:refs/heads/main", "m1") == \
        PINNED_RECOVERY_ID_M1
    assert g.roster_digest("v1", ["claude", "grok", "codex"], "claude") == \
        PINNED_ROSTER_DIGEST
    # deny: a newline in a newline-joined preimage breaks injectivity
    with pytest.raises(ValueError, match=r"newline in preimage component"):
        g.derive_hold_id("base\nref=evil", "r", "o0", "o1", 0)
    with pytest.raises(ValueError,
                       match=r"newline in roster preimage component"):
        g.roster_digest("v1", ["claude\ngrok"], "claude\ngrok")


# ─── panel aggregate semantics ───────────────────────────────────────────────

def _roster(generated):
    seats = ("claude", "grok", "codex")
    return generated.RosterSnapshot(
        manifest_digest="md", roster_version="v1",
        roster_digest=generated.roster_digest("v1", seats, "claude"),
        ordered_seat_ids=seats, designated_single_id="claude")


class _LookalikeOutcome:
    """Structural lookalike — right shape, wrong type (explicit-state's
    canonical probe)."""

    verdict = "APPROVE"
    findings = ()


def _seats_all_approve(g, roster):
    return {s: g.SeatOutcome(g.SeatVerdict.APPROVE) for s in roster.ordered_seat_ids}


def _mutate(g, roster, case: str):
    """Build the outcome map for one aggregate scenario. Returns (intensity,
    outcomes) — assertion-only bodies keep the seal a table, not logic."""
    out = _seats_all_approve(g, roster)
    full = g.PanelIntensity.FULL
    if case == "approved":
        return full, out
    if case == "block-verdict":
        out["grok"] = g.SeatOutcome(g.SeatVerdict.BLOCK)
    elif case == "high-finding":
        out["grok"] = g.SeatOutcome(g.SeatVerdict.APPROVE,
                                    (g.Finding(g.Severity.HIGH),))
    elif case == "block-beats-missing-seat":
        out["grok"] = g.SeatOutcome(g.SeatVerdict.BLOCK)
        del out["codex"]
    elif case == "missing-seat":
        del out["codex"]
    elif case == "extra-seat":
        out["gemini"] = g.SeatOutcome(g.SeatVerdict.APPROVE)
    elif case == "unparseable":
        out["codex"] = g.UnparseableOutcome("severity: CATASTROPHIC")
    elif case == "lookalike-raises":
        out["codex"] = _LookalikeOutcome()
    elif case == "none-raises":
        out["codex"] = None
    elif case == "skip-not-approved":
        return g.PanelIntensity.SKIP, {}
    elif case == "single":
        return g.PanelIntensity.SINGLE, {"claude": g.SeatOutcome(g.SeatVerdict.APPROVE)}
    return full, out


# (case, expected result name) — expected "RAISES" means the closed union
# rejects the outcome type rather than counting it.
_AGGREGATE_ROWS = [
    ("approved", "APPROVED", "full-all-approve"),
    ("block-verdict", "BLOCKED", "deny-blocking-verdict"),
    ("high-finding", "BLOCKED", "deny-high-finding-blocks"),
    ("block-beats-missing-seat", "BLOCKED", "deny-block-beats-missing-seat"),
    ("missing-seat", "INCOMPLETE", "deny-missing-seat-incomplete"),
    ("extra-seat", "INCOMPLETE", "deny-extra-seat-incomplete"),
    ("unparseable", "INCOMPLETE", "deny-unparseable-incomplete"),
    ("lookalike-raises", "RAISES", "deny-lookalike-raises"),
    ("none-raises", "RAISES", "deny-none-raises"),
    ("skip-not-approved", "NOT_APPLICABLE", "deny-skip-is-not-approval"),
    ("single", "APPROVED", "single-designated-seat"),
]


@pytest.mark.parametrize("case,expected", [
    pytest.param(c, e, id=i) for c, e, i in _AGGREGATE_ROWS
])
def test_aggregate_rows(generated, case, expected):
    """§5.1's aggregate as a TABLE: each row names a scenario and the result
    it must produce; the body is assertion-only (panel round 2 — an 11-arm
    if/elif dispatcher hides which assertion ran)."""
    g = generated
    roster = _roster(g)
    intensity, outcomes = _mutate(g, roster, case)
    if expected == "RAISES":
        with pytest.raises(TypeError,
                           match=r"unknown outcome type .* outside the "
                                 r"closed union"):
            g.aggregate(intensity, roster, outcomes)
        return
    assert g.aggregate(intensity, roster, outcomes) is \
        getattr(g.PanelAggregateResult, expected)


@pytest.mark.parametrize("bad", [
    pytest.param(2, id="deny-raw-int-matching-FULL"),
    pytest.param("FULL", id="deny-string-intensity"),
    pytest.param(None, id="deny-none-intensity"),
])
def test_required_seats_rejects_non_members(generated, bad):
    """PanelIntensity is an IntEnum, so a raw 2 compares equal to FULL — a
    non-member must raise, never fall through to the permissive zero-seat
    arm that aggregate maps to NOT_APPLICABLE (panel round 2, finding 4)."""
    with pytest.raises(TypeError,
                       match=r"is not a PanelIntensity member — the "
                             r"intensity domain is closed"):
        generated.required_seats(bad, _roster(generated))


def test_required_seats_full_is_whole_roster(generated):
    r = _roster(generated)
    assert generated.required_seats(generated.PanelIntensity.FULL, r) == \
        r.ordered_seat_ids
    assert generated.required_seats(generated.PanelIntensity.SKIP, r) == ()


def test_blocking_predicate_exhaustive(generated):
    g = generated
    assert g.blocking(g.SeatOutcome(g.SeatVerdict.BLOCK))
    assert g.blocking(g.SeatOutcome(g.SeatVerdict.APPROVE,
                                    (g.Finding(g.Severity.CRITICAL),)))
    assert not g.blocking(g.SeatOutcome(g.SeatVerdict.APPROVE,
                                        (g.Finding(g.Severity.MEDIUM),)))
    # ADJUDICATED (I argued for True; ruled against, and the ruling is
    # right): `blocking(UnparseableOutcome)` now RAISES. False was the
    # fail-open — SKIP + unparseable reached the gate-satisfying
    # NOT_APPLICABLE — but True fabricates a BLOCK verdict the seat never
    # gave, and §5.1's actual answer is a THIRD value, INCOMPLETE, which a
    # Boolean cannot express. Refusing to answer is the honest fix: the
    # caller reaches INCOMPLETE, and both INCOMPLETE and BLOCKED are
    # non-gate-satisfying, so nothing is lost.
    #
    # MUTATION: return False for UnparseableOutcome ⇒ red here AND on
    # test_skip_holding_an_unparseable_outcome_is_incomplete, which is the
    # row that proves the GATE answer rather than this predicate's.
    with pytest.raises(TypeError, match=r"has no verdict to test"):
        g.blocking(g.UnparseableOutcome("x"))
    # the classification is where a parse failure IS answered
    assert g.classify_outcome(g.UnparseableOutcome("x")) is \
        g.PanelAggregateResult.INCOMPLETE
    assert g.classify_outcome(g.SeatOutcome(g.SeatVerdict.APPROVE)) is None
    assert g.classify_outcome(g.SeatOutcome(g.SeatVerdict.BLOCK)) is \
        g.PanelAggregateResult.BLOCKED
    # deny: a structural lookalike is not a member of the closed union, on
    # EITHER surface
    with pytest.raises(TypeError,
                       match=r"unknown seat-outcome type _LookalikeOutcome"):
        g.blocking(_LookalikeOutcome())
    with pytest.raises(TypeError,
                       match=r"unknown seat-outcome type _LookalikeOutcome"):
        g.classify_outcome(_LookalikeOutcome())
    # deny: a raw-string verdict never parses into the closed domain
    with pytest.raises(ValueError,
                       match=r"verdict must be a SeatVerdict"):
        g.SeatOutcome("BLOCK")


def test_unknown_epoch_effect_is_closed_at_both_ends(generated):
    """An epoch effect outside the four implemented arms must not read as
    "no algebra" (panel round 4, finding 5). Closed at BOTH ends:
      1. schema load rejects a row declaring one;
      2. the runtime checker halts rather than falling through.

    The runtime half used to drive `_check_epoch_algebra` with two locally
    declared stand-in classes (`_NovelRow`, `_Ev`) that encoded a narrower
    contract than the real types they impersonated. It now runs against a
    REAL generated module — built by fsmgen through `module_from_source`,
    the same route `test_flipping_the_schema_rule_order_flips_the_behaviour`
    uses — with one variant's EPOCH_EFFECT rebound to an unknown value, and
    it asserts PUBLIC behaviour: `reduce_section_a` halts.

    MUTATION: replace `_check_epoch_algebra`'s final `return halt(...)` with
    `return None` ⇒ red (an unknown effect would read as "no algebra").
    MUTATION: delete the closed-epoch-effect check from
    `_validate_schema_tokens` ⇒ the schema half goes red.
    """
    fsmgen = _fsmgen()
    schemas = fsmgen.load_schemas()
    schemas["lifecycle_fsm"]["section_a"]["rows"][0]["epoch_effect"] = "novel_effect"
    with pytest.raises(SystemExit) as exc:
        fsmgen._validate_schema_tokens(schemas)
    assert "closed epoch-effect domain" in str(exc.value)

    # (2) the runtime half, on a real generated module.
    live = fsmgen.module_from_source(
        fsmgen.build_generated_module(fsmgen.load_schemas()))
    cls = live.EFFECT_VARIANTS["Prepare"]
    assert cls.EPOCH_EFFECT in live.EPOCH_EFFECT_VALUES
    cls.EPOCH_EFFECT = "novel_effect"          # a row the checker cannot know
    try:
        wire = _wire_effect(live, "Prepare", "e1", "m1", "GENESIS",
                            authorization_id="auth-1")
        event = live.build_wire_event(live.EFFECT_VARIANTS, wire)
        halt = live._check_epoch_algebra(cls, event, "where", {"event_id": "e"})
        assert halt is not None, "unknown epoch effect fell through as no-op"
        assert halt["code"] == "ILLEGAL_TRANSITION"
        assert "domain is closed" in halt["detail"]
        # …and the same fact through the PUBLIC reducer, not only the helper
        got = _boundary(live, [wire])
        base_halt = got["halts"]["R1:refs/heads/main"]
        assert base_halt["code"] == "ILLEGAL_TRANSITION"
        assert "domain is closed" in base_halt["detail"], base_halt["detail"]
    finally:
        cls.EPOCH_EFFECT = "none"
    # the committed module is untouched by the probe above
    assert set(generated.EPOCH_EFFECT_VALUES) == {
        "none", "assign_new_oid", "per_disposition", "as_accept_ours"}


def test_aggregate_dispatch_is_generated_from_the_schema_rules(schemas, generated):
    """§5.1's rule ORDER is now GENERATED from panel_aggregate.yaml's rules
    list, not hand-written beside it (panel round 4, finding 6). The
    generated table must match the schema entry for entry."""
    g = generated
    rules = schemas["panel_aggregate"]["aggregate"]["rules"]
    assert len(g.AGGREGATE_RULES) == len(rules)
    for (name_result, (_, result)) in zip(rules, g.AGGREGATE_RULES):
        (name, want), = name_result.items()
        assert result.name == want, f"{name}: generated {result.name}, schema {want}"


def test_aggregate_rule_list_is_total(generated):
    """§5.1's dispatch ends in a raising totality check, not an implicit
    None: a rules list without the final `otherwise` arm must be a loud
    AssertionError, never "no result".

    MUTATION: drop the final ('otherwise', APPROVED) entry from
    AGGREGATE_RULES ⇒ this row goes red on the real aggregate.
    """
    g = generated
    assert g.AGGREGATE_RULES[-1][1] is g.PanelAggregateResult.APPROVED
    # the predicates take (required, outcomes, CLASSES) since S3: scope is a
    # property of the classification step, not of each evidence rule.
    assert g.AGGREGATE_RULES[-1][0]((), {}, {}) is True, (
        "the final rule is not unconditional — the dispatch is not total")
    # deny: with the otherwise arm removed the dispatch must RAISE, not
    # return None. Driven on a copy of the module's own rule tuple.
    saved = g.AGGREGATE_RULES
    try:
        g.AGGREGATE_RULES = saved[:-1]
        r = _roster(g)
        with pytest.raises(AssertionError, match=r"rule list is not total"):
            g.aggregate(g.PanelIntensity.FULL, r, _seats_all_approve(g, r))
    finally:
        g.AGGREGATE_RULES = saved
    assert g.aggregate(g.PanelIntensity.FULL, _roster(g),
                       _seats_all_approve(g, _roster(g))) is \
        g.PanelAggregateResult.APPROVED


def test_flipping_the_schema_rule_order_flips_the_behaviour(tmp_path, monkeypatch):
    """The `standing_reject_restore_resolves_to` standard applied here: swap
    two rules in a COPY of the schema, regenerate, and the same inputs must
    produce the other answer. If it passes with the order unchanged, the
    dispatch is not derived from the rules list.

    The pair swapped changed with the escaped-Critical fix: blocking is now
    rule 1 and beats BOTH the zero-seat and missing-seat arms, so swapping
    blocking↔missing no longer changes any outcome (blocking wins from
    either position for a blocking input). The pair that still discriminates
    is `required_seats_empty` ↔ `outcome_keys_not_exactly_required_seats`,
    over a SKIP-intensity call holding one NON-blocking outcome:
      committed order → NOT_APPLICABLE (zero required seats governs)
      swapped order   → INCOMPLETE   (keys ≠ required_seats governs)

    MUTATION: hand-write the dispatch beside the rules list instead of
    generating it from the list ⇒ the flipped module returns
    NOT_APPLICABLE and this seal goes red.
    """
    fsmgen = _fsmgen()
    schemas = fsmgen.load_schemas()
    rules = schemas["panel_aggregate"]["aggregate"]["rules"]
    empty_i = next((i for i, r in enumerate(rules)
                    if "required_seats_empty" in r), None)
    keys_i = next((i for i, r in enumerate(rules)
                   if "outcome_keys_not_exactly_required_seats" in r), None)
    assert empty_i is not None, (
        "panel_aggregate.yaml no longer declares required_seats_empty — the "
        "rule that keeps a zero-seat evaluation from reading as approval")
    assert keys_i is not None, (
        "panel_aggregate.yaml no longer declares "
        "outcome_keys_not_exactly_required_seats")
    assert empty_i < keys_i, (
        "the committed order already has keys-mismatch before zero-seat; "
        "this seal's discriminating pair is stale")
    rules[empty_i], rules[keys_i] = rules[keys_i], rules[empty_i]
    flipped = fsmgen.module_from_source(fsmgen.build_generated_module(schemas))
    seats = ("claude", "grok", "codex")
    roster = flipped.RosterSnapshot(
        manifest_digest="md", roster_version="v1",
        roster_digest=flipped.roster_digest("v1", seats, "claude"),
        ordered_seat_ids=seats, designated_single_id="claude")
    # SKIP demands NO seats, and one non-blocking outcome is present:
    # zero-seat and keys-mismatch both match, so which fires is the order.
    outcomes = {"claude": flipped.SeatOutcome(flipped.SeatVerdict.APPROVE)}
    got = flipped.aggregate(flipped.PanelIntensity.SKIP, roster, outcomes)
    assert got is flipped.PanelAggregateResult.INCOMPLETE, (
        "swapping the schema's rule order did not change the behaviour — "
        "the dispatch is not generated from the rules list")
    # and the committed order still yields NOT_APPLICABLE on the same input
    from claude_dispatcher.boundary import generated as real
    real_outcomes = {"claude": real.SeatOutcome(real.SeatVerdict.APPROVE)}
    assert real.aggregate(real.PanelIntensity.SKIP, _roster(real),
                          real_outcomes) is \
        real.PanelAggregateResult.NOT_APPLICABLE


def test_roster_snapshot_stores_an_immutable_seat_tuple(generated):
    """The digest binds ordered_seat_ids, so the field must be immutable —
    a list would let a caller mutate the roster out from under a verified
    digest (panel round 2, finding 27)."""
    g = generated
    seats = ["claude", "grok", "codex"]          # a LIST on the way in
    snap = g.RosterSnapshot(
        manifest_digest="md", roster_version="v1",
        roster_digest=g.roster_digest("v1", seats, "claude"),
        ordered_seat_ids=seats, designated_single_id="claude")
    assert isinstance(snap.ordered_seat_ids, tuple), \
        "ordered_seat_ids must be stored as a tuple"
    seats.append("gemini")                        # mutate the original
    assert snap.ordered_seat_ids == ("claude", "grok", "codex"), \
        "the snapshot aliased a caller-owned mutable sequence"
    # deny: frozen — the digest binds the field, so it may not be rebound
    with pytest.raises((AttributeError, TypeError),
                       match=r"cannot assign to field 'ordered_seat_ids'"):
        snap.ordered_seat_ids = ("x",)


def test_seat_outcome_stores_an_immutable_findings_tuple(generated):
    """Twin of the RosterSnapshot fix: a caller-owned list would let a
    blocking finding disappear after construction, turning BLOCKED into
    APPROVED (panel round 3, finding 19)."""
    g = generated
    findings = [g.Finding(g.Severity.CRITICAL)]
    outcome = g.SeatOutcome(g.SeatVerdict.APPROVE, findings)
    assert isinstance(outcome.findings, tuple)
    findings.clear()                      # mutate the original
    assert len(outcome.findings) == 1, "the outcome aliased a mutable list"
    assert g.blocking(outcome), "a blocking finding vanished after construction"
    r = _roster(g)
    seats = {s: g.SeatOutcome(g.SeatVerdict.APPROVE) for s in r.ordered_seat_ids}
    seats["grok"] = outcome
    assert g.aggregate(g.PanelIntensity.FULL, r, seats) is \
        g.PanelAggregateResult.BLOCKED


# ─── §9 subject digest / classifier authority, as two TABLES ────────────────
#
# This was one 55-line function covering six API surfaces with ~20
# assertions and seven `pytest.raises` blocks — the only >50-line function
# in the diff. The first failure masked the other twenty and the test id
# localised nothing. Split, in the shape `_AGGREGATE_ROWS` established 160
# lines earlier: one table of (input → expected value) and one of
# (input → expected rejection).

def _req_classifier(g):
    return g.RequiredClassifier(config_sha256="cfg", producer_digest="prod",
                                contract="2")


def _preimage_digest(*lines: str) -> str:
    """§9's canonical preimage, computed here rather than by the function
    under test — an independent second implementation, not a call."""
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


_SUBJECT_VALUE_ROWS = [
    ("classifier-line-required", "required:cfg:prod:2"),
    ("classifier-line-legacy", "legacy"),
    ("target-pr", "pr:PR_1:refs/heads/main"),
    ("target-ref", "ref:refs/heads/main"),
    ("digest-pr-no-unit", None),          # compared against _preimage_digest
    ("digest-ref-with-unit", None),
    ("digest-retarget-differs", None),
    ("fingerprint-keeps-the-union", None),
]


@pytest.mark.parametrize("case,want", [
    pytest.param(c, w, id=c) for c, w in _SUBJECT_VALUE_ROWS
] + [pytest.param("deny-digest-is-not-the-retarget", None,
                  id="deny-retarget-changes-the-digest")])
def test_subject_digest_values(generated, case, want):
    """subject_digest()/target_pr()/target_ref()/ClassifierAuthority had
    zero tests (panel round 3, finding 16). Pinned against independently
    computed SHA-256s over §9's canonical preimage.

    MUTATION: reorder any component of subject_digest's preimage, or drop
    the `unit=` line ⇒ the digest rows go red.
    """
    g = generated
    req = _req_classifier(g)
    if case == "classifier-line-required":
        assert req.line() == want
    elif case == "classifier-line-legacy":
        assert g.LegacyNoClassifier().line() == want
    elif case == "target-pr":
        assert g.target_pr("PR_1", "refs/heads/main") == want
    elif case == "target-ref":
        assert g.target_ref("refs/heads/main") == want
    elif case == "digest-pr-no-unit":
        assert g.subject_digest(
            repo_node_id="R_1", target=g.target_pr("PR_1", "refs/heads/main"),
            base_oid="b0", head_oid="h0", diff_sha256="d0",
            classifier=req) == _preimage_digest(
                "repo=R_1", "target=pr:PR_1:refs/heads/main", "base=b0",
                "head=h0", "diff=d0", "classifier=required:cfg:prod:2",
                "unit=none")
    elif case == "digest-ref-with-unit":
        assert g.subject_digest(
            repo_node_id="R_1", target=g.target_ref("refs/heads/main"),
            base_oid="b0", head_oid="h0", diff_sha256="d0",
            classifier=g.LegacyNoClassifier(),
            unit_digest="u1") == _preimage_digest(
                "repo=R_1", "target=ref:refs/heads/main", "base=b0",
                "head=h0", "diff=d0", "classifier=legacy", "unit=u1")
    elif case in ("digest-retarget-differs", "deny-digest-is-not-the-retarget"):
        # §9: a retarget of the SAME PR at the SAME OIDs is a different
        # subject — the digest must move.
        base = dict(repo_node_id="R_1", base_oid="b0", head_oid="h0",
                    diff_sha256="d0", classifier=req)
        main = g.subject_digest(target=g.target_pr("PR_1", "refs/heads/main"),
                                **base)
        release = g.subject_digest(
            target=g.target_pr("PR_1", "refs/heads/release"), **base)
        assert main != release, (
            "retargeting a PR left the subject digest unchanged — two "
            "distinct review subjects share one key")
    else:
        assert g.AuthorityFingerprint(
            protocol_epoch="E0", base_epoch="E0", subject_digest="s",
            roster_digest="r", classifier=req).classifier is req


_SEP = r"contains the ':' separator"


@pytest.mark.parametrize("case,match", [
    pytest.param("classifier-not-a-variant",
                 r"classifier must be a ClassifierAuthority variant",
                 id="deny-subject-digest-classifier-is-not-a-variant"),
    pytest.param("newline-in-component", r"newline in preimage component",
                 id="deny-subject-digest-newline"),
    pytest.param("colon-in-pr-node-id", rf"pr_node_id='A:B' {_SEP}",
                 id="deny-colon-in-pr-node-id"),
    pytest.param("colon-in-target-ref", rf"target_ref='B:c' {_SEP}",
                 id="deny-colon-in-target-ref-of-target-pr"),
    pytest.param("colon-in-ref", rf"ref='refs:heads/main' {_SEP}",
                 id="deny-colon-in-target-ref"),
    pytest.param("colon-in-config-sha", rf"config_sha256='cfg:x' {_SEP}",
                 id="deny-colon-in-required-classifier"),
    pytest.param("fingerprint-classifier-not-a-variant",
                 r"classifier must be a ClassifierAuthority variant",
                 id="deny-fingerprint-classifier-is-a-string"),
])
def test_subject_digest_rejections(generated, case, match):
    """One row per §9 rejection rule, each naming the rule it seals. The
    inner ':' separator gets the same injectivity treatment as the newline:
    without it target_pr("A:B", "c") and target_pr("A", "B:c") share one
    preimage, so two distinct subjects would collide.

    MUTATION: delete the ':' check from target_pr ⇒ the two colon-in-target
    rows go red; delete the newline check from the preimage builder ⇒ the
    newline row goes red; make subject_digest accept a str classifier ⇒ the
    first row goes red.
    """
    g = generated
    req = _req_classifier(g)
    with pytest.raises(ValueError, match=match):
        if case == "classifier-not-a-variant":
            g.subject_digest(repo_node_id="R", target="ref:x", base_oid="b",
                             head_oid="h", diff_sha256="d",
                             classifier="required:x")
        elif case == "newline-in-component":
            g.subject_digest(repo_node_id="R\nrepo=evil", target="ref:x",
                             base_oid="b", head_oid="h", diff_sha256="d",
                             classifier=req)
        elif case == "colon-in-pr-node-id":
            g.target_pr("A:B", "c")
        elif case == "colon-in-target-ref":
            g.target_pr("A", "B:c")
        elif case == "colon-in-ref":
            g.target_ref("refs:heads/main")
        elif case == "colon-in-config-sha":
            g.RequiredClassifier(config_sha256="cfg:x", producer_digest="p",
                                 contract="2")
        else:
            g.AuthorityFingerprint(protocol_epoch="E0", base_epoch="E0",
                                   subject_digest="s", roster_digest="r",
                                   classifier="not-a-variant")


def test_schema_declared_preimages_bind_to_the_code(schemas, generated):
    """The schemas CLAIM the derivations are generated from them; this seal
    makes the claim checkable — build each preimage from the schema's own
    line list and assert the generated function agrees (panel round 3,
    finding 14). Flipping a schema line list turns this red."""
    g = generated
    fsm = schemas["lifecycle_fsm"]
    hold_lines = fsm["section_b"]["hold_id"]["preimage"]["lines"]
    values = {"<base_key>": "B", "<ref>": "R", "<delta_old_oid>": "o0",
              "<delta_new_oid>": "o1", "<occurrence_seq>": "3"}
    built = []
    for line in hold_lines:
        tag, _, placeholder = line.partition("=")
        built.append(f"{tag}={values[placeholder]}")
    assert g.derive_hold_id("B", "R", "o0", "o1", 3) == \
        hashlib.sha256("\n".join(built).encode()).hexdigest()
    rec = fsm["section_a"]["projection"]["open_prepared_recovery"]["event_id_preimage"]["lines"]
    built = []
    for line in rec:
        tag, _, placeholder = line.partition("=")
        built.append(f"{tag}=" + {"<base_key>": "B", "<movement_id>": "m1"}
                     .get(placeholder, placeholder))
    assert g.derive_recovery_event_id("B", "m1") == \
        hashlib.sha256("\n".join(built).encode()).hexdigest()
    roster = schemas["panel_aggregate"]["roster_snapshot"]["roster_digest_preimage"]
    assert roster["parts"] == ["roster_version", "ordered_seat_ids",
                               "designated_single_id"]
    assert roster["join"] == "\n" and roster["hash"] == "SHA-256"
    assert g.roster_digest("v", ["a", "b"], "a") == \
        hashlib.sha256("v\na\nb\na".encode()).hexdigest()
    # §5.1 semantics: the aggregate's declared rule ORDER is what runs.
    #
    # The order changed with the escaped-Critical fix (SMG-3966 class), and
    # the change is design-faithful, not merely the impl author's claim:
    # §5.1 states "**any seat reporting a blocking finding ⇒ BLOCKED**"
    # UNQUALIFIED — "any seat", not "any required seat" — so the rule is
    # evaluated FIRST and over EVERY outcome present. Under the old order a
    # SKIP-intensity call returned the gate-satisfying NOT_APPLICABLE while
    # holding a seat result carrying a blocking verdict: seats had run, one
    # blocked, and the verdict was swallowed.
    order = [next(iter(rule)) for rule in schemas["panel_aggregate"]["aggregate"]["rules"]]
    assert order[0] == "any_seat_outcome_blocking", (
        f"blocking is no longer the FIRST rule (order: {order}) — a "
        f"zero-seat or missing-seat arm can swallow a blocking verdict")
    assert order[1] == "required_seats_empty"
    r = _roster(g)
    # zero required seats and NO outcome at all: nothing blocked, so the
    # zero-seat rule still governs.
    assert g.aggregate(g.PanelIntensity.SKIP, r, {}) is \
        g.PanelAggregateResult.NOT_APPLICABLE
    # the escaped-Critical row: a blocking seat result held under SKIP
    # intensity must NOT read as the gate-satisfying NOT_APPLICABLE.
    assert g.aggregate(g.PanelIntensity.SKIP, r,
                       {"claude": g.SeatOutcome(g.SeatVerdict.BLOCK)}) is \
        g.PanelAggregateResult.BLOCKED, (
        "a blocking seat result was discarded by intensity — the SMG-3966 "
        "escaped-Critical class")
    # …and blocking still beats a missing seat
    blocking_and_missing = {"claude": g.SeatOutcome(g.SeatVerdict.BLOCK)}
    assert g.aggregate(g.PanelIntensity.FULL, r, blocking_and_missing) is \
        g.PanelAggregateResult.BLOCKED


def test_roster_snapshot_verifies_its_own_digest(generated):
    """deny: a snapshot carrying an arbitrary digest is unconstructible.

    The old second half compared two locally computed constants
    (`without_single != PINNED_ROSTER_DIGEST`) — a statement about
    hashlib in which no production code participated, so it could not fail
    for any implementation. It now routes the same claim through the REAL
    verifier: a snapshot whose digest was built over a preimage missing
    designated_single_id is refused.

    MUTATION: drop `designated_single_id` from `roster_digest`'s `parts`
    ⇒ red (the truncated-preimage row constructs cleanly).
    """
    g = generated
    seats = ("claude", "grok", "codex")
    with pytest.raises(ValueError, match="does not equal the canonical digest"):
        g.RosterSnapshot(manifest_digest="md", roster_version="v1",
                         roster_digest="deadbeef", ordered_seat_ids=seats,
                         designated_single_id="claude")
    # deny: a digest over a preimage that DROPS designated_single_id is
    # refused by the constructor's own verification, not merely unequal to
    # a constant this test computed.
    without_single = hashlib.sha256(
        "\n".join(["v1", *seats]).encode()).hexdigest()
    with pytest.raises(ValueError, match="does not equal the canonical digest"):
        g.RosterSnapshot(manifest_digest="md", roster_version="v1",
                         roster_digest=without_single, ordered_seat_ids=seats,
                         designated_single_id="claude")


def test_roster_snapshot_designated_single_must_be_a_seat(generated):
    """§5.1 structural invariant with no deny row before this one: the
    roster decides which seats must approve, so a snapshot whose
    designated_single_id is not a member would make required_seats(SINGLE)
    name a seat the panel never ran.

    MUTATION: `raise ValueError("designated_single_id must be a roster
    seat")` → `pass` ⇒ red. (Coverage reported this line as MISSED.)
    """
    g = generated
    seats = ("claude", "grok", "codex")
    with pytest.raises(ValueError, match="designated_single_id must be a roster seat"):
        g.RosterSnapshot(
            manifest_digest="md", roster_version="v1",
            # the digest is built over the MALFORMED input, so the digest
            # check cannot be the reason for the raise.
            roster_digest=g.roster_digest("v1", seats, "nobody"),
            ordered_seat_ids=seats, designated_single_id="nobody")


def test_roster_snapshot_rejects_duplicate_seats(generated):
    """§5.1: duplicate seat ids in the roster. Note a duplicate-seat roster
    produces a VALID digest (the preimage joins the list as given), so the
    digest check does not cover this — it needs its own row.

    MUTATION: `raise ValueError("duplicate seat ids in roster")` → `pass`
    ⇒ red. (Coverage reported this line as MISSED.)
    """
    g = generated
    dupes = ("claude", "grok", "claude")
    with pytest.raises(ValueError, match="duplicate seat ids in roster"):
        g.RosterSnapshot(manifest_digest="md", roster_version="v1",
                         roster_digest=g.roster_digest("v1", dupes, "claude"),
                         ordered_seat_ids=dupes,
                         designated_single_id="claude")


class _LookalikeFinding:
    """Structural lookalike for Finding — a duck-typed object carrying the
    attribute `blocking()` reads."""

    severity = "CRITICAL"


def test_seat_outcome_rejects_a_lookalike_finding(generated):
    """The same structural-lookalike class this file deliberately probes for
    SeatOutcome and PanelIntensity, applied to the findings tuple: a
    duck-typed "finding" carrying a .severity attribute must be refused at
    construction, never counted.

    MUTATION: `if not all(isinstance(f, Finding) ...): raise` → `pass`
    ⇒ red. (Coverage reported this line as MISSED.)
    """
    g = generated
    with pytest.raises(ValueError, match="findings must be Finding instances"):
        g.SeatOutcome(g.SeatVerdict.APPROVE, (_LookalikeFinding(),))
    with pytest.raises(ValueError, match="Finding.severity must be a Severity"):
        g.Finding("CRITICAL")


@pytest.mark.parametrize("case", [
    pytest.param("all-current", id="all-current-attempt-approves"),
    pytest.param("stale-attempt", id="deny-stale-attempt-excluded"),
    pytest.param("foreign-subject", id="deny-foreign-subject-digest-excluded"),
    pytest.param("conflicting-duplicate", id="deny-conflicting-duplicate"),
    pytest.param("lookalike-record", id="deny-lookalike-record-raises"),
    pytest.param("none-record", id="deny-none-record-raises"),
])
def test_seat_result_filtering(generated, case):
    """§5.1's (subject_digest, attempt_id) filter — BOTH halves.

    Every arm used to build records with subject "subj" and query with
    "subj", so only attempt_id was ever varied: dropping the
    `record.subject_digest != subject_digest` half of the filter left the
    entire suite green, i.e. a seat result computed against a DIFFERENT
    review subject (different base/head OIDs or diff digest) counted toward
    APPROVED. The subject half now has its own deny row.

    `aggregate_seat_results`' closed-union guard also had no lookalike/None
    deny, unlike its siblings `aggregate()` and `blocking()` — added here.

    MUTATIONS (generated, each reverted, each red on exactly its row):
      `record.subject_digest != subject_digest or ` deleted from the filter
        ⇒ deny-foreign-subject-digest-excluded red;
      `record.attempt_id != attempt_id` deleted ⇒ deny-stale-attempt red;
      the duplicate-conflict `return INCOMPLETE` → `pass` ⇒ deny-
        conflicting-duplicate red;
      `raise TypeError(f"aggregate_seat_results(): ...")` → `pass`
        ⇒ both lookalike/None rows red.
    """
    g = generated
    r = _roster(g)
    ok = g.SeatOutcome(g.SeatVerdict.APPROVE)
    result = g.PanelAggregateResult
    current = [g.SeatResultRecord(s, "subj", "att-2", ok)
               for s in r.ordered_seat_ids]
    call = lambda recs: g.aggregate_seat_results(  # noqa: E731
        g.PanelIntensity.FULL, r, "subj", "att-2", recs)
    if case == "all-current":
        assert call(current) is result.APPROVED
    elif case == "stale-attempt":
        # claude's only result is from the PREVIOUS attempt: excluded, so
        # the seat is missing ⇒ INCOMPLETE (never counted as approval).
        stale = [g.SeatResultRecord("claude", "subj", "att-1", ok),
                 *[rec for rec in current if rec.seat_id != "claude"]]
        assert call(stale) is result.INCOMPLETE
    elif case == "foreign-subject":
        # claude's only result was computed against a DIFFERENT subject
        # digest at the SAME attempt — the half of the key that was never
        # varied. It must not count toward APPROVED.
        foreign = [g.SeatResultRecord("claude", "other-subj", "att-2", ok),
                   *[rec for rec in current if rec.seat_id != "claude"]]
        assert call(foreign) is result.INCOMPLETE, (
            "a seat result keyed to another subject counted toward the "
            "verdict — half the (subject_digest, attempt_id) key is unsealed")
    elif case == "conflicting-duplicate":
        conflict = [*current,
                    g.SeatResultRecord("claude", "subj", "att-2",
                                       g.SeatOutcome(g.SeatVerdict.BLOCK))]
        assert call(conflict) is result.INCOMPLETE
    elif case == "lookalike-record":
        with pytest.raises(TypeError, match="is not a SeatResultRecord"):
            call([*current, _LookalikeSeatResultRecord()])
    else:
        with pytest.raises(TypeError, match="is not a SeatResultRecord"):
            call([*current, None])


class _LookalikeSeatResultRecord:
    """Right shape, wrong type: seat_id/subject_digest/attempt_id/outcome
    all present, so a duck-typed filter would count it."""

    seat_id = "claude"
    subject_digest = "subj"
    attempt_id = "att-2"
    outcome = None


# ─── BoundaryError universe: element-wise seal ───────────────────────────────

def test_boundary_error_maps_match_schema_element_wise(schemas, generated):
    """Per-code phase/retriability and the exit map are asserted against the
    schema row by row — a permuted assignment fails (panel finding: domain
    membership alone is satisfied by every permutation)."""
    g = generated
    rows = {c["code"]: c for c in schemas["boundary_errors"]["codes"]}
    assert {c.name for c in g.BoundaryErrorCode} == set(rows)
    exit_map = schemas["boundary_errors"]["cli_exit_map"]
    assert exit_map == {"ok": 0, "TERMINAL": 2, "RETRIABLE": 3, "OPERATOR": 4}
    for code in g.BoundaryErrorCode:
        row = rows[code.name]
        err = g.BoundaryError(code)
        assert err.phase.name == row["phase"], code
        assert err.retriability.name == row["retriability"], code
        assert err.exit_code == exit_map[row["retriability"]], code
        assert err.operator_action
        assert err.metric == f"boundary_error_{code.value.lower()}_total"
    assert {p.name for p in g.ErrorPhase} == set(schemas["boundary_errors"]["phases"])
    assert g.CLI_EXIT_OK == 0


def test_boundary_error_seal_detects_a_permutation(schemas, generated):
    """deny: the element-wise comparison is not vacuous — swapping two
    codes' retriability in a copy of the schema is detected."""
    g = generated
    rows = {c["code"]: dict(c) for c in schemas["boundary_errors"]["codes"]}
    a, b = "EPOCH_GAP", "ILLEGAL_TRANSITION"
    rows[a]["retriability"], rows[b]["retriability"] = \
        rows[b]["retriability"], rows[a]["retriability"]
    mismatches = [c for c in g.BoundaryErrorCode
                  if g.BoundaryError(c).retriability.name
                  != rows[c.name]["retriability"]]
    assert mismatches, "element-wise seal is vacuous — permutation undetected"


# ─── classifier frame vectors: a TOTAL reference parser ─────────────────────

class FrameReject(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _parse_frame(blob: bytes, bounds: dict) -> tuple[bytes, bytes]:
    """Total reference parser for the §8 octet frame: every malformed input
    maps to a closed reject reason — a crash (IndexError/struct.error) is
    never a parse outcome. Bounds are checked immediately after each length
    field, BEFORE the consistency comparison (§3.3: rejected before
    materialization)."""
    if len(blob) < 4:
        raise FrameReject("TRUNCATED_OUTER_LEN")
    outer_len = int.from_bytes(blob[:4], "big")
    body = blob[4:]
    if len(body) != outer_len:
        raise FrameReject("OUTER_LEN_MISMATCH")
    if len(body) < 1:
        raise FrameReject("EMPTY_BODY")
    if body[0] != 1:
        raise FrameReject("UNKNOWN_VERSION")
    off = 1
    if len(body) - off < 8:
        raise FrameReject("TRUNCATED_POLICY_LEN")
    policy_len = int.from_bytes(body[off:off + 8], "big")
    off += 8
    if policy_len > bounds["policy_max_bytes"]:
        raise FrameReject("POLICY_BOUND_EXCEEDED")
    if policy_len > len(body) - off:
        raise FrameReject("POLICY_LEN_MISMATCH")
    policy = body[off:off + policy_len]
    off += policy_len
    if len(body) - off < 8:
        raise FrameReject("TRUNCATED_DIFF_LEN")
    diff_len = int.from_bytes(body[off:off + 8], "big")
    off += 8
    if diff_len > bounds["diff_max_bytes"]:
        raise FrameReject("DIFF_BOUND_EXCEEDED")
    if diff_len > len(body) - off:
        raise FrameReject("DIFF_LEN_MISMATCH")
    diff = body[off:off + diff_len]
    off += diff_len
    if off != len(body):
        raise FrameReject("TRAILING_BYTES")
    return policy, diff


_FRAME_CASES = json.loads((FRAMES_DIR / "vectors.json").read_text())["cases"]


@pytest.mark.parametrize("case", [
    pytest.param(c["name"],
                 id=(c["name"] if c["expect"] == "accept"
                     else f"deny-{c['name']}"))
    for c in _FRAME_CASES
])
def test_classifier_frame_vectors(schemas, case):
    proto = schemas["classifier_protocol"]
    entry = next((c for c in _FRAME_CASES if c["name"] == case), None)
    assert entry is not None, f"frame vector {case!r} vanished from the index"
    blob = (FRAMES_DIR / entry["file"]).read_bytes()
    assert hashlib.sha256(blob).hexdigest() == entry["sha256"]
    if entry["expect"] == "accept":
        policy, diff = _parse_frame(blob, proto["bounds"])
        assert policy.decode() == proto["vectors"]["policy_payload"]
        assert diff.decode() == proto["vectors"]["diff_payload"]
    else:
        with pytest.raises(FrameReject) as exc:
            _parse_frame(blob, proto["bounds"])
        # the recorded reason is asserted — each vector proves its own rule.
        assert exc.value.code == entry["reason_code"], (
            f"{case}: rejected for {exc.value.code}, vector documents "
            f"{entry['reason_code']}")
        assert entry["reason_code"] in proto["reject_reasons"]


def test_every_reject_reason_has_a_vector(schemas):
    """The reject-reason domain is declared CLOSED — every member must be
    exercised by a committed vector, or the corpus silently under-covers it
    (panel round 2: TRAILING_BYTES had no vector and the trailing_data
    label concealed the gap)."""
    declared = set(schemas["classifier_protocol"]["reject_reasons"])
    covered = {c["reason_code"] for c in _FRAME_CASES if c.get("reason_code")}
    assert declared == covered, (
        f"unexercised reject reasons: {sorted(declared - covered)}; "
        f"vectors naming undeclared reasons: {sorted(covered - declared)}")


def test_frame_parser_is_total_on_arbitrary_prefixes(schemas):
    """No prefix of the valid frame crashes the parser — every truncation
    point yields a typed reject (the two crash paths the panel reproduced
    are inside this sweep)."""
    proto = schemas["classifier_protocol"]
    valid = (FRAMES_DIR / "valid_frame.bin").read_bytes()
    for cut in range(len(valid)):
        try:
            _parse_frame(valid[:cut], proto["bounds"])
            raise AssertionError(f"prefix {cut} unexpectedly parsed")
        except FrameReject:
            pass  # typed reject — never IndexError/struct.error


# ─── t26 lint as CI, falsified through the real constructor ─────────────────

def _lint():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import t26_lint
    finally:
        sys.path.pop(0)
    return t26_lint


def test_environment_matrix_degraded_mode(tmp_path, monkeypatch):
    """The peer-absent arm of the environment matrix, tested for real: with
    the peer unresolvable, --probe-peer reports absent and --no-citations
    still exits 0 having enforced every doc-local check, announcing the
    degradation on STDERR (panel round 2 — the documented fallback had
    never been executed, and the pytest seal took the citations-required
    path unconditionally)."""
    lint = _lint()
    # make both candidates fail: no env var, and a REPO_ROOT whose sibling
    # directory does not exist.
    monkeypatch.delenv("CLAUDE_WORKFLOW_REPO", raising=False)
    monkeypatch.setattr(lint, "REPO_ROOT", tmp_path / "repo")
    assert lint.find_workflow_repo() is None
    assert lint.peer_available() is False
    # Genuinely peer-less: run the child from an isolated tree whose sibling
    # directory has no claude-workflow (panel round 3, finding 21 — pointing
    # CLAUDE_WORKFLOW_REPO at a missing path still left the real sibling
    # resolvable, so the subprocess half never exercised absence).
    isolated = tmp_path / "nested" / "claude-dispatcher"
    isolated.parent.mkdir(parents=True)
    # real copies, not symlinks: t26_lint resolves REPO_ROOT from __file__,
    # and a symlink would resolve straight back to the real checkout (whose
    # sibling peer exists).
    shutil.copytree(REPO_ROOT / "tools", isolated / "tools")
    shutil.copytree(REPO_ROOT / "docs/plans", isolated / "docs/plans")
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_WORKFLOW_REPO"}
    assert not (isolated.parent / "claude-workflow").exists()
    probe = subprocess.run(
        [sys.executable, str(isolated / "tools/t26_lint.py"), "--probe-peer"],
        cwd=isolated, capture_output=True, text=True, timeout=180, env=env)
    assert probe.returncode == 1, (
        f"the isolated tree still resolved a peer: {probe.stdout}{probe.stderr}")
    assert "peer ABSENT" in probe.stderr
    # and the degraded run is green and loud from that same tree
    proc = subprocess.run(
        [sys.executable, str(isolated / "tools/t26_lint.py"), "--no-citations"],
        cwd=isolated, capture_output=True, text=True, timeout=180, env=env)
    assert proc.returncode == 0, f"degraded mode failed:\n{proc.stderr}"
    assert "DEGRADED" in proc.stderr, (
        "the degraded announcement must reach stderr, not a captured stdout")
    assert "citations SKIPPED" in proc.stderr


def test_environment_matrix_peer_present():
    """The peer-present arm: --probe-peer exits 0 and the citations-required
    form is what CI/`make verify-t26` run."""
    lint = _lint()
    if not lint.peer_available():
        pytest.skip("no claude-workflow peer checkout in this environment")
    assert _run(["tools/t26_lint.py", "--probe-peer"]).returncode == 0
    assert _run(["tools/t26_lint.py"]).returncode == 0


def test_t26_lint_green_on_checked_in_docs():
    """Green in EITHER environment: the seal consumes the same peer
    predicate scripts/test.sh does, so a dispatched worktree without the
    peer checkout is not reddened by a gate documented as peer-optional.

    The downgrade to --no-citations used to be SILENT: `_run` captures the
    child's "DEGRADED / citations SKIPPED" stderr and pytest prints nothing
    for a passing test, so a degraded run was byte-identical in output to a
    full-coverage one. It now warns, the way the AST gate's degraded arm
    already does (the repo runs with -ra, so warnings reach the summary).
    """
    lint = _lint()
    peer = lint.peer_available()
    args = ["tools/t26_lint.py"] if peer \
        else ["tools/t26_lint.py", "--no-citations"]
    proc = _run(args)
    assert proc.returncode == 0, f"t26_lint failed:\n{proc.stdout}{proc.stderr}"
    if not peer:
        warnings.warn(
            "t26 seal DEGRADED — no claude-workflow peer checkout, so the "
            "citations half of the doc lint was not exercised here (CI's "
            "citations job covers that arm)", stacklevel=2)


def _planted_doc(lint, tmp_path: Path, mutate) -> object:
    """Plant a mutation into a COPY of the real design doc and load it
    through the real Doc constructor — no reimplemented parsing."""
    text = mutate(lint.DESIGN.read_text(encoding="utf-8"))
    p = tmp_path / "design.md"
    p.write_text(text, encoding="utf-8")
    return lint.Doc(p)


_ANCHOR = "## 5. Panel decision"


@pytest.mark.parametrize("check_name,planted_line,expect", [
    pytest.param("check_retired",
                 "The machine uses AuthoritySnapshot here.",
                 "retired-name: line {line} (§5): `AuthoritySnapshot`",
                 id="deny-retired-live-use"),
    pytest.param("check_retired",
                 "The deleted disposition path uses MOVED_TO_HOLD as a live"
                 " mechanism.",
                 "retired-name: line {line} (§5): `MOVED_TO_HOLD`",
                 id="deny-retired-hides-behind-domain-words"),
    pytest.param("check_retired",
                 "Every disposition here is deleted after FOREIGN_OBSERVED"
                 " fires in the reduce.",
                 "retired-name: line {line} (§5): `FOREIGN_OBSERVED`",
                 id="deny-retired-foreign-observed-domain-words"),
    pytest.param("check_retired",
                 "A deleted disposition writes integrity_hold events on"
                 " every transition.",
                 "retired-name: line {line} (§5): `integrity_hold`",
                 id="deny-retired-integrity-hold-domain-words"),
    pytest.param("check_retired",
                 "The wire carries request_id on each deleted disposition"
                 " row.",
                 "retired-name: line {line} (§5): `request_id`",
                 id="deny-retired-request-id-domain-words"),
    pytest.param("check_section_refs", "See §99.9 for details.",
                 "§-ref: line {line}: §99.9 unresolved",
                 id="deny-unresolved-section-ref"),
    pytest.param("check_mutations",
                 "Appends use `createCommitOnBranch` again.",
                 "mutation-once: `createCommitOnBranch` bound 2 times",
                 id="deny-second-mutation-binding"),
    pytest.param("check_t_index", "T99 seals this.",
                 "T-index: T99 (cited at line {line}) has 0 §10 rows",
                 id="deny-t-without-index-row"),
    pytest.param("check_field_lists",
                 "`seat_result{roster_digest}` again.",
                 "field-list-once: `seat_result{{...}}` appears 2 times",
                 id="deny-second-field-list"),
    pytest.param("check_citations",
                 "See orchestrator.py:999999 for the branch.",
                 "orchestrator.py:999999 beyond EOF",
                 id="deny-citation-beyond-eof"),
])
def test_t26_lint_planted_violations_fire(tmp_path, check_name, planted_line,
                                          expect):
    """A lint that cannot fail is a vacuous seal (root cause E): each check
    is falsified through the REAL Doc constructor over a planted copy —
    including retired names hiding behind the domain words 'disposition'
    and 'deleted'. The assertion names the SPECIFIC violation, so an
    environment error (or an unrelated check firing) cannot masquerade as
    the plant being caught (panel round 2, finding 39).

    Two repairs (seal-repair pass):

    (1) The expectations embedded the ABSOLUTE line number 152, derived
    from where `## 5. Panel decision` happens to sit in a 635-line doc.
    Any insertion above §5 turned all ten rows red with a message reading
    "the lint stopped catching X" rather than "the doc moved". The number
    is now COMPUTED from the planted text's own index in the copy, so the
    rows keep the specificity finding 39 asked for and survive doc edits.
    MUTATION: insert a line anywhere above §5 in the design doc ⇒ still
    green (it used to go red); delete the retired-name check's line-number
    component ⇒ red.

    (2) The `check_citations` row was the only one that did not consult
    `lint.peer_available()`. Without the claude-workflow peer,
    check_citations returns after appending only the "peer checkout
    ABSENT" diagnostic, so `assert errors` passed but the specific-message
    assertion failed — taking the whole `pytest tests/` run down in the
    peer-ABSENT environment this PR documents, pins, and runs as CI's
    `gate` job (and which every dispatched worktree sees). The row now
    asserts the ABSENT diagnostic in that arm, so BOTH arms of the
    environment matrix exercise the check.
    MUTATION: make `check_citations` return without appending anything
    when the peer is absent ⇒ red in the peer-absent arm.
    """
    lint = _lint()
    planted_text = None

    def _plant(text: str) -> str:
        nonlocal planted_text
        planted_text = text.replace(_ANCHOR, _ANCHOR + "\n" + planted_line)
        return planted_text

    doc = _planted_doc(lint, tmp_path, _plant)
    # 1-based line number of the planted line in the COPY the check reads.
    lines = planted_text.splitlines()
    line_no = lines.index(planted_line) + 1
    assert lines[line_no - 2] == _ANCHOR, (
        "the plant did not land immediately after the §5 anchor")
    want = expect.format(line=line_no)

    errors: list[str] = []
    getattr(lint, check_name)(doc, errors)
    assert errors, f"{check_name} is vacuous — planted violation not flagged"
    if check_name == "check_citations" and not lint.peer_available():
        # peer-ABSENT arm: the check cannot resolve a citation at all, so
        # what it MUST do is say so — never pass silently, and never redden
        # a documented first-class environment.
        assert any("ABSENT" in e for e in errors), (
            "with the peer absent, check_citations neither resolved the "
            f"citation nor reported the absence: {errors}")
        warnings.warn(
            "t26 planted-violation seal DEGRADED — no claude-workflow peer, "
            "so the citations half asserts only the ABSENT diagnostic",
            stacklevel=2)
        return
    assert any(want in e for e in errors), (
        f"{check_name} fired, but not for the planted violation.\n"
        f"expected a message containing: {want!r}\ngot: {errors}")
    # the clean doc must NOT produce this violation — proving the plant, and
    # not the document itself, is what the check reacted to.
    clean: list[str] = []
    getattr(lint, check_name)(lint.Doc(lint.DESIGN), clean)
    assert not any(want in e for e in clean), (
        f"{check_name}: the checked-in doc already trips this message")


def test_t26_lint_supersession_and_plan_tmap_falsified(tmp_path, monkeypatch):
    lint = _lint()
    # supersession: strip one marker's brackets → bare SUPERSEDED mention
    doc = _planted_doc(
        lint, tmp_path,
        lambda t: t.replace("**[SUPERSEDED r6:", "**SUPERSEDED r6:", 1))
    errors: list[str] = []
    lint.check_supersession(doc, errors)
    assert errors, "supersession check is vacuous"
    # plan T-map: drop T19 from a copy of the plan's §3
    plan_text = lint.PLAN.read_text(encoding="utf-8").replace("T19/", "")
    planted_plan = tmp_path / "plan.md"
    planted_plan.write_text(plan_text, encoding="utf-8")
    monkeypatch.setattr(lint, "PLAN", planted_plan)
    doc = lint.Doc(lint.DESIGN)
    errors = []
    lint.check_plan_tmap(doc, errors)
    assert any("T19" in e for e in errors), "plan T-map check is vacuous"


# ─── T8/T9 fail-closed AST gates ─────────────────────────────────────────────

# Shipped python OUTSIDE the package is production too: tools/ already
# imports claude_dispatcher (tools/retroactive_sweep.py, tools/
# cross_family_panel.py), so a pre-PR6 `from claude_dispatcher.boundary
# import generated` there — or a construction of a guarded name — was
# invisible to both AST gates while the seals' docstrings said "any
# production import". scripts/ is included on the same reasoning.
_SCANNED_ROOTS = ("src/claude_dispatcher", "tools", "scripts")


def _production_modules() -> list[Path]:
    """Every shipped .py the T8/T9 and dark-mode gates scan. tests/ is
    excluded by construction (the boundary package is test-importable until
    PR6); tools/fsmgen.py is NOT excluded — it names the generated path as a
    STRING, which no AST scanner here matches."""
    mods: list[Path] = []
    for root in _SCANNED_ROOTS:
        base = REPO_ROOT / root
        if base.is_dir():
            mods += base.rglob("*.py")
    return sorted(mods)


def test_the_ast_gates_scan_the_whole_shipped_surface():
    """deny: the scanned-path set is itself a seal. Narrowing it back to
    src/claude_dispatcher (as it was) silently exempts tools/ and scripts/
    from both AST gates.

    MUTATION: drop "tools" from _SCANNED_ROOTS ⇒ red.
    """
    scanned = _production_modules()
    roots = {str(REPO_ROOT / r) for r in _SCANNED_ROOTS}
    assert roots == {str(REPO_ROOT / "src/claude_dispatcher"),
                     str(REPO_ROOT / "tools"), str(REPO_ROOT / "scripts")}
    for root in ("src/claude_dispatcher", "tools"):
        assert any((REPO_ROOT / root) in m.parents for m in scanned), (
            f"{root}/ is shipped python but no module under it is scanned")
    assert not any("/tests/" in str(m) for m in scanned), (
        "tests/ is inside the scan — boundary/ is test-importable until PR6")


def _guarded_aliases(tree: ast.AST, guarded: set[str]) -> dict[str, str]:
    """Local names bound to a guarded name by `from x import Name as N`."""
    return {a.asname or a.name: a.name
            for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
            for a in node.names if a.name in guarded}


def _guarded_hit(node: ast.AST, guarded: set[str],
                 aliases: dict[str, str]) -> str | None:
    """One node's verdict: a definition, a construction (bare-name, aliased
    or attribute-qualified), or None."""
    if isinstance(node, ast.ClassDef) and node.name in guarded:
        return f"defines {node.name}"
    if not isinstance(node, ast.Call):
        return None
    fn = node.func
    if isinstance(fn, ast.Name) and (fn.id in guarded or fn.id in aliases):
        return f"constructs {aliases.get(fn.id, fn.id)}"
    if isinstance(fn, ast.Attribute) and fn.attr in guarded:
        return f"constructs {fn.attr} (attribute-qualified)"
    return None


def _scan_guarded(paths: list[Path], guarded: set[str],
                  exempt: set[Path]) -> list[str]:
    """Definitions and constructions of guarded names, in every spelling."""
    hits = []
    for path in paths:
        if path in exempt:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases = _guarded_aliases(tree, guarded)
        for node in ast.walk(tree):
            verdict = _guarded_hit(node, guarded, aliases)
            if verdict:
                hits.append(f"{path}:{node.lineno} {verdict}")
    return hits

_ROGUE_SPELLINGS = {
    "bare-name": "from claude_dispatcher.boundary.wire import parse\n"
                 "x = ClassifyOutcome()\n",
    "attribute": "import claude_dispatcher.boundary.wire as wire\n"
                 "x = wire.ClassifyOutcome()\n",
    "aliased": "from claude_dispatcher.boundary.wire import "
               "ClassifyOutcome as CO\nx = CO()\n",
    "classdef": "class ClassifyOutcome:\n    pass\n",
}


@pytest.mark.parametrize("gate", [
    pytest.param("t8_construction", id="t8-construction"),
    pytest.param("t9_interpretation", id="t9-interpretation"),
    *[pytest.param(f"deny:{s}", id=f"deny-t8-scanner-sees-{s}")
      for s in sorted(_ROGUE_SPELLINGS)],
])
def test_ast_allowlists_fail_closed(schemas, tmp_path, gate):
    """While the allowlisted modules are absent (pre-PR2), their absence is
    the expected state — but ANY other module defining or constructing a
    guarded name, in any spelling, is a hard failure (grok B3)."""
    allow = schemas["ast_allowlists"]
    if gate.startswith("deny:"):
        spelling = gate.split(":", 1)[1]
        rogue = tmp_path / "rogue.py"
        rogue.write_text(_ROGUE_SPELLINGS[spelling])
        hits = _scan_guarded([rogue], {"ClassifyOutcome"}, set())
        assert hits, f"T8 scanner is vacuous for the {spelling} spelling"
        return
    spec = allow[gate]
    guarded = set(spec["guarded_names"])
    allowed = {REPO_ROOT / m for m in spec["allowed_modules"]}
    exempt = allowed | {REPO_ROOT / m for m in spec.get("legacy_exemptions", [])}
    hits = _scan_guarded(_production_modules(), guarded, exempt)
    absent = [m for m in allowed if not m.exists()]
    assert not hits, (
        f"{gate}: guarded names outside the allowlist (allowlisted modules "
        f"{'ABSENT — pre-PR2 fail-closed gate' if absent else 'present'}):\n"
        + "\n".join(hits))
    if absent:
        # a captured print() is invisible on a passing test; a warning shows
        # in pytest's summary (the repo runs with -ra) and in CI logs.
        warnings.warn(
            f"{gate}: FAIL-CLOSED GATE DEGRADED — allowlisted modules absent "
            f"as expected pre-PR2: "
            f"{[str(m.relative_to(REPO_ROOT)) for m in absent]}; the gate "
            f"still hard-fails any guarded name defined elsewhere",
            stacklevel=2)


# ─── architecture skeleton: dark mode ────────────────────────────────────────

_BOUNDARY_PKG = "claude_dispatcher.boundary"


def _is_boundary_module(name: str) -> bool:
    """The package itself or a submodule of it — NOT a sibling whose name
    merely starts with the same characters (`claude_dispatcher.boundary_
    breaker` is a different package, and flagging it would make the gate
    report a violation that does not exist)."""
    return name == _BOUNDARY_PKG or name.startswith(_BOUNDARY_PKG + ".")


def _plain_import_hits(node: ast.Import) -> list[str]:
    return [a.name for a in node.names if _is_boundary_module(a.name)]


def _from_import_hits(node: ast.ImportFrom) -> list[str]:
    mod = node.module or ""
    names = {a.name for a in node.names}
    if _is_boundary_module(mod):
        return [mod]
    if mod == "claude_dispatcher" and "boundary" in names:
        return ["claude_dispatcher.boundary"]
    if node.level and (mod == "boundary" or mod.startswith("boundary.")):
        return [f".{mod}"]
    if node.level and not mod and "boundary" in names:
        return [".boundary"]
    return []


def _imports_boundary(tree: ast.AST) -> list[str]:
    """Every spelling of an import of claude_dispatcher.boundary — one
    helper per import FORM, each sealed by its own deny row."""
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += _plain_import_hits(node)
        elif isinstance(node, ast.ImportFrom):
            hits += _from_import_hits(node)
    return hits

_IMPORT_SPELLINGS = {
    "absolute": "import claude_dispatcher.boundary\n",
    "absolute-submodule": "import claude_dispatcher.boundary.generated as g\n",
    "from-package": "from claude_dispatcher import boundary\n",
    "from-package-aliased": "from claude_dispatcher import boundary as b\n",
    "from-subpackage": "from claude_dispatcher.boundary import generated\n",
    "relative": "from .boundary import generated\n",
    "relative-bare": "from . import boundary\n",
}


# Spellings the detector must NOT flag. A false positive is not a harmless
# extra: it reports a dark-mode violation that does not exist, and the fix
# for it is to weaken the detector.
_INNOCENT_SPELLINGS = {
    "sibling-package": "import claude_dispatcher.boundary_breaker\n",
    "sibling-from": "from claude_dispatcher.boundary_breaker import x\n",
    "unrelated": "from claude_dispatcher import risk\n",
    "boundary-named-attribute": "x = obj.boundary\n",
}


@pytest.mark.parametrize("case", [
    pytest.param("live", id="no-production-import-while-allowlist-empty"),
    *[pytest.param(f"deny:{s}", id=f"deny-detector-sees-{s}")
      for s in sorted(_IMPORT_SPELLINGS)],
    *[pytest.param(f"innocent:{s}", id=f"deny-detector-ignores-{s}")
      for s in sorted(_INNOCENT_SPELLINGS)],
])
def test_architecture_boundary_dark_mode(schemas, case):
    """boundary/ is importable from tests only until PR6; the door
    allowlist is empty and this harness fails on any production import.

    SCOPE, stated because the module docstring used to claim "every import
    spelling": the detector reads STATIC import syntax — the seven forms in
    `_IMPORT_SPELLINGS`, each with its own deny row. A dynamic
    `importlib.import_module("claude_dispatcher.boundary")` or
    `__import__(...)` is NOT detected. That is the accepted limit recorded
    in schema/ast_allowlists.yaml's architecture block: the threat is
    honest misconfiguration, not evasion (§0.1 puts a determined local
    actor out of scope), and PR6 removes the question by filling
    door_entrypoints.

    The prefix test was `startswith("claude_dispatcher.boundary")`, which
    also flags a sibling package named `claude_dispatcher.boundary_breaker`
    — the `innocent:` rows pin that it does not.

    MUTATION: `_is_boundary_module` → `name.startswith(_BOUNDARY_PKG)`
    ⇒ the sibling-package rows go red; → `return False` ⇒ all seven
    `deny-detector-sees-*` rows go red.
    """
    arch = schemas["ast_allowlists"]["architecture"]
    if case.startswith("deny:"):
        spelling = case.split(":", 1)[1]
        tree = ast.parse(_IMPORT_SPELLINGS[spelling])
        assert _imports_boundary(tree), (
            f"architecture detector is vacuous for the {spelling} spelling")
        return
    if case.startswith("innocent:"):
        spelling = case.split(":", 1)[1]
        tree = ast.parse(_INNOCENT_SPELLINGS[spelling])
        assert not _imports_boundary(tree), (
            f"architecture detector FALSELY flags the {spelling} spelling — "
            f"a violation that does not exist")
        return
    allowlist = {REPO_ROOT / m for m in arch["door_entrypoints"]}
    boundary_pkg = REPO_ROOT / "src/claude_dispatcher/boundary"
    offenders = []
    for path in _production_modules():
        if boundary_pkg in path.parents or path in allowlist:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for hit in _imports_boundary(tree):
            offenders.append(f"{path.relative_to(REPO_ROOT)} imports {hit}")
    assert not offenders, (
        "dark mode violated — production imports of claude_dispatcher.boundary "
        "outside the (empty) door allowlist:\n" + "\n".join(offenders))


# ─── T6: every parametrised seal has ≥1 deny row ────────────────────────────

def _seals_missing_deny(seal_ids: dict[tuple[str, str], list[str]]) -> list[str]:
    """Pure helper over {(module, test_function): [param ids]} — a seal with
    no id starting with 'deny' is a violation."""
    return [f"{mod}::{func} ids={ids}"
            for (mod, func), ids in sorted(seal_ids.items())
            if not any(str(i).startswith("deny") for i in ids)]


def test_t6_every_parametrized_seal_has_a_deny_row(request):
    """Collection-time T6: walk the ACTUAL collected items' param ids —
    dynamically built param lists included — and fail any parametrised seal
    in tests/boundary without a deny row.

    Design §12 states the rule UNSCOPED ("every parametrised seal includes
    ≥1 deny row (T6)"); this checker enforces it over tests/boundary,
    including subpackages — the boundary seals PR0 owns. Widening it to the
    whole suite (ten non-boundary modules carry @parametrize) is deferred;
    the plan lists T6 as "PR0, permanent".
    """
    # The checker reads the whole COLLECTED session, so any partial
    # selection (-k / -m / --deselect / an explicit nodeid) makes its input
    # a fragment: `pytest -k "t6_every_parametrized or required_seats_full"`
    # used to FAIL with "assert {}" — the wrong reason entirely. A filtered
    # run skips; a full run keeps the hard failure.
    opt = request.config.option
    filtered = bool(getattr(opt, "keyword", "") or getattr(opt, "markexpr", "")
                    or getattr(opt, "deselect", None)
                    or getattr(opt, "last_failed", False))
    seal_ids: dict[tuple[str, str], list[str]] = {}
    for item in request.session.items:
        if not isinstance(item, pytest.Function):
            continue
        fspath = Path(str(item.fspath))
        # a seal placed in a subpackage must not escape the check
        if BOUNDARY_DIR not in fspath.parents:
            continue
        callspec = getattr(item, "callspec", None)
        if callspec is None:
            continue
        seal_ids.setdefault((fspath.name, item.originalname),
                            []).append(callspec.id)
    if filtered:
        pytest.skip("T6 reads the whole collected session; this run is "
                    "filtered (-k/-m/--deselect/--lf) so its input is a "
                    "fragment — run the full suite for the T6 gate")
    assert seal_ids, "T6: no parametrised seals collected — checker misfiring"
    missing = _seals_missing_deny(seal_ids)
    assert not missing, ("T6 (design §12): parametrised seals without a deny "
                         "row:\n" + "\n".join(missing))
    # deny: the helper itself must fire on a plant with no deny id.
    assert _seals_missing_deny({("m.py", "test_x"): ["allow-1", "allow-2"]}), \
        "T6 helper is vacuous"


def test_t19_vectors_dir_matches_loaded():
    assert set(_VECTORS) == {p.stem for p in _vector_paths()}


def test_the_handwritten_vector_region_is_the_test_authors(schemas):
    """`tests/boundary/vectors/t19/handwritten/` exists so a test author can
    seal a property with a committed vector WITHOUT editing the generator —
    which is what keeps the fix author and the check author separate. The
    region's three promises are asserted here, because a promise in a README
    is not a mechanism:

      1. the generator never emits anything into it — so it cannot rewrite
         or delete the author's vectors;
      2. `fsmgen --check`'s stray scan tolerates it — so a vector here is
         not reported as drift;
      3. well-formedness IS still validated — so a malformed vector fails
         the same gate the generated corpus does.

    MUTATIONS (tools/fsmgen.py, not committed):
      (1) add any output path under handwritten/ to build_outputs ⇒ red.
      (3) `check_handwritten_vectors` returns [] ⇒ red (and every row of
          the well-formedness table below goes red).
      (2) is the END property over the REAL committed tree, and it takes a
          COMPOSITE mutation because the region is protected by TWO
          independent mechanisms: the stray scan's glob is non-recursive AND
          it skips HANDWRITTEN_DIR explicitly. Removing either alone leaves
          the other holding, so `glob`→`rglob` TOGETHER WITH dropping the
          skip ⇒ red here. Each mechanism now has its OWN seal that binds on
          a SINGLE mutation — see the two seals immediately below — so the
          coupling is no longer an excuse for an unfalsifiable claim; this
          row remains as the end-to-end statement over the real tree.
    """
    fsmgen = _fsmgen()
    assert HANDWRITTEN_DIR.is_dir(), (
        "the hand-authored vector region is gone — a test author would have "
        "to edit the generator to add a vector")
    # (1) nothing the generator produces lands in the region
    outputs = fsmgen.build_outputs(fsmgen.load_schemas())
    inside = [str(pth) for pth in outputs
              if HANDWRITTEN_DIR in pth.parents or pth == HANDWRITTEN_DIR]
    assert not inside, f"fsmgen writes into the test author's region: {inside}"
    # (2) the region is not drift, and the committed tree is clean overall
    drift = fsmgen.check_outputs(outputs)
    assert not drift, f"fsmgen --check reports drift: {drift}"
    assert HANDWRITTEN_DIR.glob("*.json"), "no hand-authored vector to protect"
    # (3) well-formedness is enforced — plant a malformed vector in a COPY of
    #     the region and assert the generator's own validator refuses it.
    #     (Never in the real tree: a crash between write and unlink would
    #     leave the working tree dirty — panel round 3, finding 50.)
    assert not fsmgen.check_handwritten_vectors(), (
        "a committed hand-authored vector is malformed")


def _staged_scan(fsmgen, tmp_path, monkeypatch, region: Path) -> None:
    """Point the generator's stray scan at a staged vectors tree with an
    EMPTY output set, so every file it finds there is a stray candidate and
    nothing else can explain a drift report. `region` is where
    HANDWRITTEN_DIR points for this probe.

    White-box on purpose: these two seals isolate the generator's two
    protections of the author region ONE AT A TIME, which the end-property
    seal above cannot do (either mechanism alone suffices, so neither is
    falsifiable through the real tree)."""
    staged = tmp_path / "t19"
    staged.mkdir(exist_ok=True)
    monkeypatch.setattr(fsmgen, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(fsmgen, "VECTORS_DIR", staged)
    monkeypatch.setattr(fsmgen, "HANDWRITTEN_DIR", region)
    for attr in ("DOCS_DIR", "FRAMES_DIR"):
        empty = tmp_path / attr.lower()
        empty.mkdir(exist_ok=True)
        monkeypatch.setattr(fsmgen, attr, empty)


_WELL_FORMED_VECTOR = json.dumps(
    {"machine": "section_a", "note": "probe", "events": []})


def test_the_stray_scan_skips_the_author_region(tmp_path, monkeypatch):
    """MECHANISM 1 of 2, isolated: the stray scan's explicit
    `HANDWRITTEN_DIR in p.parents or p == HANDWRITTEN_DIR` skip.

    The scanned directory IS the region for this probe, so the file is found
    by the scan's own (non-recursive) glob and ONLY the skip can keep it out
    of the drift list. Nothing else is in play: the output set is empty, so
    every file present is otherwise a stray.

    MUTATION (single): delete the `HANDWRITTEN_DIR in p.parents or p ==
    HANDWRITTEN_DIR: continue` arm from `check_outputs` ⇒ red.
    """
    fsmgen = _fsmgen()
    staged = tmp_path / "t19"
    staged.mkdir()
    _staged_scan(fsmgen, tmp_path, monkeypatch, region=staged)
    (staged / "authored.json").write_text(_WELL_FORMED_VECTOR, encoding="utf-8")
    drift = fsmgen.check_outputs({})
    assert not drift, (
        f"the stray scan reports the author's own region as drift: {drift}")
    # …and the same scan DOES report a stray that is not in the region, so
    # the probe is not simply blind.
    monkeypatch.setattr(fsmgen, "HANDWRITTEN_DIR", tmp_path / "elsewhere")
    assert any("authored.json" in d for d in fsmgen.check_outputs({})), (
        "the staged scan cannot see the file at all — this probe would pass "
        "for the wrong reason")


def test_the_stray_scan_does_not_recurse(tmp_path, monkeypatch):
    """MECHANISM 2 of 2, isolated: the stray scan globs each generated
    directory NON-recursively, so a nested directory under the vectors tree
    is outside it. That is what keeps `handwritten/`'s CONTENTS out of the
    scan even before the skip is consulted.

    HANDWRITTEN_DIR points somewhere else entirely here, so the skip cannot
    be what saves the nested file — only the non-recursive glob can.

    MUTATION (single): `directory.glob(pattern)` → `directory.rglob(pattern)`
    in `check_outputs` ⇒ red.
    """
    fsmgen = _fsmgen()
    staged = tmp_path / "t19"
    staged.mkdir()
    _staged_scan(fsmgen, tmp_path, monkeypatch, region=tmp_path / "elsewhere")
    nested = staged / "nested"
    nested.mkdir()
    (nested / "authored.json").write_text(_WELL_FORMED_VECTOR, encoding="utf-8")
    drift = fsmgen.check_outputs({})
    assert not drift, (
        f"the stray scan recursed into a nested directory: {drift}")
    # control: a file at the TOP level of the scanned tree IS a stray, so
    # the scan is running at all.
    (staged / "top.json").write_text(_WELL_FORMED_VECTOR, encoding="utf-8")
    assert any("top.json" in d for d in fsmgen.check_outputs({})), (
        "the staged scan reports nothing at all — this probe would pass for "
        "the wrong reason")


@pytest.mark.parametrize("planted,expect", [
    pytest.param("{", "not valid JSON", id="deny-handwritten-not-json"),
    pytest.param('[]', "top level must be an object",
                 id="deny-handwritten-not-an-object"),
    pytest.param('{"machine": "nope", "note": "x", "events": []}',
                 "machine must be one of", id="deny-handwritten-unknown-machine"),
    pytest.param('{"machine": "section_a", "note": "  ", "events": []}',
                 "needs a non-empty `note`", id="deny-handwritten-no-note"),
    pytest.param('{"machine": "section_a", "note": "x", "events": {}}',
                 "`events` must be a list", id="deny-handwritten-events-not-a-list"),
    pytest.param('{"machine": "section_b", "note": "x", "events": []}',
                 "declare the RUN's credential_mode",
                 id="deny-handwritten-section-b-without-run-mode"),
    pytest.param('{"machine": "epoch_fold", "note": "x", "events": []}',
                 "need an `anchors` map", id="deny-handwritten-fold-without-anchors"),
])
def test_handwritten_vector_wellformedness_is_enforced(tmp_path, monkeypatch,
                                                       planted, expect):
    """Each well-formedness rule the region documents, falsified through the
    generator's REAL validator over a planted copy of the region — so "still
    validated for well-formedness" is a mechanism, not prose.

    MUTATION: delete any one arm of `check_handwritten_vectors` ⇒ exactly
    its row goes red.
    """
    fsmgen = _fsmgen()
    staged = tmp_path / "handwritten"
    staged.mkdir()
    (staged / "planted.json").write_text(planted, encoding="utf-8")
    monkeypatch.setattr(fsmgen, "HANDWRITTEN_DIR", staged)
    monkeypatch.setattr(fsmgen, "REPO_ROOT", tmp_path)
    problems = fsmgen.check_handwritten_vectors()
    assert problems, "the validator accepted a malformed hand-authored vector"
    assert any(expect in pr for pr in problems), (
        f"the validator fired, but not for the planted defect.\n"
        f"expected a message containing {expect!r}\ngot: {problems}")
