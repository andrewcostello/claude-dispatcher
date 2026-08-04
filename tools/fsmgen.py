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
    "variant": {"name", "row", "trigger", "required", "optional", "forbidden",
                "fixed", "extra_from"},
    "single": {"required", "optional", "note", "field_pair_rules"},
    "vector_case": {"name", "file", "expect", "reason", "reason_code"},
    "row": {"id", "from", "event", "to", "guard", "display", "disposition",
            "epoch_effect", "expected_base_oid_effect", "hold_effect",
            "standing_reject_restore_resolves_to",
            "standing_reject_restore_alternative",
            "auto_release_after_reject_restore"},
}


def _check_keys(record: dict, kind: str, where: str) -> None:
    allowed = _ALLOWED_KEYS[kind]
    extra = {k for k in record
             if k not in allowed and not str(k).endswith("_domain")}
    if extra:
        raise SchemaError(f"{where}: unrecognised key(s) {sorted(extra)} — "
                          f"allowed: {sorted(allowed)} (+ <field>_domain)")


def _validate_row_tokens(fsm: dict, sec: str) -> None:
    """Row tokens reach exec via the row tables and the generated
    FROM_STATES / TO_STATE / EPOCH_EFFECT / ROW_HOLD_EFFECT ClassVars."""
    states = {fsm[sec]["initial_pseudo_state"], *fsm[sec]["states"]}
    pseudo = {"ILLEGAL", "unchanged", "terminal", "any_other",
              "as_held_foreign_rows"}
    for row in fsm[sec]["rows"]:
        _require_ident(row["id"], f"{sec}.rows")
        _check_keys(row, "row", f"{sec}.rows.{row['id']}")
        for key in ("epoch_effect", "expected_base_oid_effect", "hold_effect"):
            if key in row:
                _require_ident(row[key], f"{sec}.rows.{row['id']}.{key}")
        for f in as_list(row["from"]):
            _require_ident(f, f"{sec}.rows.{row['id']}.from")
            if f not in states and f not in pseudo:
                raise SchemaError(f"{sec}.rows.{row['id']}.from: {f!r} is "
                                  f"not a declared state")
        _require_ident(row["to"], f"{sec}.rows.{row['id']}.to")
        if row["to"] not in states and row["to"] not in pseudo:
            raise SchemaError(f"{sec}.rows.{row['id']}.to: {row['to']!r} "
                              f"is not a declared state")


def _validate_machine_tokens(fsm: dict) -> None:
    for sec in ("section_a", "section_b"):
        for st in [fsm[sec]["initial_pseudo_state"], *fsm[sec]["states"]]:
            _require_ident(st, f"{sec}.states")
        for evn in fsm[sec]["events"]:
            _require_ident(evn, f"{sec}.events")
        _validate_row_tokens(fsm, sec)
    members = {m["name"] for m in fsm["reconcile_dispositions"]["members"]}
    for m in fsm["reconcile_dispositions"]["members"]:
        _require_ident(m["name"], "reconcile_dispositions")
    # These sets are emitted RAW as `ReconcileDisposition.{d}` — validate the
    # tokens and require them to name declared members (panel round 3: the
    # "no unvalidated token" invariant was false for three classes).
    for key in ("accepting", "operator_accepting"):
        for d in fsm["reconcile_dispositions"][key]:
            _require_ident(d, f"reconcile_dispositions.{key}")
            if d not in members:
                raise SchemaError(f"reconcile_dispositions.{key}: {d!r} is "
                                  f"not a declared member")
    for name, members in fsm["enums"].items():
        _require_ident(name, "enums")
        for m in members:
            _require_ident(m, f"enums.{name}")


def _validate_union_tokens(fsm: dict) -> None:
    for fam, spec in fsm["events"]["unions"].items():
        _require_ident(fam, "unions")
        # common_required/common_optional are emitted raw as dataclass field
        # declarations.
        for f in [*spec.get("common_required", []),
                  *spec.get("common_optional", [])]:
            _require_ident(f, f"unions.{fam}.common_*")
        for f, conds in spec.get("requires_when", {}).items():
            _require_ident(f, f"unions.{fam}.requires_when")
            for val, reqs in conds.items():
                _require_ident(val, f"unions.{fam}.requires_when value")
                for r in reqs:
                    _require_ident(r, f"unions.{fam}.requires_when required")
        for v in spec["variants"]:
            _require_ident(v["name"], f"unions.{fam}")
            _check_keys(v, "variant", f"unions.{fam}.{v['name']}")
            # classification_evaluated's variants are payload records, not
            # transition rows — only row-bearing variants carry a trigger.
            if "row" in v:
                _require_ident(v["trigger"], f"unions.{fam}.{v['name']}.trigger")
            for f in [*v.get("required", []), *v.get("optional", []),
                      *v.get("forbidden", []), *v.get("extra_from", [])]:
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
        "The repo gate (scripts/test.sh → tests/boundary) and",
        "`.github/workflows/verify.yml` both run `fsmgen --check`, so a hand",
        'edit here is a red build by construction."""',
        "",
        "from __future__ import annotations",
        "",
        "import datetime",
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
    row = b_rows_by_id["standing_reenter"]
    w(f"STANDING_REJECT_RESTORE_ALTERNATIVE: str = "
      f"{_require_ident(str(row['standing_reject_restore_alternative']), 'alt')!r}")
    w("# UNRATIFIED trade-off (schema): landing in HELD_FOREIGN would re-open")
    w("# the non-operator ACTOR_VERIFIED_AUTO path on a hold an operator just")
    w("# refused to release. PR0 takes the strictly safer reading.")
    w(f"AUTO_RELEASE_AFTER_REJECT_RESTORE: bool = "
      f"{bool(row['auto_release_after_reject_restore'])!r}")
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
    da = fsm["section_a"]["durability"]["dual_append"]
    w("# Byte-identity comparison sets (schema dual_append): `branch` is")
    w("# never semantic; the per-issuer envelope fields are excluded ONLY")
    w("# for DERIVED event_ids, where independent issuers must converge.")
    w(f"CANONICAL_EXCLUDES_ALWAYS: frozenset[str] = "
      f"frozenset({tuple(da['canonical_excludes_always'])!r})")
    w(f"CANONICAL_EXCLUDES_FOR_DERIVED_IDS: frozenset[str] = "
      f"frozenset({tuple(da['canonical_excludes_for_derived_ids'])!r})")
    w(f"DERIVED_ID_KINDS: frozenset[str] = "
      f"frozenset({tuple(da['derived_id_kinds'])!r})")
    w("")
    fam = fsm["events"]["reducer_family_filter"]
    w("# `family` is the event's schema name — a CLOSED domain over every")
    w("# record the protocol defines. Absent/empty/unknown halts; a family")
    w("# in the domain but not reduced by this machine is FILTERED.")
    w(f"FAMILY_FIELD: str = {fam['field']!r}")
    w(f"FAMILY_VALUES: frozenset[str] = frozenset({tuple(fam['values'])!r})")
    w(f"REDUCED_BY_FAMILIES: frozenset[str] = frozenset({tuple(fam['reduced_by'])!r})")
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
    # `family` is a generated envelope field on EVERY event type; on the
    # union variants it must equal the variant's own FAMILY (a contradiction
    # is a mis-tagged writer, not another stream).
    fam_req = ["family", *spec["common_required"]]
    fam_opt = list(spec.get("common_optional", []))
    var_req = list(v.get("required", []))
    var_opt = list(v.get("optional", []))
    forbidden = list(v.get("forbidden", []))
    required: list[str] = []
    for f in [*env["required"], *fam_req, *var_req]:
        if f not in required:
            required.append(f)
    optional = [f for f in [*env["optional"], *fam_opt, *var_opt]
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
        # conditional requirements: {field: {value: (required_fields,)}} —
        # e.g. actor_verification VERIFIED_API ⇒ actor_node_id present.
        requires_when = {
            f: {val: tuple(reqs) for val, reqs in conds.items()}
            for f, conds in spec.get("requires_when", {}).items()}
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
        if "hold_effect" in row:
            w(f"    ROW_HOLD_EFFECT: ClassVar[Optional[str]] = "
              f"{_require_ident(row['hold_effect'], row['id'] + '.hold_effect')!r}")
        else:
            w("    ROW_HOLD_EFFECT: ClassVar[Optional[str]] = None")
        w(f"    REQUIRED: ClassVar[tuple[str, ...]] = {tuple(required)!r}")
        w(f"    OPTIONAL: ClassVar[tuple[str, ...]] = {tuple(optional)!r}")
        w(f"    FORBIDDEN: ClassVar[tuple[str, ...]] = {tuple(forbidden)!r}")
        w(f"    FIXED: ClassVar[Mapping[str, str]] = {fixed!r}")
        w(f"    REQUIRES_WHEN: ClassVar[Mapping[str, Mapping[str, tuple]]] = "
          f"{requires_when!r}")
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
            pair_rules: dict, family_name: str) -> None:
        classes[event_name] = cls_name
        req: list[str] = []
        # `family` is a generated envelope field on EVERY event type: its
        # value is the event's own schema name, so a reducer can filter a
        # legitimate single off a shared carrier instead of halting.
        for f in [*env["required"], "family", *required]:
            if f not in req:
                req.append(f)
        opt = [f for f in [*env["optional"], *optional] if f not in req]
        w("@dataclass(frozen=True)")
        w(f"class {cls_name}:")
        w(f'    """§9 `{event_name}` event."""')
        w("")
        w(f"    EVENT: ClassVar[str] = \"{event_name}\"")
        w(f"    FAMILY: ClassVar[str] = \"{family_name}\"")
        w(f"    REQUIRED: ClassVar[tuple[str, ...]] = {tuple(req)!r}")
        w(f"    OPTIONAL: ClassVar[tuple[str, ...]] = {tuple(opt)!r}")
        w("    FORBIDDEN: ClassVar[tuple[str, ...]] = ()")
        w("    REQUIRES_WHEN: ClassVar[Mapping[str, Mapping[str, tuple]]] = {}")
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
        w("        if self.family != self.FAMILY:")
        w(f"            raise ValueError(f\"{cls_name}.family {{self.family!r}} \"")
        w("                             f\"contradicts its schema name {self.FAMILY!r}\")")
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
            dict(spec.get("field_pair_rules", {})), event_name)
    for v in fsm["events"]["unions"]["classification_evaluated"]["variants"]:
        one(f"classification_evaluated/{v['name']}", v["name"],
            list(v["required"]), [], {}, {}, "classification_evaluated")
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


def _valid_ts(value: str) -> bool:
    """RFC 3339 UTC, SEMANTICALLY: the regex fixes the shape (fromisoformat
    tolerates forms RFC 3339 does not), then a real parse rejects
    impossible instants — month 13, day 45, hour 99, offset +99:99 all
    pass a shape check and are not timestamps."""
    if not _TS_RE.match(value):
        return False
    try:
        datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _py_field(f: str) -> str:
    return FIELD_NAME_MAP.get(f, f)


def _short(value: object, limit: int = 60) -> str:
    """Journal-safe rendering: halt details must not dump whole payloads."""
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _validate_event_fields(event: object) -> None:
    """Shared __post_init__ validation: required fields present with the
    right type (never coerced), enum fields are enum INSTANCES, schema_major
    inside the supported range, ts RFC 3339 UTC, and the schema's
    CONDITIONAL requirements (e.g. VERIFIED_API evidence must carry an
    attributable actor_node_id — actor_display is presentation, never
    predicate input). Raises ValueError."""
    cls = type(event)
    name = cls.__name__
    for f in cls.REQUIRED:
        _validate_field_value(name, f, getattr(event, _py_field(f)), required=True)
    for f in cls.OPTIONAL:
        value = getattr(event, _py_field(f), None)
        if value is not None:
            _validate_field_value(name, f, value, required=False)
    for field, conditions in cls.REQUIRES_WHEN.items():
        current = getattr(event, _py_field(field), None)
        key = current.value if hasattr(current, "value") else current
        for needed in conditions.get(key, ()):
            got = getattr(event, _py_field(needed), None)
            if got is None or (isinstance(got, str) and got == ""):
                raise ValueError(
                    f"{name}.{field}={key!r} requires {needed!r}, which is "
                    f"absent — evidence without an attributable identity")


def _validate_row_audit_fields(event: object) -> None:
    """§9 audit fields validated against the variant's row: from ∈
    FROM_STATES, trigger_event == the row's trigger, to == the row's target
    (== from on `unchanged` no-op rows). Raises ValueError."""
    cls = type(event)
    name = cls.__name__
    if event.from_state not in cls.FROM_STATES:
        raise ValueError(
            f"{name}.from_state {event.from_state!r} not in {cls.FROM_STATES!r}")
    if event.family != cls.FAMILY:
        raise ValueError(
            f"{name}.family {event.family!r} contradicts the variant's own "
            f"schema name {cls.FAMILY!r} — a mis-tagged writer halts")
    row_hold_effect = getattr(cls, "ROW_HOLD_EFFECT", None)
    if row_hold_effect is not None and event.hold_effect is not None:
        if event.hold_effect.value != row_hold_effect:
            raise ValueError(
                f"{name}.hold_effect {event.hold_effect.value!r} contradicts "
                f"the row's declared effect {row_hold_effect!r}")
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
    if f == "ts" and not _valid_ts(value):
        raise ValueError(f"{name}.ts {_short(value)} is not an RFC 3339 UTC "
                         f"instant")


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
    if f == "ts" and not _valid_ts(value):
        raise WireViolation(f"{cls_name}.ts: {_short(value)} is not an "
                            f"RFC 3339 UTC instant")
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
    if ev.get("family") != cls.FAMILY:
        raise WireViolation(
            f"{name}: family {ev.get('family')!r} contradicts the variant's "
            f"own schema name {cls.FAMILY!r} "
            f"(event_id {ev.get('event_id')!r}) — mis-tagged writer")
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
        # Defence in depth ONLY: the authoritative gate is the RUN's
        # credential mode, checked in reduce_section_b against run context
        # (a mode the releasing event asserts about itself is no gate).
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


@dataclass(frozen=True)
class SubjectComponents:
    """The §9 subject_digest preimage's components as one frozen object —
    seven loose parameters sat at the complexity table's threshold."""

    repo_node_id: str
    target: str
    base_oid: str
    head_oid: str
    diff_sha256: str
    classifier: object
    unit_digest: Optional[str] = None


def subject_digest(components: Optional[SubjectComponents] = None, /,
                   **kwargs) -> str:
    """§9 canonical subject_digest preimage — exact tag bytes, UTF-8 lines,
    newline-joined, SHA-256. `target` is the full target line
    (`pr:<pr_node_id>:<target_ref>` or `ref:<target_ref>` — build with
    target_pr()/target_ref())."""
    c = components if components is not None else SubjectComponents(**kwargs)
    if not isinstance(c.classifier, ClassifierAuthority):
        raise ValueError("subject_digest: classifier must be a "
                         "ClassifierAuthority variant")
    preimage = _preimage([
        f"repo={c.repo_node_id}", f"target={c.target}", f"base={c.base_oid}",
        f"head={c.head_oid}", f"diff={c.diff_sha256}",
        f"classifier={c.classifier.line()}",
        f"unit={c.unit_digest if c.unit_digest is not None else 'none'}"])
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def target_pr(pr_node_id: str, target_ref: str) -> str:
    """PR subjects carry BOTH fields — a retarget changes the digest."""
    return f"pr:{pr_node_id}:{target_ref}"


def target_ref(ref: str) -> str:
    return f"ref:{ref}"


# ─── reducers (T19 skeletons; PR4 hardens against live carriers) ────────────

def _is_derived_id(d: Mapping[str, object]) -> bool:
    """True when this event's event_id is DERIVED (cold-start recovery), so
    two independent issuers legitimately mint the same id."""
    if str(d.get("trigger_event")) not in DERIVED_ID_KINDS:
        return False
    base, movement = d.get("base_key"), d.get("movement_id")
    if not isinstance(base, str) or not isinstance(movement, str):
        return False
    return d.get("event_id") == derive_recovery_event_id(base, movement)


def _canonical(d: Mapping[str, object]) -> str:
    """Byte-identity core for duplicate-event_id comparison. `branch` (which
    carrier copy) is never semantic. The per-ISSUER envelope fields are
    dropped ONLY when the event_id is DERIVED — two concurrent cold-start
    recoveries must converge and cannot agree on ts/run_id/trace_id. For
    every other event the comparison is the FULL canonical payload, as the
    design's unqualified rule requires (panel round 3)."""
    drop = set(CANONICAL_EXCLUDES_ALWAYS)
    if _is_derived_id(d):
        drop |= set(CANONICAL_EXCLUDES_FOR_DERIVED_IDS)
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
        self._seen: dict[str, tuple[bytes, str]] = {}

    def check(self, ev: Mapping[str, object], base: str) -> str:
        """'new' | 'dup'; raises _DivergentDuplicate on divergence or a
        missing envelope event_id."""
        eid = ev.get("event_id")
        if not isinstance(eid, str) or eid == "":
            raise _DivergentDuplicate(_halt(
                BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                f"event missing required envelope field 'event_id' "
                f"(fields present: {sorted(ev)})", ev), frozenset({base}))
        try:
            # a 32-byte digest detects divergence just as well as the full
            # canonical string and keeps recovery-path memory bounded.
            canon = hashlib.sha256(_canonical(ev).encode("utf-8")).digest()
        except (TypeError, ValueError):
            raise _DivergentDuplicate(_halt(
                BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                f"event {eid!r} carries a non-serializable payload — the "
                f"canonical form is undefined, so byte-identity cannot be "
                f"established", ev), frozenset({base})) from None
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
    """DEDUPLICATED counts per base: idempotent redeliveries and dual-append
    twins are exactly what the protocol expects to absorb, so they must not
    consume ceiling budget and escalate to an OPERATOR halt (panel round 3).
    The ceiling bounds the recovered HISTORY, not the wire traffic."""
    counts: dict[str, int] = {}
    seen: dict[str, set] = {}
    for ev in events:
        base = str(ev.get("base_key") or "")
        eid = ev.get("event_id")
        bucket = seen.setdefault(base, set())
        if isinstance(eid, str) and eid:
            if eid in bucket:
                continue
            bucket.add(eid)
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
    halted = base_hint in base_halts
    fam = ev.get("family")
    if not isinstance(fam, str) or fam == "":
        base_halts.setdefault(base_hint, _halt(
            BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
            f"event missing required field 'family' — the reduce filters by "
            f"event schema name (§6.0) (event_id {ev.get('event_id')!r})", ev))
        return None
    if fam not in FAMILY_VALUES:
        base_halts.setdefault(base_hint, _halt(
            BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
            f"unknown family {fam!r} outside the closed domain — an unknown "
            f"enum value halts like an unknown variant (§9) "
            f"(event_id {ev.get('event_id')!r})", ev))
        return None
    if fam != family:
        # A legitimate OTHER record on the shared carrier (the peer
        # lifecycle family, or any §9 single) is FILTERED. But an event
        # whose VARIANT belongs to this machine while its tag claims
        # another family is a mis-tagged writer, not another stream — a
        # silent drop there rewrites a durable terminal at the next cold
        # start and bypasses the conflicting-disposition halt.
        cls = variants.get(str(ev.get("variant")))
        if cls is not None:
            base_halts.setdefault(base_hint, _halt(
                BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                f"family {fam!r} contradicts variant {cls.__name__!r}, whose "
                f"own schema name is {cls.FAMILY!r} — mis-tagged writer, "
                f"never filtered (event_id {ev.get('event_id')!r})", ev))
        return None
    try:
        # dedup runs for EVERY event, halted base or not: skipping
        # registration would let a divergent twin on a HEALTHY base later in
        # the stream read as first-seen (panel round 3 — order dependence).
        seen = dedup.check(ev, base_hint)
        if halted or seen == "dup":
            return None  # halted base: register only; dup: absorbed
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


def _check_epoch_algebra(cls: type, event: object, where: str,
                         ev: Mapping[str, object]) -> Optional[dict]:
    """§6.0's per-row epoch algebra, BOTH halves (panel round 3: only the
    negative half was enforced, so an advancing row could set the fence —
    AuthorityFingerprint.base_epoch — to any string at all).

      none            ⇒ epoch_before == epoch_after
      assign_new_oid  ⇒ advances, and epoch_after IS the observed new_oid
      per_disposition ⇒ an accepting disposition advances; a non-accepting
                        one (REJECT_RESTORE_HOLD) must not; ACCEPT_OURS
                        additionally pins the fence to its new_oid payload
      as_accept_ours  ⇒ advances (the auto-release mirrors ACCEPT_OURS)
    """
    before, after = event.epoch_before, event.epoch_after
    advanced = before != after
    effect = cls.EPOCH_EFFECT

    def halt(msg: str) -> dict:
        return _halt(BoundaryErrorCode.ILLEGAL_TRANSITION,
                     f"{where}: row {cls.ROW!r} ({effect}) {msg} "
                     f"(event_id {ev.get('event_id')!r})", ev)

    if effect == "none":
        if advanced:
            return halt(f"declares no epoch effect but advances {before}→{after}")
        return None
    if effect == "assign_new_oid":
        return _check_assign_new_oid(event, advanced, after, halt)
    if effect in ("per_disposition", "as_accept_ours"):
        disposition = getattr(event, "disposition", None)
        accepting = (effect == "as_accept_ours"
                     or disposition in ACCEPTING_DISPOSITIONS)
        if accepting and not advanced:
            return halt("an accepting disposition advances the epoch; "
                        "this event did not")
        if not accepting and advanced:
            return halt(f"a non-accepting disposition "
                        f"({disposition}) must not advance "
                        f"{before}→{after}")
        # ACCEPT_OURS(new_oid) pins the fence to its payload — but only
        # where the family carries new_oid at all: §9's hold_lifecycle field
        # list has no new_oid, so section B expresses the advance through
        # epoch_after alone.
        carries_new_oid = "new_oid" in cls.REQUIRED or "new_oid" in cls.OPTIONAL
        if (disposition is ReconcileDisposition.ACCEPT_OURS and carries_new_oid
                and after != getattr(event, "new_oid", None)):
            return halt(f"ACCEPT_OURS pins the fence to its new_oid payload "
                        f"{getattr(event, 'new_oid', None)!r}, got {after!r}")
        return None
    return None


def _check_assign_new_oid(event: object, advanced: bool, after: str,
                          halt) -> Optional[dict]:
    """`:= new_oid` (§6.0's explained row): must advance, and the fence IS
    the observed new_oid."""
    if not advanced:
        return halt("must advance the epoch but did not")
    if after != getattr(event, "new_oid", None):
        return halt(f"must set the fence to the observed new_oid "
                    f"{getattr(event, 'new_oid', None)!r}, got {after!r}")
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
    epoch_halt = _check_epoch_algebra(cls, event, f"movement {mid}@{base}", ev)
    if epoch_halt is not None:
        return epoch_halt
    cur = movements.get(base, {}).get(mid, GENESIS_A)
    # §6.0 identity replay is checked BEFORE the projection preconditions:
    # the replaying writer read HELD, so its audit `from` is HELD too, and
    # a precondition error would pre-empt the idempotence rule.
    if cur.name is SectionAState.RECONCILED and isinstance(event, ReconcileAccept):
        if cur.disposition is event.disposition:
            return None                          # identity replay
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"movement {mid}@{base}: RECONCILED({cur.disposition}) × "
            f"operator_reconcile({event.disposition}) — conflicting d′ "
            f"(event_id {ev.get('event_id')!r})", ev)
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
        # writer/reducer disagreements the reducer resolved (journalled,
        # never a halt — door 0 is inherently concurrent)
        self.resolution_notes: list[str] = []
        # holds whose release an operator explicitly REFUSED — the
        # non-operator auto-release path stays closed on them.
        self.reject_restored: set = set()


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
    events (unknown holds halt). Returns (hid, cur, halt, note) — `note`
    journals a writer/reducer disagreement the reducer resolved."""
    cls = type(event)
    if cls.TRIGGER == "observe_delta":
        resolution, hid = _resolve_observe_delta(book, base, event)
        if cls.__name__ != _OBSERVE_EXPECTED[resolution]:
            # Door 0 is the most concurrent path in the system: the tag
            # encodes a decision the writer made from a read a concurrent
            # writer invalidated. The schema names the REDUCER the
            # authority for this resolution (section_b.hold_id.apply_order),
            # so apply the derived answer and journal the disagreement
            # rather than halting the base (panel round 3).
            resolution_note = (
                f"apply order resolved {resolution!r} (hold {hid}); the "
                f"event was tagged {cls.__name__!r} — the reducer's "
                f"derivation is authoritative "
                f"(event_id {ev.get('event_id')!r})")
        else:
            resolution_note = None
        if event.hold_id is not None and event.hold_id != hid:
            return None, None, _halt(
                BoundaryErrorCode.ILLEGAL_TRANSITION,
                f"declared hold_id {event.hold_id!r} contradicts the "
                f"derived/resolved {hid!r} "
                f"(event_id {ev.get('event_id')!r})", ev), None
        if resolution in ("redelivery", "record"):
            halt = _check_delta_against_hold(book, hid, event, ev)
            if halt is not None:
                return None, None, halt, None
        return hid, book.holds.get(hid, GENESIS_B), None, resolution_note
    hid = event.hold_id
    cur = book.holds.get(hid)
    if cur is None:
        return None, None, _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"{cls.__name__!r} references unknown hold {hid!r} "
            f"(event_id {ev.get('event_id')!r})", ev), None
    return hid, cur, None, None


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


# sentinel: the step is a legal idempotent replay, not a halt
_IDENTITY_REPLAY: dict = {"__identity_replay__": True}


def _check_hold_preconditions(hid: str, cur: MachineStateB, event: object,
                              ev: Mapping[str, object],
                              note: Optional[str]) -> Optional[dict]:
    """State preconditions for one section-B step. Returns a halt payload,
    the _IDENTITY_REPLAY sentinel (a legal §6.0 idempotent replay), or
    None. A writer whose apply-order tag was stale also stamped `from` from
    that same stale read, so the reducer's resolution governs both."""
    cls = type(event)
    replaying = (cur.name is SectionBState.RELEASED
                 and isinstance(event, HoldReconcileAccept))
    if (cls.TO_STATE != "unchanged" and not replaying and note is None
            and event.from_state != cur.name.value):
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"hold {hid}: audit from={event.from_state!r} contradicts the "
            f"reduced state {cur.name.value} "
            f"(event_id {ev.get('event_id')!r})", ev)
    if replaying:
        # §6.0 identity replay — same d is idempotent, d′ conflicts.
        if cur.disposition is event.disposition:
            return _IDENTITY_REPLAY
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"hold {hid}: RELEASED({cur.disposition}) × "
            f"operator_reconcile({event.disposition}) — conflicting d′ "
            f"(event_id {ev.get('event_id')!r})", ev)
    return None


def _check_auto_release_gates(book: _HoldBook, base: str, hid: str,
                              event: object, ev: Mapping[str, object],
                              run_mode: CredentialMode) -> Optional[dict]:
    """Every gate on the ONLY operator-less release of a foreign hold, in
    order: an operator's prior refusal closes it; the RUN's credential mode
    (never the event's) must be SEPARATED; then the hold-record
    consistency cross-checks."""
    if not AUTO_RELEASE_AFTER_REJECT_RESTORE and hid in book.reject_restored:
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"hold {hid}: an operator REJECTED this hold's release "
            f"(REJECT_RESTORE_HOLD); the non-operator auto-release path "
            f"stays closed until an operator disposition "
            f"(event_id {ev.get('event_id')!r})", ev)
    if run_mode is not CredentialMode.SEPARATED:
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"hold {hid}: ACTOR_VERIFIED_AUTO requires the RUN to be "
            f"SEPARATED (protocol_genesis.credential_mode); this run is "
            f"{run_mode.value} — under SHARED, never "
            f"(event_id {ev.get('event_id')!r})", ev)
    return _check_actor_verified(book, base, hid, event, ev)


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


def reduce_section_b(events: Sequence[Mapping[str, object]],
                     credential_mode: Optional[CredentialMode] = None) -> dict:
    """Reduce a hold_lifecycle stream into section-B states per
    (base_key, hold_id), implementing §6.0's observe_delta apply order and
    hold_id derivation for real. Halt isolation and ceiling are PER
    base_key (uniform shape: {holds, halts}).

    `credential_mode` is the RUN's mode — reduced from protocol_genesis
    where the stream is durable, else supplied by the caller and recorded.
    It is NOT taken from event payload: ACTOR_VERIFIED_AUTO is the only
    operator-less release of a foreign hold, and a gate a releasing event
    clears about ITSELF is no gate (§0.3: any unprobeable predicate records
    SHARED, never a soft SEPARATED). An event whose self-declared `mode`
    disagrees with the run context is a typed halt; absent context is
    treated as SHARED, so the auto-release path is closed by default.

    ACTOR_VERIFIED_AUTO releases are additionally cross-checked against the
    hold's own record (delivery membership + delta-derived digest) — those
    validate CONSISTENCY, not provenance; provenance is PR4's webhook
    protocol (schema actor_verified_evidence). Redelivery semantics
    (rounds 17–20): same source_delivery_id ⇒ same hold regardless of
    state; the no-op rows are state-independent, so their audit `from` is
    validated against FROM_STATES only (a reconcile racing the append must
    not turn an idempotent no-op into a halt)."""
    # §0.3: absent/unprobeable ⇒ SHARED, never a soft SEPARATED.
    run_mode = credential_mode or CredentialMode.SHARED
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
        halt = _step_section_b(book, base, event, ev, run_mode)
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
    notes = {b: books[b].resolution_notes for b in base_order
             if books[b].resolution_notes}
    return {"holds": out, "halts": base_halts, "resolution_notes": notes}


def _step_section_b(book: _HoldBook, base: str, event: object,
                    ev: Mapping[str, object],
                    run_mode: CredentialMode) -> Optional[dict]:
    note = None
    cls = type(event)
    # An event's self-declared `mode` is display/audit; the RUN's mode is
    # authority. Divergence is a typed halt, never a silent upgrade.
    if event.mode is not run_mode:
        return _halt(
            BoundaryErrorCode.ILLEGAL_TRANSITION,
            f"{base}: event declares credential mode {event.mode.value!r} but "
            f"the run's mode is {run_mode.value!r} — credential mode is run "
            f"context (protocol_genesis), not event payload "
            f"(event_id {ev.get('event_id')!r})", ev)
    epoch_halt = _check_epoch_algebra(cls, event, base, ev)
    if epoch_halt is not None:
        return epoch_halt
    hid, cur, halt, note = _admit_hold_event(book, base, event, ev)
    if halt is not None:
        return halt
    if note is not None:
        book.resolution_notes.append(note)
    # The `unchanged` no-op rows are state-independent by design — their
    # audit `from` is already constrained to FROM_STATES at construction;
    # every state-changing row must name the reduced state exactly.
    pre = _check_hold_preconditions(hid, cur, event, ev, note)
    if pre is not None:
        return pre if pre != _IDENTITY_REPLAY else None
    if isinstance(event, ActorVerifiedAuto):
        halt = _check_auto_release_gates(book, base, hid, event, ev, run_mode)
        if halt is not None:
            return halt
    if note is not None:
        # the reducer's resolution governs: a hold that does not yet exist
        # is created; one that does absorbs the delivery as a no-op.
        new = (MachineStateB(SectionBState.HELD_FOREIGN)
               if cur.name is SectionBState.GENESIS else cur)
    else:
        try:
            new = apply_section_b(cur, event)
        except IllegalTransitionError as exc:
            return _halt(BoundaryErrorCode.ILLEGAL_TRANSITION, str(exc), ev)
    if isinstance(event, HoldReconcileRejectRestoreHold):
        book.reject_restored.add(hid)
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
    edges_by_base = _collect_epoch_edges(events, base_halts)
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


def _collect_epoch_edges(events: Sequence[Mapping[str, object]],
                        base_halts: dict[str, dict]) -> dict:
    """§9 validation, dedup and the no-effect filter, in that order — the
    fold's output IS the fence epoch, so it runs the same schema checks as
    the reducers, and dedup registers EVERY event (halted base included) so
    divergence detection is order-independent."""
    dedup = _Dedup()
    edges_by_base: dict[str, list[Mapping[str, object]]] = {}
    for ev in events:
        base = str(ev.get("base_key") or "")
        halted = base in base_halts
        schema_halt = _validate_fold_event(ev)
        if schema_halt is not None:
            base_halts.setdefault(base, schema_halt)
            continue
        try:
            if dedup.check(ev, base) == "dup" or halted:
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
    return edges_by_base


def _validate_fold_event(ev: Mapping[str, object]) -> Optional[dict]:
    """The §9 schema checks the fold shares with the reducers: supported
    major, closed family domain, and (for lifecycle events) full variant
    validation. Returns a halt payload or None."""
    major = ev.get("schema_major")
    if isinstance(major, bool) or not isinstance(major, int):
        return _halt(BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                     f"epoch edge has a non-integer schema_major "
                     f"(event_id {ev.get('event_id')!r})", ev)
    if major not in SUPPORTED_SCHEMA_MAJORS:
        return _halt(BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                     f"epoch edge schema_major {major} outside the supported "
                     f"set {sorted(SUPPORTED_SCHEMA_MAJORS)} — an unknown "
                     f"major must never advance the fence "
                     f"(event_id {ev.get('event_id')!r})", ev)
    fam = ev.get("family")
    if not isinstance(fam, str) or fam == "":
        return _halt(BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                     f"epoch edge missing required field 'family' "
                     f"(event_id {ev.get('event_id')!r})", ev)
    if fam not in FAMILY_VALUES:
        return _halt(BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                     f"epoch edge has unknown family {fam!r} outside the "
                     f"closed domain (event_id {ev.get('event_id')!r})", ev)
    variants = (EFFECT_VARIANTS if fam == "effect_lifecycle"
                else HOLD_VARIANTS if fam == "hold_lifecycle" else None)
    if variants is not None and ev.get("variant") is not None:
        try:
            build_wire_event(variants, ev)
        except WireViolation as exc:
            return _halt(exc.code, exc.detail, ev)
        except ValueError as exc:
            return _halt(BoundaryErrorCode.ILLEGAL_TRANSITION, str(exc), ev)
    return None


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
        # immutable COPY (twin of the RosterSnapshot fix): a caller-owned
        # list would let a blocking CRITICAL/HIGH finding disappear AFTER
        # construction, turning BLOCKED into APPROVED.
        if not isinstance(self.findings, tuple):
            object.__setattr__(self, "findings", tuple(self.findings))
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
           "Source: `schema/lifecycle_fsm.yaml`. fsmgen's doc==artifact",
           "comparison diffs the cell content against the design doc's inline",
           "tables (normalized) on every run — enforced by the repo gate and",
           "by .github/workflows/verify.yml, so the two cannot drift apart",
           "silently.",
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
_A_HOLD_EFFECTS: dict[str, str] = {}
_A_EPOCH_EFFECTS: dict[str, str] = {}
_B_EPOCH_EFFECTS: dict[str, str] = {}


def _load_triggers(fsm: dict) -> None:
    for fam, table in (("effect_lifecycle", _A_TRIGGERS),
                       ("hold_lifecycle", _B_TRIGGERS)):
        for v in fsm["events"]["unions"][fam]["variants"]:
            table[v["name"]] = v["trigger"]
    rows = {r["id"]: r for r in fsm["section_a"]["rows"]}
    for v in fsm["events"]["unions"]["effect_lifecycle"]["variants"]:
        row = rows[v["row"]]
        if row.get("hold_effect"):
            _A_HOLD_EFFECTS[v["name"]] = row["hold_effect"]
        _A_EPOCH_EFFECTS[v["name"]] = (row.get("expected_base_oid_effect")
                                       or row.get("epoch_effect") or "none")
    b_rows = {r["id"]: r for r in fsm["section_b"]["rows"]}
    for v in fsm["events"]["unions"]["hold_lifecycle"]["variants"]:
        row = b_rows[v["row"]]
        _B_EPOCH_EFFECTS[v["name"]] = (row.get("epoch_effect")
                                       or row.get("expected_base_oid_effect")
                                       or "none")


def _epoch_after_for(variant: str, extra: dict, before: str,
                     effects: Mapping[str, str]) -> str:
    """§6.0's per-row epoch algebra, applied when BUILDING a vector so the
    corpus encodes the real fence semantics (panel round 3: every golden
    previously recorded epoch_before == epoch_after, even on rows whose
    declared effect is an advance)."""
    effect = effects.get(variant, "none")
    disposition = extra.get("disposition")
    if effect == "assign_new_oid":
        return str(extra.get("new_oid", before))
    if effect == "as_accept_ours":
        return str(extra.get("new_oid", f"{before}-advanced"))
    if effect == "per_disposition":
        if disposition in ("ACCEPT_OURS", "ACCEPT_FOREIGN_ADVANCED",
                           "ACTOR_VERIFIED_AUTO"):
            # accepting dispositions advance; ACCEPT_OURS pins to its
            # new_oid payload where the family carries one (section A).
            return str(extra.get("new_oid", f"{before}-advanced"))
    return before


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
              "authority": "fp-1", "epoch_before": "E0",
              "epoch_after": _epoch_after_for(variant, extra, "E0",
                                              _A_EPOCH_EFFECTS),
              "hold_effect": _A_HOLD_EFFECTS.get(variant, "NONE"),
              "actor_context": "dispatcher",
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
              "epoch_after": _epoch_after_for(variant, extra, "E0",
                                              _B_EPOCH_EFFECTS)})
    d.update(extra)
    return d


_SINGLE_PAYLOADS = {
    "protocol_genesis": {
        "protocol_epoch": "E0", "credential_mode": "SHARED",
        "protection_mode": "PREVENT", "classifier": "required:c:p:2",
        "roster_digest": "rd", "approver_set_digest": "ad",
        "per_base_epoch_anchors": "R1:refs/heads/main=E0"},
    "seat_result": {
        "roster_digest": "rd", "subject_digest": "sd", "attempt_id": "a1",
        "seat_id": "claude", "verdict": "APPROVE", "findings_digest": "fd"},
}


def _single_ev(event_name: str, eid: str, base: str = BASE1, **extra) -> dict:
    """A legitimate §9 SINGLE on the shared carrier — its `family` is its
    own schema name, so a lifecycle reducer filters it rather than halting."""
    d = _env(eid)
    d.update({"family": event_name, "base_key": base})
    d.update(_SINGLE_PAYLOADS[event_name])
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
           disposition="ACCEPT_OURS", new_oid="oid-other")])
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
    a("a_singles_on_a_shared_carrier_are_filtered",
      "panel round 3 CRITICAL: legitimate §9 SINGLES on the shared carrier "
      "(protocol_genesis, seat_result) carry their own schema name as "
      "`family` and are FILTERED — they must never halt the base, and the "
      "real effect_lifecycle pair around them must still reduce",
      [_single_ev("protocol_genesis", "s1"), prep,
       _single_ev("seat_result", "s2"),
       _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
           new_oid="oid-new")])
    a("a_unknown_family_deny",
      "DENY: a family outside the closed domain halts — an unknown enum "
      "VALUE halts like an unknown variant (§9), never a silent drop",
      [prep, _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
                 new_oid="oid-new", family="checkpoint_lifecycle")])
    a("a_empty_family_deny",
      "DENY: an empty family is absent, not 'the other stream'",
      [prep, _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
                 new_oid="oid-new", family="")])
    a("a_case_typo_family_deny",
      "DENY: a case-typo family (Effect_Lifecycle) is outside the domain — "
      "a corrupt tag must not absorb a durable terminal as success",
      [prep, _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
                 new_oid="oid-new", family="Effect_Lifecycle")])
    a("a_family_mistag_terminal_deny",
      "DENY: a durable TERMINAL mis-tagged with the peer family must halt, "
      "never be dropped — a silent drop rewrites EXPLAINED to HELD at the "
      "next cold start and bypasses the conflicting-disposition halt",
      [prep, _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
                 new_oid="oid-new", family="hold_lifecycle")])
    a("a_out_of_range_ts_deny",
      "DENY (panel round 3): a SHAPE-valid but impossible instant "
      "(2026-13-45T99:99:99Z) is not a timestamp — ts is semantically "
      "parsed, not merely regex-matched",
      [dict(prep, ts="2026-13-45T99:99:99Z")])
    a("a_epoch_advance_not_pinned_to_new_oid_deny",
      "DENY (panel round 3): the `explained` row's declared effect is "
      "`:= new_oid`, so the fence MUST be set to the observed new_oid — an "
      "advance to any other value is refused",
      [prep, _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
                 new_oid="oid-new", epoch_after="SOMETHING-ELSE")])
    a("a_advancing_row_that_does_not_advance_deny",
      "DENY: the positive half of the algebra — a row declaring an advance "
      "that leaves the fence unchanged is refused",
      [prep, _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
                 new_oid="oid-new", epoch_after="E0")])
    a("a_accept_ours_without_new_oid_deny",
      "DENY (panel round 3): ACCEPT_OURS(new_oid) is §6.0's payload "
      "algebra — the disposition is unconstructible without its payload",
      [prep,
       _ev("MoveToHoldFromPrepared", "e2", "m1", "PREPARED", "HELD",
           branch="hold"),
       _ev("MoveToHoldFromPrepared", "e2", "m1", "PREPARED", "HELD",
           branch="state"),
       {k: val for k, val in
        _ev("ReconcileAccept", "e3", "m1", "HELD", "RECONCILED",
            disposition="ACCEPT_OURS", new_oid="oid-accepted").items()
        if k != "new_oid"}])
    a("a_unknown_minor_and_field_tolerated",
      "ACCEPT (§9 evolution, reader-first rollout): a HIGHER schema_minor "
      "and an unknown top-level field are tolerated — additive minors must "
      "not halt, or a writer deploying ahead of a reader breaks the base",
      [dict(prep, schema_minor=9, some_future_field="ignored"),
       _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", "EXPLAINED",
           new_oid="oid-new", schema_minor=9)])
    a("a_replayed_accepting_reconcile_is_identity",
      "IDEMPOTENCE (§6.0): an accepting disposition re-applied to "
      "RECONCILED with the SAME d is identity, not a state-precondition "
      "error — the writer read HELD and cannot know to use the replay tag",
      [prep, hold_copy, state_copy,
       _ev("ReconcileAccept", "e3", "m1", "HELD", "RECONCILED",
           disposition="ACCEPT_FOREIGN_ADVANCED"),
       _ev("ReconcileAccept", "e4", "m1", "HELD", "RECONCILED",
           disposition="ACCEPT_FOREIGN_ADVANCED")])
    a("a_replayed_conflicting_reconcile_deny",
      "DENY: a CONFLICTING d′ on the same movement still halts",
      [prep, hold_copy, state_copy,
       _ev("ReconcileAccept", "e3", "m1", "HELD", "RECONCILED",
           disposition="ACCEPT_FOREIGN_ADVANCED"),
       _ev("ReconcileAccept", "e4", "m1", "HELD", "RECONCILED",
           disposition="ACCEPT_OURS", new_oid="oid-x")])
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

    def b(name: str, note: str, events: list[dict],
          credential_mode: str = "SHARED") -> None:
        # credential_mode is the RUN's mode (protocol_genesis), passed to the
        # reducer as context — never read from the events themselves.
        v[name] = {"machine": "section_b", "note": note,
                   "credential_mode": credential_mode, "events": events}

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
    b("b_concurrent_tag_resolved_to_new_hold",
      "CONCURRENCY (panel round 3): a writer tagged a redelivery from a "
      "read a concurrent writer invalidated — the delivery id is unseen, "
      "so the apply order resolves a NEW hold. The reducer's derivation is "
      "authoritative: park the hold and journal the disagreement, never "
      "halt the most concurrent path in the system",
      [obs, release("h2"),
       _hev("ObserveDeltaRedelivery", "h3", "RELEASED", "RELEASED",
            source_delivery_id="d9")])
    b("b_concurrent_tag_resolved_to_redelivery",
      "CONCURRENCY: the mirror case — a writer tagged a NEW delivery on an "
      "open hold but the id was already seen, so the apply order resolves a "
      "redelivery no-op; resolved and journalled, not halted",
      [obs,
       _hev("ObserveDeltaNewDeliveryOnOpenHold", "h2", "HELD_FOREIGN",
            "HELD_FOREIGN", source_delivery_id="d1", delta_old_oid="o0",
            delta_new_oid="o1")])
    b("b_concurrent_duplicate_creations",
      "CONCURRENCY: two independently-issued observe_delta creations for "
      "ONE delta — the second resolves onto the open hold rather than "
      "minting a colliding id",
      [obs,
       _hev("ObserveDelta", "h2", "GENESIS", "HELD_FOREIGN",
            delta_old_oid="o0", delta_new_oid="o1", source_delivery_id="d2")])
    b("b_replayed_accepting_reconcile_is_identity",
      "IDEMPOTENCE (§6.0): an accepting disposition re-applied with the "
      "SAME d is identity — a writer that read HELD_FOREIGN cannot know to "
      "use the replay tag, so the accept variant replayed onto the terminal "
      "it already produced must NOT halt",
      [obs, release("h2", disposition="ACCEPT_OURS"),
       release("h3", disposition="ACCEPT_OURS")])
    b("b_replayed_conflicting_reconcile_deny",
      "DENY: only a CONFLICTING d′ halts",
      [obs, release("h2", disposition="ACCEPT_OURS"),
       release("h3", disposition="ACCEPT_FOREIGN_ADVANCED")])
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
      "a SEPARATED RUN + VERIFIED_API + node id + a delivery recorded ON "
      "this hold + a matched digest deriving from the HOLD'S OWN delta: "
      "auto-release as ACTOR_VERIFIED_AUTO",
      [dict(obs, mode="SEPARATED"), ava("h2")], credential_mode="SEPARATED")
    b("b_actor_verified_shared_run_deny",
      "DENY (panel round 3): the RUN is SHARED — 'under SHARED, never' is "
      "enforced against protocol_genesis.credential_mode. The event's own "
      "`mode` AGREES with the run here, so the run-mode gate is the only "
      "rule that can fire (isolating it from the disagreement check)",
      [obs, ava("h2", mode="SHARED")], credential_mode="SHARED")
    b("b_mode_disagrees_with_run_deny",
      "DENY (panel round 3): an event whose self-declared `mode` disagrees "
      "with the run's credential mode is a typed halt — credential mode is "
      "run context, never event payload",
      [dict(obs, mode="SEPARATED")], credential_mode="SHARED")
    b("b_actor_verified_wrong_delta_digest_deny",
      "DENY (panel round 2 CRITICAL): matched_subject_digest that does not "
      "derive from the HOLD'S OWN recorded delta is self-asserted evidence "
      "— refused, not honoured",
      [dict(obs, mode="SEPARATED"),
       ava("h2", matched_subject_digest=_matched_delta_digest_for(
           BASE1, REF1, "o0", "SOMETHING-ELSE"))], credential_mode="SEPARATED")
    b("b_actor_verified_unresolvable_delivery_deny",
      "DENY (panel round 2 CRITICAL): a source_delivery_id that resolves to "
      "no delivery recorded on this hold cannot clear the auto-release gate",
      [dict(obs, mode="SEPARATED"), ava("h2", source_delivery_id="never-seen")],
      credential_mode="SEPARATED")
    b("b_replayed_actor_verified_match",
      "IDEMPOTENCE: a redelivered actor_verified_match on an already "
      "auto-released hold is absorbed by the event_id dedup",
      [dict(obs, mode="SEPARATED"), ava("h2"), ava("h2")],
      credential_mode="SEPARATED")
    b("b_verified_api_without_actor_node_id_deny",
      "DENY (panel round 3): VERIFIED_API evidence with no actor_node_id — "
      "a durable record claiming verified actor evidence with no "
      "attributable identity (actor_display is presentation, never "
      "predicate input)",
      [_hev("ObserveDelta", "h1", "GENESIS", "HELD_FOREIGN",
            delta_old_oid="o0", delta_new_oid="o1", source_delivery_id="d1",
            actor_verification="VERIFIED_API")])
    b("b_display_only_needs_no_actor_node_id",
      "the allow row for the same rule: DISPLAY_ONLY evidence carries no "
      "identity requirement",
      [obs])
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
    b("b_from_state_contradicts_reduced_deny",
      "DENY: the strict counterpart of the redelivery tolerance — a "
      "STATE-CHANGING event whose audit `from` contradicts the reduced "
      "state halts (only the state-independent no-op rows are tolerant)",
      [obs,
       _hev("HoldReconcileAccept", "h2", "STANDING", "RELEASED",
            hold_id=h0, disposition="ACCEPT_FOREIGN_ADVANCED")])
    b("b_missing_event_id_deny",
      "DENY: an event with no envelope event_id cannot be deduplicated, so "
      "byte-identity cannot be established",
      [{k: val for k, val in obs.items() if k != "event_id"}])
    b("b_auto_release_closed_after_reject_restore_deny",
      "DENY (panel round 3, cluster 7): an operator REFUSED this hold's "
      "release (REJECT_RESTORE_HOLD). Landing back in HELD_FOREIGN would "
      "otherwise re-open the ONLY state from which the non-operator "
      "ACTOR_VERIFIED_AUTO path can fire — PR0 takes the strictly safer "
      "reading and keeps it closed until an operator disposition. "
      "UNRATIFIED: see schema standing_reject_restore_* keys",
      [dict(obs, mode="SEPARATED"),
       _hev("HoldReconcileRejectRestoreHold", "h2", "HELD_FOREIGN",
            "HELD_FOREIGN", hold_id=h0, disposition="REJECT_RESTORE_HOLD",
            mode="SEPARATED"),
       ava("h3")],
      credential_mode="SEPARATED")
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
    b("b_family_mistag_deny",
      "DENY: a foreign-hold observation mis-tagged `effect_lifecycle` must "
      "halt — a silent drop leaves the base unparked: no hold, no "
      "admission pressure, no operator reconcile demanded",
      [dict(obs, family="effect_lifecycle")])
    b("b_unknown_family_deny",
      "DENY: a family outside the closed domain halts in section B too",
      [dict(obs, family="checkpoint_lifecycle")])
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
    e("epoch_missing_base_key_deny",
      "DENY: an epoch edge with no base_key cannot be partitioned — the "
      "fold refuses rather than folding it into an arbitrary base",
      [{k: val for k, val in _edge("e1", "E0", "E1").items()
        if k != "base_key"}], anchors1)
    e("epoch_unknown_major_deny",
      "DENY (panel round 3): the fold is the THIRD consumer of the durable "
      "stream and its output IS the fence epoch — an unknown-major event "
      "must never advance it",
      [dict(_edge("e1", "E0", "E1"), schema_major=7)], anchors1)
    e("epoch_unknown_family_deny",
      "DENY: the fold runs the same closed-family check as the reducers",
      [dict(_edge("e1", "E0", "E1"), family="checkpoint_lifecycle")], anchors1)
    e("epoch_cross_base_divergent_after_halt_deny",
      "DENY (panel round 3): a base pre-halted by a schema violation must "
      "still REGISTER its events in dedup — otherwise a divergent twin on "
      "a HEALTHY base later in the stream reads as first-seen and advances "
      "that base's fence from a reused id",
      [dict(_edge("x0", "E0", "E1", base=BASE2), schema_major=7),
       _edge("e1", "E0", "E1", base=BASE2),
       _edge("e1", "E0", "E9")],
      {BASE1: "E0", BASE2: "E0"})
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
