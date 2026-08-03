"""PR0 seals — generated truth + CI gates (implementation plan §2 PR0).

Every seal here exists to make a specific drift class a red build:

- fsmgen --check: hand edits to generated files, or schema/doc divergence
  (the comparison against the design's inline tables runs inside fsmgen).
- enum exhaustiveness: a YAML state/event that never reached the dispatch.
- T19 goldens: reducer semantics changing under a frozen history.
- t26_lint: the design doc's own lint, wired as CI.
- T8/T9 fail-closed: guarded names defined/constructed outside the (still
  absent) allowlisted modules — the gate is live from PR0 (grok B3).
- architecture skeleton: any production import of claude_dispatcher.boundary
  while the door-entrypoint allowlist is empty (dark mode, grok M1/M15).
- T6: every parametrised module in tests/boundary carries a deny row.
"""

from __future__ import annotations

import ast
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_DIR = REPO_ROOT / "schema"
VECTORS_DIR = REPO_ROOT / "tests/boundary/vectors/t19"
BOUNDARY_DIR = REPO_ROOT / "tests/boundary"
FRAMES_DIR = REPO_ROOT / "schema/testdata/classifier_frames"


def load_vectors() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(VECTORS_DIR.glob("*.json"))}


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=REPO_ROOT,
                          capture_output=True, text=True)


# ─── fsmgen: committed and diff-clean ────────────────────────────────────────

def test_fsmgen_output_committed_and_diff_clean():
    """Regeneration is byte-identical to what is committed; fsmgen also
    fails here if the schema and the design doc's inline tables diverge."""
    proc = _run(["tools/fsmgen.py", "--check"])
    assert proc.returncode == 0, (
        f"fsmgen --check failed:\n{proc.stdout}{proc.stderr}")


def test_generated_paths_git_clean():
    proc = subprocess.run(
        ["git", "diff", "--exit-code", "--stat", "--",
         "src/claude_dispatcher/boundary/generated", "docs/generated",
         "tests/boundary/vectors", "schema/testdata"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, f"generated paths dirty:\n{proc.stdout}"


# ─── FSM enum/dispatch exhaustiveness ────────────────────────────────────────

def test_section_a_states_and_events_exhaustive(schemas, generated):
    fsm = schemas["lifecycle_fsm"]["section_a"]
    want_states = {fsm["initial_pseudo_state"], *fsm["states"]}
    assert {s.name for s in generated.SectionAState} == want_states
    assert set(generated.SECTION_A_EVENTS) == set(fsm["events"])
    # every event in the alphabet appears as some variant's trigger — an
    # event with no dispatch entry is unreachable truth.
    triggers = {cls.TRIGGER for cls in generated.EFFECT_VARIANTS.values()}
    assert triggers == set(fsm["events"])
    # every non-ILLEGAL row is represented by at least one variant.
    rows_with_variants = {cls.ROW for cls in generated.EFFECT_VARIANTS.values()}
    for row in fsm["rows"]:
        if row["to"] in ("ILLEGAL", "terminal", "unchanged"):
            continue
        assert row["id"] in rows_with_variants, f"row {row['id']} has no variant"


def test_section_b_states_and_events_exhaustive(schemas, generated):
    fsm = schemas["lifecycle_fsm"]["section_b"]
    want_states = {fsm["initial_pseudo_state"], *fsm["states"]}
    assert {s.name for s in generated.SectionBState} == want_states
    assert set(generated.SECTION_B_EVENTS) == set(fsm["events"])
    triggers = {cls.TRIGGER for cls in generated.HOLD_VARIANTS.values()}
    assert triggers == set(fsm["events"])
    rows_with_variants = {cls.ROW for cls in generated.HOLD_VARIANTS.values()}
    for row in fsm["rows"]:
        if row["to"] in ("ILLEGAL", "terminal", "as_held_foreign_rows"):
            continue
        assert row["id"] in rows_with_variants, f"row {row['id']} has no variant"


def test_durability_partition_is_exclusive_and_total(schemas, generated):
    dur = schemas["lifecycle_fsm"]["section_a"]["durability"]
    parts = [set(dur["durable_state_branch"]), set(dur["memory_only"]),
             set(dur["hold_branch"])]
    union = set().union(*parts)
    assert union == set(schemas["lifecycle_fsm"]["section_a"]["states"])
    assert sum(len(p) for p in parts) == len(union), "partition overlaps"
    assert set(generated.PROJECTION_DURABLE_STATES) == \
        {"GENESIS"} | parts[0] | parts[2]


def test_reconcile_disposition_algebra(schemas, generated):
    disp = schemas["lifecycle_fsm"]["reconcile_dispositions"]
    assert {d.name for d in generated.ReconcileDisposition} == \
        {m["name"] for m in disp["members"]}
    assert {d.name for d in generated.ACCEPTING_DISPOSITIONS} == set(disp["accepting"])
    assert {d.name for d in generated.SECTION_B_ONLY_DISPOSITIONS} == \
        {m["name"] for m in disp["members"] if m.get("section_b_only")}


# ─── illegal pairs raise typed errors (deny rows) ────────────────────────────

def _mk_effect(generated, variant: str, **over):
    cls = generated.EFFECT_VARIANTS[variant]
    kwargs = dict(movement_id="m", base_key="b", authority="a",
                  epoch_before="E0", epoch_after="E0", hold_effect="NONE",
                  actor_context="ctx", credential_mode="SHARED")
    for f in ("authorization_id", "new_oid"):
        if f in cls.REQUIRED:
            kwargs[f] = f
    if "disposition" in cls.REQUIRED:
        kwargs["disposition"] = generated.ReconcileDisposition.ACCEPT_FOREIGN_ADVANCED
    kwargs.update(over)
    return cls(**kwargs)


@pytest.mark.parametrize("state,variant", [
    pytest.param("EXPLAINED", "Submit", id="deny-terminal-explained-submit"),
    pytest.param("RECONCILED", "Prepare", id="deny-terminal-reconciled-prepare"),
    pytest.param("HELD", "Submit", id="deny-held-submit"),
    pytest.param("GENESIS", "Explained", id="deny-genesis-explained"),
    pytest.param("PREPARED", "Prepare", id="deny-double-prepare"),
])
def test_section_a_illegal_pairs_raise(generated, state, variant):
    cls = generated.EFFECT_VARIANTS[variant]
    ev = _mk_effect(generated, variant, from_state=cls.FROM_STATES[0])
    st = generated.MachineStateA(generated.SectionAState[state])
    with pytest.raises(generated.IllegalTransitionError) as exc:
        generated.apply_section_a(st, ev)
    assert exc.value.error.code is generated.BoundaryErrorCode.ILLEGAL_TRANSITION


@pytest.mark.parametrize("legal", [
    pytest.param(("GENESIS", "Prepare", "PREPARED"), id="genesis-prepare"),
    pytest.param(("PREPARED", "Submit", "SUBMITTED"), id="prepared-submit"),
    pytest.param(("SUBMITTED", "ObserveReject", "REJECTED_NO_EFFECT"),
                 id="submitted-reject"),
    pytest.param(("EFFECT_OBSERVED", "Explained", "EXPLAINED"), id="explained"),
])
def test_section_a_legal_pairs_apply(generated, legal):
    state, variant, want = legal
    ev = _mk_effect(generated, variant, from_state=state)
    got = generated.apply_section_a(
        generated.MachineStateA(generated.SectionAState[state]), ev)
    assert got.name.value == want


def test_section_b_shared_actor_verified_denied(generated):
    """Under SHARED, never — §6.0's mode split is a typed error, not a
    quiet downgrade (deny row for the ACTOR_VERIFIED_AUTO path)."""
    ev = generated.HOLD_VARIANTS["ActorVerifiedAuto"](
        hold_id="H", base_key="b", epoch_before="E0", epoch_after="E0",
        ref="refs/heads/main", mode="SHARED", actor_verification="VERIFIED_API",
        actor_display="x", actor_node_id="N", matched_subject_digest="s",
        disposition=generated.ReconcileDisposition.ACTOR_VERIFIED_AUTO,
        from_state="HELD_FOREIGN")
    st = generated.MachineStateB(generated.SectionBState.HELD_FOREIGN)
    with pytest.raises(generated.IllegalTransitionError):
        generated.apply_section_b(st, ev)


# ─── T19 goldens re-reduce to themselves ─────────────────────────────────────

_VECTORS = load_vectors()


@pytest.mark.parametrize("name", [
    pytest.param(n, id=("deny-" + n) if ("deny" in n) else n)
    for n in sorted(_VECTORS)
])
def test_t19_goldens_re_reduce(generated, name):
    vec = _VECTORS[name]
    if vec["machine"] == "section_a":
        got = generated.reduce_section_a(vec["events"])
    elif vec["machine"] == "section_b":
        got = generated.reduce_section_b(vec["events"])
    else:
        got = generated.fold_epochs(vec["events"], vec["anchors"])
    # normalize through JSON: goldens are the frozen JSON form.
    assert json.loads(json.dumps(got)) == vec["expected"]


def test_t19_vector_inventory():
    """The §6.0/§12 named histories all exist (incl. every held origin,
    all four dual-append crash points, the seven epoch histories and the
    redelivery golden)."""
    names = set(_VECTORS)
    required = {
        "success", "reject", "timeout",
        "held_from_prepared_crash", "held_from_prepared_later",
        "held_from_prepared_move", "held_from_submitted_mismatch",
        "held_from_submitted_crash", "held_from_submitted_later",
        "held_from_unknown_later", "held_from_unknown_crash",
        "crash_p1_before_hold_append", "crash_p2_between_appends",
        "crash_p3_after_both_appends", "crash_p4_redelivered_duplicate",
        "dual_append_divergent_payload_deny",
        "epoch_empty", "epoch_prepare_only", "epoch_no_effect_reject",
        "epoch_cross_stream", "epoch_gap", "epoch_fork", "epoch_cycle",
        "b_redelivery_after_released",
    }
    missing = required - names
    assert not missing, f"missing T19 vectors: {sorted(missing)}"
    deny = {n for n in names if "deny" in n}
    assert len(deny) >= 4, "T19 needs deny rows (T6)"


# ─── panel aggregate semantics ───────────────────────────────────────────────

def _roster(generated):
    seats = ("claude", "grok", "codex")
    return generated.RosterSnapshot(
        manifest_digest="md", roster_version="v1",
        roster_digest=generated.roster_digest("v1", seats, "claude"),
        ordered_seat_ids=seats, designated_single_id="claude")


@pytest.mark.parametrize("case", [
    pytest.param("approved", id="full-all-approve"),
    pytest.param("block-verdict", id="deny-blocking-verdict"),
    pytest.param("high-finding", id="deny-high-finding-blocks"),
    pytest.param("missing-seat", id="deny-missing-seat-incomplete"),
    pytest.param("extra-seat", id="deny-extra-seat-incomplete"),
    pytest.param("unparseable", id="deny-unparseable-incomplete"),
    pytest.param("single", id="single-designated-seat"),
])
def test_aggregate_rows(generated, case):
    g = generated
    r = _roster(g)
    ok = g.SeatOutcome(g.SeatVerdict.APPROVE)
    full = {s: ok for s in r.ordered_seat_ids}
    if case == "approved":
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is \
            g.PanelAggregateResult.APPROVED
    elif case == "block-verdict":
        full["grok"] = g.SeatOutcome(g.SeatVerdict.BLOCK)
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is \
            g.PanelAggregateResult.BLOCKED
    elif case == "high-finding":
        full["grok"] = g.SeatOutcome(g.SeatVerdict.APPROVE,
                                     (g.Finding(g.Severity.HIGH),))
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is \
            g.PanelAggregateResult.BLOCKED
    elif case == "missing-seat":
        del full["codex"]
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is \
            g.PanelAggregateResult.INCOMPLETE
    elif case == "extra-seat":
        full["gemini"] = ok
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is \
            g.PanelAggregateResult.INCOMPLETE
    elif case == "unparseable":
        full["codex"] = g.UnparseableOutcome("severity: CATASTROPHIC")
        assert g.aggregate(g.PanelIntensity.FULL, r, full) is \
            g.PanelAggregateResult.INCOMPLETE
    elif case == "single":
        assert g.required_seats(g.PanelIntensity.SINGLE, r) == ("claude",)
        assert g.aggregate(g.PanelIntensity.SINGLE, r, {"claude": ok}) is \
            g.PanelAggregateResult.APPROVED


def test_required_seats_full_is_whole_roster(generated):
    r = _roster(generated)
    assert generated.required_seats(generated.PanelIntensity.FULL, r) == \
        r.ordered_seat_ids
    assert generated.required_seats(generated.PanelIntensity.SKIP, r) == ()


def test_blocking_predicate_closed_domain(generated):
    g = generated
    assert g.blocking(g.SeatOutcome(g.SeatVerdict.BLOCK))
    assert g.blocking(g.SeatOutcome(g.SeatVerdict.APPROVE,
                                    (g.Finding(g.Severity.CRITICAL),)))
    assert not g.blocking(g.SeatOutcome(g.SeatVerdict.APPROVE,
                                        (g.Finding(g.Severity.MEDIUM),)))
    assert not g.blocking(g.UnparseableOutcome("x"))  # parse failure ≠ block


# ─── BoundaryError universe ──────────────────────────────────────────────────

def test_boundary_error_maps_exhaustive(schemas, generated):
    g = generated
    want = {c["code"] for c in schemas["boundary_errors"]["codes"]}
    got = {c.name for c in g.BoundaryErrorCode}
    assert got == want
    for code in g.BoundaryErrorCode:
        err = g.BoundaryError(code)
        assert err.phase in set(g.ErrorPhase)
        assert err.retriability in set(g.Retriability)
        assert err.operator_action
        assert err.metric == f"boundary_error_{code.value.lower()}_total"
        assert err.exit_code in (2, 3, 4)
    assert {p.name for p in g.ErrorPhase} == set(schemas["boundary_errors"]["phases"])
    assert g.CLI_EXIT_OK == 0


# ─── classifier frame vectors ────────────────────────────────────────────────

def _parse_frame(blob: bytes, bounds: dict) -> tuple[bytes, bytes]:
    """Reference parser for the §8 octet frame — mirrors the reject rules
    the schema states (truncated lengths, trailing bytes, bound overflow)."""
    if len(blob) < 4:
        raise ValueError("truncated outer_len")
    (outer_len,) = struct.unpack(">I", blob[:4])
    body = blob[4:]
    if len(body) != outer_len:
        raise ValueError("outer_len mismatch (truncation or trailing data)")
    if body[0] != 1:
        raise ValueError("unknown frame version")
    off = 1
    (policy_len,) = struct.unpack(">Q", body[off:off + 8]); off += 8
    if policy_len > bounds["policy_max_bytes"] or policy_len > len(body) - off:
        raise ValueError("policy_len exceeds bounds/frame")
    policy = body[off:off + policy_len]; off += policy_len
    (diff_len,) = struct.unpack(">Q", body[off:off + 8]); off += 8
    if diff_len > bounds["diff_max_bytes"] or diff_len > len(body) - off:
        raise ValueError("diff_len exceeds bounds/frame")
    diff = body[off:off + diff_len]; off += diff_len
    if off != len(body):
        raise ValueError("trailing bytes inside frame")
    return policy, diff


@pytest.mark.parametrize("case", [
    pytest.param("valid_frame", id="valid-frame"),
    pytest.param("malformed_length", id="deny-malformed-length"),
    pytest.param("truncation", id="deny-truncation"),
    pytest.param("trailing_data", id="deny-trailing-data"),
])
def test_classifier_frame_vectors(schemas, case):
    proto = schemas["classifier_protocol"]
    index = json.loads((FRAMES_DIR / "vectors.json").read_text())
    entry = next(c for c in index["cases"] if c["name"] == case)
    blob = (FRAMES_DIR / entry["file"]).read_bytes()
    assert hashlib.sha256(blob).hexdigest() == entry["sha256"]
    if entry["expect"] == "accept":
        policy, diff = _parse_frame(blob, proto["bounds"])
        assert policy.decode() == proto["vectors"]["policy_payload"]
        assert diff.decode() == proto["vectors"]["diff_payload"]
    else:
        with pytest.raises(ValueError):
            _parse_frame(blob, proto["bounds"])


# ─── t26 lint as CI ──────────────────────────────────────────────────────────

def test_t26_lint_green_on_checked_in_docs():
    proc = _run(["tools/t26_lint.py"])
    assert proc.returncode == 0, f"t26_lint failed:\n{proc.stdout}{proc.stderr}"


def test_t26_lint_catches_planted_violations(tmp_path):
    """Deny rows for the lint itself: each check must actually fire (a lint
    that cannot fail is a vacuous seal — root cause E)."""
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import t26_lint as lint
    finally:
        sys.path.pop(0)
    base = lint.DESIGN.read_text(encoding="utf-8")

    def violations(text: str, check) -> list[str]:
        doc = lint.Doc.__new__(lint.Doc)
        doc.text = text
        doc.lines = []
        cur = "header"
        import re as _re
        for i, line in enumerate(text.splitlines(), 1):
            m = _re.match(r"^#{2,3} (\d+(?:\.\d+)?)[. ]", line)
            if m:
                cur = m.group(1)
            doc.lines.append((i, cur, line))
        doc.headings = {s for _, s, _ in doc.lines if s != "header"}
        errs: list[str] = []
        check(doc, errs)
        return errs

    # retired name on a live-mechanism line in §5
    planted = base.replace("## 5. Panel decision",
                           "## 5. Panel decision\nThe machine uses AuthoritySnapshot here.")
    assert violations(planted, lint.check_retired), "retired-name check is vacuous"
    # unresolved §-reference
    planted = base.replace("## 5. Panel decision",
                           "## 5. Panel decision\nSee §99.9 for details.")
    assert violations(planted, lint.check_section_refs), "§-ref check is vacuous"
    # second normative mutation binding
    planted = base.replace("## 5. Panel decision",
                           "## 5. Panel decision\nAppends use `createCommitOnBranch` again.")
    assert violations(planted, lint.check_mutations), "mutation-once check is vacuous"
    # T cited with no §10 row
    planted = base.replace("## 5. Panel decision",
                           "## 5. Panel decision\nT99 seals this.")
    assert violations(planted, lint.check_t_index), "T-index check is vacuous"
    # second field list for a §9 event
    planted = base.replace("## 5. Panel decision",
                           "## 5. Panel decision\n`seat_result{roster_digest}` again.")
    assert violations(planted, lint.check_field_lists), "field-list-once check is vacuous"


# ─── T8/T9 fail-closed AST gates ─────────────────────────────────────────────

def _production_modules() -> list[Path]:
    src = REPO_ROOT / "src/claude_dispatcher"
    return sorted(p for p in src.rglob("*.py"))


def _scan_guarded(paths: list[Path], guarded: set[str],
                  exempt: set[Path]) -> list[str]:
    hits = []
    for path in paths:
        if path in exempt:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in guarded:
                hits.append(f"{path}:{node.lineno} defines {node.name}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in guarded:
                hits.append(f"{path}:{node.lineno} constructs {node.func.id}")
    return hits


@pytest.mark.parametrize("gate", [
    pytest.param("t8_construction", id="t8-construction"),
    pytest.param("t9_interpretation", id="t9-interpretation"),
    pytest.param("t8-deny", id="deny-t8-detects-rogue-definition"),
])
def test_ast_allowlists_fail_closed(schemas, tmp_path, gate):
    """While the allowlisted modules are absent (pre-PR2), their absence is
    the expected state — but ANY other module defining or constructing a
    guarded name is a hard failure. When they land, the same scan enforces
    the allowlist (fail closed either way — grok B3)."""
    allow = schemas["ast_allowlists"]
    if gate == "t8-deny":
        # falsify the scanner itself against a rogue module.
        rogue = tmp_path / "rogue.py"
        rogue.write_text("class ClassifyOutcome:\n    pass\n")
        hits = _scan_guarded([rogue], {"ClassifyOutcome"}, set())
        assert hits, "T8 scanner is vacuous — it missed a rogue definition"
        return
    spec = allow[gate]
    guarded = set(spec["guarded_names"])
    allowed = {REPO_ROOT / m for m in spec["allowed_modules"]}
    exempt = allowed | {REPO_ROOT / m for m in spec.get("legacy_exemptions", [])}
    hits = _scan_guarded(_production_modules(), guarded, exempt)
    absent = [m for m in allowed if not m.exists()]
    assert not hits, (
        f"{gate}: guarded names outside the allowlist "
        f"(allowlisted modules {'ABSENT — pre-PR2 fail-closed gate' if absent else 'present'}):\n"
        + "\n".join(hits))
    # record the expected pre-PR2 state loudly in the test output.
    if absent:
        print(f"{gate}: allowlisted modules absent as expected pre-PR2: "
              f"{[str(m.relative_to(REPO_ROOT)) for m in absent]}")


# ─── architecture skeleton: dark mode ────────────────────────────────────────

def _imports_boundary(tree: ast.AST) -> list[str]:
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += [a.name for a in node.names
                     if a.name.startswith("claude_dispatcher.boundary")]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("claude_dispatcher.boundary"):
                hits.append(mod)
            if node.level and (mod == "boundary" or mod.startswith("boundary.")):
                hits.append(f".{mod}")
            if node.level and mod == "" and any(a.name == "boundary"
                                                for a in node.names):
                hits.append(".boundary")
    return hits


@pytest.mark.parametrize("case", [
    pytest.param("live", id="no-production-import-while-allowlist-empty"),
    pytest.param("deny", id="deny-detector-sees-boundary-import"),
])
def test_architecture_boundary_dark_mode(schemas, tmp_path, case):
    """boundary/ is importable from tests only until PR6; the door
    allowlist is empty and this harness fails on any production import
    (plan §1 — dark mode; PR6 fills the allowlist)."""
    arch = schemas["ast_allowlists"]["architecture"]
    if case == "deny":
        rogue = tmp_path / "rogue.py"
        rogue.write_text("from claude_dispatcher.boundary import generated\n")
        assert _imports_boundary(ast.parse(rogue.read_text())), \
            "architecture detector is vacuous"
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


# ─── T6: every parametrised module here has ≥1 deny case ────────────────────

def test_t6_every_parametrized_module_has_a_deny_case():
    for path in sorted(BOUNDARY_DIR.glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        if "parametrize" not in text:
            continue
        assert "deny" in text, (
            f"{path.name}: parametrised seal without a deny row (T6 — design "
            f"§12 harness rules)")


def test_t19_vectors_dir_matches_loaded():
    assert set(_VECTORS) == {p.stem for p in VECTORS_DIR.glob("*.json")}
