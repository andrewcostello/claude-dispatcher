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


def _validate_schema_tokens(s: dict) -> None:
    """No unvalidated schema token reaches exec() (panel finding)."""
    fsm, errors = s["lifecycle_fsm"], s["boundary_errors"]
    for sec in ("section_a", "section_b"):
        for st in [fsm[sec]["initial_pseudo_state"], *fsm[sec]["states"]]:
            _require_ident(st, f"{sec}.states")
        for evn in fsm[sec]["events"]:
            _require_ident(evn, f"{sec}.events")
        for row in fsm[sec]["rows"]:
            _require_ident(row["id"], f"{sec}.rows")
    for m in fsm["reconcile_dispositions"]["members"]:
        _require_ident(m["name"], "reconcile_dispositions")
    for name, members in fsm["enums"].items():
        _require_ident(name, "enums")
        for m in members:
            _require_ident(m, f"enums.{name}")
    for fam, spec in fsm["events"]["unions"].items():
        _require_ident(fam, "unions")
        for v in spec["variants"]:
            _require_ident(v["name"], f"unions.{fam}")
            for f in [*v.get("required", []), *v.get("forbidden", [])]:
                _require_ident(f, f"unions.{fam}.{v['name']}")
    for name, spec in fsm["events"]["singles"].items():
        _require_ident(name, "singles")
        for f in [*spec["required"], *spec.get("optional", [])]:
            _require_ident(f, f"singles.{name}")
    for f in [*fsm["events"]["envelope"]["required"],
              *fsm["events"]["envelope"]["optional"]]:
        _require_ident(f, "envelope")
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


def emit_machine_constants(fsm: dict, reachable: dict, proj_edges: list) -> list[str]:
    L: list[str] = ["# ─── machine states, events, dispositions ───────────────────────────", ""]
    w = L.append
    a, b = fsm["section_a"], fsm["section_b"]
    disp = fsm["reconcile_dispositions"]
    for enum_name, sec in (("SectionAState", a), ("SectionBState", b)):
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
    w(f"STATE_BRANCH_REF: str = \"{dur['state_branch_ref']}\"")
    w(f"HOLD_BRANCH_REF: str = \"{dur['hold_branch_ref']}\"")
    w("")
    ceiling = a["recovery_ceiling"]
    w("# Recovery admission ceiling (§6.0 provisional bounds; the elapsed-")
    w("# time half is a PR4 obligation — see schema recovery_ceiling).")
    w(f"RECOVERY_CEILING_EVENTS: int = {int(ceiling['events'])}")
    w(f"RECOVERY_CEILING_REDUCE_SECONDS: int = {int(ceiling['reduce_seconds'])}")
    w("")
    w("# Projection machine (round 14, codex): durable states + composed edges,")
    w("# derived from the live table by composing through memory-only states.")
    w(f"PROJECTION_DURABLE_STATES: tuple[str, ...] = "
      f"{tuple(a['projection']['durable_states'])!r}")
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
        sec = fsm[sec_key]
        w(f"{table_name}: tuple[Mapping[str, object], ...] = (")
        for row in sec["rows"]:
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


def _variant_field_sets(fsm: dict, spec: dict, v: dict) -> tuple[list[str], list[str], list[str]]:
    """(required, optional, forbidden) wire-field lists for one variant —
    envelope + family commons + per-variant, disjoint by construction."""
    env = fsm["events"]["envelope"]
    fam_req = [f for f in spec["common_required"]
               if f not in ("trigger_event", "from", "to")]
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
    py_name = "from_state" if f == "from" else f
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
        w(f"    FAMILY: ClassVar[str] = \"{family}\"")
        w(f"    TRIGGER: ClassVar[str] = \"{v['trigger']}\"")
        w(f"    ROW: ClassVar[str] = \"{row['id']}\"")
        w(f"    FROM_STATES: ClassVar[tuple[str, ...]] = {froms!r}")
        w(f"    TO_STATE: ClassVar[str] = {row['to']!r}")
        w(f"    REQUIRED: ClassVar[tuple[str, ...]] = {tuple(required)!r}")
        w(f"    OPTIONAL: ClassVar[tuple[str, ...]] = {tuple(optional)!r}")
        w(f"    FORBIDDEN: ClassVar[tuple[str, ...]] = {tuple(forbidden)!r}")
        w(f"    FIXED: ClassVar[Mapping[str, str]] = {fixed!r}")
        w("")
        for f in required:
            _emit_field_decl(w, f, optional=False)
        for f in optional:
            _emit_field_decl(w, f, optional=True)
        w(f"    from_state: str = {froms[0]!r}  # audit `from` — validated ∈ FROM_STATES")
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
            optional: list[str], domains: dict[str, list[str]]) -> None:
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
        w("")

    for event_name, spec in fsm["events"]["singles"].items():
        domains = {key[:-len("_domain")]: list(val)
                   for key, val in spec.items() if key.endswith("_domain")}
        one(event_name, camel(event_name), list(spec["required"]),
            list(spec.get("optional", [])), domains)
    for v in fsm["events"]["unions"]["classification_evaluated"]["variants"]:
        one(f"classification_evaluated/{v['name']}", v["name"],
            list(v["required"]), [], {})
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


def _py_field(f: str) -> str:
    return FIELD_NAME_MAP.get(f, f)


def _validate_event_fields(event: object) -> None:
    """Shared __post_init__ validation: required fields present with the
    right type (never coerced), enum fields are enum INSTANCES, the audit
    from_state names a legal FROM state. Raises ValueError."""
    cls = type(event)
    name = cls.__name__
    for f in cls.REQUIRED:
        _validate_field_value(name, f, getattr(event, _py_field(f)), required=True)
    for f in cls.OPTIONAL:
        value = getattr(event, _py_field(f), None)
        if value is not None:
            _validate_field_value(name, f, value, required=False)
    from_states = getattr(cls, "FROM_STATES", None)
    if from_states is not None:
        from_state = event.from_state
        if from_state not in from_states:
            raise ValueError(
                f"{name}.from_state {from_state!r} not in {from_states!r}")


def _validate_field_value(name: str, f: str, value: object, required: bool) -> None:
    enum_t = _ENUM_WIRE_FIELDS.get(f)
    if enum_t is not None:
        if not isinstance(value, enum_t):
            raise ValueError(
                f"{name}.{f} must be a {enum_t.__name__} instance, got {value!r}")
        return
    if f in _INT_WIRE_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name}.{f} must be an int, got {value!r}")
        return
    if not isinstance(value, str) or (required and value == ""):
        raise ValueError(f"{name}.{f} must be a non-empty str, got {value!r}")


def _convert_wire_value(cls_name: str, f: str, value: object) -> object:
    """Convert one wire value to the typed field — unknown enum values and
    wrong types raise WireViolation (typed halt), never KeyError."""
    enum_t = _ENUM_WIRE_FIELDS.get(f)
    if enum_t is not None:
        if isinstance(value, enum_t):
            return value
        try:
            return enum_t(str(value))
        except ValueError:
            raise WireViolation(
                f"{cls_name}.{f}: unknown value {value!r} for closed enum "
                f"{enum_t.__name__} — halts like an unknown variant (§9)") from None
    if f in _INT_WIRE_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int):
            raise WireViolation(f"{cls_name}.{f}: must be an int, got {value!r}")
        return value
    if not isinstance(value, str) or value == "":
        raise WireViolation(f"{cls_name}.{f}: must be a non-empty str, got {value!r}")
    return value


def build_wire_event(variants: Mapping[str, type], ev: Mapping[str, object]) -> object:
    """Construct a typed event from a wire dict, fail-closed: unknown
    variant, missing REQUIRED, present FORBIDDEN, or unknown enum value ⇒
    WireViolation (⇒ SCHEMA_MAJOR_UNKNOWN halt); required fields are NEVER
    defaulted. Guard breaches inside the variant's __post_init__ surface as
    ValueError (⇒ ILLEGAL_TRANSITION)."""
    variant = ev.get("variant")
    cls = variants.get(str(variant))
    if cls is None:
        raise WireViolation(
            f"unknown event variant {variant!r} "
            f"(event_id {ev.get('event_id')!r}) — unknown variants halt (§9)")
    name = cls.__name__
    if ev.get("from") is None:
        raise WireViolation(f"{name}: required audit field 'from' absent "
                            f"(event_id {ev.get('event_id')!r})")
    if cls.TO_STATE != "unchanged" and ev.get("to") not in (None, cls.TO_STATE):
        raise WireViolation(
            f"{name}: audit 'to' {ev.get('to')!r} contradicts the row's "
            f"{cls.TO_STATE!r} (event_id {ev.get('event_id')!r})")
    kwargs: dict = {"from_state": str(ev["from"])}
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


# ─── reducers (T19 skeletons; PR4 hardens against live carriers) ────────────

def _canonical(d: Mapping[str, object]) -> str:
    return json.dumps({k: v for k, v in d.items() if k != "branch"},
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
    def __init__(self, halt: dict):
        super().__init__(halt["detail"])
        self.halt = halt


class _Dedup:
    """Duplicate-event_id absorption with byte-identical enforcement —
    divergence is an integrity violation (EVENT_PAYLOAD_DIVERGENT). Shared
    by both reducers AND the epoch fold so the contract cannot drift
    (panel finding: the fold silently kept the first payload)."""

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}

    def check(self, ev: Mapping[str, object]) -> str:
        """'new' | 'dup'; raises _DivergentDuplicate on divergence or a
        missing envelope event_id."""
        eid = ev.get("event_id")
        if not isinstance(eid, str) or eid == "":
            raise _DivergentDuplicate(_halt(
                BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                f"event missing required envelope field 'event_id': {ev!r}", ev))
        canon = _canonical(ev)
        if eid in self._seen:
            if self._seen[eid] != canon:
                raise _DivergentDuplicate(_halt(
                    BoundaryErrorCode.EVENT_PAYLOAD_DIVERGENT,
                    f"event_id {eid!r} has divergent payloads — integrity "
                    f"violation, halt this base", ev))
            return "dup"
        self._seen[eid] = canon
        return "new"


def _fmt_a(st: MachineStateA, via_recovery: bool = False) -> dict:
    return {"state": st.name.value,
            "disposition": st.disposition.value if st.disposition else None,
            "via_recovery_append": via_recovery}


def reduce_section_a(events: Sequence[Mapping[str, object]]) -> dict:
    """Reduce a durable effect_lifecycle stream through the PROJECTION
    machine (durable states + composed edges), never the live table
    (round 14, codex) — reconcile steps, whose durable states ARE live
    states, delegate to apply_section_a. Partitioned by base_key.

    Uniform result shape — success and halt both carry
    {movements, recovery_appends, halted}; a halted base is never
    indistinguishable from an empty one, and halt results carry the state
    reduced so far.

    Cold-start step (5): an open PREPARED with no hold and no terminal gets
    a dual-appended {crash_recovery, PREPARED → HELD} with a DERIVED
    event_id; resume-submit is ILLEGAL (round 15, grok)."""
    movements: dict[str, dict[str, MachineStateA]] = {}
    order: list[tuple[str, str]] = []

    def finish(halted: Optional[dict]) -> dict:
        out: dict[str, dict] = {}
        recovery: list[dict] = []
        for base, mid in order:
            st = movements[base][mid]
            if halted is None and st.name is SectionAState.PREPARED:
                recovery.append({
                    "event_id": derive_recovery_event_id(base, mid),
                    "movement_id": mid, "base_key": base,
                    "trigger_event": "crash_recovery",
                    "from": "PREPARED", "to": "HELD"})
                out.setdefault(base, {})[mid] = _fmt_a(
                    MachineStateA(SectionAState.HELD), via_recovery=True)
            else:
                out.setdefault(base, {})[mid] = _fmt_a(st)
        return {"movements": out, "recovery_appends": recovery, "halted": halted}

    if len(events) > RECOVERY_CEILING_EVENTS:
        return finish(_halt(BoundaryErrorCode.RECOVERY_CEILING,
                            f"{len(events)} events exceed the recovery "
                            f"admission ceiling ({RECOVERY_CEILING_EVENTS})"))
    dedup = _Dedup()
    for ev in events:
        try:
            if dedup.check(ev) == "dup":
                continue  # dual-append twin / redelivered copy
            event = build_wire_event(EFFECT_VARIANTS, ev)
        except _DivergentDuplicate as exc:
            return finish(exc.halt)
        except WireViolation as exc:
            return finish(_halt(exc.code, exc.detail, ev))
        except ValueError as exc:
            return finish(_halt(BoundaryErrorCode.ILLEGAL_TRANSITION, str(exc), ev))
        cls = type(event)
        if cls.TO_STATE in MEMORY_ONLY:
            return finish(_halt(
                BoundaryErrorCode.ILLEGAL_TRANSITION,
                f"memory-only transition {cls.__name__!r} in the durable "
                f"stream (event_id {ev.get('event_id')!r}) — resume-submit "
                f"is ILLEGAL", ev))
        base, mid = event.base_key, event.movement_id
        cur = movements.get(base, {}).get(mid, GENESIS_A)
        if mid not in movements.get(base, {}):
            movements.setdefault(base, {})[mid] = GENESIS_A
            order.append((base, mid))
        # projection validation: audit `from` must sit on a composed path out
        # of the current durable state, and the durable pair must be an edge.
        frontier = PROJECTION_REACHABLE.get(cur.name.value, ())
        if event.from_state not in frontier:
            return finish(_halt(
                BoundaryErrorCode.ILLEGAL_TRANSITION,
                f"movement {mid}@{base}: durable {cls.__name__!r} audit "
                f"from={event.from_state!r} unreachable from durable state "
                f"{cur.name.value} (event_id {ev.get('event_id')!r})", ev))
        if (cur.name.value, cls.TO_STATE) not in PROJECTION_EDGES:
            return finish(_halt(
                BoundaryErrorCode.ILLEGAL_TRANSITION,
                f"movement {mid}@{base}: no projection edge "
                f"{cur.name.value} → {cls.TO_STATE} "
                f"({cls.__name__!r}, event_id {ev.get('event_id')!r})", ev))
        if cls.TRIGGER == "operator_reconcile":
            # durable HELD/RECONCILED are live states — delegate to the one
            # live-table dispatch instead of re-implementing it.
            try:
                movements[base][mid] = apply_section_a(cur, event)
            except IllegalTransitionError as exc:
                return finish(_halt(BoundaryErrorCode.ILLEGAL_TRANSITION,
                                    str(exc), ev))
        else:
            movements[base][mid] = MachineStateA(SectionAState[cls.TO_STATE])
    return finish(None)


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


def reduce_section_b(events: Sequence[Mapping[str, object]]) -> dict:
    """Reduce a hold_lifecycle stream into section-B states per
    (base_key, hold_id), implementing §6.0's observe_delta apply order and
    hold_id derivation for real: the reducer resolves the hold; an event
    whose variant tag contradicts the resolution, or whose declared hold_id
    contradicts the derivation, is an integrity halt — fail closed on
    mis-tagged writers. Redelivery semantics (rounds 17–20): the same
    source_delivery_id maps to the same hold_id regardless of state; a
    genuinely NEW delivery after RELEASED derives the next occurrence and
    parks again. Uniform result shape as reduce_section_a."""
    books: dict[str, _HoldBook] = {}
    base_order: list[str] = []

    def finish(halted: Optional[dict]) -> dict:
        out: dict[str, dict] = {}
        for base in base_order:
            book = books[base]
            out[base] = {
                hid: {"state": book.holds[hid].name.value,
                      "disposition": (book.holds[hid].disposition.value
                                      if book.holds[hid].disposition else None),
                      "deliveries": book.deliveries.get(hid, [])}
                for hid in book.order}
        return {"holds": out, "halted": halted}

    if len(events) > RECOVERY_CEILING_EVENTS:
        return finish(_halt(BoundaryErrorCode.RECOVERY_CEILING,
                            f"{len(events)} events exceed the recovery "
                            f"admission ceiling ({RECOVERY_CEILING_EVENTS})"))
    dedup = _Dedup()
    for ev in events:
        try:
            if dedup.check(ev) == "dup":
                continue
            event = build_wire_event(HOLD_VARIANTS, ev)
        except _DivergentDuplicate as exc:
            return finish(exc.halt)
        except WireViolation as exc:
            return finish(_halt(exc.code, exc.detail, ev))
        except ValueError as exc:
            return finish(_halt(BoundaryErrorCode.ILLEGAL_TRANSITION, str(exc), ev))
        base = event.base_key
        book = books.get(base)
        if book is None:
            book = books[base] = _HoldBook()
            base_order.append(base)
        cls = type(event)
        if cls.TRIGGER == "observe_delta":
            resolution, hid = _resolve_observe_delta(book, base, event)
            if cls.__name__ != _OBSERVE_EXPECTED[resolution]:
                return finish(_halt(
                    BoundaryErrorCode.ILLEGAL_TRANSITION,
                    f"apply order resolves {resolution!r} (hold {hid}) but "
                    f"the event is tagged {cls.__name__!r} "
                    f"(event_id {ev.get('event_id')!r})", ev))
            if event.hold_id is not None and event.hold_id != hid:
                return finish(_halt(
                    BoundaryErrorCode.ILLEGAL_TRANSITION,
                    f"declared hold_id {event.hold_id!r} contradicts the "
                    f"derived/resolved {hid!r} "
                    f"(event_id {ev.get('event_id')!r})", ev))
            cur = book.holds.get(hid, GENESIS_B)
        else:
            hid = event.hold_id
            cur = book.holds.get(hid)
            if cur is None:
                return finish(_halt(
                    BoundaryErrorCode.ILLEGAL_TRANSITION,
                    f"{cls.__name__!r} references unknown hold {hid!r} "
                    f"(event_id {ev.get('event_id')!r})", ev))
        if event.from_state != cur.name.value:
            return finish(_halt(
                BoundaryErrorCode.ILLEGAL_TRANSITION,
                f"hold {hid}: audit from={event.from_state!r} contradicts "
                f"the reduced state {cur.name.value} "
                f"(event_id {ev.get('event_id')!r})", ev))
        try:
            new = apply_section_b(cur, event)
        except IllegalTransitionError as exc:
            return finish(_halt(BoundaryErrorCode.ILLEGAL_TRANSITION, str(exc), ev))
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
    return finish(None)


def fold_epochs(events: Sequence[Mapping[str, object]],
                anchors: Mapping[str, str]) -> dict:
    """The §6.0 recovery-step-(3) epoch fold, per base_key: edges are only
    epoch-ADVANCING transitions (epoch_before ≠ epoch_after), deduplicated
    by event_id (divergent duplicates halt — the same _Dedup contract as
    the reducers), walked from the protocol_genesis anchor consuming unused
    edges. O(E): edges are bucketed by epoch_before once. Exactly one
    candidate successor continues; zero with no unused edges is the valid
    tail; zero WITH unused edges is a gap ⇒ halt; more than one is a fork
    ⇒ halt; cycles or reused epochs ⇒ halt. A base that has edges but NO
    anchor is a typed halt, never silently dropped. Halt details name the
    offending epochs and event_ids."""
    if len(events) > RECOVERY_CEILING_EVENTS:
        return {base: {"status": "halt", "epoch": anchor,
                       "halt": _halt(BoundaryErrorCode.RECOVERY_CEILING,
                                     f"{len(events)} events exceed the "
                                     f"recovery admission ceiling "
                                     f"({RECOVERY_CEILING_EVENTS})")}
                for base, anchor in sorted(anchors.items())}
    dedup = _Dedup()
    edges_by_base: dict[str, list[Mapping[str, object]]] = {}
    base_halts: dict[str, dict] = {}
    for ev in events:
        eb, ea = ev.get("epoch_before"), ev.get("epoch_after")
        if eb is None or ea is None or eb == ea:
            continue  # no-effect pairs are not edges (round 16, codex)
        base = str(ev.get("base_key") or "")
        try:
            if dedup.check(ev) == "dup":
                continue  # carrier copies of one advance share an event_id
        except _DivergentDuplicate as exc:
            base_halts.setdefault(base, exc.halt)
            continue
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
    {designated_single_id}; SKIP demands no seats (§5.1/§5.2)."""
    if intensity is PanelIntensity.FULL:
        return tuple(roster.ordered_seat_ids)
    if intensity is PanelIntensity.SINGLE:
        return (roster.designated_single_id,)
    return ()


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
    return {
        "valid_frame.bin": valid,
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


def _recovery_id_for(base: str, movement_id: str) -> str:
    preimage = "\n".join(["recovery=crash_recovery", f"base={base}",
                          f"movement={movement_id}"])
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def _env(eid: str) -> dict:
    return {"schema_major": 1, "schema_minor": 0, "event_id": eid,
            "ts": "1970-01-01T00:00:00Z", "run_id": "run-1",
            "trace_id": "trace-1", "protocol_epoch": "E0"}


def _ev(variant: str, eid: str, mid: str, frm: str, to: str,
        base: str = BASE1, branch: str = "state", **extra) -> dict:
    d = _env(eid)
    d.update({"family": "effect_lifecycle", "variant": variant,
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
              "base_key": base, "from": frm, "to": to, "ref": REF1,
              "mode": "SHARED", "actor_verification": "DISPLAY_ONLY",
              "actor_display": "someone", "epoch_before": "E0",
              "epoch_after": "E0"})
    d.update(extra)
    return d


def _edge(eid: str, eb: str, ea: str, base: str = BASE1, **extra) -> dict:
    d = _env(eid)
    d.update({"base_key": base, "epoch_before": eb, "epoch_after": ea})
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
      "— byte-identical twins converge through dedup instead of halting",
      [prep,
       _ev("CrashRecoveryFromPrepared", _recovery_id_for(BASE1, "m1"),
           "m1", "PREPARED", "HELD", branch="hold"),
       _ev("CrashRecoveryFromPrepared", _recovery_id_for(BASE1, "m1"),
           "m1", "PREPARED", "HELD", branch="state")])
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
    b("b_actor_verified_auto_separated",
      "SEPARATED + VERIFIED_API + node id + matched subject: auto-release "
      "as ACTOR_VERIFIED_AUTO",
      [dict(obs, mode="SEPARATED"),
       _hev("ActorVerifiedAuto", "h2", "HELD_FOREIGN", "RELEASED",
            hold_id=h0, actor_node_id="N-op", matched_subject_digest="subj-1",
            actor_verification="VERIFIED_API", mode="SEPARATED",
            disposition="ACTOR_VERIFIED_AUTO")])
    b("b_actor_verified_shared_deny",
      "DENY: under SHARED, never — the ActorVerifiedAuto event is "
      "unconstructible without SEPARATED (§6.0)",
      [obs,
       _hev("ActorVerifiedAuto", "h2", "HELD_FOREIGN", "RELEASED",
            hold_id=h0, actor_node_id="N-op", matched_subject_digest="subj-1",
            actor_verification="VERIFIED_API", mode="SHARED",
            disposition="ACTOR_VERIFIED_AUTO")])
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
    return v


def build_t19_vectors() -> dict[str, dict]:
    """Named §6.0 histories — INPUTS ONLY. Expected outputs are the
    hand-written oracle in tests/boundary/vectors/t19_expected.json, which
    this tool never writes (independent-oracle rule)."""
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
    for name, vec in build_t19_vectors().items():
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
    # the vector corpus is exact: stray files are drift too (the expected
    # oracle lives OUTSIDE this dir and is never generated).
    want_vectors = {p.name for p in outputs if p.parent == VECTORS_DIR}
    if VECTORS_DIR.exists():
        for p in sorted(VECTORS_DIR.glob("*.json")):
            if p.name not in want_vectors:
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
