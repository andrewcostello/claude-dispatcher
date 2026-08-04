#!/usr/bin/env python3
"""fsmgen — generate the boundary's safety truth from schema/*.yaml.

Why this exists
---------------
Design v20 (docs/plans/2026-08-02-classification-gating-design.md) §12 orders
PR0 to land the FSM artifact and its generated outputs BEFORE any feature
code: six consecutive review rounds of that document were spent killing
hand-copied dual definitions, and the ruling is that the §6.0 tables, the §9
unions, the §5.1 aggregate and the BoundaryError universe are never written
by hand again. This tool reads:

    schema/lifecycle_fsm.yaml      §6.0 tables + §9 unions + fold/durability
    schema/panel_aggregate.yaml    §5.1 roster/required_seats/blocking/aggregate
    schema/boundary_errors.yaml    plan §0.2 closed error universe
    schema/classifier_protocol.yaml §3.3/§8 frame constants + vector specs

and generates, deterministically (no timestamps, no randomness — regeneration
is byte-identical):

    src/claude_dispatcher/boundary/generated/__init__.py
        enums, frozen dataclasses for every §9 event (unions AND singles,
        every one carrying the common envelope), fail-closed wire
        construction (missing REQUIRED / present FORBIDDEN / unknown enum
        value / unknown variant ⇒ typed halt), apply() dispatch for both
        machines, both reducers (section-A projection machine; section-B
        with the §6.0 observe_delta apply order and derive_hold_id), the
        epoch fold, required_seats/blocking/aggregate + seat-result
        filtering, BoundaryError enum + maps.
    docs/generated/lifecycle_tables.md   the two §6.0 tables
    docs/generated/event_unions.md       the §9 union listings
    tests/boundary/vectors/t19/*.json    T19 vector INPUTS (named histories)
    schema/testdata/classifier_frames/*  golden + malformed frame vectors

INDEPENDENT ORACLE RULE (panel CRITICAL): this tool emits vector INPUTS
only. The expected reduce outputs live in
tests/boundary/vectors/t19_expected.json — hand-written from the design's
§6.0 tables and NEVER touched by fsmgen, so a semantic change in a reducer
goes red against the frozen expectation even after regeneration.

It also compares the generated tables/unions against the design doc's own
inline text (normalized) — doc == artifact is enforced, not hoped for.

Usage:
    python tools/fsmgen.py            regenerate everything in place
    python tools/fsmgen.py --check    verify committed outputs are exactly
                                      what regeneration would produce
                                      (CI mode; exit 1 on any drift)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import types
from collections.abc import Sequence
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "schema"
GENERATED_PY = REPO_ROOT / "src/claude_dispatcher/boundary/generated/__init__.py"
DOCS_DIR = REPO_ROOT / "docs/generated"
VECTORS_DIR = REPO_ROOT / "tests/boundary/vectors/t19"
FRAMES_DIR = REPO_ROOT / "schema/testdata/classifier_frames"
DESIGN_DOC = REPO_ROOT / "docs/plans/2026-08-02-classification-gating-design.md"

# Every schema token that becomes a Python identifier or enum member must
# satisfy this — a quote or newline in a schema string must fail loudly at
# load, never reach exec() (panel finding).
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Wire fields carried as generated enums / ints; everything else is str.
ENUM_FIELD_TYPES = {
    "disposition": "ReconcileDisposition",
    "credential_mode": "CredentialMode",
    "mode": "CredentialMode",
    "actor_verification": "ActorVerification",
    "protection_mode": "ProtectionMode",
    "hold_effect": "HoldEffect",
}
INT_FIELDS = {"schema_major", "schema_minor", "duration_ms"}


class SchemaError(SystemExit):
    def __init__(self, msg: str):
        super().__init__(f"fsmgen: SCHEMA ERROR: {msg}")


def _require_ident(token: object, where: str) -> str:
    if not isinstance(token, str) or not _IDENT.match(token):
        raise SchemaError(f"{where}: {token!r} is not a valid identifier")
    return token


# Keys each schema record may carry. An unrecognised key is a hard schema
# error, not silent data (panel round 2: a YAML comma turned a scalar into a
# stray null key nobody noticed).
_ALLOWED_KEYS = {
    "variant": {"name", "row", "trigger", "required", "forbidden", "fixed",
                "extra_from"},
    "single": {"required", "optional", "note", "field_pair_rules"},
    "vector_case": {"name", "file", "expect", "reason", "reason_code"},
    "row": {"id", "from", "event", "to", "guard", "display", "disposition",
            "epoch_effect", "expected_base_oid_effect",
            "standing_reject_restore_resolves_to"},
}


def _check_keys(record: dict, kind: str, where: str) -> None:
    allowed = _ALLOWED_KEYS[kind]
    extra = {k for k in record
             if k not in allowed and not str(k).endswith("_domain")}
    if extra:
        raise SchemaError(f"{where}: unrecognised key(s) {sorted(extra)} — "
                          f"allowed: {sorted(allowed)} (+ <field>_domain)")


def _validate_machine_tokens(fsm: dict) -> None:
    for sec in ("section_a", "section_b"):
        for st in [fsm[sec]["initial_pseudo_state"], *fsm[sec]["states"]]:
            _require_ident(st, f"{sec}.states")
        for evn in fsm[sec]["events"]:
            _require_ident(evn, f"{sec}.events")
        for row in fsm[sec]["rows"]:
            _require_ident(row["id"], f"{sec}.rows")
            _check_keys(row, "row", f"{sec}.rows.{row['id']}")
            for key in ("epoch_effect", "expected_base_oid_effect"):
                if key in row:
                    _require_ident(row[key], f"{sec}.rows.{row['id']}.{key}")
    for m in fsm["reconcile_dispositions"]["members"]:
        _require_ident(m["name"], "reconcile_dispositions")
    for name, members in fsm["enums"].items():
        _require_ident(name, "enums")
        for m in members:
            _require_ident(m, f"enums.{name}")


def _validate_union_tokens(fsm: dict) -> None:
    for fam, spec in fsm["events"]["unions"].items():
        _require_ident(fam, "unions")
        for v in spec["variants"]:
            _require_ident(v["name"], f"unions.{fam}")
            _check_keys(v, "variant", f"unions.{fam}.{v['name']}")
            # classification_evaluated's variants are payload records, not
            # transition rows — only row-bearing variants carry a trigger.
            if "row" in v:
                _require_ident(v["trigger"], f"unions.{fam}.{v['name']}.trigger")
            for f in [*v.get("required", []), *v.get("forbidden", []),
                      *v.get("extra_from", [])]:
                _require_ident(f, f"unions.{fam}.{v['name']}")
            for k, val in v.get("fixed", {}).items():
                _require_ident(k, f"unions.{fam}.{v['name']}.fixed key")
                _require_ident(val, f"unions.{fam}.{v['name']}.fixed value")


def _validate_single_tokens(fsm: dict) -> None:
    for name, spec in fsm["events"]["singles"].items():
        _require_ident(name, "singles")
        _check_keys(spec, "single", f"singles.{name}")
        for f in [*spec["required"], *spec.get("optional", [])]:
            _require_ident(f, f"singles.{name}")
        for key, val in spec.items():
            if key.endswith("_domain"):
                _require_ident(key[:-len("_domain")], f"singles.{name} domain")
                for member in val:
                    _require_ident(member, f"singles.{name}.{key}")
        for key, rule in spec.get("field_pair_rules", {}).items():
            _require_ident(key, f"singles.{name}.field_pair_rules key")
            _require_ident(rule["field"], f"singles.{name}.field_pair_rules field")
            for lhs, rhs in rule["allowed"].items():
                _require_ident(lhs, f"singles.{name}.pair lhs")
                for member in rhs:
                    _require_ident(member, f"singles.{name}.pair rhs")


def _validate_envelope_tokens(fsm: dict) -> None:
    env = fsm["events"]["envelope"]
    for f in [*env["required"], *env["optional"]]:
        _require_ident(f, "envelope")
    for m in env["supported_majors"]:
        if isinstance(m, bool) or not isinstance(m, int):
            raise SchemaError(f"envelope.supported_majors: {m!r} is not an int")
    for f in fsm["events"]["reducer_family_filter"]["values"]:
        _require_ident(f, "reducer_family_filter.values")
    for k, v in fsm["events"]["field_name_map"].items():
        _require_ident(v, f"field_name_map[{k!r}]")


def _validate_event_tokens(fsm: dict) -> None:
    _validate_union_tokens(fsm)
    _validate_single_tokens(fsm)
    _validate_envelope_tokens(fsm)


def _validate_shared_object_tokens(fsm: dict) -> None:
    shared = fsm["events"]["shared_objects"]
    for variant, spec in shared["ClassifierAuthority"]["union"].items():
        _require_ident(variant, "shared_objects.ClassifierAuthority")
        for f in spec["required"]:
            _require_ident(f, f"shared_objects.ClassifierAuthority.{variant}")
    for f in shared["AuthorityFingerprint"]["required"]:
        _require_ident(f, "shared_objects.AuthorityFingerprint")


def _validate_panel_tokens(panel: dict) -> None:
    for k in panel["panel_intensity"]:
        _require_ident(k, "panel_intensity")
    for m in panel["strategy"]:
        _require_ident(m, "strategy")
    for key in ("verdict_domain", "severity_domain"):
        for m in panel["seat_outcome"][key]:
            _require_ident(m, f"seat_outcome.{key}")
    for m in panel["aggregate"]["result_domain"]:
        _require_ident(m, "aggregate.result_domain")
    for key in ("verdict_blocks", "severity_blocks"):
        for m in panel["blocking_predicate"][key]:
            _require_ident(m, f"blocking_predicate.{key}")


def _validate_schema_tokens(s: dict) -> None:
    """No unvalidated schema token reaches exec(): every token the emitters
    interpolate as an identifier, attribute or enum member is checked, plus
    a per-record key allowlist so a stray or typo'd key is a load-time error
    rather than silent data (panel round 2)."""
    fsm, errors = s["lifecycle_fsm"], s["boundary_errors"]
    _validate_machine_tokens(fsm)
    _validate_event_tokens(fsm)
    _validate_shared_object_tokens(fsm)
    _validate_panel_tokens(s["panel_aggregate"])
    for case in s["classifier_protocol"]["vectors"]["cases"]:
        _check_keys(case, "vector_case",
                    f"classifier_protocol.vectors.{case.get('name')}")
    for c in errors["codes"]:
        _require_ident(c["code"], "boundary_errors.codes")
        _require_ident(c["phase"], "boundary_errors.phase")
        _require_ident(c["retriability"], "boundary_errors.retriability")
    for p in errors["phases"]:
        _require_ident(p, "boundary_errors.phases")
    for r in errors["retriability"]:
        _require_ident(r, "boundary_errors.retriability")


def load_schemas() -> dict:
    out = {}
    for name in ("lifecycle_fsm", "panel_aggregate", "boundary_errors",
                 "classifier_protocol", "ast_allowlists"):
        with open(SCHEMA_DIR / f"{name}.yaml", encoding="utf-8") as fh:
            out[name] = yaml.safe_load(fh)
    _validate_schema_tokens(out)
    return out


# ─── helpers ─────────────────────────────────────────────────────────────────

def as_list(v) -> list:
    return v if isinstance(v, list) else [v]


def camel(snake: str) -> str:
    return "".join(part.capitalize() for part in snake.split("_"))


def compose_projection(fsm: dict) -> tuple[dict[str, list[str]], list[list[str]]]:
    """Derive the projection machine: for each durable state D, which live
    states are reachable from D through memory-only intermediates (the
    frontier a durable event's audit `from` may legally name), and the
    durable edge list (composed edges)."""
    sec = fsm["section_a"]
    memory = set(sec["durability"]["memory_only"])
    durable = set(sec["projection"]["durable_states"])
    adj: dict[str, set[str]] = {}
    for row in sec["rows"]:
        frm, to = row["from"], row["to"]
        if to in ("ILLEGAL", "unchanged", "terminal") or frm == "any_other":
            continue
        for f in as_list(frm):
            adj.setdefault(f, set()).add(to)
    reachable: dict[str, list[str]] = {}
    edges: set[tuple[str, str]] = set()
    for d in sorted(durable):
        seen, stack = {d}, [d]
        while stack:
            cur = stack.pop()
            for nxt in adj.get(cur, ()):  # noqa: B007
                if nxt in memory:
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
                else:
                    edges.add((d, nxt))
                    seen.add(nxt)
        reachable[d] = sorted(s for s in seen if s in memory or s == d)
    return reachable, sorted([list(e) for e in edges])


# ─── generated module: emitters ──────────────────────────────────────────────

def emit_header() -> list[str]:
    return [
        '"""GENERATED by tools/fsmgen.py from schema/*.yaml — DO NOT EDIT.',
        "",
        "The single source of truth for the classification→gating boundary's",
        "state machines, event unions, panel aggregate and error universe",
        "(design v20 §§5.1/6.0/9; implementation plan §0.2). Regenerate with:",
        "",
        "    python tools/fsmgen.py",
        "",
        "CI runs `python tools/fsmgen.py --check` — hand edits here are a red",
        'build by construction."""',
        "",
        "from __future__ import annotations",
        "",
        "import hashlib",
        "import json",
        "import re",
        "from dataclasses import dataclass",
        "from enum import Enum, IntEnum",
        "from typing import ClassVar, Mapping, Optional, Sequence",
        "",
    ]


def emit_errors(errors: dict) -> list[str]:
    L: list[str] = ["# ─── errors (plan §0.2 closed universe) ─────────────────────────────", ""]
    w = L.append
    codes = errors["codes"]
    w("class BoundaryErrorCode(Enum):")
    for c in codes:
        w(f"    {c['code']} = \"{c['code']}\"")
    w("")
    w("class ErrorPhase(Enum):")
    for p in errors["phases"]:
        w(f"    {p} = \"{p}\"")
    w("")
    w("class Retriability(Enum):")
    for r in errors["retriability"]:
        w(f"    {r} = \"{r}\"")
    w("")
    for map_name, key, target in (("ERROR_PHASE", "phase", "ErrorPhase"),
                                  ("ERROR_RETRIABILITY", "retriability", "Retriability")):
        w(f"{map_name}: Mapping[BoundaryErrorCode, {target}] = {{")
        for c in codes:
            w(f"    BoundaryErrorCode.{c['code']}: {target}.{c[key]},")
        w("}")
        w("")
    w("ERROR_OPERATOR_ACTION: Mapping[BoundaryErrorCode, str] = {")
    for c in codes:
        action = " ".join(str(c["operator_action"]).split())
        w(f"    BoundaryErrorCode.{c['code']}: {json.dumps(action)},")
    w("}")
    w("")
    pattern = errors["metric_name_pattern"]
    w("ERROR_METRIC: Mapping[BoundaryErrorCode, str] = {")
    for c in codes:
        w(f"    BoundaryErrorCode.{c['code']}: "
          f"{json.dumps(pattern.format(code_lower=c['code'].lower()))},")
    w("}")
    w("")
    exit_map = errors["cli_exit_map"]
    w("# CLI exit map (plan §0.2): 0/2/3/4 = ok/TERMINAL/RETRIABLE/OPERATOR.")
    w(f"CLI_EXIT_OK: int = {int(exit_map['ok'])}")
    w("CLI_EXIT_MAP: Mapping[Retriability, int] = {")
    for r in errors["retriability"]:
        w(f"    Retriability.{r}: {int(exit_map[r])},")
    w("}")
    w("")
    w(f"UNKNOWN_CODE_RULE: str = "
      f"{json.dumps(' '.join(str(errors['unknown_code_rule']).split()))}")
    w(ERROR_RUNTIME)
    return L


def _emit_state_and_disposition_enums(fsm: dict) -> list[str]:
    L: list[str] = []
    w = L.append
    disp = fsm["reconcile_dispositions"]
    for enum_name, sec in (("SectionAState", fsm["section_a"]),
                           ("SectionBState", fsm["section_b"])):
        w(f"class {enum_name}(Enum):")
        for st in [sec["initial_pseudo_state"], *sec["states"]]:
            w(f"    {st} = \"{st}\"")
        w("")
    w("class ReconcileDisposition(Enum):")
    for m in disp["members"]:
        w(f"    {m['name']} = \"{m['name']}\"")
    w("")
    for set_name, members in (
            ("ACCEPTING_DISPOSITIONS", disp["accepting"]),
            ("OPERATOR_ACCEPTING_DISPOSITIONS", disp["operator_accepting"]),
            ("SECTION_B_ONLY_DISPOSITIONS",
             [m["name"] for m in disp["members"] if m.get("section_b_only")])):
        w(f"{set_name} = frozenset({{")
        for d in members:
            w(f"    ReconcileDisposition.{d},")
        w("})")
    w("")
    for enum_name, members in fsm["enums"].items():
        w(f"class {enum_name}(Enum):")
        for m in members:
            w(f"    {m} = \"{m}\"")
        w("")
    return L


def _emit_durability_and_ceiling(fsm: dict) -> list[str]:
    L: list[str] = []
    w = L.append
    a, b = fsm["section_a"], fsm["section_b"]
    w(f"SECTION_A_EVENTS: tuple[str, ...] = {tuple(a['events'])!r}")
    w(f"SECTION_B_EVENTS: tuple[str, ...] = {tuple(b['events'])!r}")
    w(f"SECTION_A_TERMINAL: frozenset[str] = frozenset({tuple(a['terminal_states'])!r})")
    w(f"SECTION_B_TERMINAL: frozenset[str] = frozenset({tuple(b['terminal_states'])!r})")
    w("")
    dur = a["durability"]
    w("# Durability — an exclusive partition (§6.0, round 11 grok).")
    w(f"DURABLE_STATE_BRANCH: frozenset[str] = frozenset({tuple(dur['durable_state_branch'])!r})")
    w(f"MEMORY_ONLY: frozenset[str] = frozenset({tuple(dur['memory_only'])!r})")
    w(f"HOLD_BRANCH: frozenset[str] = frozenset({tuple(dur['hold_branch'])!r})")
    w(f"STATE_BRANCH_REF: str = {json.dumps(str(dur['state_branch_ref']))}")
    w(f"HOLD_BRANCH_REF: str = {json.dumps(str(dur['hold_branch_ref']))}")
    w("")
    ceiling = a["recovery_ceiling"]
    w("# Recovery admission ceiling (§6.0 provisional bounds; the elapsed-")
    w("# time half is a PR4 obligation — see schema recovery_ceiling).")
    w(f"RECOVERY_CEILING_EVENTS: int = {int(ceiling['events'])}")
    w(f"RECOVERY_CEILING_REDUCE_SECONDS: int = {int(ceiling['reduce_seconds'])}")
    w("")
    env = fsm["events"]["envelope"]
    w("# The v1 wire supports exactly these schema majors; anything else halts")
    w("# as SCHEMA_MAJOR_UNKNOWN — the named §9 halt, range-checked at intake.")
    w(f"SUPPORTED_SCHEMA_MAJORS: frozenset[int] = frozenset({tuple(int(m) for m in env['supported_majors'])!r})")
    w("")
    b_rows_by_id = {r["id"]: r for r in b["rows"]}
    standing_target = _require_ident(
        str(b_rows_by_id["standing_reenter"]["standing_reject_restore_resolves_to"]),
        "standing_reject_restore_resolves_to")
    if standing_target not in b["states"]:
        raise SchemaError(f"standing_reject_restore_resolves_to names unknown "
                          f"state {standing_target!r}")
    w("# STANDING × REJECT_RESTORE_HOLD resolution — driven by the schema key")
    w("# standing_reject_restore_resolves_to (the single place to change if")
    w("# the author ratifies the other reading).")
    w(f"STANDING_REJECT_RESTORE_TARGET_NAME: str = {standing_target!r}")
    w("")
    return L


def _emit_projection_and_rows(fsm: dict, reachable: dict,
                              proj_edges: list) -> list[str]:
    L: list[str] = []
    w = L.append
    w("# Projection machine (round 14, codex): durable states + composed edges,")
    w("# derived from the live table by composing through memory-only states.")
    w(f"PROJECTION_DURABLE_STATES: tuple[str, ...] = "
      f"{tuple(fsm['section_a']['projection']['durable_states'])!r}")
    w("PROJECTION_EDGES: frozenset[tuple[str, str]] = frozenset({")
    for e in proj_edges:
        w(f"    ({e[0]!r}, {e[1]!r}),")
    w("})")
    w("# For each durable state: the live states reachable through memory-only")
    w("# intermediates — the frontier a durable event's audit `from` may name.")
    w("PROJECTION_REACHABLE: Mapping[str, tuple[str, ...]] = {")
    for d, states in sorted(reachable.items()):
        w(f"    {d!r}: {tuple(states)!r},")
    w("}")
    w("")
    for sec_key, table_name in (("section_a", "SECTION_A_ROWS"),
                                ("section_b", "SECTION_B_ROWS")):
        w(f"{table_name}: tuple[Mapping[str, object], ...] = (")
        for row in fsm[sec_key]["rows"]:
            w("    {" + ", ".join([
                f"'id': {row['id']!r}",
                f"'from': {tuple(as_list(row['from']))!r}",
                f"'event': {tuple(as_list(row['event']))!r}",
                f"'to': {row['to']!r}",
                f"'guard': {row.get('guard')!r}",
            ]) + "},")
        w(")")
        w("")
    env = fsm["events"]["envelope"]
    w(f"ENVELOPE_REQUIRED: tuple[str, ...] = {tuple(env['required'])!r}")
    w(f"ENVELOPE_OPTIONAL: tuple[str, ...] = {tuple(env['optional'])!r}")
    w(f"FIELD_NAME_MAP: Mapping[str, str] = {dict(fsm['events']['field_name_map'])!r}")
    w("")
    return L


def emit_machine_constants(fsm: dict, reachable: dict, proj_edges: list) -> list[str]:
    return (["# ─── machine states, events, dispositions ───────────────────────────", ""]
            + _emit_state_and_disposition_enums(fsm)
            + _emit_durability_and_ceiling(fsm)
            + _emit_projection_and_rows(fsm, reachable, proj_edges))


def _variant_field_sets(fsm: dict, spec: dict, v: dict) -> tuple[list[str], list[str], list[str]]:
    """(required, optional, forbidden) wire-field lists for one variant —
    envelope + family commons + per-variant, disjoint by construction.
    §9-required trigger_event/from/to are REAL required wire fields
    (validated against the row, never stripped — panel round 2)."""
    env = fsm["events"]["envelope"]
    fam_req = list(spec["common_required"])
    fam_opt = list(spec.get("common_optional", []))
    var_req = list(v.get("required", []))
    forbidden = list(v.get("forbidden", []))
    required: list[str] = []
    for f in [*env["required"], *fam_req, *var_req]:
        if f not in required:
            required.append(f)
    optional = [f for f in [*env["optional"], *fam_opt]
                if f not in required and f not in forbidden]
    return required, optional, forbidden


def _emit_field_decl(w, f: str, optional: bool) -> None:
    py_name = {"from": "from_state", "to": "to_state"}.get(f, f)
    enum_t = ENUM_FIELD_TYPES.get(f)
    if enum_t:
        w(f"    {py_name}: Optional[{enum_t}] = None" if optional
          else f"    {py_name}: {enum_t}")
    elif f in INT_FIELDS:
        w(f"    {py_name}: Optional[int] = None" if optional
          else f"    {py_name}: int")
    else:
        w(f"    {py_name}: Optional[str] = None" if optional
          else f"    {py_name}: str")


def _emit_post_init(w, name: str, fixed: dict, guard: str | None) -> None:
    w("    def __post_init__(self) -> None:")
    w("        _validate_event_fields(self)")
    w("        _validate_row_audit_fields(self)")
    for k, val in fixed.items():
        if k == "disposition":
            w(f"        if self.disposition is not ReconcileDisposition.{val}:")
            w(f"            raise ValueError(\"{name}.disposition must be {val}\")")
        else:
            enum_t = ENUM_FIELD_TYPES.get(k)
            w(f"        if self.{k} is not {enum_t}.{val}:")
            w(f"            raise ValueError(\"{name}.{k} must be {val}\")")
    if guard == "accepting_disposition":
        w("        # operator_reconcile can carry only operator-mintable accepting")
        w("        # dispositions — ACTOR_VERIFIED_AUTO/STANDING are section-B-only,")
        w("        # and the auto disposition is mintable solely by ActorVerifiedAuto.")
        w("        if self.disposition not in OPERATOR_ACCEPTING_DISPOSITIONS:")
        w(f"            raise ValueError(f\"{name}: disposition must be \"")
        w("                             f\"operator-accepting, got {self.disposition}\")")
    elif guard == "reject_restore_hold":
        w("        if self.disposition is not ReconcileDisposition.REJECT_RESTORE_HOLD:")
        w(f"            raise ValueError(\"{name} requires REJECT_RESTORE_HOLD\")")
    elif guard == "same_disposition":
        w("        # a replay repeats the operator-accepting disposition it echoes")
        w("        if self.disposition not in OPERATOR_ACCEPTING_DISPOSITIONS:")
        w(f"            raise ValueError(f\"{name}: replay disposition must be \"")
        w("                             f\"operator-accepting, got {self.disposition}\")")
    if name == "ActorVerifiedAuto":
        w("        # SEPARATED + VERIFIED_API + actor_node_id + matched_subject_digest —")
        w("        # constructible with the full evidence tuple or not at all (§6.0/§9).")
        w("        if self.mode is not CredentialMode.SEPARATED:")
        w("            raise ValueError(")
        w("                \"ActorVerifiedAuto requires SEPARATED; under SHARED, never\")")
    w("")


def emit_variants_family(fsm: dict, family: str,
                         row_lookup: dict[str, dict]) -> tuple[list[str], list[str]]:
    spec = fsm["events"]["unions"][family]
    L: list[str] = []
    w = L.append
    names = []
    for v in spec["variants"]:
        name = v["name"]
        names.append(name)
        row = row_lookup[v["row"]]
        froms = tuple(as_list(row["from"]) + list(v.get("extra_from", [])))
        required, optional, forbidden = _variant_field_sets(fsm, spec, v)
        fixed = dict(v.get("fixed", {}))
        w("@dataclass(frozen=True)")
        w(f"class {name}:")
        w(f'    """{family} variant — row `{row["id"]}`: '
          f'{"/".join(froms)} × {v["trigger"]} → {row["to"]}."""')
        w("")
        epoch_effect = (row.get("expected_base_oid_effect")
                        or row.get("epoch_effect") or "none")
        w(f"    FAMILY: ClassVar[str] = \"{family}\"")
        w(f"    TRIGGER: ClassVar[str] = \"{v['trigger']}\"")
        w(f"    ROW: ClassVar[str] = \"{row['id']}\"")
        w(f"    FROM_STATES: ClassVar[tuple[str, ...]] = {froms!r}")
        w(f"    TO_STATE: ClassVar[str] = {row['to']!r}")
        w(f"    EPOCH_EFFECT: ClassVar[str] = {_require_ident(epoch_effect, row['id'] + '.epoch_effect')!r}")
        w(f"    REQUIRED: ClassVar[tuple[str, ...]] = {tuple(required)!r}")
        w(f"    OPTIONAL: ClassVar[tuple[str, ...]] = {tuple(optional)!r}")
        w(f"    FORBIDDEN: ClassVar[tuple[str, ...]] = {tuple(forbidden)!r}")
        w(f"    FIXED: ClassVar[Mapping[str, str]] = {fixed!r}")
        w("")
        for f in required:
            _emit_field_decl(w, f, optional=False)
        for f in optional:
            _emit_field_decl(w, f, optional=True)
        w("")
        _emit_post_init(w, name, fixed, row.get("guard"))
    return names, L


def emit_singles(fsm: dict) -> tuple[dict[str, str], list[str]]:
    """§9 single-variant events + the classification_evaluated split — every
    one carries the envelope and validates its closed domains (panel
    finding: authorization_granted, the sole authorization record, must be
    a generated, sealed type)."""
    env = fsm["events"]["envelope"]
    L: list[str] = ["# ─── §9 single-variant events (every one carries the envelope) ──────", ""]
    w = L.append
    classes: dict[str, str] = {}

    def one(event_name: str, cls_name: str, required: list[str],
            optional: list[str], domains: dict[str, list[str]],
            pair_rules: dict) -> None:
        classes[event_name] = cls_name
        req: list[str] = []
        for f in [*env["required"], *required]:
            if f not in req:
                req.append(f)
        opt = [f for f in [*env["optional"], *optional] if f not in req]
        w("@dataclass(frozen=True)")
        w(f"class {cls_name}:")
        w(f'    """§9 `{event_name}` event."""')
        w("")
        w(f"    EVENT: ClassVar[str] = \"{event_name}\"")
        w(f"    REQUIRED: ClassVar[tuple[str, ...]] = {tuple(req)!r}")
        w(f"    OPTIONAL: ClassVar[tuple[str, ...]] = {tuple(opt)!r}")
        w("    FORBIDDEN: ClassVar[tuple[str, ...]] = ()")
        w(f"    DOMAINS: ClassVar[Mapping[str, tuple[str, ...]]] = "
          f"{ {k: tuple(vv) for k, vv in domains.items()} !r}")
        pairs = {k: {"field": v["field"],
                     "allowed": {kk: tuple(vv) for kk, vv in v["allowed"].items()}}
                 for k, v in pair_rules.items()}
        w(f"    PAIR_RULES: ClassVar[Mapping[str, Mapping[str, object]]] = {pairs!r}")
        w("")
        for f in req:
            if f in domains:
                w(f"    {f}: str")
            else:
                _emit_field_decl(w, f, optional=False)
        for f in opt:
            _emit_field_decl(w, f, optional=True)
        w("")
        w("    def __post_init__(self) -> None:")
        w("        _validate_event_fields(self)")
        for f in domains:
            w(f"        if self.{f} not in self.DOMAINS[{f!r}]:")
            w(f"            raise ValueError(f\"{cls_name}.{f}: unknown value \"")
            w(f"                             f\"{{self.{f}!r}} outside the closed domain\")")
        for key, rule in pair_rules.items():
            other = rule["field"]
            w(f"        _allowed = self.PAIR_RULES[{key!r}]['allowed'].get(self.{key})")
            w(f"        if _allowed is not None and self.{other} not in _allowed:")
            w(f"            raise ValueError(")
            w(f"                f\"{cls_name}: {key}={{self.{key}!r}} admits \"")
            w(f"                f\"{other} {{_allowed!r}}, got {{self.{other}!r}}\")")
        w("")

    for event_name, spec in fsm["events"]["singles"].items():
        domains = {key[:-len("_domain")]: list(val)
                   for key, val in spec.items() if key.endswith("_domain")}
        one(event_name, camel(event_name), list(spec["required"]),
            list(spec.get("optional", [])), domains,
            dict(spec.get("field_pair_rules", {})))
    for v in fsm["events"]["unions"]["classification_evaluated"]["variants"]:
        one(f"classification_evaluated/{v['name']}", v["name"],
            list(v["required"]), [], {}, {})
    w("SINGLE_EVENTS: Mapping[str, type] = {")
    for event_name, cls_name in classes.items():
        w(f"    \"{event_name}\": {cls_name},")
    w("}")
    w("")
    return classes, L


def emit_panel(panel: dict) -> list[str]:
    L: list[str] = ["", "# ─── §5.1 panel aggregate ────────────────────────────────────────────", ""]
    w = L.append
    w("class PanelIntensity(IntEnum):")
    for k, v in panel["panel_intensity"].items():
        w(f"    {_require_ident(k, 'panel_intensity')} = {int(v)}")
    w("")
    for enum_name, members in (("Strategy", panel["strategy"]),
                               ("SeatVerdict", panel["seat_outcome"]["verdict_domain"]),
                               ("Severity", panel["seat_outcome"]["severity_domain"]),
                               ("PanelAggregateResult", panel["aggregate"]["result_domain"])):
        w(f"class {enum_name}(Enum):")
        for m in members:
            w(f"    {_require_ident(m, enum_name)} = \"{m}\"")
        w("")
    blocking = panel["blocking_predicate"]
    w("BLOCKING_VERDICTS = frozenset({"
      + ", ".join("SeatVerdict." + v for v in blocking["verdict_blocks"]) + "})")
    w("BLOCKING_SEVERITIES = frozenset({"
      + ", ".join("Severity." + v for v in blocking["severity_blocks"]) + "})")
    w("")
    w(PANEL_RUNTIME)
    return L


def build_generated_module(s: dict) -> str:
    fsm = s["lifecycle_fsm"]
    reachable, proj_edges = compose_projection(fsm)
    a_rows = {r["id"]: r for r in fsm["section_a"]["rows"]}
    b_rows = {r["id"]: r for r in fsm["section_b"]["rows"]}

    L = emit_header()
    L += emit_errors(s["boundary_errors"])
    L += emit_machine_constants(fsm, reachable, proj_edges)
    L.append(VALIDATE_RUNTIME)
    eff_names, eff_lines = emit_variants_family(fsm, "effect_lifecycle", a_rows)
    hold_names, hold_lines = emit_variants_family(fsm, "hold_lifecycle", b_rows)
    L += eff_lines
    L += hold_lines
    L.append("EFFECT_VARIANTS: Mapping[str, type] = {")
    L += [f"    \"{n}\": {n}," for n in eff_names]
    L.append("}")
    L.append("HOLD_VARIANTS: Mapping[str, type] = {")
    L += [f"    \"{n}\": {n}," for n in hold_names]
    L.append("}")
    L.append("")
    _classes, singles_lines = emit_singles(fsm)
    L += singles_lines
    L.append(RUNTIME)
    L += emit_panel(s["panel_aggregate"])
    src = "\n".join(L)
    return src if src.endswith("\n") else src + "\n"


# ─── static runtime blocks (parameterized by the generated literals) ─────────

ERROR_RUNTIME = '''
@dataclass(frozen=True)
class BoundaryError:
    """One closed error value — plan §0.2. Unknown code ⇒ TERMINAL."""

    code: BoundaryErrorCode
    detail: str = ""

    @property
    def phase(self) -> ErrorPhase:
        return ERROR_PHASE[self.code]

    @property
    def retriability(self) -> Retriability:
        return ERROR_RETRIABILITY[self.code]

    @property
    def operator_action(self) -> str:
        return ERROR_OPERATOR_ACTION[self.code]

    @property
    def metric(self) -> str:
        return ERROR_METRIC[self.code]

    @property
    def exit_code(self) -> int:
        return CLI_EXIT_MAP[self.retriability]


class BoundaryFault(Exception):
    """Typed carrier for a BoundaryError."""

    def __init__(self, error: BoundaryError):
        super().__init__(f"{error.code.value}: {error.detail}")
        self.error = error


class IllegalTransitionError(BoundaryFault):
    """ILLEGAL (state × event) pair — typed error, journalled, never a
    silent no-op (§6.0 default rows)."""

    def __init__(self, machine: str, state: str, event: str, detail: str = ""):
        msg = f"{machine}: {state} × {event}" + (f" — {detail}" if detail else "")
        super().__init__(BoundaryError(BoundaryErrorCode.ILLEGAL_TRANSITION, msg))
        self.machine, self.state, self.event = machine, state, event


class WireViolation(Exception):
    """A wire event that does not satisfy its §9 schema — unknown variant,
    unknown enum value, missing REQUIRED or present FORBIDDEN field. The
    reducers convert this to a typed SCHEMA_MAJOR_UNKNOWN halt; §9: unknown
    variants and unknown enum VALUES halt identically to an unknown major.
    Validate, never coerce."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.code = BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN
        self.detail = detail
'''

VALIDATE_RUNTIME = '''
# Wire fields carried as enums / ints. Everything else is a non-empty str.
_ENUM_WIRE_FIELDS: Mapping[str, type] = {
    "disposition": ReconcileDisposition,
    "credential_mode": CredentialMode,
    "mode": CredentialMode,
    "actor_verification": ActorVerification,
    "protection_mode": ProtectionMode,
    "hold_effect": HoldEffect,
}
_INT_WIRE_FIELDS = frozenset({"schema_major", "schema_minor", "duration_ms"})

# Audit timestamps are RFC 3339 UTC — offset-bearing so records are orderable
# across hosts; anything else is a schema violation.
_TS_RE = re.compile(
    r"^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:\\d{2})$")


def _py_field(f: str) -> str:
    return FIELD_NAME_MAP.get(f, f)


def _short(value: object, limit: int = 60) -> str:
    """Journal-safe rendering: halt details must not dump whole payloads."""
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _validate_event_fields(event: object) -> None:
    """Shared __post_init__ validation: required fields present with the
    right type (never coerced), enum fields are enum INSTANCES, schema_major
    inside the supported range, ts RFC 3339 UTC. Raises ValueError."""
    cls = type(event)
    name = cls.__name__
    for f in cls.REQUIRED:
        _validate_field_value(name, f, getattr(event, _py_field(f)), required=True)
    for f in cls.OPTIONAL:
        value = getattr(event, _py_field(f), None)
        if value is not None:
            _validate_field_value(name, f, value, required=False)


def _validate_row_audit_fields(event: object) -> None:
    """§9 audit fields validated against the variant's row: from ∈
    FROM_STATES, trigger_event == the row's trigger, to == the row's target
    (== from on `unchanged` no-op rows). Raises ValueError."""
    cls = type(event)
    name = cls.__name__
    if event.from_state not in cls.FROM_STATES:
        raise ValueError(
            f"{name}.from_state {event.from_state!r} not in {cls.FROM_STATES!r}")
    if event.trigger_event != cls.TRIGGER:
        raise ValueError(
            f"{name}.trigger_event {event.trigger_event!r} contradicts the "
            f"row's trigger {cls.TRIGGER!r} — a mis-tagged writer halts")
    want_to = event.from_state if cls.TO_STATE == "unchanged" else cls.TO_STATE
    if event.to_state != want_to:
        raise ValueError(
            f"{name}.to {event.to_state!r} contradicts the row's {want_to!r}")


def _validate_field_value(name: str, f: str, value: object, required: bool) -> None:
    enum_t = _ENUM_WIRE_FIELDS.get(f)
    if enum_t is not None:
        if not isinstance(value, enum_t):
            raise ValueError(f"{name}.{f} must be a {enum_t.__name__} "
                             f"instance, got {_short(value)}")
        return
    if f in _INT_WIRE_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name}.{f} must be an int, got {_short(value)}")
        if f == "schema_major" and value not in SUPPORTED_SCHEMA_MAJORS:
            raise ValueError(
                f"{name}.schema_major {value} outside the supported set "
                f"{sorted(SUPPORTED_SCHEMA_MAJORS)} — unknown major halts (§9)")
        return
    if not isinstance(value, str) or (required and value == ""):
        raise ValueError(f"{name}.{f} must be a non-empty str, got {_short(value)}")
    if f == "ts" and not _TS_RE.match(value):
        raise ValueError(f"{name}.ts {_short(value)} is not RFC 3339 UTC")


def _convert_wire_value(cls_name: str, f: str, value: object) -> object:
    """Convert one wire value to the typed field — unknown enum values,
    unsupported majors and wrong types raise WireViolation (typed halt),
    never KeyError."""
    enum_t = _ENUM_WIRE_FIELDS.get(f)
    if enum_t is not None:
        if isinstance(value, enum_t):
            return value
        try:
            return enum_t(str(value))
        except ValueError:
            raise WireViolation(
                f"{cls_name}.{f}: unknown value {_short(value)} for closed "
                f"enum {enum_t.__name__} — halts like an unknown variant "
                f"(§9)") from None
    if f in _INT_WIRE_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int):
            raise WireViolation(f"{cls_name}.{f}: must be an int, "
                                f"got {_short(value)}")
        if f == "schema_major" and value not in SUPPORTED_SCHEMA_MAJORS:
            raise WireViolation(
                f"{cls_name}.schema_major: {value} outside the supported set "
                f"{sorted(SUPPORTED_SCHEMA_MAJORS)} — unknown major halts (§9)")
        return value
    if not isinstance(value, str) or value == "":
        raise WireViolation(f"{cls_name}.{f}: must be a non-empty str, "
                            f"got {_short(value)}")
    if f == "ts" and not _TS_RE.match(value):
        raise WireViolation(f"{cls_name}.ts: {_short(value)} is not RFC 3339 UTC")
    return value


def build_wire_event(variants: Mapping[str, type], ev: Mapping[str, object]) -> object:
    """Construct a typed event from a wire dict, fail-closed: unknown
    variant, missing REQUIRED (trigger_event/from/to included — §9 audit
    fields are real wire fields), present FORBIDDEN, unknown enum value or
    unsupported schema_major ⇒ WireViolation (⇒ SCHEMA_MAJOR_UNKNOWN halt);
    required fields are NEVER defaulted. A trigger/to contradiction with the
    variant's row is the same schema-violation class. Guard breaches inside
    __post_init__ surface as ValueError (⇒ ILLEGAL_TRANSITION)."""
    variant = ev.get("variant")
    cls = variants.get(str(variant))
    if cls is None:
        raise WireViolation(
            f"unknown event variant {variant!r} "
            f"(event_id {ev.get('event_id')!r}) — unknown variants halt (§9)")
    name = cls.__name__
    kwargs: dict = {}
    for f in cls.REQUIRED:
        value = ev.get(f)
        if value is None:
            raise WireViolation(
                f"{name}: required field {f!r} absent "
                f"(event_id {ev.get('event_id')!r}) — never defaulted")
        kwargs[_py_field(f)] = _convert_wire_value(name, f, value)
    for f in cls.OPTIONAL:
        value = ev.get(f)
        if value is not None:
            kwargs[_py_field(f)] = _convert_wire_value(name, f, value)
    for f in cls.FORBIDDEN:
        if ev.get(f) is not None:
            raise WireViolation(
                f"{name}: forbidden field {f!r} present "
                f"(event_id {ev.get('event_id')!r})")
    if kwargs.get("trigger_event") != cls.TRIGGER:
        raise WireViolation(
            f"{name}: trigger_event {ev.get('trigger_event')!r} contradicts "
            f"the variant's row trigger {cls.TRIGGER!r} "
            f"(event_id {ev.get('event_id')!r}) — mis-tagged writer")
    want_to = kwargs.get("from_state") if cls.TO_STATE == "unchanged" else cls.TO_STATE
    if kwargs.get("to_state") != want_to:
        raise WireViolation(
            f"{name}: audit 'to' {ev.get('to')!r} contradicts the row's "
            f"{want_to!r} (event_id {ev.get('event_id')!r})")
    return cls(**kwargs)
'''

RUNTIME = '''
# ─── machine state values ────────────────────────────────────────────────────

@dataclass(frozen=True)
class MachineStateA:
    """Section-A state, with the disposition RECONCILED(d) is parameterized
    by (None everywhere else)."""

    name: SectionAState
    disposition: Optional[ReconcileDisposition] = None


@dataclass(frozen=True)
class MachineStateB:
    """Section-B state; RELEASED(d) carries its disposition."""

    name: SectionBState
    disposition: Optional[ReconcileDisposition] = None


GENESIS_A = MachineStateA(SectionAState.GENESIS)
GENESIS_B = MachineStateB(SectionBState.GENESIS)


def apply_section_a(state: MachineStateA, event: object) -> MachineStateA:
    """One §6.0 section-A step. Any pair outside the table raises
    IllegalTransitionError — never a silent no-op."""
    variant = type(event).__name__
    if EFFECT_VARIANTS.get(variant) is not type(event):
        raise IllegalTransitionError("section_a", state.name.value, variant,
                                     "unknown event variant halts (§9)")
    if state.name.value not in event.FROM_STATES:
        raise IllegalTransitionError("section_a", state.name.value, variant)
    if isinstance(event, ReconcileReplayIdentity):
        if state.disposition is not event.disposition:
            # RECONCILED(d) × operator_reconcile(d′ ≠ d) ⇒ ILLEGAL.
            raise IllegalTransitionError(
                "section_a", state.name.value, variant,
                f"conflicting disposition {event.disposition} vs {state.disposition}")
        return state
    if isinstance(event, ReconcileAccept):
        return MachineStateA(SectionAState.RECONCILED, event.disposition)
    if isinstance(event, ReconcileRejectRestoreHold):
        return MachineStateA(SectionAState.HELD)  # stays HELD, assessment recorded
    return MachineStateA(SectionAState[event.TO_STATE])


def apply_section_b(state: MachineStateB, event: object) -> MachineStateB:
    """One §6.0 section-B step (foreign door-0 machine)."""
    variant = type(event).__name__
    if HOLD_VARIANTS.get(variant) is not type(event):
        raise IllegalTransitionError("section_b", state.name.value, variant,
                                     "unknown event variant halts (§9)")
    if state.name.value not in event.FROM_STATES:
        raise IllegalTransitionError("section_b", state.name.value, variant)
    if isinstance(event, (ObserveDeltaRedelivery, ObserveDeltaNewDeliveryOnOpenHold)):
        return state  # unchanged — idempotent no-op / delivery recorded
    if isinstance(event, ActorVerifiedAuto):
        # Defense in depth: construction already enforces SEPARATED +
        # VERIFIED_API + node id + matched subject (§6.0: under SHARED, never).
        if event.mode is not CredentialMode.SEPARATED:
            raise IllegalTransitionError(
                "section_b", state.name.value, variant,
                "ACTOR_VERIFIED_AUTO requires SEPARATED; under SHARED, never")
        return MachineStateB(SectionBState.RELEASED,
                             ReconcileDisposition.ACTOR_VERIFIED_AUTO)
    if isinstance(event, HoldReconcileReplayIdentity):
        if state.disposition is not event.disposition:
            raise IllegalTransitionError(
                "section_b", state.name.value, variant,
                f"conflicting disposition {event.disposition} vs {state.disposition}")
        return state
    if isinstance(event, HoldReconcileAccept):
        return MachineStateB(SectionBState.RELEASED, event.disposition)
    if isinstance(event, HoldReconcileRejectRestoreHold):
        # "as the HELD_FOREIGN rows"; from STANDING the resolved reading is
        # schema-driven (STANDING_REJECT_RESTORE_TARGET_NAME — the single
        # place to change if the author ratifies the other reading).
        if state.name is SectionBState.STANDING:
            return MachineStateB(SectionBState[STANDING_REJECT_RESTORE_TARGET_NAME])
        return MachineStateB(SectionBState.HELD_FOREIGN)
    if isinstance(event, HoldReconcileStanding):
        return MachineStateB(SectionBState.STANDING)
    return MachineStateB(SectionBState[event.TO_STATE])


# ─── derivations (schema-pinned preimages; components newline-free) ─────────

def _preimage(lines: Sequence[str]) -> str:
    """Tagged newline-joined preimage; injective only over newline-free
    components, so a newline in any component is rejected, never coerced."""
    for line in lines:
        _, _, component = line.partition("=")
        if "\\n" in component:
            raise ValueError(f"newline in preimage component {line!r} — "
                             f"non-injective; rejected, never coerced")
    return "\\n".join(lines)


def derive_hold_id(base_key: str, ref: str, delta_old_oid: str,
                   delta_new_oid: str, occurrence_seq: int) -> str:
    """§6.0 hold_id derivation over the schema's tagged newline-joined
    preimage (injective: components validated newline-free)."""
    preimage = _preimage([
        f"base={base_key}", f"ref={ref}", f"old={delta_old_oid}",
        f"new={delta_new_oid}", f"seq={occurrence_seq}"])
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def derive_recovery_event_id(base_key: str, movement_id: str) -> str:
    """Deterministic event_id for the cold-start crash_recovery dual-append
    — two concurrent recoveries mint the SAME id and converge through the
    duplicate-event_id dedup instead of halting the base."""
    preimage = _preimage([
        "recovery=crash_recovery", f"base={base_key}", f"movement={movement_id}"])
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def derive_matched_delta_digest(base_key: str, ref: str, delta_old_oid: str,
                                delta_new_oid: str) -> str:
    """The PR0 consistency digest binding an ACTOR_VERIFIED_AUTO release to
    the HOLD'S OWN recorded delta (schema actor_verified_evidence). PR4's
    webhook protocol supplies provenance; this digest makes self-asserted
    evidence structurally checkable NOW."""
    preimage = _preimage([
        f"subject-base={base_key}", f"subject-ref={ref}",
        f"subject-old={delta_old_oid}", f"subject-new={delta_new_oid}"])
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


# ─── §9 shared objects (generated from schema shared_objects) ───────────────

@dataclass(frozen=True)
class RequiredClassifier:
    """ClassifierAuthority REQUIRED variant — exact-variant equality at the
    fence is dataclass equality over the closed union."""

    config_sha256: str
    producer_digest: str
    contract: str

    def line(self) -> str:
        return f"required:{self.config_sha256}:{self.producer_digest}:{self.contract}"


@dataclass(frozen=True)
class LegacyNoClassifier:
    """ClassifierAuthority LEGACY variant — constructible only by the LEGACY
    factory (PR2); never compares equal to any RequiredClassifier."""

    def line(self) -> str:
        return "legacy"


ClassifierAuthority = (RequiredClassifier, LegacyNoClassifier)


@dataclass(frozen=True)
class AuthorityFingerprint:
    """§9: one generated object the §6.0 fence compares; the classifier sum
    carries digests/contract in the REQUIRED variant."""

    protocol_epoch: str
    base_epoch: str
    subject_digest: str
    roster_digest: str
    classifier: object

    def __post_init__(self) -> None:
        if not isinstance(self.classifier, ClassifierAuthority):
            raise ValueError(
                f"AuthorityFingerprint.classifier must be a ClassifierAuthority "
                f"variant, got {type(self.classifier).__name__}")


def subject_digest(*, repo_node_id: str, target: str, base_oid: str,
                   head_oid: str, diff_sha256: str, classifier: object,
                   unit_digest: Optional[str] = None) -> str:
    """§9 canonical subject_digest preimage — exact tag bytes, UTF-8 lines,
    newline-joined, SHA-256. `target` is the full target line
    (`pr:<pr_node_id>:<target_ref>` or `ref:<target_ref>` — build with
    target_pr()/target_ref())."""
    if not isinstance(classifier, ClassifierAuthority):
        raise ValueError("subject_digest: classifier must be a "
                         "ClassifierAuthority variant")
    preimage = _preimage([
        f"repo={repo_node_id}", f"target={target}", f"base={base_oid}",
        f"head={head_oid}", f"diff={diff_sha256}",
        f"classifier={classifier.line()}",
        f"unit={unit_digest if unit_digest is not None else 'none'}"])
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def target_pr(pr_node_id: str, target_ref: str) -> str:
    """PR subjects carry BOTH fields — a retarget changes the digest."""
    return f"pr:{pr_node_id}:{target_ref}"


def target_ref(ref: str) -> str:
    return f"ref:{ref}"


# ─── reducers (T19 skeletons; PR4 hardens against live carriers) ────────────

def _canonical(d: Mapping[str, object]) -> str:
    """Byte-identity core for duplicate-event_id comparison. `branch` (which
    carrier copy) and the per-ISSUER envelope fields ts/run_id/trace_id are
    excluded so independently-issued twins of a DERIVED event (cold-start
    recovery) converge; every semantic field still diverges loudly."""
    drop = {"branch", "ts", "run_id", "trace_id"}
    return json.dumps({k: v for k, v in d.items() if k not in drop},
                      sort_keys=True, separators=(",", ":"))


def _halt(code: BoundaryErrorCode, detail: str,
          ev: Optional[Mapping[str, object]] = None) -> dict:
    """Uniform halt payload: code decides, detail names the offending
    epochs/event_ids (3am test), run/trace ids correlate back to the
    evidence, metric is ready to increment."""
    return {"code": code.value, "detail": detail,
            "metric": ERROR_METRIC[code],
            "run_id": None if ev is None else ev.get("run_id"),
            "trace_id": None if ev is None else ev.get("trace_id")}


class _DivergentDuplicate(Exception):
    def __init__(self, halt: dict, bases: frozenset):
        super().__init__(halt["detail"])
        self.halt = halt
        self.bases = bases


class _Dedup:
    """Duplicate-event_id absorption with byte-identical enforcement —
    divergence is an integrity violation (EVENT_PAYLOAD_DIVERGENT) that
    halts EVERY base a copy touched (cross-base reuse is not
    order-dependent). Shared by both reducers AND the epoch fold."""

    def __init__(self) -> None:
        self._seen: dict[str, tuple[str, str]] = {}

    def check(self, ev: Mapping[str, object], base: str) -> str:
        """'new' | 'dup'; raises _DivergentDuplicate on divergence or a
        missing envelope event_id."""
        eid = ev.get("event_id")
        if not isinstance(eid, str) or eid == "":
            raise _DivergentDuplicate(_halt(
                BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                f"event missing required envelope field 'event_id' "
                f"(fields present: {sorted(ev)})", ev), frozenset({base}))
        canon = _canonical(ev)
        if eid in self._seen:
            seen_canon, seen_base = self._seen[eid]
            if seen_canon != canon:
                raise _DivergentDuplicate(_halt(
                    BoundaryErrorCode.EVENT_PAYLOAD_DIVERGENT,
                    f"event_id {eid!r} has divergent payloads — integrity "
                    f"violation, halt this base", ev),
                    frozenset({base, seen_base}))
            return "dup"
        self._seen[eid] = (canon, base)
        return "new"


def _per_base_counts(events: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ev in events:
        base = str(ev.get("base_key") or "")
        counts[base] = counts.get(base, 0) + 1
    return counts


def _ceiling_halts(events: Sequence[Mapping[str, object]]) -> dict[str, dict]:
    """RECOVERY_CEILING per base_key — one busy base never halts another."""
    return {base: _halt(BoundaryErrorCode.RECOVERY_CEILING,
                        f"{base or '<no base_key>'}: {n} events exceed the "
                        f"recovery admission ceiling ({RECOVERY_CEILING_EVENTS})")
            for base, n in _per_base_counts(events).items()
            if n > RECOVERY_CEILING_EVENTS}


def _intake(dedup: _Dedup, ev: Mapping[str, object], family: str,
            variants: Mapping[str, type], base_halts: dict[str, dict]):
    """Shared reducer intake: family filter (§6.0 — 'each reduce filters by
    event schema name'; missing family is a schema violation, the OTHER
    family is filtered, not halted), dedup, fail-closed construction.
    Returns the typed event, or None when the event was consumed (dup /
    other family / halt recorded)."""
    base_hint = str(ev.get("base_key") or "")
    if base_hint in base_halts:
        return None  # base already halted — isolation, not suppression
    fam = ev.get("family")
    if fam is None:
        base_halts.setdefault(base_hint, _halt(
            BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
            f"event missing required field 'family' — the reduce filters by "
            f"event schema name (§6.0) (event_id {ev.get('event_id')!r})", ev))
        return None
    if fam != family:
        return None  # the other stream's events on a shared carrier
    try:
        if dedup.check(ev, base_hint) == "dup":
            return None  # dual-append twin / redelivered copy
        return build_wire_event(variants, ev)
    except _DivergentDuplicate as exc:
        for b in exc.bases:
            base_halts.setdefault(b, exc.halt)
    except WireViolation as exc:
        base_halts.setdefault(base_hint, _halt(exc.code, exc.detail, ev))
    except ValueError as exc:
        base_halts.setdefault(base_hint, _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION, str(exc), ev))
    return None


def _fmt_a(st: MachineStateA, via_recovery: bool = False) -> dict:
    return {"state": st.name.value,
            "disposition": st.disposition.value if st.disposition else None,
            "via_recovery_append": via_recovery}


def reduce_section_a(events: Sequence[Mapping[str, object]]) -> dict:
    """Reduce a durable effect_lifecycle stream through the PROJECTION
    machine (durable states + composed edges), never the live table
    (round 14, codex) — reconcile steps, whose durable states ARE live
    states, delegate to apply_section_a.

    Halt isolation is PER base_key: one bad base's halt never suppresses
    results or recovery appends for healthy bases, and the recovery
    admission ceiling is counted per base. Result shape is uniform:
    {movements, recovery_appends, halts} with halts == {} when clean and
    partial reduced state present for halted bases.

    Cold-start step (5): an open PREPARED with no hold and no terminal gets
    a dual-appended {crash_recovery, PREPARED → HELD} with a DERIVED
    event_id; resume-submit is ILLEGAL (round 15, grok)."""
    movements: dict[str, dict[str, MachineStateA]] = {}
    order: list[tuple[str, str]] = []
    base_halts: dict[str, dict] = _ceiling_halts(events)
    dedup = _Dedup()
    for ev in events:
        event = _intake(dedup, ev, "effect_lifecycle", EFFECT_VARIANTS, base_halts)
        if event is None:
            continue
        base, mid = event.base_key, event.movement_id
        if base in base_halts:
            continue
        halt = _step_section_a(movements, order, base, mid, event, ev)
        if halt is not None:
            base_halts[base] = halt
    return _finish_section_a(movements, order, base_halts)


def _step_section_a(movements, order, base: str, mid: str, event: object,
                    ev: Mapping[str, object]) -> Optional[dict]:
    cls = type(event)
    if cls.TO_STATE in MEMORY_ONLY:
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"memory-only transition {cls.__name__!r} in the durable stream "
            f"(event_id {ev.get('event_id')!r}) — resume-submit is ILLEGAL", ev)
    if cls.EPOCH_EFFECT == "none" and event.epoch_before != event.epoch_after:
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"movement {mid}@{base}: row {cls.ROW!r} declares no epoch effect "
            f"but the event advances {event.epoch_before}→{event.epoch_after} "
            f"(event_id {ev.get('event_id')!r})", ev)
    cur = movements.get(base, {}).get(mid, GENESIS_A)
    if mid not in movements.get(base, {}):
        movements.setdefault(base, {})[mid] = GENESIS_A
        order.append((base, mid))
    # projection validation: audit `from` must sit on a composed path out
    # of the current durable state, and the durable pair must be an edge.
    frontier = PROJECTION_REACHABLE.get(cur.name.value, ())
    if event.from_state not in frontier:
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"movement {mid}@{base}: durable {cls.__name__!r} audit "
            f"from={event.from_state!r} unreachable from durable state "
            f"{cur.name.value} (event_id {ev.get('event_id')!r})", ev)
    if (cur.name.value, cls.TO_STATE) not in PROJECTION_EDGES:
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"movement {mid}@{base}: no projection edge "
            f"{cur.name.value} → {cls.TO_STATE} "
            f"({cls.__name__!r}, event_id {ev.get('event_id')!r})", ev)
    if cls.TRIGGER == "operator_reconcile":
        # durable HELD/RECONCILED are live states — delegate to the one
        # live-table dispatch instead of re-implementing it.
        try:
            movements[base][mid] = apply_section_a(cur, event)
        except IllegalTransitionError as exc:
            return _halt(BoundaryErrorCode.ILLEGAL_TRANSITION, str(exc), ev)
    else:
        movements[base][mid] = MachineStateA(SectionAState[cls.TO_STATE])
    return None


def _finish_section_a(movements, order, base_halts) -> dict:
    out: dict[str, dict] = {}
    recovery: list[dict] = []
    for base, mid in order:
        st = movements[base][mid]
        if base not in base_halts and st.name is SectionAState.PREPARED:
            recovery.append({
                "event_id": derive_recovery_event_id(base, mid),
                "movement_id": mid, "base_key": base,
                "trigger_event": "crash_recovery",
                "from": "PREPARED", "to": "HELD"})
            out.setdefault(base, {})[mid] = _fmt_a(
                MachineStateA(SectionAState.HELD), via_recovery=True)
        else:
            out.setdefault(base, {})[mid] = _fmt_a(st)
    return {"movements": out, "recovery_appends": recovery, "halts": base_halts}


class _HoldBook:
    """Per-base section-B bookkeeping: the §6.0 observe_delta apply order
    needs the delivery index, the open holds by delta tuple, and the
    terminal count that feeds occurrence_seq."""

    def __init__(self) -> None:
        self.delivery_index: dict[str, str] = {}
        self.open_by_delta: dict[tuple, str] = {}
        self.terminal_count: dict[tuple, int] = {}
        self.holds: dict[str, MachineStateB] = {}
        self.hold_delta: dict[str, tuple] = {}
        self.deliveries: dict[str, list[str]] = {}
        self.order: list[str] = []


def _resolve_observe_delta(book: _HoldBook, base: str, event: object) -> tuple[str, str]:
    """§6.0 apply order: (1) lookup by source_delivery_id → the no-op row;
    (2) else lookup an OPEN hold for the delta tuple → record the delivery
    on it; (3) else derive hold_id via occurrence_seq → create."""
    sdid = event.source_delivery_id
    delta = (event.ref, event.delta_old_oid, event.delta_new_oid)
    if sdid is not None and sdid in book.delivery_index:
        return "redelivery", book.delivery_index[sdid]
    if None not in delta and delta in book.open_by_delta:
        return "record", book.open_by_delta[delta]
    seq = book.terminal_count.get(delta, 0)
    return "create", derive_hold_id(base, event.ref or "",
                                    event.delta_old_oid or "",
                                    event.delta_new_oid or "", seq)


_OBSERVE_EXPECTED = {"redelivery": "ObserveDeltaRedelivery",
                     "record": "ObserveDeltaNewDeliveryOnOpenHold",
                     "create": "ObserveDelta"}


def _admit_hold_event(book: _HoldBook, base: str, event: object,
                      ev: Mapping[str, object]):
    """Resolve which hold an event addresses: the §6.0 apply order for
    observe_delta (mis-tagged variants, contradicted hold_ids AND
    contradicted delta tuples halt), reference lookup for actor/reconcile
    events (unknown holds halt). Returns (hid, cur, halt)."""
    cls = type(event)
    if cls.TRIGGER == "observe_delta":
        resolution, hid = _resolve_observe_delta(book, base, event)
        if cls.__name__ != _OBSERVE_EXPECTED[resolution]:
            return None, None, _halt(
                BoundaryErrorCode.ILLEGAL_TRANSITION,
                f"apply order resolves {resolution!r} (hold {hid}) but "
                f"the event is tagged {cls.__name__!r} "
                f"(event_id {ev.get('event_id')!r})", ev)
        if event.hold_id is not None and event.hold_id != hid:
            return None, None, _halt(
                BoundaryErrorCode.ILLEGAL_TRANSITION,
                f"declared hold_id {event.hold_id!r} contradicts the "
                f"derived/resolved {hid!r} "
                f"(event_id {ev.get('event_id')!r})", ev)
        if resolution in ("redelivery", "record"):
            halt = _check_delta_against_hold(book, hid, event, ev)
            if halt is not None:
                return None, None, halt
        return hid, book.holds.get(hid, GENESIS_B), None
    hid = event.hold_id
    cur = book.holds.get(hid)
    if cur is None:
        return None, None, _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"{cls.__name__!r} references unknown hold {hid!r} "
            f"(event_id {ev.get('event_id')!r})", ev)
    return hid, cur, None


def _check_delta_against_hold(book: _HoldBook, hid: str, event: object,
                              ev: Mapping[str, object]) -> Optional[dict]:
    """A redelivery/record whose DECLARED delta contradicts the hold its
    source_delivery_id resolves to is an integrity halt — never absorbed as
    a no-op (fail-open otherwise)."""
    recorded = book.hold_delta.get(hid)
    if recorded is None:
        return None
    declared = (event.ref, event.delta_old_oid, event.delta_new_oid)
    for name, decl, rec in zip(("ref", "delta_old_oid", "delta_new_oid"),
                               declared, recorded):
        if decl is not None and rec is not None and decl != rec:
            return _halt(
                BoundaryErrorCode.ILLEGAL_TRANSITION,
                f"hold {hid}: declared {name} {decl!r} contradicts the "
                f"hold's recorded delta {rec!r} "
                f"(event_id {ev.get('event_id')!r})", ev)
    return None


def _check_actor_verified(book: _HoldBook, base: str, hid: str, event: object,
                          ev: Mapping[str, object]) -> Optional[dict]:
    """PR0's structurally-possible ACTOR_VERIFIED_AUTO cross-checks (schema
    actor_verified_evidence): the release's source_delivery_id must resolve
    to a delivery recorded ON this hold, and matched_subject_digest must
    equal the digest derived from the HOLD'S OWN recorded delta. These
    validate CONSISTENCY, not provenance — the §6.0 webhook verification
    protocol that establishes provenance is wired in PR4; under SHARED the
    mode gate already refuses the release."""
    if event.source_delivery_id not in book.deliveries.get(hid, []):
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"hold {hid}: ACTOR_VERIFIED_AUTO source_delivery_id "
            f"{event.source_delivery_id!r} is not a delivery recorded on "
            f"this hold — self-asserted evidence refused "
            f"(event_id {ev.get('event_id')!r})", ev)
    ref, old, new = book.hold_delta[hid]
    want = derive_matched_delta_digest(base, ref or "", old or "", new or "")
    if event.matched_subject_digest != want:
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"hold {hid}: matched_subject_digest does not derive from the "
            f"hold's recorded delta — self-asserted evidence refused "
            f"(event_id {ev.get('event_id')!r})", ev)
    return None


def _record_hold_outcome(book: _HoldBook, hid: str, event: object,
                         cur: MachineStateB, new: MachineStateB) -> None:
    """Bookkeeping after a legal step: creation registers the delta tuple
    as open; a first-seen source_delivery_id is indexed; a transition INTO
    RELEASED closes the delta and feeds occurrence_seq."""
    if hid not in book.holds:
        book.order.append(hid)
        book.hold_delta[hid] = (event.ref, event.delta_old_oid,
                                event.delta_new_oid)
        book.open_by_delta[book.hold_delta[hid]] = hid
    sdid = getattr(event, "source_delivery_id", None)
    if sdid is not None and sdid not in book.delivery_index:
        book.delivery_index[sdid] = hid
        book.deliveries.setdefault(hid, []).append(sdid)
    if cur.name is not SectionBState.RELEASED and new.name is SectionBState.RELEASED:
        delta = book.hold_delta.get(hid)
        book.open_by_delta.pop(delta, None)
        book.terminal_count[delta] = book.terminal_count.get(delta, 0) + 1
    book.holds[hid] = new


def reduce_section_b(events: Sequence[Mapping[str, object]]) -> dict:
    """Reduce a hold_lifecycle stream into section-B states per
    (base_key, hold_id), implementing §6.0's observe_delta apply order and
    hold_id derivation for real. Halt isolation and ceiling are PER
    base_key (uniform shape: {holds, halts}).

    ACTOR_VERIFIED_AUTO releases are cross-checked against the hold's own
    record (delivery membership + delta-derived digest) — this reducer
    validates CONSISTENCY, not provenance; provenance is PR4's webhook
    protocol (schema actor_verified_evidence). Redelivery semantics
    (rounds 17–20): same source_delivery_id ⇒ same hold regardless of
    state; the no-op rows are state-independent, so their audit `from` is
    validated against FROM_STATES only (a reconcile racing the append must
    not turn an idempotent no-op into a halt)."""
    books: dict[str, _HoldBook] = {}
    base_order: list[str] = []
    base_halts: dict[str, dict] = _ceiling_halts(events)
    dedup = _Dedup()
    for ev in events:
        event = _intake(dedup, ev, "hold_lifecycle", HOLD_VARIANTS, base_halts)
        if event is None:
            continue
        base = event.base_key
        if base in base_halts:
            continue
        book = books.get(base)
        if book is None:
            book = books[base] = _HoldBook()
            base_order.append(base)
        halt = _step_section_b(book, base, event, ev)
        if halt is not None:
            base_halts[base] = halt
    out: dict[str, dict] = {}
    for base in base_order:
        book = books[base]
        out[base] = {
            hid: {"state": book.holds[hid].name.value,
                  "disposition": (book.holds[hid].disposition.value
                                  if book.holds[hid].disposition else None),
                  "deliveries": book.deliveries.get(hid, [])}
            for hid in book.order}
    return {"holds": out, "halts": base_halts}


def _step_section_b(book: _HoldBook, base: str, event: object,
                    ev: Mapping[str, object]) -> Optional[dict]:
    cls = type(event)
    if cls.EPOCH_EFFECT == "none" and event.epoch_before != event.epoch_after:
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"{base}: row {cls.ROW!r} declares no epoch effect but the event "
            f"advances {event.epoch_before}→{event.epoch_after} "
            f"(event_id {ev.get('event_id')!r})", ev)
    hid, cur, halt = _admit_hold_event(book, base, event, ev)
    if halt is not None:
        return halt
    # The `unchanged` no-op rows are state-independent by design — their
    # audit `from` is already constrained to FROM_STATES at construction;
    # every state-changing row must name the reduced state exactly.
    if cls.TO_STATE != "unchanged" and event.from_state != cur.name.value:
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"hold {hid}: audit from={event.from_state!r} contradicts the "
            f"reduced state {cur.name.value} "
            f"(event_id {ev.get('event_id')!r})", ev)
    if isinstance(event, ActorVerifiedAuto):
        halt = _check_actor_verified(book, base, hid, event, ev)
        if halt is not None:
            return halt
    try:
        new = apply_section_b(cur, event)
    except IllegalTransitionError as exc:
        return _halt(BoundaryErrorCode.ILLEGAL_TRANSITION, str(exc), ev)
    _record_hold_outcome(book, hid, event, cur, new)
    return None


def fold_epochs(events: Sequence[Mapping[str, object]],
                anchors: Mapping[str, str]) -> dict:
    """The §6.0 recovery-step-(3) epoch fold, per base_key. Edges are only
    epoch-ADVANCING transitions, but EVERY event with an event_id is
    registered for dedup FIRST — a divergent no-effect twin halts instead
    of silently advancing, and a cross-base reuse halts every base a copy
    touched. Halt isolation and the recovery ceiling are per base; a base
    with edges but no anchor is a typed halt on every path (ceiling
    included), and a ceiling breach with empty anchors still returns an
    explicit halt entry — never {} silently."""
    base_halts: dict[str, dict] = _ceiling_halts(events)
    dedup = _Dedup()
    edges_by_base: dict[str, list[Mapping[str, object]]] = {}
    for ev in events:
        base = str(ev.get("base_key") or "")
        if base in base_halts:
            continue
        # dedup BEFORE the no-effect filter (panel round 2: a divergent
        # duplicate must never slip in as a legitimate edge).
        try:
            if dedup.check(ev, base) == "dup":
                continue  # carrier copies of one advance share an event_id
        except _DivergentDuplicate as exc:
            for b in exc.bases:
                base_halts.setdefault(b, exc.halt)
            continue
        eb, ea = ev.get("epoch_before"), ev.get("epoch_after")
        if eb is None or ea is None or eb == ea:
            continue  # no-effect pairs are not edges (round 16, codex)
        if not base:
            base_halts.setdefault("", _halt(
                BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                f"epoch edge missing base_key "
                f"(event_id {ev.get('event_id')!r})", ev))
            continue
        edges_by_base.setdefault(base, []).append(ev)
    out: dict[str, dict] = {}
    for base in sorted(set(anchors) | set(edges_by_base) | set(base_halts)):
        if base in base_halts:
            out[base] = {"status": "halt", "epoch": anchors.get(base),
                         "halt": base_halts[base]}
            continue
        edges = edges_by_base.get(base, [])
        anchor = anchors.get(base)
        if anchor is None:
            first = min(edges, key=lambda e: str(e["event_id"]))
            out[base] = {"status": "halt", "epoch": None, "halt": _halt(
                BoundaryErrorCode.EPOCH_GAP,
                f"{base}: {len(edges)} epoch edge(s) but no protocol_genesis "
                f"anchor (first {first['event_id']} "
                f"{first['epoch_before']}→{first['epoch_after']}) — never "
                f"silently dropped", first)}
            continue
        out[base] = _walk_epoch_chain(base, anchor, edges)
    return out


def _walk_epoch_chain(base: str, anchor: str,
                      edges: Sequence[Mapping[str, object]]) -> dict:
    buckets: dict[str, list[Mapping[str, object]]] = {}
    for e in edges:
        buckets.setdefault(str(e["epoch_before"]), []).append(e)
    current, visited, consumed = anchor, {anchor}, 0
    while True:
        cand = buckets.get(current, [])
        if len(cand) > 1:
            forks = ", ".join(
                f"{e['event_id']}→{e['epoch_after']}"
                for e in sorted(cand, key=lambda e: str(e["event_id"])))
            return {"status": "halt", "epoch": current, "halt": _halt(
                BoundaryErrorCode.EPOCH_FORK,
                f"{base}: fork at {current} — candidates: {forks}", cand[0])}
        if not cand:
            if consumed < len(edges):
                orphans = [e for b in buckets.values() for e in b]
                first = min(orphans, key=lambda e: str(e["event_id"]))
                return {"status": "halt", "epoch": current, "halt": _halt(
                    BoundaryErrorCode.EPOCH_GAP,
                    f"{base}: {len(orphans)} unused edge(s) at tail {current} "
                    f"— first orphan {first['event_id']} "
                    f"{first['epoch_before']}→{first['epoch_after']}", first)}
            return {"status": "ok", "epoch": current, "halt": None}
        edge = cand[0]
        buckets[current] = []
        consumed += 1
        nxt = str(edge["epoch_after"])
        if nxt in visited:
            return {"status": "halt", "epoch": current, "halt": _halt(
                BoundaryErrorCode.EPOCH_FORK,
                f"{base}: cycle/reused epoch {nxt} "
                f"(event {edge['event_id']})", edge)}
        visited.add(nxt)
        current = nxt
'''

PANEL_RUNTIME = '''
def roster_digest(roster_version: str, ordered_seat_ids: Sequence[str],
                  designated_single_id: str) -> str:
    """Canonical roster-digest preimage: roster_version ‖ ordered seat IDs ‖
    designated_single_id, newline-joined, SHA-256 (§5.1). Newline-joining is
    injective only over newline-free components — validated, never coerced."""
    parts = [roster_version, *ordered_seat_ids, designated_single_id]
    for part in parts:
        if "\\n" in part:
            raise ValueError(
                f"newline in roster preimage component {part!r} — two "
                f"different rosters would hash equal; rejected")
    return hashlib.sha256("\\n".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RosterSnapshot:
    """§5.1: {manifest_digest, roster_version, roster_digest,
    ordered_seat_ids, designated_single_id}. The constructor VERIFIES
    roster_digest against the canonical digest of its own fields — a
    snapshot carrying an arbitrary digest string is unconstructible."""

    manifest_digest: str
    roster_version: str
    roster_digest: str
    ordered_seat_ids: tuple[str, ...]
    designated_single_id: str

    def __post_init__(self) -> None:
        # the digest binds ordered_seat_ids, so the field must be an
        # immutable COPY — a caller-owned list could be mutated out from
        # under a verified digest.
        if not isinstance(self.ordered_seat_ids, tuple):
            object.__setattr__(self, "ordered_seat_ids",
                               tuple(self.ordered_seat_ids))
        if self.designated_single_id not in self.ordered_seat_ids:
            raise ValueError("designated_single_id must be a roster seat")
        if len(set(self.ordered_seat_ids)) != len(self.ordered_seat_ids):
            raise ValueError("duplicate seat ids in roster")
        expected = roster_digest(self.roster_version, self.ordered_seat_ids,
                                 self.designated_single_id)
        if self.roster_digest != expected:
            raise ValueError(
                f"roster_digest {self.roster_digest!r} does not equal the "
                f"canonical digest {expected!r} of this snapshot's fields")


@dataclass(frozen=True)
class Finding:
    severity: Severity

    def __post_init__(self) -> None:
        if not isinstance(self.severity, Severity):
            raise ValueError(f"Finding.severity must be a Severity, "
                             f"got {self.severity!r}")


@dataclass(frozen=True)
class SeatOutcome:
    verdict: SeatVerdict
    findings: tuple[Finding, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.verdict, SeatVerdict):
            raise ValueError(f"SeatOutcome.verdict must be a SeatVerdict, "
                             f"got {self.verdict!r}")
        if not all(isinstance(f, Finding) for f in self.findings):
            raise ValueError("SeatOutcome.findings must be Finding instances")


@dataclass(frozen=True)
class UnparseableOutcome:
    """A seat result whose verdict or a finding severity fell outside the
    closed domains — a parse failure ⇒ INCOMPLETE, never skipped."""

    raw: str = ""


@dataclass(frozen=True)
class SeatResultRecord:
    """One seat's result keyed the way §5.1 requires: (subject_digest,
    attempt_id) — two attempts on an identical subject must not interleave
    (rounds 17–18)."""

    seat_id: str
    subject_digest: str
    attempt_id: str
    outcome: object


def required_seats(intensity: PanelIntensity, roster: RosterSnapshot) -> tuple[str, ...]:
    """required_seats(FULL) = all roster seats; required_seats(SINGLE) =
    {designated_single_id}; SKIP demands no seats (§5.1/§5.2). The dispatch
    is EXHAUSTIVE with a raising else arm: a raw int (PanelIntensity is an
    IntEnum, so `2 == FULL` compares true), a string or None must never
    fall through to the permissive zero-seat value, which aggregate maps to
    NOT_APPLICABLE and §5.2 routes to a gate-satisfying satisfaction."""
    if intensity is PanelIntensity.FULL:
        return tuple(roster.ordered_seat_ids)
    if intensity is PanelIntensity.SINGLE:
        return (roster.designated_single_id,)
    if intensity is PanelIntensity.SKIP:
        return ()
    raise TypeError(f"required_seats(): {intensity!r} is not a PanelIntensity "
                    f"member — the intensity domain is closed")


def blocking(outcome: object) -> bool:
    """blocking(outcome) ⟺ verdict == BLOCK ∨ ∃ finding with severity ∈
    {CRITICAL, HIGH} — over the closed outcome union, dispatched
    exhaustively: an UnparseableOutcome is a parse failure the aggregate
    turns into INCOMPLETE, and anything else raises — a structural
    lookalike is never counted, in either direction (explicit-state)."""
    if isinstance(outcome, UnparseableOutcome):
        return False
    if isinstance(outcome, SeatOutcome):
        if outcome.verdict in BLOCKING_VERDICTS:
            return True
        return any(f.severity in BLOCKING_SEVERITIES for f in outcome.findings)
    raise TypeError(f"blocking(): unknown seat-outcome type "
                    f"{type(outcome).__name__} — not a member of the closed "
                    f"SeatOutcome | UnparseableOutcome union")


def aggregate(intensity: PanelIntensity, roster: RosterSnapshot,
              outcomes: Mapping[str, object]) -> PanelAggregateResult:
    """§5.1's one total aggregate, executed by BOTH strategies, over seat
    results already filtered to the plan's (subject_digest, attempt_id) key
    (aggregate_seat_results does that filtering). Rule order is normative:
    zero required seats ⇒ NOT_APPLICABLE (a panel that evaluated nothing
    approves nothing — §5.2's SKIP satisfaction is NOT_REQUIRED, never
    approval); any required seat reporting a blocking finding ⇒ BLOCKED
    (unconditional in §5.1, so it decides even with another seat missing);
    outcome keys must equal required_seats exactly and a required seat
    unavailable or unparseable ⇒ INCOMPLETE, never skipped; otherwise
    APPROVED. A non-member outcome type raises — never counted, never
    approved."""
    required = required_seats(intensity, roster)
    for seat, outcome in outcomes.items():
        if not isinstance(outcome, (SeatOutcome, UnparseableOutcome)):
            raise TypeError(
                f"aggregate(): seat {seat!r} carries unknown outcome type "
                f"{type(outcome).__name__} — outside the closed union")
    if not required:
        return PanelAggregateResult.NOT_APPLICABLE
    if any(blocking(outcomes[s]) for s in required if s in outcomes):
        return PanelAggregateResult.BLOCKED
    if set(outcomes.keys()) != set(required):
        return PanelAggregateResult.INCOMPLETE
    if any(isinstance(outcomes[s], UnparseableOutcome) for s in required):
        return PanelAggregateResult.INCOMPLETE
    return PanelAggregateResult.APPROVED


def aggregate_seat_results(intensity: PanelIntensity, roster: RosterSnapshot,
                           subject_digest: str, attempt_id: str,
                           seat_results: Sequence[SeatResultRecord]) -> PanelAggregateResult:
    """The generated (subject_digest, attempt_id) filter in front of the
    aggregate: a seat result keyed to a different subject or attempt never
    reaches it (its absence surfaces as INCOMPLETE), and conflicting
    duplicate results for one seat are INCOMPLETE — evidence integrity,
    never last-write-wins."""
    outcomes: dict[str, object] = {}
    for record in seat_results:
        if not isinstance(record, SeatResultRecord):
            raise TypeError(f"aggregate_seat_results(): {type(record).__name__} "
                            f"is not a SeatResultRecord")
        if record.subject_digest != subject_digest or record.attempt_id != attempt_id:
            continue  # stale/foreign attempt — excluded, never counted
        if record.seat_id in outcomes and outcomes[record.seat_id] != record.outcome:
            return PanelAggregateResult.INCOMPLETE
        outcomes[record.seat_id] = record.outcome
    return aggregate(intensity, roster, outcomes)
'''


# ─── docs/generated markdown ─────────────────────────────────────────────────

def build_tables_md(s: dict) -> str:
    fsm = s["lifecycle_fsm"]
    out = ["# §6.0 state×event tables — GENERATED by tools/fsmgen.py",
           "",
           "Source: `schema/lifecycle_fsm.yaml`. CI diffs the cell content",
           "against the design doc's inline tables (normalized); the design",
           "and this artifact cannot drift apart silently.",
           ""]
    for sec_key, title in (("section_b", "Section B — foreign door-0 hold machine"),
                           ("section_a", "Section A — dispatcher-initiated effect machine")):
        sec = fsm[sec_key]
        out.append(f"## {title}")
        out.append("")
        out.append("| " + " | ".join(sec["table_header"]) + " |")
        out.append("|" + "---|" * len(sec["table_header"]))
        for row in sec["rows"]:
            out.append("| " + " | ".join(row["display"]) + " |")
        out.append("")
    return "\n".join(out)


def union_field_sets(fsm: dict) -> dict[str, list[str]]:
    """The union-of-variant-fields view of each §9 family (what the design's
    reading lists enumerate)."""
    out = {}
    for fam in ("effect_lifecycle", "hold_lifecycle"):
        spec = fsm["events"]["unions"][fam]
        fields = list(spec["common_required"]) + list(spec.get("common_optional", []))
        for v in spec["variants"]:
            for f in v.get("required", []):
                if f not in fields:
                    fields.append(f)
        out[fam] = fields
    return out


def build_unions_md(s: dict) -> str:
    fsm = s["lifecycle_fsm"]
    ev = fsm["events"]
    out = ["# §9 event unions — GENERATED by tools/fsmgen.py",
           "",
           "Source: `schema/lifecycle_fsm.yaml`. One variant per legal",
           "transition row; per-variant required payloads as §9 states.",
           "Every generated event type carries the common envelope.",
           ""]
    out.append("## Common envelope")
    out.append("")
    req = ", ".join(ev["envelope"]["required"])
    opt = ", ".join(f + "?" for f in ev["envelope"]["optional"])
    out.append(f"`{{{req}, {opt}}}`")
    out.append("")
    for fam in ("effect_lifecycle", "hold_lifecycle", "classification_evaluated"):
        spec = ev["unions"][fam]
        out.append(f"## `{fam}`")
        out.append("")
        if fam in ("effect_lifecycle", "hold_lifecycle"):
            fields = union_field_sets(fsm)[fam]
            out.append("Union of variant fields (reading view): `" +
                       ", ".join(fields) + "`")
            out.append("")
            out.append("| Variant | Row | Trigger | Extra required | Forbidden |")
            out.append("|---|---|---|---|---|")
            for v in spec["variants"]:
                out.append("| {name} | {row} | {trig} | {req} | {forb} |".format(
                    name=v["name"], row=v["row"], trig=v["trigger"],
                    req=", ".join(v.get("required", [])) or "—",
                    forb=", ".join(v.get("forbidden", [])) or "—"))
        else:
            out.append("| Variant | Required |")
            out.append("|---|---|")
            for v in spec["variants"]:
                out.append(f"| {v['name']} | {', '.join(v['required'])} |")
        out.append("")
    out.append("## Single-variant events")
    out.append("")
    out.append("| Event | Required | Optional |")
    out.append("|---|---|---|")
    for name, spec in ev["singles"].items():
        out.append("| `{n}` | {req} | {opt} |".format(
            n=name, req=", ".join(spec["required"]),
            opt=", ".join(spec.get("optional", [])) or "—"))
    out.append("")
    return "\n".join(out)


# ─── design-doc comparison (doc == artifact) ─────────────────────────────────

def _norm_cell(cell: str) -> str:
    cell = cell.replace("**", "").replace("`", "").replace("*", "")
    return " ".join(cell.split())


def _extract_md_tables(text: str) -> list[list[list[str]]]:
    tables, cur = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(set(c) <= {"-", " ", ":"} for c in cells):
                continue  # separator row
            cur.append(cells)
        else:
            if cur:
                tables.append(cur)
                cur = []
    if cur:
        tables.append(cur)
    return tables


def compare_tables_with_design(s: dict) -> list[str]:
    """Diff the generated §6.0 tables against the design's inline ones,
    cell-content-normalized (design §12: doc == artifact enforced)."""
    fsm = s["lifecycle_fsm"]
    design = DESIGN_DOC.read_text(encoding="utf-8")
    m = re.search(r"^### 6\.0 .*?$(.*?)^### 6\.1", design, re.M | re.S)
    if not m:
        return ["design doc: cannot locate §6.0"]
    tables = _extract_md_tables(m.group(1))
    if len(tables) < 2:
        return [f"design §6.0: expected 2 tables, found {len(tables)}"]
    problems = []
    for sec_key, table in (("section_b", tables[0]), ("section_a", tables[1])):
        sec = fsm[sec_key]
        want = [[_norm_cell(c) for c in [*sec["table_header"]]]] + [
            [_norm_cell(c) for c in row["display"]] for row in sec["rows"]]
        got = [[_norm_cell(c) for c in r] for r in table]
        if want != got:
            for i, (wrow, grow) in enumerate(zip(want, got)):
                if wrow != grow:
                    problems.append(f"{sec_key} row {i}: design={grow!r} schema={wrow!r}")
            if len(want) != len(got):
                problems.append(f"{sec_key}: row count design={len(got)} schema={len(want)}")
    return problems


_FIELD_LIST_RE = {
    # §9 reading lists: `name{fields}` (effect/hold lists are bolded in the doc).
    "effect_lifecycle": r"`effect_lifecycle\{(.*?)\}`",
    "hold_lifecycle": r"`hold_lifecycle\{(.*?)\}`",
    "panel_decided": r"`panel_decided\{(.*?)\}`",
    "merge_planned": r"`merge_planned\{(.*?)\}`",
    "approval_evaluated": r"`approval_evaluated\{(.*?)\}`",
    "authorization_granted": r"`authorization_granted\{(.*?)\}`",
    "consent": r"`consent\{(.*?)\}`",
    "protocol_genesis": r"`protocol_genesis\{(.*?)\}`",
    "merge_unit_declared": r"`merge_unit_declared\{(.*?)\}`",
    "merge_unit_member_added": r"`merge_unit_member_added\{(.*?)\}`",
    "protocol_epoch_advanced": r"`protocol_epoch_advanced\{(.*?)\}`",
    "panel_roster_declared": r"`panel_roster_declared\{(.*?)\}`",
    "panel_roster_augmented": r"`panel_roster_augmented\{(.*?)\}`",
    "seat_result": r"`seat_result\{(.*?)\}`",
}

# Where §9 writes prose inside a field list, the alias below maps it onto the
# schema field name (recorded here, not hidden in the comparator).
_FIELD_ALIASES = {"deciding contributions": "contributions"}


def _tokenize_fields(raw: str) -> set[str]:
    toks = set()
    for part in raw.split(","):
        part = part.split(":")[0]
        part = part.replace("`", "").replace("**", "").strip()
        part = part.rstrip("?").rstrip("…").strip()
        if not part:
            continue
        part = _FIELD_ALIASES.get(part, part)
        if " " in part:
            part = part.split()[-1]
        toks.add(part)
    return toks


def compare_unions_with_design(s: dict) -> list[str]:
    fsm = s["lifecycle_fsm"]
    design = DESIGN_DOC.read_text(encoding="utf-8")
    m = re.search(r"^## 9\. .*?$(.*?)^## 10\.", design, re.M | re.S)
    if not m:
        return ["design doc: cannot locate §9"]
    sect = m.group(1)
    problems = []
    unions = union_field_sets(fsm)
    singles = fsm["events"]["singles"]
    for name, pattern in _FIELD_LIST_RE.items():
        mm = re.search(pattern, sect, re.S)
        if not mm:
            problems.append(f"§9: no field list found for {name}")
            continue
        want = _tokenize_fields(mm.group(1))
        if name in unions:
            got = set(unions[name])
        else:
            spec = singles[name]
            got = set(spec["required"]) | set(spec.get("optional", []))
        if want != got:
            problems.append(
                f"§9 {name}: design fields {sorted(want)} != schema fields {sorted(got)}")
    for vname in ("CompleteClassification", "IncompleteClassification"):
        mm = re.search(vname + r"\{(.*?)\}", sect, re.S)
        if not mm:
            problems.append(f"§9: no field list for {vname}")
            continue
        want = _tokenize_fields(mm.group(1))
        spec = next(v for v in fsm["events"]["unions"]["classification_evaluated"]["variants"]
                    if v["name"] == vname)
        if want != set(spec["required"]):
            problems.append(f"§9 {vname}: design {sorted(want)} != schema {sorted(spec['required'])}")
    mm = re.search(r"common envelope `\{(.*?)\}`", sect, re.S)
    if not mm:
        problems.append("§9: no common envelope list")
    else:
        want = _tokenize_fields(mm.group(1))
        env = fsm["events"]["envelope"]
        got = set(env["required"]) | set(env["optional"])
        if want != got:
            problems.append(f"§9 envelope: design {sorted(want)} != schema {sorted(got)}")
    return problems


# ─── classifier frame vectors ────────────────────────────────────────────────

def build_frames(s: dict) -> dict[str, bytes]:
    proto = s["classifier_protocol"]
    policy = proto["vectors"]["policy_payload"].encode("utf-8")
    diff = proto["vectors"]["diff_payload"].encode("utf-8")
    policy_max = int(proto["bounds"]["policy_max_bytes"])
    diff_max = int(proto["bounds"]["diff_max_bytes"])

    def frame(policy_b: bytes, diff_b: bytes, version: int = 1) -> bytes:
        body = (struct.pack(">B", version)
                + struct.pack(">Q", len(policy_b)) + policy_b
                + struct.pack(">Q", len(diff_b)) + diff_b)
        return struct.pack(">I", len(body)) + body

    def with_policy_len(policy_len: int) -> bytes:
        """Declared policy_len is a lie; outer_len stays consistent with the
        actual octets — isolates the length/bound checks."""
        body = (struct.pack(">B", 1)
                + struct.pack(">Q", policy_len) + policy
                + struct.pack(">Q", len(diff)) + diff)
        return struct.pack(">I", len(body)) + body

    def with_diff_len(diff_len: int) -> bytes:
        body = (struct.pack(">B", 1)
                + struct.pack(">Q", len(policy)) + policy
                + struct.pack(">Q", diff_len) + diff)
        return struct.pack(">I", len(body)) + body

    valid = frame(policy, diff)
    body = valid[4:]
    # TRAILING_BYTES: outer_len CONSISTENT (it counts the extra octets) but
    # octets remain inside the body after the last declared field — distinct
    # from trailing_data.bin, which breaks the outer-length equality first.
    inner_trailing_body = body + b"PAD!"
    return {
        "valid_frame.bin": valid,
        "trailing_bytes.bin": (struct.pack(">I", len(inner_trailing_body))
                               + inner_trailing_body),
        # policy_len exceeds the frame's remaining octets (within bounds)
        "malformed_length.bin": with_policy_len(len(policy) + 4096),
        "truncation.bin": valid[: len(valid) - 7],
        "trailing_data.bin": valid + b"EXTRA",
        "empty_frame.bin": struct.pack(">I", 0),
        "short_outer_len.bin": b"\x00\x00",
        "cut_in_policy_len.bin": struct.pack(">I", 5) + body[:5],
        "cut_in_diff_len.bin": (struct.pack(">I", 1 + 8 + len(policy) + 3)
                                + body[: 1 + 8 + len(policy) + 3]),
        "bad_version.bin": frame(policy, diff, version=2),
        "inner_diff_truncation.bin": with_diff_len(len(diff) + 64),
        "policy_over_bound.bin": with_policy_len(policy_max * 2),
        "diff_over_bound.bin": with_diff_len(diff_max + 1024 * 1024),
    }


def build_frames_index(s: dict, frames: dict[str, bytes]) -> str:
    proto = s["classifier_protocol"]
    cases = []
    for case in proto["vectors"]["cases"]:
        blob = frames[case["file"]]
        cases.append({
            "name": case["name"],
            "file": case["file"],
            "expect": case["expect"],
            "reason_code": case.get("reason_code"),
            "reason": case.get("reason"),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
        })
    doc = {
        "_generated_by": "tools/fsmgen.py",
        "frame_layout": "u32be outer_len | u8 version=1 | u64be policy_len | policy | u64be diff_len | diff",
        "bounds": proto["bounds"],
        "reject_reasons": proto["reject_reasons"],
        "cases": cases,
    }
    return json.dumps(doc, indent=2, sort_keys=False) + "\n"


# ─── T19 vector inputs (histories only — expectations are hand-written) ─────

BASE1 = "R1:refs/heads/main"
BASE2 = "R2:refs/heads/main"
REF1 = "refs/heads/main"


def _hold_id_for(base: str, ref: str, old: str, new: str, seq: int) -> str:
    """Local mirror of the schema hold_id preimage, used only to place
    derived ids into vector INPUTS (reconcile events must reference the
    hold §6.0 derives). The EXPECTED ids live in the hand-written oracle."""
    preimage = "\n".join([f"base={base}", f"ref={ref}", f"old={old}",
                          f"new={new}", f"seq={seq}"])
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def _matched_delta_digest_for(base: str, ref: str, old: str, new: str) -> str:
    """Mirror of the schema's actor_verified_evidence preimage — used only to
    place consistent evidence into vector INPUTS."""
    preimage = "\n".join([f"subject-base={base}", f"subject-ref={ref}",
                          f"subject-old={old}", f"subject-new={new}"])
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def _recovery_id_for(base: str, movement_id: str) -> str:
    preimage = "\n".join(["recovery=crash_recovery", f"base={base}",
                          f"movement={movement_id}"])
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def _env(eid: str) -> dict:
    return {"schema_major": 1, "schema_minor": 0, "event_id": eid,
            "ts": "1970-01-01T00:00:00Z", "run_id": "run-1",
            "trace_id": "trace-1", "protocol_epoch": "E0"}


# trigger_event is derived from the variant's own row so a vector never
# hand-desynchronises the audit field from the tag it claims (the deny
# vectors that DO desynchronise pass it explicitly).
_A_TRIGGERS: dict[str, str] = {}
_B_TRIGGERS: dict[str, str] = {}


def _load_triggers(fsm: dict) -> None:
    for fam, table in (("effect_lifecycle", _A_TRIGGERS),
                       ("hold_lifecycle", _B_TRIGGERS)):
        for v in fsm["events"]["unions"][fam]["variants"]:
            table[v["name"]] = v["trigger"]


def _ev(variant: str, eid: str, mid: str, frm: str, to: str,
        **extra) -> dict:
    """One effect_lifecycle wire event. `base`/`branch` ride in **extra so
    the signature stays under the parameter bound; they are popped here."""
    base = extra.pop("base", BASE1)
    branch = extra.pop("branch", "state")
    d = _env(eid)
    d.update({"family": "effect_lifecycle", "variant": variant,
              "trigger_event": _A_TRIGGERS.get(variant, "prepare"),
              "movement_id": mid, "base_key": base, "from": frm, "to": to,
              "authority": "fp-1", "epoch_before": "E0", "epoch_after": "E0",
              "hold_effect": "NONE", "actor_context": "dispatcher",
              "credential_mode": "SHARED", "branch": branch})
    d.update(extra)
    return d


def _hev(variant: str, eid: str, frm: str, to: str, base: str = BASE1,
         **extra) -> dict:
    d = _env(eid)
    d.update({"family": "hold_lifecycle", "variant": variant,
              "trigger_event": _B_TRIGGERS.get(variant, "observe_delta"),
              "base_key": base, "from": frm, "to": to, "ref": REF1,
              "mode": "SHARED", "actor_verification": "DISPLAY_ONLY",
              "actor_display": "someone", "epoch_before": "E0",
              "epoch_after": "E0"})
    d.update(extra)
    return d


def _edge(eid: str, eb: str, ea: str, base: str = BASE1, **extra) -> dict:
    d = _env(eid)
    d.update({"base_key": base, "epoch_before": eb, "epoch_after": ea,
              "family": "effect_lifecycle"})
    d.update(extra)
    return d


def _section_a_vectors() -> dict[str, dict]:
    prep = _ev("Prepare", "e1", "m1", "GENESIS", "PREPARED",
               authorization_id="auth-1")
    hold_copy = _ev("MoveToHoldFromPrepared", "e2", "m1", "PREPARED", "HELD",
                    branch="hold")
    state_copy = dict(hold_copy, branch="state")
    v: dict[str, dict] = {}

    def a(name: str, note: str, events: list[dict]) -> None:
        v[name] = {"machine": "section_a", "note": note, "events": events}

    a("success", "prepare → (submit/observe_effect in memory) → EXPLAINED terminal",
      [prep, _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
                 new_oid="oid-new")])
    a("reject", "REJECTED_NO_EFFECT explained — never silently terminal",
      [prep, _ev("RejectExplained", "e2", "m1", "REJECTED_NO_EFFECT", "EXPLAINED",
                 reason="ruleset refused the merge")])
    a("timeout",
      "submit/timeout_unknown die with the process — the durable trace "
      "degrades to PREPARED; recovery dual-appends crash_recovery → HELD",
      [prep])
    held_origins = [
        ("held_from_prepared_crash", "CrashRecoveryFromPrepared", "PREPARED", {}),
        ("held_from_prepared_later", "LaterObservationFromPrepared", "PREPARED", {}),
        ("held_from_prepared_move", "MoveToHoldFromPrepared", "PREPARED", {}),
        ("held_from_submitted_mismatch", "ObserveEffectParentMismatch", "SUBMITTED",
         {"new_oid": "oid-x", "authorization_id": "auth-1"}),
        ("held_from_submitted_crash", "CrashRecoveryFromSubmitted", "SUBMITTED", {}),
        ("held_from_submitted_later", "LaterObservationFromSubmitted", "SUBMITTED", {}),
        ("held_from_unknown_later", "LaterObservationFromOutcomeUnknown",
         "OUTCOME_UNKNOWN", {}),
        ("held_from_unknown_crash", "CrashRecoveryFromOutcomeUnknown",
         "OUTCOME_UNKNOWN", {}),
    ]
    for name, variant, frm, extra in held_origins:
        a(name, f"held origin: {frm} × {variant}",
          [prep,
           _ev(variant, "e2", "m1", frm, "HELD", branch="hold", **extra),
           _ev(variant, "e2", "m1", frm, "HELD", branch="state", **extra)])
    a("crash_p1_before_hold_append",
      "kill -9 before the hold-branch append: dangling PREPARED — "
      "coalesce recovers exactly one HELD, never a second submit", [prep])
    a("crash_p2_between_appends",
      "kill -9 between the dual appends: hold-branch copy is canonical "
      "inside the crash window — one movement, one hold", [prep, hold_copy])
    a("crash_p3_after_both_appends",
      "both copies present, one event_id — dedup makes the pair idempotent",
      [prep, hold_copy, state_copy])
    a("crash_p4_redelivered_duplicate",
      "duplicate redelivery of both copies — byte-identical, still one hold",
      [prep, hold_copy, state_copy, dict(hold_copy), dict(state_copy)])
    a("dual_append_divergent_payload_deny",
      "DENY: duplicate event_id with non-byte-identical payloads is an "
      "integrity violation ⇒ halt that base",
      [prep, hold_copy, dict(state_copy, reason="tampered")])
    a("reconciled_accept_ours",
      "HELD × operator_reconcile(ACCEPT_OURS) → RECONCILED(d)",
      [prep, hold_copy, state_copy,
       _ev("ReconcileAccept", "e3", "m1", "HELD", "RECONCILED",
           disposition="ACCEPT_OURS", new_oid="oid-accepted")])
    a("reject_restore_then_accept",
      "REJECT_RESTORE_HOLD stays HELD (assessment recorded); a later "
      "accepting reconcile is legal",
      [prep, hold_copy, state_copy,
       _ev("ReconcileRejectRestoreHold", "e3", "m1", "HELD", "HELD",
           disposition="REJECT_RESTORE_HOLD"),
       _ev("ReconcileAccept", "e4", "m1", "HELD", "RECONCILED",
           disposition="ACCEPT_FOREIGN_ADVANCED")])
    a("reconcile_replay_identity",
      "RECONCILED(d) × operator_reconcile(same d) — identity, idempotent replay",
      [prep, hold_copy, state_copy,
       _ev("ReconcileAccept", "e3", "m1", "HELD", "RECONCILED",
           disposition="ACCEPT_FOREIGN_ADVANCED"),
       _ev("ReconcileReplayIdentity", "e4", "m1", "RECONCILED", "RECONCILED",
           disposition="ACCEPT_FOREIGN_ADVANCED")])
    a("reconcile_conflict_deny",
      "DENY: RECONCILED(d) × operator_reconcile(d′ ≠ d) ⇒ ILLEGAL typed error",
      [prep, hold_copy, state_copy,
       _ev("ReconcileAccept", "e3", "m1", "HELD", "RECONCILED",
           disposition="ACCEPT_FOREIGN_ADVANCED"),
       _ev("ReconcileReplayIdentity", "e4", "m1", "RECONCILED", "RECONCILED",
           disposition="ACCEPT_OURS")])
    a("resume_submit_illegal_deny",
      "DENY: a durable stream carrying a memory-only transition "
      "(resume-submit after crash) is ILLEGAL",
      [prep, _ev("Submit", "e2", "m1", "PREPARED", "SUBMITTED",
                 authorization_id="auth-1")])
    a("a_missing_required_field_deny",
      "DENY: §9-REQUIRED field (new_oid on Explained) absent ⇒ typed "
      "schema halt, never coerced to a permissive default",
      [prep, _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED")])
    a("a_forbidden_authorization_id_deny",
      "DENY: authorization_id is FORBIDDEN on crash variants (§9) — "
      "presence is a schema violation",
      [prep,
       _ev("CrashRecoveryFromPrepared", "e2", "m1", "PREPARED", "HELD",
           branch="hold", authorization_id="SMUGGLED"),
       _ev("CrashRecoveryFromPrepared", "e2", "m1", "PREPARED", "HELD",
           branch="state", authorization_id="SMUGGLED")])
    a("a_unknown_variant_deny",
      "DENY: unknown transition variant halts that base (§9)",
      [prep, _ev("TotallyNovelEvent", "e2", "m1", "PREPARED", "HELD")])
    a("a_unknown_enum_value_deny",
      "DENY: unknown VALUE of a known enum field halts identically (§9)",
      [prep, _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
                 new_oid="oid-new", credential_mode="NOT_A_MODE")])
    a("a_section_b_disposition_deny",
      "DENY: ACTOR_VERIFIED_AUTO is section-B only — a section-A "
      "operator_reconcile cannot mint it",
      [prep, hold_copy, state_copy,
       _ev("ReconcileAccept", "e3", "m1", "HELD", "RECONCILED",
           disposition="ACTOR_VERIFIED_AUTO", new_oid="oid-x")])
    a("a_multi_base",
      "base_key partitions the reduce: one base's terminal never explains "
      "another base's dangling PREPARED",
      [prep,
       _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
           new_oid="oid-new"),
       _ev("Prepare", "e3", "m2", "GENESIS", "PREPARED", base=BASE2,
           authorization_id="auth-2")])
    a("a_recovery_converges",
      "two independently-issued recovery appends share the DERIVED event_id "
      "and DIFFERENT per-issuer envelopes (ts/run_id/trace_id) — the "
      "byte-identity core excludes those, so the twins converge through "
      "dedup instead of halting the base",
      [prep,
       dict(_ev("CrashRecoveryFromPrepared", _recovery_id_for(BASE1, "m1"),
                "m1", "PREPARED", "HELD", branch="hold"),
            ts="1970-01-01T00:00:01Z", run_id="run-A", trace_id="trace-A"),
       dict(_ev("CrashRecoveryFromPrepared", _recovery_id_for(BASE1, "m1"),
                "m1", "PREPARED", "HELD", branch="state"),
            ts="1970-01-01T00:00:09Z", run_id="run-B", trace_id="trace-B")])
    a("a_unsupported_major_deny",
      "DENY: schema_major outside the supported set halts — the named §9 "
      "unknown-major halt, range-checked at intake",
      [prep, dict(_ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
                      new_oid="oid-new"), schema_major=2)])
    a("a_major_zero_deny",
      "DENY: schema_major 0 is outside the supported set",
      [dict(prep, schema_major=0)])
    a("a_major_99_deny",
      "DENY: schema_major 99 is outside the supported set",
      [dict(prep, schema_major=99)])
    a("a_missing_to_deny",
      "DENY: §9-REQUIRED audit field `to` absent ⇒ schema halt",
      [prep, {k: val for k, val in
              _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
                  new_oid="oid-new").items() if k != "to"}])
    a("a_to_contradiction_deny",
      "DENY: audit `to` contradicting the row's target ⇒ schema halt",
      [prep, _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "HELD",
                 new_oid="oid-new")])
    a("a_trigger_variant_mismatch_deny",
      "DENY: trigger_event contradicting the variant's row trigger — a "
      "mis-tagged writer must not smuggle a crash variant's exemptions",
      [prep, _ev("MoveToHoldFromPrepared", "e2", "m1", "PREPARED", "HELD",
                 trigger_event="crash_recovery")])
    a("a_missing_trigger_deny",
      "DENY: §9-REQUIRED trigger_event absent ⇒ schema halt",
      [prep, {k: val for k, val in
              _ev("MoveToHoldFromPrepared", "e2", "m1", "PREPARED",
                  "HELD").items() if k != "trigger_event"}])
    a("a_missing_family_deny",
      "DENY: the reduce filters by event schema name (§6.0) — an event "
      "with no `family` cannot be filtered and halts its base",
      [prep, {k: val for k, val in
              _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
                  new_oid="oid-new").items() if k != "family"}])
    a("a_bad_ts_deny",
      "DENY: ts outside RFC 3339 UTC — the audit trail's only time anchor "
      "must be orderable across hosts",
      [dict(prep, ts="yesterday-ish")])
    a("a_none_effect_row_advances_deny",
      "DENY: a row declaring no epoch effect cannot advance the base epoch "
      "— per-row epoch algebra is enforced, not decorative",
      [dict(prep, epoch_after="E1")])
    a("a_mixed_family_filtered",
      "the hold branch carries BOTH families (§6.0): a hold_lifecycle event "
      "in this stream is FILTERED by schema name, never halted",
      [prep,
       _hev("ObserveDelta", "h9", "GENESIS", "HELD_FOREIGN",
            delta_old_oid="o0", delta_new_oid="o1", source_delivery_id="dX"),
       _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
           new_oid="oid-new")])
    a("a_halt_isolation_after_halt",
      "halt isolation ORDERING: a base halts FIRST, then a healthy base's "
      "events arrive — they must still reduce and still earn their "
      "crash-recovery append (a global 'stop on first halt' would silently "
      "swallow them)",
      [dict(_ev("Prepare", "e1", "m2", "GENESIS", "PREPARED", base=BASE2,
                authorization_id="auth-2"), schema_major=7),
       _ev("Prepare", "e2", "m1", "GENESIS", "PREPARED",
           authorization_id="auth-1"),
       _ev("Prepare", "e3", "m3", "GENESIS", "PREPARED",
           authorization_id="auth-3")])
    a("a_halt_isolation_multi_base",
      "halt isolation: one base's schema violation must not suppress the "
      "healthy base's reduce OR its crash-recovery append — the healthy "
      "base is left with an OPEN PREPARED precisely so the append is the "
      "thing under test",
      [prep,   # BASE1/m1 stays open PREPARED ⇒ must still get its append
       _ev("Prepare", "e3", "m2", "GENESIS", "PREPARED", base=BASE2,
           authorization_id="auth-2"),
       dict(_ev("Explained", "e4", "m2", "EFFECT_OBSERVED", "EXPLAINED",
                base=BASE2, new_oid="oid-x"), schema_major=7)])
    return v


def _section_b_vectors() -> dict[str, dict]:
    h0 = _hold_id_for(BASE1, REF1, "o0", "o1", 0)
    obs = _hev("ObserveDelta", "h1", "GENESIS", "HELD_FOREIGN",
               delta_old_oid="o0", delta_new_oid="o1", source_delivery_id="d1")

    def release(eid: str, frm: str = "HELD_FOREIGN",
                disposition: str = "ACCEPT_FOREIGN_ADVANCED") -> dict:
        return _hev("HoldReconcileAccept", eid, frm, "RELEASED",
                    hold_id=h0, disposition=disposition)

    v: dict[str, dict] = {}

    def b(name: str, note: str, events: list[dict]) -> None:
        v[name] = {"machine": "section_b", "note": note, "events": events}

    b("b_foreign_hold_created",
      "— × observe_delta → HELD_FOREIGN (created); hold_id derived per §6.0",
      [obs])
    b("b_redelivery_after_released",
      "cold-start golden (round 19, claude B2): redelivered webhook after "
      "RELEASED — same source_delivery_id resolves to the same hold via the "
      "delivery index ⇒ idempotent no-op, no re-park, no halt",
      [obs, release("h2"),
       _hev("ObserveDeltaRedelivery", "h3", "RELEASED", "RELEASED",
            source_delivery_id="d1")])
    b("b_new_delivery_on_open_hold",
      "round-20 row: NEW source_delivery_id, same delta tuple, open hold — "
      "delivery recorded, state unchanged",
      [obs,
       _hev("ObserveDeltaNewDeliveryOnOpenHold", "h2", "HELD_FOREIGN",
            "HELD_FOREIGN", source_delivery_id="d2", delta_old_oid="o0",
            delta_new_oid="o1")])
    b("b_repark_after_released",
      "a genuinely NEW delivery of the same delta after RELEASED derives "
      "occurrence_seq+1 and parks a NEW hold — door 0 keeps its record",
      [obs, release("h2"),
       _hev("ObserveDelta", "h3", "GENESIS", "HELD_FOREIGN",
            delta_old_oid="o0", delta_new_oid="o1", source_delivery_id="d2")])
    b("b_redelivery_unseen_deny",
      "DENY: an ObserveDeltaRedelivery naming a source_delivery_id never "
      "seen on this base is mis-tagged — the apply order resolves a NEW "
      "hold, so the no-op claim is an integrity halt",
      [obs, release("h2"),
       _hev("ObserveDeltaRedelivery", "h3", "RELEASED", "RELEASED",
            source_delivery_id="d9")])
    b("b_mistagged_new_delivery_deny",
      "DENY: an ObserveDeltaNewDeliveryOnOpenHold carrying an ALREADY-seen "
      "delivery id resolves as a redelivery — mis-tag halts",
      [obs,
       _hev("ObserveDeltaNewDeliveryOnOpenHold", "h2", "HELD_FOREIGN",
            "HELD_FOREIGN", source_delivery_id="d1", delta_old_oid="o0",
            delta_new_oid="o1")])
    matched = _matched_delta_digest_for(BASE1, REF1, "o0", "o1")

    def ava(eid: str, **over) -> dict:
        kwargs = dict(hold_id=h0, actor_node_id="N-op",
                      matched_subject_digest=matched,
                      source_delivery_id="d1",
                      actor_verification="VERIFIED_API", mode="SEPARATED",
                      disposition="ACTOR_VERIFIED_AUTO")
        kwargs.update(over)
        return _hev("ActorVerifiedAuto", eid, "HELD_FOREIGN", "RELEASED",
                    **kwargs)

    b("b_actor_verified_auto_separated",
      "SEPARATED + VERIFIED_API + node id + a delivery recorded ON this "
      "hold + a matched digest deriving from the HOLD'S OWN delta: "
      "auto-release as ACTOR_VERIFIED_AUTO",
      [dict(obs, mode="SEPARATED"), ava("h2")])
    b("b_actor_verified_shared_deny",
      "DENY: under SHARED, never — the ActorVerifiedAuto event is "
      "unconstructible without SEPARATED (§6.0)",
      [obs, ava("h2", mode="SHARED")])
    b("b_actor_verified_wrong_delta_digest_deny",
      "DENY (panel round 2 CRITICAL): matched_subject_digest that does not "
      "derive from the HOLD'S OWN recorded delta is self-asserted evidence "
      "— refused, not honoured",
      [dict(obs, mode="SEPARATED"),
       ava("h2", matched_subject_digest=_matched_delta_digest_for(
           BASE1, REF1, "o0", "SOMETHING-ELSE"))])
    b("b_actor_verified_unresolvable_delivery_deny",
      "DENY (panel round 2 CRITICAL): a source_delivery_id that resolves to "
      "no delivery recorded on this hold cannot clear the auto-release gate",
      [dict(obs, mode="SEPARATED"), ava("h2", source_delivery_id="never-seen")])
    b("b_reject_restore_hold",
      "HELD_FOREIGN × operator_reconcile(REJECT_RESTORE_HOLD) → "
      "HELD_FOREIGN (assessment recorded; further reconcile legal)",
      [obs,
       _hev("HoldReconcileRejectRestoreHold", "h2", "HELD_FOREIGN",
            "HELD_FOREIGN", hold_id=h0, disposition="REJECT_RESTORE_HOLD"),
       release("h3")])
    b("b_standing_reenter",
      "STANDING is re-enterable: park persistent, then reconcile releases",
      [obs,
       _hev("HoldReconcileStanding", "h2", "HELD_FOREIGN", "STANDING",
            hold_id=h0, disposition="STANDING"),
       _hev("HoldReconcileAccept", "h3", "STANDING", "RELEASED",
            hold_id=h0, disposition="ACCEPT_OURS")])
    b("b_standing_reject_restore",
      "STANDING × operator_reconcile(REJECT_RESTORE_HOLD) dispatches 'as "
      "the HELD_FOREIGN rows' — resolved literal reading: → HELD_FOREIGN "
      "(schema standing_reject_restore_resolves_to; flagged for author "
      "confirmation)",
      [obs,
       _hev("HoldReconcileStanding", "h2", "HELD_FOREIGN", "STANDING",
            hold_id=h0, disposition="STANDING"),
       _hev("HoldReconcileRejectRestoreHold", "h3", "STANDING",
            "HELD_FOREIGN", hold_id=h0, disposition="REJECT_RESTORE_HOLD")])
    b("b_standing_standing",
      "STANDING × operator_reconcile(STANDING) — re-acknowledged, stays "
      "STANDING",
      [obs,
       _hev("HoldReconcileStanding", "h2", "HELD_FOREIGN", "STANDING",
            hold_id=h0, disposition="STANDING"),
       _hev("HoldReconcileStanding", "h3", "STANDING", "STANDING",
            hold_id=h0, disposition="STANDING")])
    b("b_release_replay_identity",
      "RELEASED(d) × operator_reconcile(same d) — identity",
      [obs, release("h2", disposition="ACCEPT_OURS"),
       _hev("HoldReconcileReplayIdentity", "h3", "RELEASED", "RELEASED",
            hold_id=h0, disposition="ACCEPT_OURS")])
    b("b_release_conflict_deny",
      "DENY: RELEASED(d) × operator_reconcile(d′ ≠ d) ⇒ ILLEGAL typed error",
      [obs, release("h2", disposition="ACCEPT_OURS"),
       _hev("HoldReconcileReplayIdentity", "h3", "RELEASED", "RELEASED",
            hold_id=h0, disposition="ACCEPT_FOREIGN_ADVANCED")])
    b("b_reconcile_accept_actor_verified_deny",
      "DENY: an operator_reconcile cannot mint ACTOR_VERIFIED_AUTO — the "
      "accept guard admits operator-accepting dispositions only",
      [obs,
       _hev("HoldReconcileAccept", "h2", "HELD_FOREIGN", "RELEASED",
            hold_id=h0, disposition="ACTOR_VERIFIED_AUTO")])
    b("b_unknown_actor_verification_deny",
      "DENY: unknown VALUE of actor_verification halts like an unknown "
      "variant (§9)",
      [_hev("ObserveDelta", "h1", "GENESIS", "HELD_FOREIGN",
            delta_old_oid="o0", delta_new_oid="o1", source_delivery_id="d1",
            actor_verification="TOTALLY_BOGUS")])
    b("b_reconcile_unknown_hold_deny",
      "DENY: a reconcile referencing a hold_id the stream never created "
      "halts — no hold is invented",
      [obs,
       _hev("HoldReconcileAccept", "h2", "HELD_FOREIGN", "RELEASED",
            hold_id="not-a-real-hold", disposition="ACCEPT_OURS")])
    b("b_declared_hold_id_mismatch_deny",
      "DENY: an observe_delta declaring a hold_id that contradicts the "
      "§6.0 derivation halts — the derivation is the authority",
      [_hev("ObserveDelta", "h1", "GENESIS", "HELD_FOREIGN",
            delta_old_oid="o0", delta_new_oid="o1", source_delivery_id="d1",
            hold_id="declared-wrong")])
    b("b_redelivery_delta_contradiction_deny",
      "DENY: a redelivery whose DECLARED delta contradicts the hold its "
      "source_delivery_id resolves to is never absorbed as a no-op",
      [obs,
       _hev("ObserveDeltaRedelivery", "h2", "HELD_FOREIGN", "HELD_FOREIGN",
            source_delivery_id="d1", delta_old_oid="o0",
            delta_new_oid="TOTALLY-DIFFERENT")])
    b("b_redelivery_stale_from_state",
      "the redelivery no-op is STATE-INDEPENDENT by design: a writer that "
      "stamped `from` before a concurrent reconcile released the hold must "
      "not turn an idempotent no-op into a base halt (TOCTOU)",
      [obs,
       _hev("HoldReconcileAccept", "h2", "HELD_FOREIGN", "RELEASED",
            hold_id=h0, disposition="ACCEPT_OURS"),
       _hev("ObserveDeltaRedelivery", "h3", "HELD_FOREIGN", "HELD_FOREIGN",
            source_delivery_id="d1")])
    b("b_forbidden_authorization_id_deny",
      "DENY: section-A parity — authorization_id is FORBIDDEN on the "
      "section-B reconcile variants too",
      [obs,
       _hev("HoldReconcileAccept", "h2", "HELD_FOREIGN", "RELEASED",
            hold_id=h0, disposition="ACCEPT_OURS",
            authorization_id="SMUGGLED")])
    b("b_none_effect_row_advances_deny",
      "DENY: the section-B creation row declares `epoch effect: none` — an "
      "observe_delta cannot advance the base epoch",
      [dict(obs, epoch_after="E1")])
    b("b_halt_isolation_after_halt",
      "halt isolation ORDERING (section B): one base halts first, a later "
      "healthy base still reduces its holds",
      [dict(_hev("ObserveDelta", "x1", "GENESIS", "HELD_FOREIGN", base=BASE2,
                 delta_old_oid="p0", delta_new_oid="p1",
                 source_delivery_id="e1"), schema_major=3),
       obs])
    b("b_halt_isolation_multi_base",
      "halt isolation: a schema violation on one base leaves the other "
      "base's holds intact and reduced",
      [obs,
       _hev("ObserveDelta", "x1", "GENESIS", "HELD_FOREIGN", base=BASE2,
            delta_old_oid="p0", delta_new_oid="p1", source_delivery_id="e1"),
       dict(_hev("ObserveDelta", "x2", "GENESIS", "HELD_FOREIGN", base=BASE2,
                 delta_old_oid="p1", delta_new_oid="p2",
                 source_delivery_id="e2"), schema_major=3)])
    return v


def _epoch_vectors() -> dict[str, dict]:
    anchors1 = {BASE1: "E0"}
    v: dict[str, dict] = {}

    def e(name: str, note: str, events: list[dict], anchors: dict) -> None:
        v[name] = {"machine": "epoch_fold", "note": note, "events": events,
                   "anchors": anchors}

    e("epoch_empty", "empty history: the anchor is the valid tail", [], anchors1)
    e("epoch_prepare_only",
      "no-effect PREPARED(E0→E0) pairs are not edges — anchor stays the tail",
      [_edge("e1", "E0", "E0")], anchors1)
    e("epoch_no_effect_reject",
      "a no-effect reject (E0→E0) beside no advance — not a false fork",
      [_edge("e1", "E0", "E0"), _edge("e2", "E0", "E0")], anchors1)
    e("epoch_cross_stream",
      "sequential advances across BOTH durable streams chain to one tail",
      [_edge("e1", "E0", "E1", stream="effect_lifecycle"),
       _edge("h1", "E1", "E2", stream="hold_lifecycle")], anchors1)
    e("epoch_gap",
      "DENY: an advance whose epoch_before nothing produced — unused edge "
      "remains ⇒ gap ⇒ halt",
      [_edge("e1", "E1", "E2")], anchors1)
    e("epoch_fork",
      "DENY: two candidate successors from one epoch ⇒ fork ⇒ halt",
      [_edge("e1", "E0", "E1"), _edge("e2", "E0", "E2")], anchors1)
    e("epoch_cycle", "DENY: reused epoch / cycle ⇒ halt",
      [_edge("e1", "E0", "E1"), _edge("e2", "E1", "E0")], anchors1)
    e("epoch_dual_append_copies",
      "carrier copies of one advance share an event_id — dedup, no fork",
      [_edge("e1", "E0", "E1", branch="hold"),
       _edge("e1", "E0", "E1", branch="state")], anchors1)
    e("epoch_dup_divergent_deny",
      "DENY: a reused event_id with a DIFFERENT epoch payload is an "
      "integrity violation ⇒ EVENT_PAYLOAD_DIVERGENT, never a silent dedup",
      [_edge("e1", "E0", "E1"), _edge("e1", "E1", "E2")], anchors1)
    e("epoch_unanchored_base_deny",
      "DENY: a base with epoch edges but no protocol_genesis anchor is a "
      "typed halt, never silently dropped",
      [_edge("e1", "E0", "E1"), _edge("x1", "E0", "E1", base=BASE2)], anchors1)
    e("epoch_multi_base",
      "the fold partitions by base_key: one base's clean chain, another's "
      "fork — independent results",
      [_edge("e1", "E0", "E1"),
       _edge("x1", "E0", "E1", base=BASE2), _edge("x2", "E0", "E2", base=BASE2)],
      {BASE1: "E0", BASE2: "E0"})
    e("epoch_no_effect_twin_divergent_deny",
      "DENY: a NO-EFFECT copy and an advancing copy sharing one event_id — "
      "dedup registers before the no-effect filter, so the divergence halts "
      "instead of the advance slipping in as a legitimate edge",
      [_edge("e1", "E0", "E0"), _edge("e1", "E0", "E1")], anchors1)
    e("epoch_no_effect_twin_divergent_reverse_deny",
      "DENY: the same pair in the opposite arrival order halts identically",
      [_edge("e1", "E0", "E1"), _edge("e1", "E0", "E0")], anchors1)
    e("epoch_cross_base_divergent_deny",
      "DENY: one event_id reused across two bases with divergent payloads "
      "halts BOTH bases — never order-dependent",
      [_edge("e1", "E0", "E1"), _edge("e1", "E0", "E2", base=BASE2)],
      {BASE1: "E0", BASE2: "E0"})
    # The RECOVERY_CEILING histories (breach with empty anchors, breach with
    # partial anchors, and the exactly-N boundary) are exercised in-memory by
    # tests/boundary/test_pr0.py::test_recovery_ceiling_* — a 10k-event JSON
    # corpus would be noise, and the halt is a function of the event COUNT,
    # which a generated history cannot make more faithful.
    return v


def build_t19_vectors(fsm: dict) -> dict[str, dict]:
    """Named §6.0 histories — INPUTS ONLY. Expected outputs are the
    hand-written oracle in tests/boundary/vectors/t19_expected.json, which
    this tool never writes (independent-oracle rule)."""
    _load_triggers(fsm)
    vectors: dict[str, dict] = {}
    vectors.update(_section_a_vectors())
    vectors.update(_section_b_vectors())
    vectors.update(_epoch_vectors())
    return vectors


# ─── output orchestration ────────────────────────────────────────────────────

def module_from_source(src: str) -> types.ModuleType:
    """Compile-smoke the generated module (registered in sys.modules for the
    dataclass machinery)."""
    name = "_fsmgen_generated"
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    try:
        exec(compile(src, str(GENERATED_PY), "exec"), mod.__dict__)  # noqa: S102
    finally:
        sys.modules.pop(name, None)
    return mod


def build_outputs(s: dict) -> dict[Path, bytes]:
    src = build_generated_module(s)
    module_from_source(src)  # smoke: the emitted module must import cleanly
    frames = build_frames(s)
    out: dict[Path, bytes] = {
        GENERATED_PY: src.encode("utf-8"),
        DOCS_DIR / "lifecycle_tables.md": (build_tables_md(s) + "\n").encode("utf-8"),
        DOCS_DIR / "event_unions.md": (build_unions_md(s) + "\n").encode("utf-8"),
        FRAMES_DIR / "vectors.json": build_frames_index(s, frames).encode("utf-8"),
    }
    for name, blob in frames.items():
        out[FRAMES_DIR / name] = blob
    for name, vec in build_t19_vectors(s["lifecycle_fsm"]).items():
        out[VECTORS_DIR / f"{name}.json"] = (
            json.dumps(vec, indent=2, sort_keys=False) + "\n").encode("utf-8")
    return out


def check_outputs(outputs: dict[Path, bytes]) -> list[str]:
    drift = []
    for path, blob in sorted(outputs.items()):
        if not path.exists():
            drift.append(f"missing: {path.relative_to(REPO_ROOT)}")
        elif path.read_bytes() != blob:
            drift.append(f"stale: {path.relative_to(REPO_ROOT)}")
    # Every generated directory is EXACT: a stray file in any of them is
    # drift (panel round 2 — the scan previously covered only the vectors
    # tree, so an extra file under docs/generated or the frame corpus passed
    # both seals). The hand-written oracle lives outside these directories
    # and is never generated; if it ever appeared inside one, this scan is
    # what calls it drift.
    for directory, pattern in ((VECTORS_DIR, "*.json"),
                               (DOCS_DIR, "*.md"),
                               (FRAMES_DIR, "*")):
        if not directory.exists():
            continue
        want = {p.name for p in outputs if p.parent == directory}
        for p in sorted(directory.glob(pattern)):
            if p.is_file() and p.name not in want:
                drift.append(f"stray: {p.relative_to(REPO_ROOT)}")
    return drift


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify committed outputs match regeneration; exit 1 on drift")
    args = ap.parse_args(argv)

    s = load_schemas()
    problems = compare_tables_with_design(s) + compare_unions_with_design(s)
    if problems:
        for p in problems:
            print(f"fsmgen: FAIL [design-mismatch]: {p}", file=sys.stderr)
        return 1

    outputs = build_outputs(s)
    if args.check:
        drift = check_outputs(outputs)
        if drift:
            for d in drift:
                print(f"fsmgen: FAIL [check-drift]: {d} "
                      f"(run: python tools/fsmgen.py)", file=sys.stderr)
            return 1
        print(f"fsmgen --check: {len(outputs)} generated files are current")
        return 0
    for path, blob in sorted(outputs.items()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        print(f"fsmgen: wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
