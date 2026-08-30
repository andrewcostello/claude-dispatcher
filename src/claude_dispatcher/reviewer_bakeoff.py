"""Reviewer bake-off: which families actually catch a seeded defect.

The panel's seat order — and therefore which seat is dropped first when the
panel is trimmed — cites a bake-off (PR-1353) whose evidence is not in this
repo and cannot be reproduced. Two recorded numbers already disagree with it:
`docs/retroactive_panel_results/REPORT.md` has codex raising CHANGES_REQUESTED
on 6 of 7 tickets while claude approved 3 of 7, and the seat-roster comment
records lifetime finding counts of claude 115, codex 127, grok 129.

So this harness answers the question with GROUND TRUTH rather than tallies.
Every case in ``docs/reviewer-bakeoff/corpus`` is a before/after pair where the
defect (or its absence) is known by construction, which is the same move the
project already makes for tests: break it on purpose and see who notices.

Two numbers per family, and the second is why controls exist:

  * DETECTION — of the seeded defects, how many did this family raise as a
    blocking (HIGH/CRITICAL) finding on the right file.
  * FALSE POSITIVE — of the control cases, which contain no defect, how many
    did it block anyway. A family that blocks everything scores 100% detection
    and is worthless.

Reviewers are driven through ``cross_family_reviewer.run_panel``, so each one
sees the exact prompt it sees in a production panel.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import cross_family_reviewer as cfr
from . import prompt_provenance

#: Severities that make a finding count as "caught it". A MEDIUM note about a
#: money-conservation defect did not stop the merge, so it is not a catch.
BLOCKING = (cfr.Severity.CRITICAL, cfr.Severity.HIGH)


@dataclass
class Case:
    """One corpus case: a diff, and the truth about what is wrong with it."""

    cid: str
    language: str
    kind: str
    severity: str
    control: bool
    defect_file: str | None
    #: Every file the defect spans. A cross-file defect has no single site —
    #: each hunk is plausible alone and only the INTERACTION is wrong — so
    #: naming any of the involved files is a legitimate way to report it.
    defect_files: tuple[str, ...]
    defect_description: str | None
    #: Optional narrowing. Matching on the file alone is enough when the file
    #: holds only the seeded defect, and NOT enough for a large file where a
    #: reviewer can name the right file for the wrong reason — the
    #: attention-under-noise case is exactly that. When set, a finding must
    #: also mention one of these.
    defect_markers: tuple[str, ...]
    summary: str
    diff: str

    @property
    def defect_basename(self) -> str:
        return Path(self.defect_file or "").name

    @property
    def defect_basenames(self) -> tuple[str, ...]:
        return tuple(Path(f).name for f in self.defect_files if f)


@dataclass
class FamilyScore:
    detected: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)
    clean_controls: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    findings_total: int = 0
    seconds_total: float = 0.0

    @property
    def detection_rate(self) -> float:
        n = len(self.detected) + len(self.missed)
        return len(self.detected) / n if n else 0.0

    @property
    def false_positive_rate(self) -> float:
        n = len(self.false_positives) + len(self.clean_controls)
        return len(self.false_positives) / n if n else 0.0


def load_corpus(corpus_dir: Path) -> list[Case]:
    """Read every case directory, rendering before/after into a real diff."""
    cases: list[Case] = []
    for d in sorted(p for p in corpus_dir.iterdir() if p.is_dir()):
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        defect = meta.get("defect") or {}
        cases.append(Case(
            cid=meta["id"],
            language=meta["language"],
            kind=meta["kind"],
            severity=meta["severity"],
            control=bool(meta.get("control")),
            defect_file=defect.get("file"),
            defect_files=tuple(defect.get("files") or (
                [defect["file"]] if defect.get("file") else [])),
            defect_description=defect.get("description"),
            defect_markers=tuple(defect.get("markers") or ()),
            summary=meta["summary"],
            diff=_render_diff(d),
        ))
    return cases


def _render_diff(case_dir: Path) -> str:
    """`git diff --no-index before after`, with the scaffolding paths removed.

    The reviewer must see `src/ledger.ts`, not `after/src/ledger.ts`: a path
    that looks like a fixture invites a different standard of review than a
    path that looks like production.
    """
    proc = subprocess.run(
        ["git", "diff", "--no-index", "--", "before", "after"],
        cwd=case_dir, capture_output=True, text=True, check=False,
    )
    # git exits 1 when the trees differ, which is the normal case here.
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"{case_dir}: git diff failed: {proc.stderr.strip()}")
    out = proc.stdout
    for prefix in ("a/before/", "b/before/", "a/after/", "b/after/"):
        out = out.replace(prefix, prefix[:2])
    return out.replace(" before/", " ").replace(" after/", " ")


def _caught(verdict: cfr.ReviewerVerdict, case: Case) -> bool:
    """Did this family raise the seeded defect as a blocking finding?

    Location match is on the file's BASENAME. Families spell a location
    differently (`src/ledger.ts:12`, `ledger.ts`, `split()` in `src/ledger.ts`),
    and requiring an exact line would score presentation rather than detection.
    """
    names = case.defect_basenames
    for f in verdict.findings:
        if f.severity not in BLOCKING:
            continue
        where = f"{getattr(f, 'location', '') or ''} {getattr(f, 'description', '') or ''}"
        if not names or not any(n in where for n in names):
            continue
        if case.defect_markers and not any(
            m.lower() in where.lower() for m in case.defect_markers
        ):
            continue
        return True
    return False


def _blocked(verdict: cfr.ReviewerVerdict) -> bool:
    return any(f.severity in BLOCKING for f in verdict.findings)


def run_bakeoff(
    *,
    corpus_dir: Path,
    reviewers: list[cfr.Reviewer] | None = None,
    log: Callable[[str], None] = print,
    only: list[str] | None = None,
) -> dict:
    """Run every case past every family and score the results."""
    cases = load_corpus(corpus_dir)
    if only:
        cases = [c for c in cases if c.cid in only]
    revs = reviewers if reviewers is not None else cfr.default_reviewers()
    families = [r.family for r in revs]

    scores: dict[str, FamilyScore] = {f: FamilyScore() for f in families}
    rows: list[dict] = []

    # A bake-off opens no journal, so the prompt gate has nothing to anchor
    # to: declare it under this file's registry row or the load refuses.
    # Raises if this process holds an anchor — a bake-off run inside a
    # journalled process is judged by that run's tree.
    prompt_provenance.declare_unanchored(
        prompt_provenance.entry_point_row("src/claude_dispatcher/reviewer_bakeoff.py"),
        "reviewer bake-off: no run journal, no genesis to anchor the prompt to",
    )
    for i, case in enumerate(cases, 1):
        log(f"[{i}/{len(cases)}] {case.cid} ({'control' if case.control else case.kind})")
        started = time.monotonic()
        verdict = cfr.run_panel(
            ticket_key=case.cid,
            ticket_summary=case.summary,
            summary_md=_summary_for(case),
            diff=case.diff,
            branch=f"bakeoff/{case.cid}",
            base_branch="main",
            reviewers=list(revs),
            log=lambda m: None,
        )
        elapsed = time.monotonic() - started

        row: dict = {
            "case": case.cid, "kind": case.kind, "control": case.control,
            "severity": case.severity, "seconds": round(elapsed, 1), "families": {},
        }
        for rv in verdict.reviewers:
            s = scores.get(rv.family)
            if s is None:
                continue
            s.findings_total += len(rv.findings)
            s.seconds_total += float(rv.duration_seconds or 0.0)
            entry = {
                "verdict": rv.verdict.value,
                "findings": len(rv.findings),
                "blocking": len([f for f in rv.findings if f.severity in BLOCKING]),
                "seconds": round(float(rv.duration_seconds or 0.0), 1),
                "detail": [
                    {"severity": f.severity.value,
                     "location": getattr(f, "location", ""),
                     "description": (getattr(f, "description", "") or "")[:400]}
                    for f in rv.findings
                ],
            }
            if rv.verdict in (cfr.Verdict.UNAVAILABLE, cfr.Verdict.PARSE_FAILED):
                s.unavailable.append(case.cid)
                entry["outcome"] = "unavailable"
            elif case.control:
                if _blocked(rv):
                    s.false_positives.append(case.cid)
                    entry["outcome"] = "false-positive"
                else:
                    s.clean_controls.append(case.cid)
                    entry["outcome"] = "clean"
            elif _caught(rv, case):
                s.detected.append(case.cid)
                entry["outcome"] = "caught"
            else:
                s.missed.append(case.cid)
                entry["outcome"] = "missed"
            row["families"][rv.family] = entry
            log(f"    {rv.family:8} {entry['outcome']:15} "
                f"{rv.verdict.value:20} findings={len(rv.findings)} "
                f"{entry['seconds']}s")
        rows.append(row)

    return {
        "harness_version": "1",
        "corpus": str(corpus_dir),
        "cases": len(cases),
        "defect_cases": len([c for c in cases if not c.control]),
        "control_cases": len([c for c in cases if c.control]),
        "families": families,
        "rows": rows,
        "scores": {
            f: {
                "detection_rate": round(s.detection_rate, 3),
                "detected": len(s.detected),
                "missed": len(s.missed),
                "false_positive_rate": round(s.false_positive_rate, 3),
                "false_positives": len(s.false_positives),
                "clean_controls": len(s.clean_controls),
                "unavailable": len(s.unavailable),
                "findings_total": s.findings_total,
                "seconds_total": round(s.seconds_total, 1),
                "missed_cases": sorted(s.missed),
                "false_positive_cases": sorted(s.false_positives),
            }
            for f, s in scores.items()
        },
    }


def _summary_for(case: Case) -> str:
    """The implementer summary the panel reads.

    Says nothing about the defect — a summary that hinted at it would measure
    reading comprehension rather than review — but it MUST describe the change
    accurately. The first run of this harness gave every control the same
    "a refactor with no behaviour change", which was false of the case that
    adds a function; all three families correctly flagged the mismatch and the
    harness scored the one that rated it HIGH as a false positive. A summary
    that does not match its diff is a seeded defect, so the corpus states each
    one explicitly rather than inferring it.
    """
    return (
        f"## What changed\n\n{case.summary}\n\n"
        f"## Testing\n\nThe existing suite passes.\n"
    )


def render_markdown(result: dict) -> str:
    """The report a human reads to decide the seat order.

    Renders the harness score AND any human adjudications against it. The
    harness cannot tell a false positive from a finding that is correct about
    something the corpus author got wrong, and on this corpus both of codex's
    scored false positives turned out to be the latter — so the adjudication
    is part of the result, not a footnote to it.
    """
    fams = result["families"]
    out = [
        "# Reviewer bake-off",
        "",
        f"{result['defect_cases']} seeded-defect cases, "
        f"{result['control_cases']} controls, {len(fams)} families.",
        "",
        "A catch is a HIGH or CRITICAL finding naming the file the defect is in.",
        "A false positive is a blocking finding on a case that has no defect.",
        "",
        "| family | detection | caught | missed | false-positive rate | FPs | findings | total s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f in fams:
        s = result["scores"][f]
        out.append(
            f"| {f} | {s['detection_rate']:.0%} | {s['detected']} | {s['missed']} "
            f"| {s['false_positive_rate']:.0%} | {s['false_positives']} "
            f"| {s['findings_total']} | {s['seconds_total']} |"
        )
    out += ["", "## Per case", "",
            "| case | kind | " + " | ".join(fams) + " |",
            "|---|---|" + "---|" * len(fams)]
    for row in result["rows"]:
        cells = []
        for f in fams:
            e = row["families"].get(f)
            cells.append(e["outcome"] if e else "-")
        kind = "CONTROL" if row["control"] else row["kind"]
        out.append(f"| {row['case']} | {kind} | " + " | ".join(cells) + " |")

    adj = result.get("adjudications") or []
    if adj:
        out += ["", "## Adjudications", "",
                "Cases where a human overruled the harness score, with the reason.",
                ""]
        for a in adj:
            out.append(
                f"* **{a['case']} / {a['family']}** — scored "
                f"`{a['scored']}`, adjudicated **{a['adjudicated']}**. {a['note']}"
            )
    notes = result.get("notes") or []
    if notes:
        out += ["", "## Notes", ""] + [f"* {n}" for n in notes]
    return "\n".join(out) + "\n"
