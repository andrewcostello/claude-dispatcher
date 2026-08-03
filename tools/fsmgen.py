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
        enums, frozen dataclasses per event variant, apply() dispatch for
        both machines (typed errors on illegal pairs), both reducers
        (section-A projection machine over the durable states, section-B
        hold reducer), the epoch fold, required_seats/blocking/aggregate,
        BoundaryError enum + maps.
    docs/generated/lifecycle_tables.md   the two §6.0 tables
    docs/generated/event_unions.md       the §9 union listings
    tests/boundary/vectors/t19/*.json    T19 vector skeletons with expected
                                         outputs computed BY the generated
                                         reducers and frozen as goldens
    schema/testdata/classifier_frames/*  golden + malformed frame vectors

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


def load_schemas() -> dict:
    out = {}
    for name in ("lifecycle_fsm", "panel_aggregate", "boundary_errors",
                 "classifier_protocol", "ast_allowlists"):
        with open(SCHEMA_DIR / f"{name}.yaml", encoding="utf-8") as fh:
            out[name] = yaml.safe_load(fh)
    return out


# ─── helpers ─────────────────────────────────────────────────────────────────

def as_list(v) -> list:
    return v if isinstance(v, list) else [v]


def snake_from_states(fsm: dict, section: str) -> list[str]:
    sec = fsm[section]
    return [sec["initial_pseudo_state"], *sec["states"]]


def compose_projection(fsm: dict) -> tuple[dict[str, list[str]], list[list[str]]]:
    """Derive the projection machine: for each durable state D, which live
    states are reachable from D through memory-only intermediates (the
    frontier a durable event's audit `from` may legally name), and the
    durable edge list (composed edges).
    """
    sec = fsm["section_a"]
    memory = set(sec["durability"]["memory_only"])
    durable = set(fsm["section_a"]["projection"]["durable_states"])
    # live adjacency over concrete rows only
    adj: dict[str, set[str]] = {}
    for row in sec["rows"]:
        frm = row["from"]
        to = row["to"]
        if to in ("ILLEGAL", "unchanged", "terminal") or frm in ("any_other",):
            continue
        for f in as_list(frm):
            adj.setdefault(f, set()).add(to)
    reachable: dict[str, list[str]] = {}
    edges: set[tuple[str, str]] = set()
    for d in sorted(durable):
        seen = {d}
        stack = [d]
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


# ─── generated python module ────────────────────────────────────────────────

def build_generated_module(s: dict) -> str:
    fsm = s["lifecycle_fsm"]
    panel = s["panel_aggregate"]
    errors = s["boundary_errors"]
    a = fsm["section_a"]
    b = fsm["section_b"]
    reachable, proj_edges = compose_projection(fsm)
    disp = fsm["reconcile_dispositions"]
    accepting = disp["accepting"]
    disp_names = [m["name"] for m in disp["members"]]

    L: list[str] = []
    w = L.append
    w('"""GENERATED by tools/fsmgen.py from schema/*.yaml — DO NOT EDIT.')
    w("")
    w("The single source of truth for the classification→gating boundary's")
    w("state machines, event unions, panel aggregate and error universe")
    w("(design v20 §§5.1/6.0/9; implementation plan §0.2). Regenerate with:")
    w("")
    w("    python tools/fsmgen.py")
    w("")
    w("CI runs `python tools/fsmgen.py --check` — hand edits here are a red")
    w('build by construction."""')
    w("")
    w("from __future__ import annotations")
    w("")
    w("import hashlib")
    w("import json")
    w("from dataclasses import dataclass")
    w("from enum import Enum, IntEnum")
    w("from typing import ClassVar, Mapping, Optional, Sequence")
    w("")
    w("# ─── errors ──────────────────────────────────────────────────────────")
    w("")

    # BoundaryError universe
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
    w("ERROR_PHASE: Mapping[BoundaryErrorCode, ErrorPhase] = {")
    for c in codes:
        w(f"    BoundaryErrorCode.{c['code']}: ErrorPhase.{c['phase']},")
    w("}")
    w("")
    w("ERROR_RETRIABILITY: Mapping[BoundaryErrorCode, Retriability] = {")
    for c in codes:
        w(f"    BoundaryErrorCode.{c['code']}: Retriability.{c['retriability']},")
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
        metric = pattern.format(code_lower=c["code"].lower())
        w(f"    BoundaryErrorCode.{c['code']}: \"{metric}\",")
    w("}")
    w("")
    exit_map = errors["cli_exit_map"]
    w("# CLI exit map (plan §0.2): 0/2/3/4 = ok/TERMINAL/RETRIABLE/OPERATOR.")
    w(f"CLI_EXIT_OK: int = {exit_map['ok']}")
    w("CLI_EXIT_MAP: Mapping[Retriability, int] = {")
    for r in errors["retriability"]:
        w(f"    Retriability.{r}: {exit_map[r]},")
    w("}")
    w("")
    unknown_rule = " ".join(str(errors["unknown_code_rule"]).split())
    w(f"UNKNOWN_CODE_RULE: str = {json.dumps(unknown_rule)}")
    w("")
    w("@dataclass(frozen=True)")
    w("class BoundaryError:")
    w('    """One closed error value — plan §0.2. Unknown code ⇒ TERMINAL."""')
    w("    code: BoundaryErrorCode")
    w("    detail: str = \"\"")
    w("")
    w("    @property")
    w("    def phase(self) -> ErrorPhase:")
    w("        return ERROR_PHASE[self.code]")
    w("")
    w("    @property")
    w("    def retriability(self) -> Retriability:")
    w("        return ERROR_RETRIABILITY[self.code]")
    w("")
    w("    @property")
    w("    def operator_action(self) -> str:")
    w("        return ERROR_OPERATOR_ACTION[self.code]")
    w("")
    w("    @property")
    w("    def metric(self) -> str:")
    w("        return ERROR_METRIC[self.code]")
    w("")
    w("    @property")
    w("    def exit_code(self) -> int:")
    w("        return CLI_EXIT_MAP[self.retriability]")
    w("")
    w("class BoundaryFault(Exception):")
    w('    """Typed carrier for a BoundaryError."""')
    w("")
    w("    def __init__(self, error: BoundaryError):")
    w("        super().__init__(f\"{error.code.value}: {error.detail}\")")
    w("        self.error = error")
    w("")
    w("class IllegalTransitionError(BoundaryFault):")
    w('    """ILLEGAL (state × event) pair — typed error, journalled, never a')
    w('    silent no-op (§6.0 default rows)."""')
    w("")
    w("    def __init__(self, machine: str, state: str, event: str, detail: str = \"\"):")
    w("        msg = f\"{machine}: {state} × {event}\" + (f\" — {detail}\" if detail else \"\")")
    w("        super().__init__(BoundaryError(BoundaryErrorCode.ILLEGAL_TRANSITION, msg))")
    w("        self.machine, self.state, self.event = machine, state, event")
    w("")

    # enums for machines
    w("# ─── machine states, events, dispositions ───────────────────────────")
    w("")
    w("class SectionAState(Enum):")
    for st in snake_from_states(fsm, "section_a"):
        w(f"    {st} = \"{st}\"")
    w("")
    w("class SectionBState(Enum):")
    for st in snake_from_states(fsm, "section_b"):
        w(f"    {st} = \"{st}\"")
    w("")
    w("class ReconcileDisposition(Enum):")
    for d in disp_names:
        w(f"    {d} = \"{d}\"")
    w("")
    w("ACCEPTING_DISPOSITIONS = frozenset({")
    for d in accepting:
        w(f"    ReconcileDisposition.{d},")
    w("})")
    w("SECTION_B_ONLY_DISPOSITIONS = frozenset({")
    for m in disp["members"]:
        if m.get("section_b_only"):
            w(f"    ReconcileDisposition.{m['name']},")
    w("})")
    w("")
    for enum_name, members in s["lifecycle_fsm"]["enums"].items():
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
    w("# Projection machine (round 14, codex): durable states + composed edges,")
    w("# derived from the live table by composing through memory-only states.")
    w(f"PROJECTION_DURABLE_STATES: tuple[str, ...] = {tuple(fsm['section_a']['projection']['durable_states'])!r}")
    w("PROJECTION_EDGES: tuple[tuple[str, str], ...] = (")
    for e in proj_edges:
        w(f"    ({e[0]!r}, {e[1]!r}),")
    w(")")
    w("# For each durable state: the live states reachable through memory-only")
    w("# intermediates — the frontier a durable event's audit `from` may name.")
    w("PROJECTION_REACHABLE: Mapping[str, tuple[str, ...]] = {")
    for d, states in sorted(reachable.items()):
        w(f"    {d!r}: {tuple(states)!r},")
    w("}")
    w("")

    # raw row tables
    for sec_key, table_name in (("section_a", "SECTION_A_ROWS"), ("section_b", "SECTION_B_ROWS")):
        sec = fsm[sec_key]
        w(f"{table_name}: tuple[Mapping[str, object], ...] = (")
        for row in sec["rows"]:
            frm = tuple(as_list(row["from"]))
            evs = tuple(as_list(row["event"]))
            w("    {" + ", ".join([
                f"'id': {row['id']!r}",
                f"'from': {frm!r}",
                f"'event': {evs!r}",
                f"'to': {row['to']!r}",
                f"'guard': {row.get('guard')!r}",
            ]) + "},")
        w(")")
        w("")

    # event variant dataclasses
    field_map = fsm["events"]["field_name_map"]
    envelope = fsm["events"]["envelope"]
    w("# ─── §9 event unions: one frozen dataclass per legal transition row ─")
    w("")
    w(f"ENVELOPE_REQUIRED: tuple[str, ...] = {tuple(envelope['required'])!r}")
    w(f"ENVELOPE_OPTIONAL: tuple[str, ...] = {tuple(envelope['optional'])!r}")
    w(f"FIELD_NAME_MAP: Mapping[str, str] = {dict(field_map)!r}")
    w("")

    def emit_variants(family: str, spec: dict, row_lookup: dict[str, dict]) -> list[str]:
        names = []
        common_req = [f for f in spec["common_required"]
                      if f not in ("trigger_event", "from", "to")]
        common_opt = list(spec.get("common_optional", []))
        for v in spec["variants"]:
            name = v["name"]
            names.append(name)
            row = row_lookup[v["row"]]
            froms = tuple(as_list(row["from"]) + list(v.get("extra_from", [])))
            to = row["to"]
            req_extra = [f for f in v.get("required", []) if f not in common_req]
            forbidden = tuple(v.get("forbidden", []))
            fixed = v.get("fixed", {})
            # required instance fields (no default), then optionals.
            req_fields = common_req + [f for f in req_extra if f not in common_opt]
            opt_fields = [f for f in common_opt if f not in v.get("required", [])]
            promoted = [f for f in v.get("required", []) if f in common_opt]
            req_fields += promoted
            w("@dataclass(frozen=True)")
            w(f"class {name}:")
            w(f'    """{family} variant — row `{row["id"]}`: '
              f'{"/".join(froms)} × {v["trigger"]} → {to}."""')
            w("")
            w(f"    FAMILY: ClassVar[str] = \"{family}\"")
            w(f"    TRIGGER: ClassVar[str] = \"{v['trigger']}\"")
            w(f"    ROW: ClassVar[str] = \"{row['id']}\"")
            w(f"    FROM_STATES: ClassVar[tuple[str, ...]] = {froms!r}")
            w(f"    TO_STATE: ClassVar[str] = {to!r}")
            w(f"    REQUIRED: ClassVar[tuple[str, ...]] = {tuple(req_fields)!r}")
            w(f"    FORBIDDEN: ClassVar[tuple[str, ...]] = {forbidden!r}")
            w(f"    FIXED: ClassVar[Mapping[str, str]] = {dict(fixed)!r}")
            w("")
            for f in req_fields:
                if f == "disposition":
                    w("    disposition: ReconcileDisposition")
                else:
                    w(f"    {field_map.get(f, f)}: str")
            for f in opt_fields:
                if f == "disposition":
                    w("    disposition: Optional[ReconcileDisposition] = None")
                else:
                    w(f"    {field_map.get(f, f)}: Optional[str] = None")
            w(f"    from_state: str = {froms[0]!r}")
            w("")
            w("    def __post_init__(self) -> None:")
            w("        if self.from_state not in self.FROM_STATES:")
            w("            raise ValueError(")
            w(f"                f\"{name}.from_state {{self.from_state!r}} \"")
            w(f"                f\"not in {{self.FROM_STATES!r}}\")")
            if fixed:
                for k, val in fixed.items():
                    if k == "disposition":
                        w(f"        if self.disposition is not ReconcileDisposition.{val}:")
                        w(f"            raise ValueError(\"{name}.disposition must be {val}\")")
                    elif k == "actor_verification":
                        w(f"        if self.{k} != \"{val}\":")
                        w(f"            raise ValueError(\"{name}.{k} must be {val}\")")
            if v["trigger"] == "operator_reconcile" and "guard" in row:
                if row["guard"] == "accepting_disposition":
                    w("        if self.disposition not in ACCEPTING_DISPOSITIONS:")
                    w(f"            raise ValueError(\"{name} requires an accepting disposition\")")
                elif row["guard"] == "reject_restore_hold":
                    w("        if self.disposition is not ReconcileDisposition.REJECT_RESTORE_HOLD:")
                    w(f"            raise ValueError(\"{name} requires REJECT_RESTORE_HOLD\")")
            w("")
        return names

    a_rows = {r["id"]: r for r in a["rows"]}
    b_rows = {r["id"]: r for r in b["rows"]}
    eff_names = emit_variants("effect_lifecycle", fsm["events"]["unions"]["effect_lifecycle"], a_rows)
    hold_names = emit_variants("hold_lifecycle", fsm["events"]["unions"]["hold_lifecycle"], b_rows)

    w("EFFECT_VARIANTS: Mapping[str, type] = {")
    for n in eff_names:
        w(f"    \"{n}\": {n},")
    w("}")
    w("HOLD_VARIANTS: Mapping[str, type] = {")
    for n in hold_names:
        w(f"    \"{n}\": {n},")
    w("}")
    w("")

    # static runtime (apply / reducers / fold / panel) — parameterized by the
    # literals above.
    w(RUNTIME)

    # panel literals
    rs = panel["roster_snapshot"]
    w("")
    w("# ─── §5.1 panel aggregate ────────────────────────────────────────────")
    w("")
    w("class PanelIntensity(IntEnum):")
    for k, v in panel["panel_intensity"].items():
        w(f"    {k} = {v}")
    w("")
    w("class Strategy(Enum):")
    for m in panel["strategy"]:
        w(f"    {m} = \"{m}\"")
    w("")
    w("class SeatVerdict(Enum):")
    for m in panel["seat_outcome"]["verdict_domain"]:
        w(f"    {m} = \"{m}\"")
    w("")
    w("class Severity(Enum):")
    for m in panel["seat_outcome"]["severity_domain"]:
        w(f"    {m} = \"{m}\"")
    w("")
    w("class PanelAggregateResult(Enum):")
    for m in panel["aggregate"]["result_domain"]:
        w(f"    {m} = \"{m}\"")
    w("")
    blocking = panel["blocking_predicate"]
    w(f"BLOCKING_VERDICTS = frozenset({{{', '.join('SeatVerdict.' + v for v in blocking['verdict_blocks'])}}})")
    w(f"BLOCKING_SEVERITIES = frozenset({{{', '.join('Severity.' + v for v in blocking['severity_blocks'])}}})")
    w("")
    w(PANEL_RUNTIME)
    src = "\n".join(L)
    if not src.endswith("\n"):
        src += "\n"
    return src


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
    if variant not in EFFECT_VARIANTS:
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
    if variant not in HOLD_VARIANTS:
        raise IllegalTransitionError("section_b", state.name.value, variant,
                                     "unknown event variant halts (§9)")
    if state.name.value not in event.FROM_STATES:
        raise IllegalTransitionError("section_b", state.name.value, variant)
    if isinstance(event, (ObserveDeltaRedelivery, ObserveDeltaNewDeliveryOnOpenHold)):
        return state  # unchanged — idempotent no-op / delivery recorded
    if isinstance(event, ActorVerifiedAuto):
        # SEPARATED + VERIFIED_API only; under SHARED, never (§6.0).
        if event.mode != CredentialMode.SEPARATED.value:
            raise IllegalTransitionError(
                "section_b", state.name.value, variant,
                "ACTOR_VERIFIED_AUTO requires SEPARATED; under SHARED, never")
        return MachineStateB(SectionBState.RELEASED, ReconcileDisposition.ACTOR_VERIFIED_AUTO)
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


# ─── reducers (T19 skeletons; PR4 hardens against live carriers) ────────────

def _canonical(d: Mapping[str, object]) -> str:
    return json.dumps({k: v for k, v in d.items() if k != "branch"},
                      sort_keys=True, separators=(",", ":"))


def _halt(code: BoundaryErrorCode, detail: str) -> dict:
    return {"code": code.value, "detail": detail}


def reduce_section_a(events: Sequence[Mapping[str, object]]) -> dict:
    """Reduce a durable effect_lifecycle stream through the PROJECTION
    machine (durable states + composed edges), never the live table
    (round 14, codex). Input event dicts carry at least: variant, event_id,
    movement_id, from, to; duplicate event_ids (dual-append twins) must be
    byte-identical or the base halts (EVENT_PAYLOAD_DIVERGENT).

    Cold-start step (5): an open PREPARED with no hold and no terminal gets
    a dual-appended {crash_recovery, PREPARED → HELD}; resume-submit is
    ILLEGAL (round 15, grok).
    """
    seen: dict[str, str] = {}
    movements: dict[str, MachineStateA] = {}
    order: list[str] = []
    for ev in events:
        eid = str(ev["event_id"])
        canon = _canonical(ev)
        if eid in seen:
            if seen[eid] != canon:
                return {"halted": _halt(BoundaryErrorCode.EVENT_PAYLOAD_DIVERGENT,
                                        f"event_id {eid} has divergent payloads")}
            continue  # dedup: dual-append twin / redelivered copy
        seen[eid] = canon
        variant = str(ev["variant"])
        cls = EFFECT_VARIANTS.get(variant)
        if cls is None:
            return {"halted": _halt(BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                                    f"unknown effect_lifecycle variant {variant!r}")}
        to_state = cls.TO_STATE
        if to_state in MEMORY_ONLY:
            return {"halted": _halt(BoundaryErrorCode.ILLEGAL_TRANSITION,
                                    f"memory-only transition {variant!r} in the durable stream")}
        mid = str(ev["movement_id"])
        cur = movements.get(mid, GENESIS_A)
        if mid not in movements:
            order.append(mid)
        live_from = str(ev.get("from", cls.FROM_STATES[0]))
        # Projection-machine step, NOT the live table: the durable `from` is
        # audit metadata naming a (possibly memory-only) live state, and must
        # sit on a composed path out of the current durable state; the
        # (durable, durable) pair must be a composed projection edge.
        frontier = PROJECTION_REACHABLE.get(cur.name.value, ())
        if live_from not in frontier or live_from not in cls.FROM_STATES:
            return {"halted": _halt(
                BoundaryErrorCode.ILLEGAL_TRANSITION,
                f"movement {mid}: durable {variant!r} audit from={live_from!r} "
                f"unreachable from durable state {cur.name.value}")}
        if (cur.name.value, to_state) not in PROJECTION_EDGES:
            return {"halted": _halt(
                BoundaryErrorCode.ILLEGAL_TRANSITION,
                f"movement {mid}: no projection edge "
                f"{cur.name.value} → {to_state} ({variant!r})")}
        disp = ev.get("disposition")
        kwargs: dict = {"from_state": live_from}
        if disp is not None:
            kwargs["disposition"] = ReconcileDisposition[str(disp)]
        for f in cls.REQUIRED:
            wire = FIELD_NAME_MAP.get(f, f)
            if wire in ("disposition", "from_state"):
                continue
            kwargs[wire] = str(ev.get(f, ev.get(wire, "")))
        try:
            event = cls(**kwargs)  # payload validation (guards, fixed values)
        except ValueError as exc:
            return {"halted": _halt(BoundaryErrorCode.ILLEGAL_TRANSITION, str(exc))}
        if isinstance(event, ReconcileReplayIdentity):
            if cur.disposition is not event.disposition:
                return {"halted": _halt(
                    BoundaryErrorCode.ILLEGAL_TRANSITION,
                    f"movement {mid}: RECONCILED({cur.disposition}) × "
                    f"operator_reconcile({event.disposition}) — conflicting d′")}
            movements[mid] = cur
        elif isinstance(event, ReconcileAccept):
            movements[mid] = MachineStateA(SectionAState.RECONCILED, event.disposition)
        elif isinstance(event, ReconcileRejectRestoreHold):
            movements[mid] = MachineStateA(SectionAState.HELD)
        else:
            movements[mid] = MachineStateA(SectionAState[to_state])
    result: dict[str, dict] = {}
    recovery: list[dict] = []
    for mid in order:
        st = movements[mid]
        if st.name is SectionAState.PREPARED:
            # open PREPARED, no hold, no terminal ⇒ recovery dual-append.
            recovery.append({
                "movement_id": mid, "trigger_event": "crash_recovery",
                "from": "PREPARED", "to": "HELD",
            })
            result[mid] = {"state": "HELD", "disposition": None,
                           "via_recovery_append": True}
        else:
            result[mid] = {"state": st.name.value,
                           "disposition": st.disposition.value if st.disposition else None,
                           "via_recovery_append": False}
    return {"movements": result, "recovery_appends": recovery, "halted": None}


def reduce_section_b(events: Sequence[Mapping[str, object]]) -> dict:
    """Reduce a hold_lifecycle stream into section-B states per hold_id.

    Redelivery semantics (§6.0, rounds 17–20): the same source_delivery_id
    maps to the same hold_id regardless of state — a redelivered
    dispositioned delta is an idempotent no-op, never a re-park.
    """
    seen: dict[str, str] = {}
    holds: dict[str, MachineStateB] = {}
    deliveries: dict[str, list[str]] = {}
    order: list[str] = []
    for ev in events:
        eid = str(ev["event_id"])
        canon = _canonical(ev)
        if eid in seen:
            if seen[eid] != canon:
                return {"halted": _halt(BoundaryErrorCode.EVENT_PAYLOAD_DIVERGENT,
                                        f"event_id {eid} has divergent payloads")}
            continue
        seen[eid] = canon
        variant = str(ev["variant"])
        cls = HOLD_VARIANTS.get(variant)
        if cls is None:
            return {"halted": _halt(BoundaryErrorCode.SCHEMA_MAJOR_UNKNOWN,
                                    f"unknown hold_lifecycle variant {variant!r}")}
        hid = str(ev["hold_id"])
        cur = holds.get(hid, GENESIS_B)
        if hid not in holds:
            order.append(hid)
        kwargs: dict = {"from_state": str(ev.get("from", cur.name.value))}
        disp = ev.get("disposition")
        if disp is not None:
            kwargs["disposition"] = ReconcileDisposition[str(disp)]
        for f in cls.REQUIRED:
            wire = FIELD_NAME_MAP.get(f, f)
            if wire in ("disposition", "from_state"):
                continue
            kwargs[wire] = str(ev.get(f, ev.get(wire, "")))
        if "mode" in ev and "mode" not in kwargs:
            kwargs["mode"] = str(ev["mode"])
        try:
            holds[hid] = apply_section_b(cur, cls(**kwargs))
        except (IllegalTransitionError, ValueError) as exc:
            return {"halted": _halt(BoundaryErrorCode.ILLEGAL_TRANSITION, str(exc))}
        sdid = ev.get("source_delivery_id")
        if sdid is not None and str(sdid) not in deliveries.setdefault(hid, []):
            deliveries[hid].append(str(sdid))
    result = {}
    for hid in order:
        st = holds[hid]
        result[hid] = {"state": st.name.value,
                       "disposition": st.disposition.value if st.disposition else None,
                       "deliveries": deliveries.get(hid, [])}
    return {"holds": result, "halted": None}


def fold_epochs(events: Sequence[Mapping[str, object]],
                anchors: Mapping[str, str]) -> dict:
    """The §6.0 recovery-step-(3) epoch fold, per base_key: edges are only
    epoch-ADVANCING transitions (epoch_before ≠ epoch_after), deduplicated by
    event_id, walked from the protocol_genesis anchor consuming unused edges.
    Exactly one candidate successor continues; zero with no unused edges is
    the valid tail; zero WITH unused edges is a gap ⇒ halt; more than one is
    a fork ⇒ halt; cycles or reused epochs ⇒ halt.
    """
    by_base: dict[str, dict[str, Mapping[str, object]]] = {}
    for ev in events:
        eb, ea = ev.get("epoch_before"), ev.get("epoch_after")
        if eb == ea:
            continue  # no-effect pairs are not edges (round 16, codex)
        base = str(ev.get("base_key", ""))
        by_base.setdefault(base, {}).setdefault(str(ev["event_id"]), ev)
    out: dict[str, dict] = {}
    for base, anchor in anchors.items():
        edges = list(by_base.get(base, {}).values())
        unused = list(edges)
        current = anchor
        visited = {anchor}
        status: dict = {"status": "ok", "epoch": current, "halt": None}
        while True:
            candidates = [e for e in unused if str(e["epoch_before"]) == current]
            if len(candidates) > 1:
                status = {"status": "halt", "epoch": current,
                          "halt": _halt(BoundaryErrorCode.EPOCH_FORK,
                                        f"{base}: fork at {current}")}
                break
            if not candidates:
                if unused:
                    status = {"status": "halt", "epoch": current,
                              "halt": _halt(BoundaryErrorCode.EPOCH_GAP,
                                            f"{base}: {len(unused)} unused edge(s)")}
                else:
                    status = {"status": "ok", "epoch": current, "halt": None}
                break
            edge = candidates[0]
            unused.remove(edge)
            nxt = str(edge["epoch_after"])
            if nxt in visited:
                status = {"status": "halt", "epoch": current,
                          "halt": _halt(BoundaryErrorCode.EPOCH_FORK,
                                        f"{base}: cycle/reused epoch {nxt}")}
                break
            visited.add(nxt)
            current = nxt
        out[base] = status
    return out
'''


PANEL_RUNTIME = '''
@dataclass(frozen=True)
class RosterSnapshot:
    """§5.1: {manifest_digest, roster_version, roster_digest,
    ordered_seat_ids, designated_single_id}."""

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


def roster_digest(roster_version: str, ordered_seat_ids: Sequence[str],
                  designated_single_id: str) -> str:
    """Canonical roster-digest preimage: roster_version ‖ ordered seat IDs ‖
    designated_single_id, newline-joined, SHA-256 (§5.1)."""
    preimage = "\\n".join([roster_version, *ordered_seat_ids, designated_single_id])
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Finding:
    severity: Severity


@dataclass(frozen=True)
class SeatOutcome:
    verdict: SeatVerdict
    findings: tuple[Finding, ...] = ()


@dataclass(frozen=True)
class UnparseableOutcome:
    """A seat result whose verdict or a finding severity fell outside the
    closed domains — a parse failure ⇒ INCOMPLETE, never skipped."""

    raw: str = ""


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
    {CRITICAL, HIGH} — over the closed domains; an UnparseableOutcome is not
    "blocking", it is a parse failure the aggregate turns into INCOMPLETE."""
    if isinstance(outcome, UnparseableOutcome):
        return False
    if outcome.verdict in BLOCKING_VERDICTS:
        return True
    return any(f.severity in BLOCKING_SEVERITIES for f in outcome.findings)


def aggregate(intensity: PanelIntensity, roster: RosterSnapshot,
              outcomes: Mapping[str, object]) -> PanelAggregateResult:
    """§5.1's one total aggregate, executed by BOTH strategies. The caller
    has already filtered seat results to the plan's (subject_digest,
    attempt_id) key. Any seat reporting a blocking finding ⇒ BLOCKED
    (unconditional in §5.1); outcome keys must equal required_seats exactly
    — no duplicates, no missing — and a required seat unavailable or
    unparseable ⇒ INCOMPLETE, never skipped. Otherwise APPROVED."""
    required = required_seats(intensity, roster)
    if any(blocking(outcomes[s]) for s in required if s in outcomes):
        return PanelAggregateResult.BLOCKED
    if set(outcomes.keys()) != set(required):
        return PanelAggregateResult.INCOMPLETE
    if any(isinstance(outcomes[s], UnparseableOutcome) for s in required):
        return PanelAggregateResult.INCOMPLETE
    return PanelAggregateResult.APPROVED
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
    # classification_evaluated variants
    for vname in ("CompleteClassification", "IncompleteClassification"):
        mm = re.search(vname + r"\{(.*?)\}", sect, re.S)
        if not mm:
            problems.append(f"§9: no field list for {vname}")
            continue
        want = _tokenize_fields(mm.group(1))
        spec = next(v for v in fsm["events"]["unions"]["classification_evaluated"]["variants"]
                    if v["name"] == vname)
        # the doc's outcome_kind token appears as outcome_kind; subject… → subject
        if want != set(spec["required"]):
            problems.append(f"§9 {vname}: design {sorted(want)} != schema {sorted(spec['required'])}")
    # common envelope
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

    def frame(policy_b: bytes, diff_b: bytes) -> bytes:
        body = (struct.pack(">B", 1)
                + struct.pack(">Q", len(policy_b)) + policy_b
                + struct.pack(">Q", len(diff_b)) + diff_b)
        return struct.pack(">I", len(body)) + body

    valid = frame(policy, diff)
    # policy_len exceeds the frame's remaining octets
    malformed = (struct.pack(">I", 1 + 8 + len(policy) + 8 + len(diff))
                 + struct.pack(">B", 1)
                 + struct.pack(">Q", len(policy) + 4096) + policy
                 + struct.pack(">Q", len(diff)) + diff)
    truncated = valid[: len(valid) - 7]
    trailing = valid + b"EXTRA"
    return {
        "valid_frame.bin": valid,
        "malformed_length.bin": malformed,
        "truncation.bin": truncated,
        "trailing_data.bin": trailing,
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
            "reason": case.get("reason"),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
        })
    doc = {
        "_generated_by": "tools/fsmgen.py",
        "frame_layout": "u32be outer_len | u8 version=1 | u64be policy_len | policy | u64be diff_len | diff",
        "bounds": s["classifier_protocol"]["bounds"],
        "cases": cases,
    }
    return json.dumps(doc, indent=2, sort_keys=False) + "\n"


# ─── T19 vector skeletons ────────────────────────────────────────────────────

def _ev(variant: str, eid: str, mid: str, frm: str, branch: str = "state",
        **extra) -> dict:
    d = {"family": "effect_lifecycle", "variant": variant, "event_id": eid,
         "movement_id": mid, "base_key": "R1:refs/heads/main", "from": frm,
         "branch": branch}
    d.update(extra)
    return d


def _hev(variant: str, eid: str, hid: str, frm: str, **extra) -> dict:
    d = {"family": "hold_lifecycle", "variant": variant, "event_id": eid,
         "hold_id": hid, "base_key": "R1:refs/heads/main", "from": frm}
    d.update(extra)
    return d


def build_t19_vectors(mod: types.ModuleType) -> dict[str, dict]:
    """Named §6.0 histories; expected outputs computed BY the generated
    reducers and frozen as goldens (design §12 / T19)."""
    prep = _ev("Prepare", "e1", "m1", "GENESIS")
    vectors: dict[str, dict] = {}

    def a_case(name: str, note: str, events: list[dict]) -> None:
        vectors[name] = {"machine": "section_a", "note": note, "events": events,
                         "expected": mod.reduce_section_a(events)}

    def b_case(name: str, note: str, events: list[dict]) -> None:
        vectors[name] = {"machine": "section_b", "note": note, "events": events,
                         "expected": mod.reduce_section_b(events)}

    def e_case(name: str, note: str, events: list[dict],
               anchors: dict[str, str]) -> None:
        vectors[name] = {"machine": "epoch_fold", "note": note, "events": events,
                         "anchors": anchors,
                         "expected": mod.fold_epochs(events, anchors)}

    a_case("success",
           "prepare → (submit/observe_effect in memory) → EXPLAINED terminal",
           [prep, _ev("Explained", "e2", "m1", "EFFECT_OBSERVED", new_oid="oid-new")])
    a_case("reject",
           "REJECTED_NO_EFFECT explained — never silently terminal",
           [prep, _ev("RejectExplained", "e2", "m1", "REJECTED_NO_EFFECT",
                      reason="ruleset refused the merge")])
    a_case("timeout",
           "submit/timeout_unknown die with the process — the durable trace "
           "degrades to PREPARED; recovery dual-appends crash_recovery → HELD",
           [prep])
    held_origins = [
        ("held_from_prepared_crash", "CrashRecoveryFromPrepared", "PREPARED"),
        ("held_from_prepared_later", "LaterObservationFromPrepared", "PREPARED"),
        ("held_from_prepared_move", "MoveToHoldFromPrepared", "PREPARED"),
        ("held_from_submitted_mismatch", "ObserveEffectParentMismatch", "SUBMITTED"),
        ("held_from_submitted_crash", "CrashRecoveryFromSubmitted", "SUBMITTED"),
        ("held_from_submitted_later", "LaterObservationFromSubmitted", "SUBMITTED"),
        ("held_from_unknown_later", "LaterObservationFromOutcomeUnknown", "OUTCOME_UNKNOWN"),
        ("held_from_unknown_crash", "CrashRecoveryFromOutcomeUnknown", "OUTCOME_UNKNOWN"),
    ]
    for name, variant, frm in held_origins:
        extra = {"new_oid": "oid-x", "authorization_id": "auth1"} \
            if variant == "ObserveEffectParentMismatch" else {}
        events = [prep,
                  _ev(variant, "e2", "m1", frm, branch="hold", **extra),
                  _ev(variant, "e2", "m1", frm, branch="state", **extra)]
        a_case(name, f"held origin: {frm} × {variant}", events)
    # the four dual-append crash points (hold branch happens-before the
    # state-branch closer — round 13, claude; the kill -9 golden is the seal)
    hold_copy = _ev("MoveToHoldFromPrepared", "e2", "m1", "PREPARED", branch="hold")
    state_copy = _ev("MoveToHoldFromPrepared", "e2", "m1", "PREPARED", branch="state")
    a_case("crash_p1_before_hold_append",
           "kill -9 before the hold-branch append: dangling PREPARED — "
           "coalesce recovers exactly one HELD, never a second submit",
           [prep])
    a_case("crash_p2_between_appends",
           "kill -9 between the dual appends: hold-branch copy is canonical "
           "inside the crash window — one movement, one hold",
           [prep, hold_copy])
    a_case("crash_p3_after_both_appends",
           "both copies present, one event_id — dedup makes the pair idempotent",
           [prep, hold_copy, state_copy])
    a_case("crash_p4_redelivered_duplicate",
           "duplicate redelivery of both copies — byte-identical, still one hold",
           [prep, hold_copy, state_copy, dict(hold_copy), dict(state_copy)])
    a_case("dual_append_divergent_payload_deny",
           "DENY: duplicate event_id with non-byte-identical payloads is an "
           "integrity violation ⇒ halt that base",
           [prep, hold_copy,
            _ev("MoveToHoldFromPrepared", "e2", "m1", "PREPARED", branch="state",
                reason="tampered")])
    a_case("reconciled_accept_ours",
           "HELD × operator_reconcile(ACCEPT_OURS) → RECONCILED(d)",
           [prep, hold_copy, state_copy,
            _ev("ReconcileAccept", "e3", "m1", "HELD", disposition="ACCEPT_OURS",
                new_oid="oid-accepted")])
    a_case("reject_restore_then_accept",
           "REJECT_RESTORE_HOLD stays HELD (assessment recorded); a later "
           "accepting reconcile is legal",
           [prep, hold_copy, state_copy,
            _ev("ReconcileRejectRestoreHold", "e3", "m1", "HELD",
                disposition="REJECT_RESTORE_HOLD"),
            _ev("ReconcileAccept", "e4", "m1", "HELD",
                disposition="ACCEPT_FOREIGN_ADVANCED")])
    a_case("reconcile_replay_identity",
           "RECONCILED(d) × operator_reconcile(same d) — identity, idempotent replay",
           [prep, hold_copy, state_copy,
            _ev("ReconcileAccept", "e3", "m1", "HELD",
                disposition="ACCEPT_FOREIGN_ADVANCED"),
            _ev("ReconcileReplayIdentity", "e4", "m1", "RECONCILED",
                disposition="ACCEPT_FOREIGN_ADVANCED")])
    a_case("reconcile_conflict_deny",
           "DENY: RECONCILED(d) × operator_reconcile(d′ ≠ d) ⇒ ILLEGAL typed error",
           [prep, hold_copy, state_copy,
            _ev("ReconcileAccept", "e3", "m1", "HELD",
                disposition="ACCEPT_FOREIGN_ADVANCED"),
            _ev("ReconcileReplayIdentity", "e4", "m1", "RECONCILED",
                disposition="ACCEPT_OURS")])
    a_case("resume_submit_illegal_deny",
           "DENY: a durable stream carrying a memory-only transition "
           "(resume-submit after crash) is ILLEGAL",
           [prep, _ev("Submit", "e2", "m1", "PREPARED", authorization_id="auth1")])

    # section B
    obs = _hev("ObserveDelta", "h1", "H1", "GENESIS", delta_old_oid="o0",
               delta_new_oid="o1", source_delivery_id="d1")
    b_case("b_foreign_hold_created",
           "— × observe_delta → HELD_FOREIGN (created)", [obs])
    b_case("b_redelivery_after_released",
           "cold-start golden (round 19, claude B2): redelivered webhook after "
           "RELEASED — same source_delivery_id ⇒ idempotent no-op, no re-park, "
           "no halt",
           [obs,
            _hev("HoldReconcileAccept", "h2", "H1", "HELD_FOREIGN",
                 disposition="ACCEPT_FOREIGN_ADVANCED"),
            _hev("ObserveDeltaRedelivery", "h3", "H1", "RELEASED",
                 source_delivery_id="d1")])
    b_case("b_new_delivery_on_open_hold",
           "round-20 row: NEW source_delivery_id, same delta tuple, open hold — "
           "delivery recorded, state unchanged",
           [obs,
            _hev("ObserveDeltaNewDeliveryOnOpenHold", "h2", "H1", "HELD_FOREIGN",
                 source_delivery_id="d2", delta_old_oid="o0", delta_new_oid="o1")])
    b_case("b_actor_verified_auto_separated",
           "SEPARATED + VERIFIED_API: auto-release as ACTOR_VERIFIED_AUTO",
           [obs,
            _hev("ActorVerifiedAuto", "h2", "H1", "HELD_FOREIGN",
                 actor_node_id="N_op", matched_subject_digest="s1",
                 actor_verification="VERIFIED_API", mode="SEPARATED",
                 disposition="ACTOR_VERIFIED_AUTO")])
    b_case("b_actor_verified_shared_deny",
           "DENY: under SHARED, never — actor_verified_match is "
           "SEPARATED-only (§6.0)",
           [obs,
            _hev("ActorVerifiedAuto", "h2", "H1", "HELD_FOREIGN",
                 actor_node_id="N_op", matched_subject_digest="s1",
                 actor_verification="VERIFIED_API", mode="SHARED",
                 disposition="ACTOR_VERIFIED_AUTO")])
    b_case("b_standing_reenter",
           "STANDING is re-enterable: park persistent, then reconcile releases",
           [obs,
            _hev("HoldReconcileStanding", "h2", "H1", "HELD_FOREIGN",
                 disposition="STANDING"),
            _hev("HoldReconcileAccept", "h3", "H1", "STANDING",
                 disposition="ACCEPT_OURS")])
    b_case("b_release_replay_identity",
           "RELEASED(d) × operator_reconcile(same d) — identity",
           [obs,
            _hev("HoldReconcileAccept", "h2", "H1", "HELD_FOREIGN",
                 disposition="ACCEPT_OURS"),
            _hev("HoldReconcileReplayIdentity", "h3", "H1", "RELEASED",
                 disposition="ACCEPT_OURS")])
    b_case("b_release_conflict_deny",
           "DENY: RELEASED(d) × operator_reconcile(d′ ≠ d) ⇒ ILLEGAL typed error",
           [obs,
            _hev("HoldReconcileAccept", "h2", "H1", "HELD_FOREIGN",
                 disposition="ACCEPT_OURS"),
            _hev("HoldReconcileReplayIdentity", "h3", "H1", "RELEASED",
                 disposition="ACCEPT_FOREIGN_ADVANCED")])

    # epoch fold histories (round 16, codex — seven histories)
    base = "R1:refs/heads/main"
    anchors = {base: "E0"}
    e_case("epoch_empty", "empty history: the anchor is the valid tail",
           [], anchors)
    e_case("epoch_prepare_only",
           "no-effect PREPARED(E0→E0) pairs are not edges — anchor stays the tail",
           [{"event_id": "e1", "base_key": base, "epoch_before": "E0",
             "epoch_after": "E0"}], anchors)
    e_case("epoch_no_effect_reject",
           "a no-effect reject (E0→E0) beside no advance — not a false fork",
           [{"event_id": "e1", "base_key": base, "epoch_before": "E0",
             "epoch_after": "E0"},
            {"event_id": "e2", "base_key": base, "epoch_before": "E0",
             "epoch_after": "E0"}], anchors)
    e_case("epoch_cross_stream",
           "sequential advances across BOTH durable streams (section A then "
           "section B release) chain to one tail",
           [{"event_id": "e1", "base_key": base, "epoch_before": "E0",
             "epoch_after": "E1", "stream": "effect_lifecycle"},
            {"event_id": "h1", "base_key": base, "epoch_before": "E1",
             "epoch_after": "E2", "stream": "hold_lifecycle"}], anchors)
    e_case("epoch_gap",
           "DENY: an advance whose epoch_before nothing produced — unused "
           "edge remains ⇒ gap ⇒ halt",
           [{"event_id": "e1", "base_key": base, "epoch_before": "E1",
             "epoch_after": "E2"}], anchors)
    e_case("epoch_fork",
           "DENY: two candidate successors from one epoch ⇒ fork ⇒ halt",
           [{"event_id": "e1", "base_key": base, "epoch_before": "E0",
             "epoch_after": "E1"},
            {"event_id": "e2", "base_key": base, "epoch_before": "E0",
             "epoch_after": "E2"}], anchors)
    e_case("epoch_cycle",
           "DENY: reused epoch / cycle ⇒ halt",
           [{"event_id": "e1", "base_key": base, "epoch_before": "E0",
             "epoch_after": "E1"},
            {"event_id": "e2", "base_key": base, "epoch_before": "E1",
             "epoch_after": "E0"}], anchors)
    # dual-append copies are deduplicated by event_id before the walk
    e_case("epoch_dual_append_copies",
           "carrier copies of one advance share an event_id — dedup, no fork",
           [{"event_id": "e1", "base_key": base, "epoch_before": "E0",
             "epoch_after": "E1", "branch": "hold"},
            {"event_id": "e1", "base_key": base, "epoch_before": "E0",
             "epoch_after": "E1", "branch": "state"}], anchors)
    return vectors


# ─── output orchestration ────────────────────────────────────────────────────

def module_from_source(src: str) -> types.ModuleType:
    # Registered in sys.modules for the exec: dataclass machinery resolves
    # cls.__module__ through it.
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
    mod = module_from_source(src)
    vectors = build_t19_vectors(mod)
    frames = build_frames(s)
    out: dict[Path, bytes] = {
        GENERATED_PY: src.encode("utf-8"),
        DOCS_DIR / "lifecycle_tables.md": (build_tables_md(s) + "\n").encode("utf-8"),
        DOCS_DIR / "event_unions.md": (build_unions_md(s) + "\n").encode("utf-8"),
        FRAMES_DIR / "vectors.json": build_frames_index(s, frames).encode("utf-8"),
    }
    for name, blob in frames.items():
        out[FRAMES_DIR / name] = blob
    for name, vec in vectors.items():
        out[VECTORS_DIR / f"{name}.json"] = (
            json.dumps(vec, indent=2, sort_keys=False) + "\n").encode("utf-8")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify committed outputs match regeneration; exit 1 on drift")
    args = ap.parse_args(argv)

    s = load_schemas()
    problems = compare_tables_with_design(s) + compare_unions_with_design(s)
    if problems:
        for p in problems:
            print(f"fsmgen: DESIGN/SCHEMA MISMATCH: {p}", file=sys.stderr)
        return 1

    outputs = build_outputs(s)
    if args.check:
        drift = []
        for path, blob in sorted(outputs.items()):
            if not path.exists():
                drift.append(f"missing: {path.relative_to(REPO_ROOT)}")
            elif path.read_bytes() != blob:
                drift.append(f"stale: {path.relative_to(REPO_ROOT)}")
        if drift:
            for d in drift:
                print(f"fsmgen --check: {d} (run: python tools/fsmgen.py)",
                      file=sys.stderr)
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
