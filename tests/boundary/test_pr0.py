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
  import-aliased constructions; dark-mode detector covering every import
  spelling; each with deny fixtures.
- T6: every parametrised seal carries a deny row — checked over the
  COLLECTED items' real param ids.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import warnings
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

# Parametrize decorators run at collection time, before fixtures exist, so
# the generated module is imported once here for the param lists. Tests
# still take the `generated` fixture for the assertions themselves.
sys.path.insert(0, str(REPO_ROOT / "src"))
from claude_dispatcher.boundary import generated as _GEN  # noqa: E402


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


def test_ast_gate_schema_lists_cannot_be_silently_emptied(schemas):
    """Both AST gates take their teeth from schema lists nothing asserted:
    emptying `guarded_names`, or adding a module to `door_entrypoints`,
    left them trivially green (panel round 3, finding 34)."""
    allow = schemas["ast_allowlists"]
    t8 = set(allow["t8_construction"]["guarded_names"])
    # the §3.1 closed sum and the §3.2 validated payload — the names the
    # design closes construction over.
    assert t8 == {"Classification", "ClassifyOutcome", "ClassifyOk",
                  "ClassifyAbsent", "ClassifyEmpty", "ClassifyFailed"}
    t9 = set(allow["t9_interpretation"]["guarded_names"])
    assert t9 == {"MergePlan", "Mergeable", "Unmergeable", "PanelPlan"}
    for gate in ("t8_construction", "t9_interpretation"):
        assert allow[gate]["allowed_modules"], f"{gate}: allowlist emptied"
    # dark mode: the door allowlist stays EMPTY until PR6 fills it
    assert allow["architecture"]["door_entrypoints"] == [], (
        "door_entrypoints is non-empty — dark mode ends at PR6, not before")
    assert allow["architecture"]["package"] == "claude_dispatcher.boundary"


@pytest.mark.parametrize("event_name", [
    # every row carries its own in-test deny (an out-of-domain value per
    # declared domain), so the id marks it as such for T6.
    pytest.param(n, id=f"deny-domain-{n}") for n in sorted(_GEN.SINGLE_EVENTS)
])
def test_every_single_event_constructs(generated, schemas, event_name):
    """8 of 14 §9 singles were never constructed while the docstring claimed
    all were sealed (panel round 3, finding 33). Every one is now built from
    its REQUIRED set, and every declared domain gets a deny."""
    g = generated
    cls = g.SINGLE_EVENTS[event_name]
    env = {"schema_major": 1, "schema_minor": 0, "event_id": "e1",
           "ts": "1970-01-01T00:00:00Z", "run_id": "r", "trace_id": "t",
           "protocol_epoch": "E0", "family": cls.FAMILY}
    typed = {"duration_ms": 1,
             "credential_mode": g.CredentialMode.SHARED,
             "protection_mode": g.ProtectionMode.PREVENT,
             "actor_verification": g.ActorVerification.VERIFIED_API,
             "hold_effect": g.HoldEffect.NONE}
    payload = {f: typed.get(f, f) for f in cls.REQUIRED if f not in env}
    for field, domain in cls.DOMAINS.items():
        payload[field] = domain[0]
    pairs = getattr(cls, "PAIR_RULES", {})
    for key, rule in pairs.items():
        allowed = rule["allowed"].get(payload.get(key))
        if allowed:
            payload[rule["field"]] = allowed[0]
    built = cls(**env, **payload)
    assert built.family == cls.FAMILY
    for field in cls.DOMAINS:
        with pytest.raises(ValueError):
            cls(**env, **dict(payload, **{field: "NOT_IN_DOMAIN"}))


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
    for attr in ("DOCS_DIR", "FRAMES_DIR"):
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
    env = dict(schema_major=1, schema_minor=0, event_id="e1",
               ts="1970-01-01T00:00:00Z", run_id="r", trace_id="tr",
               protocol_epoch="E0", family="authorization_granted")
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
    got = generated.reduce_section_a([prep, to_held, bad])
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
    env = dict(schema_major=1, schema_minor=0, event_id="e1",
               ts="1970-01-01T00:00:00Z", run_id="r", trace_id="t",
               protocol_epoch="E0", family="authorization_granted")
    build = lambda: ag(  # noqa: E731
        **env, authorization_id="a1", base_key="b", authority="fp",
        kind=kind, assurance=assurance, evidence_ref="ev", actor="dispatcher")
    if ok:
        assert build().assurance == assurance
    else:
        with pytest.raises(ValueError):
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
])
def test_singles_closed_domains_reject_unknown_values(schemas, generated,
                                                      event, field, bad):
    """§9: an unknown VALUE of a known enum field halts identically to an
    unknown variant — asserted for every gate-decision field the design
    closes (panel round 2, finding 12)."""
    spec = schemas["lifecycle_fsm"]["events"]["singles"][event]
    cls = generated.SINGLE_EVENTS[event]
    assert f"{field}_domain" in spec, f"{event}.{field} has no declared domain"
    env = dict(schema_major=1, schema_minor=0, event_id="e1",
               ts="1970-01-01T00:00:00Z", run_id="r", trace_id="t",
               protocol_epoch="E0", family=event)
    payload = {f: f for f in spec["required"]}
    for dom_key, members in spec.items():
        if dom_key.endswith("_domain"):
            payload[dom_key[:-len("_domain")]] = members[0]
    if event == "authorization_granted":
        payload["assurance"] = "NOT_APPLICABLE"
    payload[field] = bad
    with pytest.raises(ValueError):
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

def _envelope_kwargs():
    return dict(schema_major=1, schema_minor=0, event_id="e1",
                ts="1970-01-01T00:00:00Z", run_id="run-1",
                trace_id="trace-1", protocol_epoch="E0")


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
    ev = {"schema_major": 1, "schema_minor": 0, "event_id": eid,
          "ts": "1970-01-01T00:00:00Z", "run_id": "run-1",
          "trace_id": "trace-1", "protocol_epoch": "E0",
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
    pytest.param("no-actor-node-id", id="deny-verified-api-without-identity"),
    pytest.param("valid", id="actor-verified-valid-evidence"),
])
def test_actor_verified_auto_evidence_guards(generated, case):
    """The auto-release path's constructor guards, exercised through the
    REAL constructor (panel round 3: only the SHARED arm had a deny)."""
    g = generated
    over = {"mode": g.CredentialMode.SEPARATED}
    if case == "display-only":
        over["actor_verification"] = g.ActorVerification.DISPLAY_ONLY
    elif case == "non-auto-disposition":
        over["disposition"] = g.ReconcileDisposition.ACCEPT_OURS
    elif case == "no-actor-node-id":
        over["actor_node_id"] = None
    if case == "valid":
        ev = _mk_hold(g, "ActorVerifiedAuto", **over)
        assert ev.disposition is g.ReconcileDisposition.ACTOR_VERIFIED_AUTO
        assert ev.actor_verification is g.ActorVerification.VERIFIED_API
        return
    with pytest.raises(ValueError):
        _mk_hold(g, "ActorVerifiedAuto", **over)


def test_actor_verified_fixed_values_match_the_schema(schemas, generated):
    """Emptying the schema's `fixed:` must be red, not silently permissive."""
    variants = schemas["lifecycle_fsm"]["events"]["unions"]["hold_lifecycle"]["variants"]
    spec = next(v for v in variants if v["name"] == "ActorVerifiedAuto")
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
        with pytest.raises(ValueError):
            _mk_hold(g, "ObserveDelta", **over)


def test_credential_mode_is_run_context_not_event_payload(generated):
    """The authoritative gate is the RUN's mode: the same event stream that
    auto-releases under a SEPARATED run must NOT under a SHARED one, and an
    absent context defaults closed (§0.3: never a soft SEPARATED)."""
    g = generated
    vec = _VECTORS["b_actor_verified_auto_separated"]
    released = g.reduce_section_b(vec["events"], g.CredentialMode.SEPARATED)
    assert not released["halts"]
    assert {d["state"] for h in released["holds"].values()
            for d in h.values()} == {"RELEASED"}
    for mode in (g.CredentialMode.SHARED, None):
        got = g.reduce_section_b(vec["events"], mode)
        assert got["halts"], f"mode={mode}: auto-release was not refused"
        # TWO independent layers refuse it, and the seal names which:
        #   (1) the event's self-declared mode disagrees with the run;
        #   (2) the run-mode gate on the auto-release path itself.
        # Both are load-bearing — removing either leaves the other
        # refusing (verified by the round-3 falsification probes).
        detail = " ".join(h["detail"] for h in got["halts"].values())
        assert ("credential mode is run context" in detail
                or "under SHARED, never" in detail), detail


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
        with pytest.raises(generated.IllegalTransitionError):
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
        with pytest.raises(generated.IllegalTransitionError):
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
    with pytest.raises(generated.IllegalTransitionError) as exc:
        generated.apply_section_b(st, ev)
    assert exc.value.error.code is generated.BoundaryErrorCode.ILLEGAL_TRANSITION


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
                "halts": {b: {"code": h["code"]} for b, h in got["halts"].items()},
                "resolution_notes": {b: len(n)
                                     for b, n in got["resolution_notes"].items()}}
    return {base: {"status": entry["status"], "epoch": entry["epoch"],
                   "halt": _project_halt(entry["halt"])}
            for base, entry in got.items()}


def _reduce(generated, vec: dict) -> dict:
    if vec["machine"] == "section_a":
        return generated.reduce_section_a(vec["events"])
    if vec["machine"] == "section_b":
        # credential_mode is RUN context (protocol_genesis), supplied by the
        # caller — never read from the events.
        mode = generated.CredentialMode[vec["credential_mode"]]
        return generated.reduce_section_b(vec["events"], mode)
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
    "epoch_missing_base_key_deny": ["missing base_key"],
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


def _ceiling_events(generated, n: int, base: str = "B1") -> list[dict]:
    """Minimally SCHEMA-VALID events (the fold now runs the same §9 checks
    as the reducers, so a bare dict would halt as a schema violation and
    mask what the ceiling tests are actually asserting)."""
    return [{"event_id": f"{base}-e{i}", "base_key": base, "schema_major": 1,
             "schema_minor": 0, "family": "effect_lifecycle"}
            for i in range(n)]


def test_ceiling_exactly_n_is_admitted(generated):
    """Boundary: exactly N events is admitted (they then fail their own
    schema checks, but never with RECOVERY_CEILING)."""
    g, n = generated, generated.RECOVERY_CEILING_EVENTS
    for result in (g.reduce_section_a(_ceiling_events(g, n)),
                   g.reduce_section_b(_ceiling_events(g, n))):
        assert "RECOVERY_CEILING" not in {h["code"] for h in result["halts"].values()}
    assert g.fold_epochs(_ceiling_events(g, n), {"B1": "E0"})["B1"]["halt"] is None


def test_ceiling_n_plus_one_halts(generated):
    """deny: one event past the ceiling halts all three consumers."""
    g, n = generated, generated.RECOVERY_CEILING_EVENTS
    for result in (g.reduce_section_a(_ceiling_events(g, n + 1)),
                   g.reduce_section_b(_ceiling_events(g, n + 1))):
        assert result["halts"]["B1"]["code"] == "RECOVERY_CEILING"
    fold = g.fold_epochs(_ceiling_events(g, n + 1), {"B1": "E0"})
    assert fold["B1"]["halt"]["code"] == "RECOVERY_CEILING"


def test_ceiling_is_counted_per_base(generated):
    """deny: one busy base must never halt a quiet one."""
    g, n = generated, generated.RECOVERY_CEILING_EVENTS
    events = _ceiling_events(g, n + 1, "BUSY") + _ceiling_events(g, 3, "QUIET")
    for result in (g.reduce_section_a(events), g.reduce_section_b(events)):
        assert result["halts"]["BUSY"]["code"] == "RECOVERY_CEILING"
        assert result["halts"].get("QUIET", {}).get("code") != "RECOVERY_CEILING"
    fold = g.fold_epochs(events, {"BUSY": "E0", "QUIET": "E0"})
    assert fold["BUSY"]["halt"]["code"] == "RECOVERY_CEILING"
    assert fold["QUIET"]["halt"] is None


def test_ceiling_with_empty_anchors_still_halts(generated):
    """deny: a ceiling breach with NO anchors must be an explicit halt — {}
    would read as a clean, empty fold."""
    g = generated
    fold = g.fold_epochs(_ceiling_events(g, g.RECOVERY_CEILING_EVENTS + 1), {})
    assert fold, "empty result: a ceiling breach read as 'nothing to fold'"
    assert fold["B1"]["status"] == "halt"
    assert fold["B1"]["halt"]["code"] == "RECOVERY_CEILING"


def test_ceiling_with_partial_anchors_keeps_edge_bearing_bases(generated):
    """deny: an edge-bearing base must not vanish on the ceiling path."""
    g, n = generated, generated.RECOVERY_CEILING_EVENTS
    other = [{"event_id": "o1", "base_key": "OTHER", "schema_major": 1,
              "schema_minor": 0, "family": "effect_lifecycle",
              "epoch_before": "E0", "epoch_after": "E1"}]
    fold = g.fold_epochs(_ceiling_events(g, n + 1, "BUSY") + other,
                         {"BUSY": "E0"})
    assert fold["BUSY"]["halt"]["code"] == "RECOVERY_CEILING"
    assert fold["OTHER"]["halt"]["code"] == "EPOCH_GAP"


def test_ceiling_counts_deduplicated_events(generated):
    """The ceiling bounds recovered HISTORY, not wire traffic: N+1 COPIES of
    one event must not trip an OPERATOR halt, while N+1 DISTINCT events
    must (panel round 3 — at-least-once redelivery is exactly what the
    protocol absorbs)."""
    g, n = generated, generated.RECOVERY_CEILING_EVENTS
    one = {"event_id": "same", "base_key": "B1", "schema_major": 1,
           "schema_minor": 0, "family": "effect_lifecycle"}
    copies = [dict(one) for _ in range(n + 1)]
    assert "RECOVERY_CEILING" not in {
        h["code"] for h in g.reduce_section_a(copies)["halts"].values()}
    distinct = _ceiling_events(g, n + 1)
    assert g.reduce_section_a(distinct)["halts"]["B1"]["code"] == "RECOVERY_CEILING"


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
        with pytest.raises(TypeError):
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
    with pytest.raises(TypeError):
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
    assert not g.blocking(g.UnparseableOutcome("x"))  # parse failure ≠ block
    with pytest.raises(TypeError):  # deny: lookalike is not a member
        g.blocking(_LookalikeOutcome())
    with pytest.raises(ValueError):  # deny: raw-string verdict never parses
        g.SeatOutcome("BLOCK")


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
    with pytest.raises((AttributeError, TypeError)):   # deny: frozen
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


def test_subject_digest_and_classifier_authority(generated):
    """subject_digest()/target_pr()/target_ref()/ClassifierAuthority had zero
    tests (panel round 3, finding 16). Pinned against independently computed
    SHA-256s over §9's canonical preimage."""
    g = generated
    req = g.RequiredClassifier(config_sha256="cfg", producer_digest="prod",
                               contract="2")
    assert req.line() == "classifier=required:cfg:prod:2".split("=", 1)[1]
    assert g.LegacyNoClassifier().line() == "legacy"
    assert g.target_pr("PR_1", "refs/heads/main") == "pr:PR_1:refs/heads/main"
    assert g.target_ref("refs/heads/main") == "ref:refs/heads/main"
    want_pr = hashlib.sha256("\n".join([
        "repo=R_1", "target=pr:PR_1:refs/heads/main", "base=b0", "head=h0",
        "diff=d0", "classifier=required:cfg:prod:2", "unit=none"]).encode()
    ).hexdigest()
    assert g.subject_digest(
        repo_node_id="R_1", target=g.target_pr("PR_1", "refs/heads/main"),
        base_oid="b0", head_oid="h0", diff_sha256="d0", classifier=req) == want_pr
    want_ref_unit = hashlib.sha256("\n".join([
        "repo=R_1", "target=ref:refs/heads/main", "base=b0", "head=h0",
        "diff=d0", "classifier=legacy", "unit=u1"]).encode()).hexdigest()
    assert g.subject_digest(
        repo_node_id="R_1", target=g.target_ref("refs/heads/main"),
        base_oid="b0", head_oid="h0", diff_sha256="d0",
        classifier=g.LegacyNoClassifier(), unit_digest="u1") == want_ref_unit
    # a retarget of the same PR at the same OIDs changes the digest (§9)
    assert g.subject_digest(
        repo_node_id="R_1", target=g.target_pr("PR_1", "refs/heads/release"),
        base_oid="b0", head_oid="h0", diff_sha256="d0",
        classifier=req) != want_pr
    with pytest.raises(ValueError):        # deny: not a ClassifierAuthority
        g.subject_digest(repo_node_id="R", target="ref:x", base_oid="b",
                         head_oid="h", diff_sha256="d", classifier="required:x")
    with pytest.raises(ValueError):        # deny: newline breaks injectivity
        g.subject_digest(repo_node_id="R\nrepo=evil", target="ref:x",
                         base_oid="b", head_oid="h", diff_sha256="d",
                         classifier=req)
    with pytest.raises(ValueError):        # deny: fingerprint needs the union
        g.AuthorityFingerprint(protocol_epoch="E0", base_epoch="E0",
                               subject_digest="s", roster_digest="r",
                               classifier="not-a-variant")
    assert g.AuthorityFingerprint(protocol_epoch="E0", base_epoch="E0",
                                  subject_digest="s", roster_digest="r",
                                  classifier=req).classifier is req


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
    # §5.1 semantics: the aggregate's declared rule ORDER is what runs
    order = [next(iter(rule)) for rule in schemas["panel_aggregate"]["aggregate"]["rules"]]
    assert order[0] == "required_seats_empty"
    assert order[1] == "any_required_seat_outcome_blocking"
    r = _roster(g)
    assert g.aggregate(g.PanelIntensity.SKIP, r, {}) is \
        g.PanelAggregateResult.NOT_APPLICABLE          # rule 1 wins
    blocking_and_missing = {"claude": g.SeatOutcome(g.SeatVerdict.BLOCK)}
    assert g.aggregate(g.PanelIntensity.FULL, r, blocking_and_missing) is \
        g.PanelAggregateResult.BLOCKED                 # rule 2 beats rule 3


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
    peer checkout is not reddened by a gate documented as peer-optional."""
    lint = _lint()
    args = ["tools/t26_lint.py"] if lint.peer_available() \
        else ["tools/t26_lint.py", "--no-citations"]
    proc = _run(args)
    assert proc.returncode == 0, f"t26_lint failed:\n{proc.stdout}{proc.stderr}"


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
                 "retired-name: line 152 (§5): `AuthoritySnapshot`",
                 id="deny-retired-live-use"),
    pytest.param("check_retired",
                 "The deleted disposition path uses MOVED_TO_HOLD as a live"
                 " mechanism.",
                 "retired-name: line 152 (§5): `MOVED_TO_HOLD`",
                 id="deny-retired-hides-behind-domain-words"),
    pytest.param("check_retired",
                 "Every disposition here is deleted after FOREIGN_OBSERVED"
                 " fires in the reduce.",
                 "retired-name: line 152 (§5): `FOREIGN_OBSERVED`",
                 id="deny-retired-foreign-observed-domain-words"),
    pytest.param("check_retired",
                 "A deleted disposition writes integrity_hold events on"
                 " every transition.",
                 "retired-name: line 152 (§5): `integrity_hold`",
                 id="deny-retired-integrity-hold-domain-words"),
    pytest.param("check_retired",
                 "The wire carries request_id on each deleted disposition"
                 " row.",
                 "retired-name: line 152 (§5): `request_id`",
                 id="deny-retired-request-id-domain-words"),
    pytest.param("check_section_refs", "See §99.9 for details.",
                 "§-ref: line 152: §99.9 unresolved",
                 id="deny-unresolved-section-ref"),
    pytest.param("check_mutations",
                 "Appends use `createCommitOnBranch` again.",
                 "mutation-once: `createCommitOnBranch` bound 2 times",
                 id="deny-second-mutation-binding"),
    pytest.param("check_t_index", "T99 seals this.",
                 "T-index: T99 (cited at line 152) has 0 §10 rows",
                 id="deny-t-without-index-row"),
    pytest.param("check_field_lists",
                 "`seat_result{roster_digest}` again.",
                 "field-list-once: `seat_result{...}` appears 2 times",
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
    the plant being caught (panel round 2, finding 39)."""
    lint = _lint()
    doc = _planted_doc(lint, tmp_path,
                       lambda text: text.replace(
                           _ANCHOR, _ANCHOR + "\n" + planted_line))
    errors: list[str] = []
    getattr(lint, check_name)(doc, errors)
    assert errors, f"{check_name} is vacuous — planted violation not flagged"
    assert any(expect in e for e in errors), (
        f"{check_name} fired, but not for the planted violation.\n"
        f"expected a message containing: {expect!r}\ngot: {errors}")
    # the clean doc must NOT produce this violation — proving the plant, and
    # not the document itself, is what the check reacted to.
    clean: list[str] = []
    getattr(lint, check_name)(lint.Doc(lint.DESIGN), clean)
    assert not any(expect in e for e in clean), (
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

def _production_modules() -> list[Path]:
    return sorted((REPO_ROOT / "src/claude_dispatcher").rglob("*.py"))


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

def _plain_import_hits(node: ast.Import) -> list[str]:
    return [a.name for a in node.names
            if a.name.startswith("claude_dispatcher.boundary")]


def _from_import_hits(node: ast.ImportFrom) -> list[str]:
    mod = node.module or ""
    names = {a.name for a in node.names}
    if mod.startswith("claude_dispatcher.boundary"):
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
        # design §12 states the rule over tests/boundary AS A WHOLE — a seal
        # placed in a subpackage must not escape it (panel round 2).
        if BOUNDARY_DIR not in fspath.parents:
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
