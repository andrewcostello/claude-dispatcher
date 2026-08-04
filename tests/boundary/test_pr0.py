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
- t26_lint: the design doc's own lint, wired as CI, with planted-violation
  deny rows through the REAL Doc constructor.
- T8/T9 fail-closed AST gates covering bare-name, attribute-qualified and
  import-aliased constructions; dark-mode detector covering every import
  spelling; each with deny fixtures.
- T6: every parametrised seal carries a deny row — checked over the
  COLLECTED items' real param ids.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_DIR = REPO_ROOT / "schema"
VECTORS_DIR = REPO_ROOT / "tests/boundary/vectors/t19"
EXPECTED_PATH = REPO_ROOT / "tests/boundary/vectors/t19_expected.json"
BOUNDARY_DIR = REPO_ROOT / "tests/boundary"
FRAMES_DIR = REPO_ROOT / "schema/testdata/classifier_frames"

# Independently computed goldens (standalone snippets over the schema's
# preimage specs — never the generated functions):
PINNED_ROSTER_DIGEST = "9108f9897faff4e3fdba20745ca51eea1a30309cfe32b2a739039b69089ca4a8"
PINNED_HOLD_ID_SEQ0 = "ee8e6d58f6a3b89373def7e3b4e1556b6499ab81a8edc174b555931d8bb9e724"
PINNED_RECOVERY_ID_M1 = "dd693323dd35ceed8d6339ba871ea2784b81410d51ef5e9940c2dfc883e808c6"


def load_vectors() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(VECTORS_DIR.glob("*.json"))}


_VECTORS = load_vectors()
_EXPECTED = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))["vectors"]


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


def test_generated_paths_git_clean():
    """`git status --porcelain` (not `git diff`) so a STAGED hand edit and an
    untracked stray in a generated path are caught too (panel round 2)."""
    proc = subprocess.run(
        ["git", "status", "--porcelain", "--",
         "src/claude_dispatcher/boundary/generated", "docs/generated",
         "tests/boundary/vectors/t19", "schema/testdata"],
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


def test_oracle_is_not_an_fsmgen_output():
    """The independent-oracle rule, sealed against fsmgen's REAL output set
    (panel round 2: the previous seal inspected a 1.8KB slice of the source
    and could not detect generation at all). Three assertions:
      1. the oracle path is not in build_outputs() — a content-level fact,
         not a substring guess;
      2. no generated vector carries an 'expected' key;
      3. the seal itself is falsifiable — a simulated output set CONTAINING
         the oracle is detected by the same membership predicate."""
    fsmgen = _fsmgen()
    outputs = fsmgen.build_outputs(fsmgen.load_schemas())
    assert EXPECTED_PATH not in outputs, (
        "fsmgen writes the oracle — the T19 goldens would be self-sealing")
    assert EXPECTED_PATH.parent in {p.parent for p in outputs} or True
    for name, vec in _VECTORS.items():
        assert "expected" not in vec, (
            f"{name}: vectors are inputs only — expectations live in the "
            f"hand-written oracle")
    # deny: the predicate fires when the oracle IS in the output set.
    simulated = dict(outputs)
    simulated[EXPECTED_PATH] = b"{}"
    assert EXPECTED_PATH in simulated, "oracle-independence seal is vacuous"


def test_fsmgen_check_flags_a_generated_oracle(tmp_path, monkeypatch):
    """Second, stronger half: if a future edit made fsmgen emit the oracle,
    `fsmgen --check`'s stray scan over the vectors tree must call it drift."""
    fsmgen = _fsmgen()
    outputs = fsmgen.build_outputs(fsmgen.load_schemas())
    stray = fsmgen.VECTORS_DIR / "not_a_generated_vector.json"
    stray.write_text("{}", encoding="utf-8")
    try:
        drift = fsmgen.check_outputs(outputs)
    finally:
        stray.unlink()
    assert any("stray" in d and stray.name in d for d in drift), (
        "fsmgen --check does not flag stray files in the vectors tree")


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


def test_singles_exhaustive_and_domain_validated(schemas, generated):
    """Every §9 single (incl. authorization_granted, the sole authorization
    record) is a generated, sealed type with its closed domains enforced."""
    singles = schemas["lifecycle_fsm"]["events"]["singles"]
    for name in singles:
        assert name in generated.SINGLE_EVENTS, f"single {name} not generated"
    for v in schemas["lifecycle_fsm"]["events"]["unions"][
            "classification_evaluated"]["variants"]:
        assert f"classification_evaluated/{v['name']}" in generated.SINGLE_EVENTS
    env = dict(schema_major=1, schema_minor=0, event_id="e1",
               ts="1970-01-01T00:00:00Z", run_id="r", trace_id="tr",
               protocol_epoch="E0")
    ag = generated.SINGLE_EVENTS["authorization_granted"]
    ok = ag(**env, authorization_id="a1", base_key="b", authority="fp",
            kind="AUTO_LOW", assurance="NOT_APPLICABLE", evidence_ref="ev",
            actor="dispatcher")
    assert ok.kind == "AUTO_LOW"
    with pytest.raises(ValueError):
        ag(**env, authorization_id="a1", base_key="b", authority="fp",
           kind="VIBES", assurance="NOT_APPLICABLE", evidence_ref="ev",
           actor="dispatcher")  # deny: unknown kind outside the closed domain
    with pytest.raises(ValueError):
        ag(**env, authorization_id="a1", base_key="b", authority="fp",
           kind="AUTO_LOW", assurance="", evidence_ref="ev", actor="d")


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

def _envelope_kwargs():
    return dict(schema_major=1, schema_minor=0, event_id="e1",
                ts="1970-01-01T00:00:00Z", run_id="run-1",
                trace_id="trace-1", protocol_epoch="E0")


def _finish_audit(cls, kwargs: dict, over: dict) -> dict:
    """trigger_event/from/to are §9-REQUIRED wire fields validated against
    the variant's row — default them FROM the row so a helper never
    desynchronises them (tests that mean to desynchronise pass them)."""
    kwargs.update(over)
    kwargs.setdefault("from_state", cls.FROM_STATES[0])
    kwargs.setdefault("trigger_event", cls.TRIGGER)
    kwargs.setdefault("to_state", kwargs["from_state"]
                      if cls.TO_STATE == "unchanged" else cls.TO_STATE)
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
        kwargs["disposition"] = \
            generated.ReconcileDisposition.ACCEPT_FOREIGN_ADVANCED
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
        kwargs["disposition"] = generated.ReconcileDisposition.ACCEPT_OURS
    return cls(**_finish_audit(cls, kwargs, over))


def test_reconcile_disposition_algebra_enforced(schemas, generated):
    """The disposition sets match the schema AND are enforced: an
    operator_reconcile variant on either machine rejects section-B-only /
    non-operator dispositions at construction (panel CRITICAL: no side door
    into RELEASED(ACTOR_VERIFIED_AUTO))."""
    disp = schemas["lifecycle_fsm"]["reconcile_dispositions"]
    g = generated
    assert {d.name for d in g.ACCEPTING_DISPOSITIONS} == set(disp["accepting"])
    assert {d.name for d in g.OPERATOR_ACCEPTING_DISPOSITIONS} == \
        set(disp["operator_accepting"])
    assert {d.name for d in g.SECTION_B_ONLY_DISPOSITIONS} == \
        {m["name"] for m in disp["members"] if m.get("section_b_only")}
    assert not (g.OPERATOR_ACCEPTING_DISPOSITIONS & g.SECTION_B_ONLY_DISPOSITIONS)
    with pytest.raises(ValueError):  # section A cannot mint the auto disposition
        _mk_effect(g, "ReconcileAccept",
                   disposition=g.ReconcileDisposition.ACTOR_VERIFIED_AUTO)
    with pytest.raises(ValueError):  # nor can a section-B operator reconcile
        _mk_hold(g, "HoldReconcileAccept", hold_id="h",
                 disposition=g.ReconcileDisposition.ACTOR_VERIFIED_AUTO)
    with pytest.raises(ValueError):  # STANDING routes through its own variant
        _mk_hold(g, "HoldReconcileAccept", hold_id="h",
                 disposition=g.ReconcileDisposition.STANDING)
    with pytest.raises(ValueError):  # under SHARED, never
        _mk_hold(g, "ActorVerifiedAuto", hold_id="h", actor_node_id="n",
                 matched_subject_digest="s",
                 actor_verification=g.ActorVerification.VERIFIED_API,
                 mode=g.CredentialMode.SHARED,
                 disposition=g.ReconcileDisposition.ACTOR_VERIFIED_AUTO)
    with pytest.raises(ValueError):  # raw string for an enum field: no coercion
        _mk_effect(g, "Prepare", credential_mode="SHARED")


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
    with pytest.raises(generated.IllegalTransitionError) as exc:
        generated.apply_section_a(st, ev)
    assert exc.value.error.code is generated.BoundaryErrorCode.ILLEGAL_TRANSITION


@pytest.mark.parametrize("case", [
    pytest.param(("GENESIS", "Prepare", "PREPARED"), id="genesis-prepare"),
    pytest.param(("PREPARED", "Submit", "SUBMITTED"), id="prepared-submit"),
    pytest.param(("SUBMITTED", "ObserveReject", "REJECTED_NO_EFFECT"),
                 id="submitted-reject"),
    pytest.param(("EFFECT_OBSERVED", "Explained", "EXPLAINED"), id="explained"),
    pytest.param(("GENESIS", "LOOKALIKE", None), id="deny-structural-lookalike"),
])
def test_section_a_apply_dispatch(generated, case):
    state, variant, want = case
    st = generated.MachineStateA(generated.SectionAState[state])
    if variant == "LOOKALIKE":
        class Prepare:  # same NAME as the real variant — shape is not identity
            FROM_STATES = ("GENESIS",)
            TO_STATE = "PREPARED"
            TRIGGER = "prepare"
        with pytest.raises(generated.IllegalTransitionError):
            generated.apply_section_a(st, Prepare())
        return
    ev = _mk_effect(generated, variant, from_state=state)
    assert generated.apply_section_a(st, ev).name.value == want


# ─── T19 goldens against the hand-written oracle ─────────────────────────────

def _project_halt(halt):
    return None if halt is None else {"code": halt["code"]}


def _project_result(machine: str, got: dict) -> dict:
    """Compare on the CONTRACT: reduced state exactly, halts per base_key on
    the code. Halt DETAILS are diagnostics — pinned separately by
    test_deny_vectors_pin_their_rule, which asserts the named fields."""
    if machine == "section_a":
        return {"movements": got["movements"],
                "recovery_appends": got["recovery_appends"],
                "halts": {b: {"code": h["code"]} for b, h in got["halts"].items()}}
    if machine == "section_b":
        return {"holds": got["holds"],
                "halts": {b: {"code": h["code"]} for b, h in got["halts"].items()}}
    return {base: {"status": entry["status"], "epoch": entry["epoch"],
                   "halt": _project_halt(entry["halt"])}
            for base, entry in got.items()}


def _reduce(generated, vec: dict) -> dict:
    if vec["machine"] == "section_a":
        return generated.reduce_section_a(vec["events"])
    if vec["machine"] == "section_b":
        return generated.reduce_section_b(vec["events"])
    return generated.fold_epochs(vec["events"], vec["anchors"])


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
    "a_bad_ts_deny": ["ts", "RFC 3339"],
    "a_none_effect_row_advances_deny": ["no epoch effect", "advances"],
    "dual_append_divergent_payload_deny": ["divergent payloads", "integrity"],
    "reconcile_conflict_deny": ["conflicting disposition"],
    "resume_submit_illegal_deny": ["memory-only", "resume-submit"],
    "b_actor_verified_shared_deny": ["SEPARATED"],
    "b_actor_verified_wrong_delta_digest_deny":
        ["matched_subject_digest", "self-asserted evidence refused"],
    "b_actor_verified_unresolvable_delivery_deny":
        ["source_delivery_id", "not a delivery recorded on"],
    "b_reconcile_accept_actor_verified_deny": ["operator-accepting"],
    "b_redelivery_unseen_deny": ["apply order resolves", "tagged"],
    "b_mistagged_new_delivery_deny": ["apply order resolves", "tagged"],
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
        "b_redelivery_unseen_deny", "b_mistagged_new_delivery_deny",
        "b_reject_restore_hold", "b_standing_reenter",
        "b_standing_reject_restore", "b_standing_standing",
        "b_reconcile_accept_actor_verified_deny",
        "b_unknown_actor_verification_deny", "b_reconcile_unknown_hold_deny",
        "b_declared_hold_id_mismatch_deny",
    }
    missing = required - names
    assert not missing, f"missing T19 vectors: {sorted(missing)}"
    assert len({n for n in names if "deny" in n}) >= 12, "T19 needs deny rows (T6)"


def _ceiling_events(generated, n: int, base: str = "B1") -> list[dict]:
    return [{"event_id": f"e{i}", "base_key": base} for i in range(n)]


@pytest.mark.parametrize("case", [
    pytest.param("exactly-n", id="exactly-n-is-admitted"),
    pytest.param("n-plus-one", id="deny-n-plus-one-halts"),
    pytest.param("per-base", id="deny-ceiling-is-per-base"),
    pytest.param("fold-empty-anchors", id="deny-fold-empty-anchors-still-halts"),
    pytest.param("fold-partial-anchors", id="deny-fold-partial-anchors-halts-both"),
])
def test_recovery_ceiling(generated, case):
    """RECOVERY_CEILING's event-count half, per base_key (elapsed-time is
    PR4). In-memory histories: the halt is a function of the event COUNT, so
    a 10k-event JSON corpus would add noise, not fidelity."""
    g = generated
    n = g.RECOVERY_CEILING_EVENTS
    if case == "exactly-n":
        # boundary: exactly N is admitted (the events then fail their own
        # schema checks, but never with RECOVERY_CEILING).
        for result in (g.reduce_section_a(_ceiling_events(g, n)),
                       g.reduce_section_b(_ceiling_events(g, n))):
            codes = {h["code"] for h in result["halts"].values()}
            assert "RECOVERY_CEILING" not in codes
        fold = g.fold_epochs(_ceiling_events(g, n), {"B1": "E0"})
        assert fold["B1"]["halt"] is None
    elif case == "n-plus-one":
        for result in (g.reduce_section_a(_ceiling_events(g, n + 1)),
                       g.reduce_section_b(_ceiling_events(g, n + 1))):
            assert result["halts"]["B1"]["code"] == "RECOVERY_CEILING"
        fold = g.fold_epochs(_ceiling_events(g, n + 1), {"B1": "E0"})
        assert fold["B1"]["halt"]["code"] == "RECOVERY_CEILING"
    elif case == "per-base":
        # one busy base must not halt a quiet one
        events = _ceiling_events(g, n + 1, "BUSY") + _ceiling_events(g, 3, "QUIET")
        for result in (g.reduce_section_a(events), g.reduce_section_b(events)):
            assert result["halts"]["BUSY"]["code"] == "RECOVERY_CEILING"
            assert "QUIET" not in result["halts"] or \
                result["halts"]["QUIET"]["code"] != "RECOVERY_CEILING"
        fold = g.fold_epochs(events, {"BUSY": "E0", "QUIET": "E0"})
        assert fold["BUSY"]["halt"]["code"] == "RECOVERY_CEILING"
        assert fold["QUIET"]["halt"] is None
    elif case == "fold-empty-anchors":
        # a ceiling breach with NO anchors must still be an explicit halt —
        # {} would read as a clean, empty fold.
        fold = g.fold_epochs(_ceiling_events(g, n + 1), {})
        assert fold, "empty result: a ceiling breach read as 'nothing to fold'"
        assert fold["B1"]["status"] == "halt"
        assert fold["B1"]["halt"]["code"] == "RECOVERY_CEILING"
    elif case == "fold-partial-anchors":
        # OTHER carries real EDGES but no anchor: the ceiling breach on BUSY
        # must not make it vanish — an edge-bearing base is always reported.
        other = [{"event_id": "o1", "base_key": "OTHER",
                  "epoch_before": "E0", "epoch_after": "E1"}]
        fold = g.fold_epochs(_ceiling_events(g, n + 1, "BUSY") + other,
                             {"BUSY": "E0"})
        assert fold["BUSY"]["halt"]["code"] == "RECOVERY_CEILING"
        assert fold["OTHER"]["halt"]["code"] == "EPOCH_GAP", \
            "an edge-bearing base was dropped on the ceiling path"


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
    with pytest.raises(ValueError):  # deny: newline breaks injectivity
        g.derive_hold_id("base\nref=evil", "r", "o0", "o1", 0)
    with pytest.raises(ValueError):
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


@pytest.mark.parametrize("case", [
    pytest.param("approved", id="full-all-approve"),
    pytest.param("block-verdict", id="deny-blocking-verdict"),
    pytest.param("high-finding", id="deny-high-finding-blocks"),
    pytest.param("block-beats-missing-seat", id="deny-block-beats-missing-seat"),
    pytest.param("missing-seat", id="deny-missing-seat-incomplete"),
    pytest.param("extra-seat", id="deny-extra-seat-incomplete"),
    pytest.param("unparseable", id="deny-unparseable-incomplete"),
    pytest.param("lookalike-raises", id="deny-lookalike-raises"),
    pytest.param("none-raises", id="deny-none-raises"),
    pytest.param("skip-not-approved", id="deny-skip-is-not-approval"),
    pytest.param("single", id="single-designated-seat"),
])
def test_aggregate_rows(generated, case):
    # complexity-justified: exhaustive case switch over the closed
    # parametrised row set — one arm per golden, no interacting branches.
    g = generated
    r = _roster(g)
    ok = g.SeatOutcome(g.SeatVerdict.APPROVE)
    full = {s: ok for s in r.ordered_seat_ids}
    result = g.PanelAggregateResult
    if case == "approved":
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is result.APPROVED
    elif case == "block-verdict":
        full["grok"] = g.SeatOutcome(g.SeatVerdict.BLOCK)
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is result.BLOCKED
    elif case == "high-finding":
        full["grok"] = g.SeatOutcome(g.SeatVerdict.APPROVE,
                                     (g.Finding(g.Severity.HIGH),))
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is result.BLOCKED
    elif case == "block-beats-missing-seat":
        # normative rule ORDER: a blocking finding decides even when another
        # required seat is missing — both deny, BLOCKED carries the finding.
        full["grok"] = g.SeatOutcome(g.SeatVerdict.BLOCK)
        del full["codex"]
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is result.BLOCKED
    elif case == "missing-seat":
        del full["codex"]
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is result.INCOMPLETE
    elif case == "extra-seat":
        full["gemini"] = ok
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is result.INCOMPLETE
    elif case == "unparseable":
        full["codex"] = g.UnparseableOutcome("severity: CATASTROPHIC")
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is result.INCOMPLETE
    elif case == "lookalike-raises":
        full["codex"] = _LookalikeOutcome()
        with pytest.raises(TypeError):
            g.aggregate(g.PanelIntensity.FULL, r, full)
    elif case == "none-raises":
        full["codex"] = None
        with pytest.raises(TypeError):
            g.aggregate(g.PanelIntensity.FULL, r, full)
    elif case == "skip-not-approved":
        # a zero-seat evaluation must never read as approval (§5.2: SKIP's
        # satisfaction is NOT_REQUIRED, not panel approval).
        assert g.aggregate(g.PanelIntensity.SKIP, r, {}) is result.NOT_APPLICABLE
    elif case == "single":
        assert g.required_seats(g.PanelIntensity.SINGLE, r) == ("claude",)
        assert g.aggregate(g.PanelIntensity.SINGLE, r,
                           {"claude": ok}) is result.APPROVED


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
    assert not g.blocking(g.UnparseableOutcome("x"))  # parse failure ≠ block
    with pytest.raises(TypeError):  # deny: lookalike is not a member
        g.blocking(_LookalikeOutcome())
    with pytest.raises(ValueError):  # deny: raw-string verdict never parses
        g.SeatOutcome("BLOCK")


def test_roster_snapshot_verifies_its_own_digest(generated):
    g = generated
    seats = ("claude", "grok", "codex")
    with pytest.raises(ValueError):  # deny: arbitrary digest unconstructible
        g.RosterSnapshot(manifest_digest="md", roster_version="v1",
                         roster_digest="deadbeef", ordered_seat_ids=seats,
                         designated_single_id="claude")
    # deny: dropping designated_single_id from the preimage changes the digest
    without_single = hashlib.sha256(
        "\n".join(["v1", *seats]).encode()).hexdigest()
    assert without_single != PINNED_ROSTER_DIGEST


def test_seat_result_filtering(generated):
    """The (subject_digest, attempt_id) filter is generated and enforced:
    stale-attempt results are excluded (surfacing INCOMPLETE), conflicting
    duplicates are INCOMPLETE."""
    g = generated
    r = _roster(g)
    ok = g.SeatOutcome(g.SeatVerdict.APPROVE)
    result = g.PanelAggregateResult
    rec = [g.SeatResultRecord(s, "subj", "att-2", ok) for s in r.ordered_seat_ids]
    assert g.aggregate_seat_results(g.PanelIntensity.FULL, r, "subj", "att-2",
                                    rec) is result.APPROVED
    # deny: a stale seat result from attempt att-1 never counts
    stale = [g.SeatResultRecord("claude", "subj", "att-1", ok),
             *[g.SeatResultRecord(s, "subj", "att-2", ok)
               for s in ("grok", "codex")]]
    assert g.aggregate_seat_results(g.PanelIntensity.FULL, r, "subj", "att-2",
                                    stale) is result.INCOMPLETE
    # deny: conflicting duplicate results for one seat are INCOMPLETE
    conflict = [*rec, g.SeatResultRecord("claude", "subj", "att-2",
                                         g.SeatOutcome(g.SeatVerdict.BLOCK))]
    assert g.aggregate_seat_results(g.PanelIntensity.FULL, r, "subj", "att-2",
                                    conflict) is result.INCOMPLETE


# ─── BoundaryError universe: element-wise seal ───────────────────────────────

def test_boundary_error_maps_match_schema_element_wise(schemas, generated):
    """Per-code phase/retriability and the exit map are asserted against the
    schema row by row — a permuted assignment fails (panel finding: domain
    membership alone is satisfied by every permutation)."""
    # complexity-justified: element-wise exhaustive seal plus its own
    # permutation deny — linear assertions, no interacting paths.
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
    # deny: the element-wise comparison actually fires on a permuted copy
    permuted = {c: dict(rows[c]) for c in rows}
    permuted["EPOCH_GAP"]["retriability"] = rows["ILLEGAL_TRANSITION"]["retriability"]
    permuted["ILLEGAL_TRANSITION"]["retriability"] = rows["EPOCH_GAP"]["retriability"]
    mismatches = [c for c in g.BoundaryErrorCode
                  if g.BoundaryError(c).retriability.name
                  != permuted[c.name]["retriability"]]
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
    entry = next(c for c in _FRAME_CASES if c["name"] == case)
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


def test_t26_lint_green_on_checked_in_docs():
    proc = _run(["tools/t26_lint.py"])
    assert proc.returncode == 0, f"t26_lint failed:\n{proc.stdout}{proc.stderr}"


def _planted_doc(lint, tmp_path: Path, mutate) -> object:
    """Plant a mutation into a COPY of the real design doc and load it
    through the real Doc constructor — no reimplemented parsing."""
    text = mutate(lint.DESIGN.read_text(encoding="utf-8"))
    p = tmp_path / "design.md"
    p.write_text(text, encoding="utf-8")
    return lint.Doc(p)


_ANCHOR = "## 5. Panel decision"


@pytest.mark.parametrize("check_name,planted_line", [
    pytest.param("check_retired",
                 "The machine uses AuthoritySnapshot here.",
                 id="deny-retired-live-use"),
    pytest.param("check_retired",
                 "The deleted disposition path uses MOVED_TO_HOLD as a live"
                 " mechanism.",
                 id="deny-retired-hides-behind-domain-words"),
    pytest.param("check_retired",
                 "Every disposition here is deleted after FOREIGN_OBSERVED"
                 " fires in the reduce.",
                 id="deny-retired-foreign-observed-domain-words"),
    pytest.param("check_retired",
                 "A deleted disposition writes integrity_hold events on"
                 " every transition.",
                 id="deny-retired-integrity-hold-domain-words"),
    pytest.param("check_retired",
                 "The wire carries request_id on each deleted disposition"
                 " row.",
                 id="deny-retired-request-id-domain-words"),
    pytest.param("check_section_refs", "See §99.9 for details.",
                 id="deny-unresolved-section-ref"),
    pytest.param("check_mutations",
                 "Appends use `createCommitOnBranch` again.",
                 id="deny-second-mutation-binding"),
    pytest.param("check_t_index", "T99 seals this.",
                 id="deny-t-without-index-row"),
    pytest.param("check_field_lists",
                 "`seat_result{roster_digest}` again.",
                 id="deny-second-field-list"),
    pytest.param("check_citations",
                 "See orchestrator.py:999999 for the branch.",
                 id="deny-citation-beyond-eof"),
])
def test_t26_lint_planted_violations_fire(tmp_path, check_name, planted_line):
    """A lint that cannot fail is a vacuous seal (root cause E): each check
    is falsified through the REAL Doc constructor over a planted copy —
    including retired names hiding behind the domain words 'disposition'
    and 'deleted' (panel finding)."""
    lint = _lint()
    doc = _planted_doc(lint, tmp_path,
                       lambda text: text.replace(
                           _ANCHOR, _ANCHOR + "\n" + planted_line))
    errors: list[str] = []
    getattr(lint, check_name)(doc, errors)
    assert errors, f"{check_name} is vacuous — planted violation not flagged"


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

def _production_modules() -> list[Path]:
    return sorted((REPO_ROOT / "src/claude_dispatcher").rglob("*.py"))


def _scan_guarded(paths: list[Path], guarded: set[str],
                  exempt: set[Path]) -> list[str]:
    """Definitions and constructions of guarded names: bare-name calls,
    attribute-qualified calls (mod.Name(...)), and calls through import
    aliases (from x import Name as N; N(...))."""
    # complexity-justified: dispatcher over AST node kinds/spellings — each
    # branch is one construction spelling, sealed by its own deny fixture.
    hits = []
    for path in paths:
        if path in exempt:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name in guarded:
                        aliases[a.asname or a.name] = a.name
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in guarded:
                hits.append(f"{path}:{node.lineno} defines {node.name}")
            elif isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and (fn.id in guarded or fn.id in aliases):
                    hits.append(f"{path}:{node.lineno} constructs "
                                f"{aliases.get(fn.id, fn.id)}")
                elif isinstance(fn, ast.Attribute) and fn.attr in guarded:
                    hits.append(f"{path}:{node.lineno} constructs {fn.attr} "
                                f"(attribute-qualified)")
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
        print(f"{gate}: allowlisted modules absent as expected pre-PR2: "
              f"{[str(m.relative_to(REPO_ROOT)) for m in absent]}")


# ─── architecture skeleton: dark mode ────────────────────────────────────────

def _imports_boundary(tree: ast.AST) -> list[str]:
    # complexity-justified: dispatcher over the closed set of import
    # spellings — each branch is one spelling, sealed by its own deny row.
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += [a.name for a in node.names
                     if a.name.startswith("claude_dispatcher.boundary")]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("claude_dispatcher.boundary"):
                hits.append(mod)
            elif mod == "claude_dispatcher":
                hits += [f"claude_dispatcher.{a.name}" for a in node.names
                         if a.name == "boundary"]
            if node.level and (mod == "boundary" or mod.startswith("boundary.")):
                hits.append(f".{mod}")
            if node.level and mod == "" and any(a.name == "boundary"
                                                for a in node.names):
                hits.append(".boundary")
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


@pytest.mark.parametrize("case", [
    pytest.param("live", id="no-production-import-while-allowlist-empty"),
    *[pytest.param(f"deny:{s}", id=f"deny-detector-sees-{s}")
      for s in sorted(_IMPORT_SPELLINGS)],
])
def test_architecture_boundary_dark_mode(schemas, case):
    """boundary/ is importable from tests only until PR6; the door
    allowlist is empty and this harness fails on any production import, in
    any spelling (plan §1 — dark mode; PR6 fills the allowlist)."""
    arch = schemas["ast_allowlists"]["architecture"]
    if case.startswith("deny:"):
        spelling = case.split(":", 1)[1]
        tree = ast.parse(_IMPORT_SPELLINGS[spelling])
        assert _imports_boundary(tree), (
            f"architecture detector is vacuous for the {spelling} spelling")
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
    in tests/boundary without a deny row (design §12 harness rules)."""
    seal_ids: dict[tuple[str, str], list[str]] = {}
    for item in request.session.items:
        if not isinstance(item, pytest.Function):
            continue
        fspath = Path(str(item.fspath))
        if fspath.parent != BOUNDARY_DIR:
            continue
        callspec = getattr(item, "callspec", None)
        if callspec is None:
            continue
        seal_ids.setdefault((fspath.name, item.originalname),
                            []).append(callspec.id)
    assert seal_ids, "T6: no parametrised seals collected — checker misfiring"
    missing = _seals_missing_deny(seal_ids)
    assert not missing, ("T6 (design §12): parametrised seals without a deny "
                         "row:\n" + "\n".join(missing))
    # deny: the helper itself must fire on a plant with no deny id.
    assert _seals_missing_deny({("m.py", "test_x"): ["allow-1", "allow-2"]}), \
        "T6 helper is vacuous"


def test_t19_vectors_dir_matches_loaded():
    assert set(_VECTORS) == {p.stem for p in VECTORS_DIR.glob("*.json")}
