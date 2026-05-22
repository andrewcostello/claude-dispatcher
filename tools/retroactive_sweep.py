#!/usr/bin/env python3
"""Run the cross-family panel against every BSA-FU ticket on epic/bay-session-architecture.

For each ticket:
  - resolve `base = merge_sha^1`, `branch = merge_sha`
  - run the three-family panel
  - save the PanelVerdict JSON + the rendered markdown to results/<key>/
  - compare panel verdict to the auto_integrate_status the dispatcher recorded

At the end, produce a markdown report summarising the per-ticket
agreement (panel-approve vs auto-integrate-integrated etc.) and write it
to results/REPORT.md.

This is a one-time validation script. The tickets and merge SHAs are
hard-coded; it is NOT a generic tool.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

# Ensure the in-tree src/ is importable without `pip install`.
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from claude_dispatcher import cross_family_reviewer as cfr  # noqa: E402


EVENPLAY = Path("/home/andrew/Project/evenplay-mono")
RUN_DIR = EVENPLAY / "docs/runs/2026-05-21T20-54-45Z-bsa-followup-and-coverage-tasks"


# Hard-coded ticket → merge SHA mapping, in chronological merge order
# (oldest first). `auto_integrate_status` comes from the YAML.
TICKETS = [
    {
        "key": "BSA-FU-AUTH-PEER-BRIDGE",
        "merge_sha": "baa11620",
        "labels": ["security", "critical"],
        "auto_integrate_status": "integrated",
    },
    {
        "key": "BSA-FU-RECOVERY-REFUND-PRIO",
        "merge_sha": "49efcc8b",
        "labels": ["financial", "critical"],
        # NB: manual, not integrated — this is the human-gated ticket where
        # pr-reviewer caught a test-quality issue. The panel SHOULD flag this.
        "auto_integrate_status": "manual",
    },
    {
        "key": "BSA-FU-RECOVERY-OUTCOME",
        "merge_sha": "4037c784",
        "labels": ["financial", "critical"],
        "auto_integrate_status": "integrated",
    },
    {
        "key": "BSA-FU-CASCADE-REFUND-DRAIN",
        "merge_sha": "0e2fe088",
        "labels": ["financial", "critical"],
        "auto_integrate_status": "integrated",
    },
    {
        "key": "BSA-FU-XPOD-ORDERING",
        "merge_sha": "83708bdf",
        "labels": ["critical"],
        "auto_integrate_status": "integrated",
    },
    {
        "key": "BSA-FU-NATS-PARTITION-RECOVERY",
        "merge_sha": "a1c42956",
        "labels": ["high"],
        "auto_integrate_status": "integrated",
    },
    {
        "key": "BSA-FU-SHUTDOWN-GOROUTINE-WG",
        "merge_sha": "6593e1f0",
        "labels": ["high"],
        "auto_integrate_status": "integrated",
    },
]


def run_one(ticket: dict, results_dir: Path, timeout: int, log) -> dict:
    key = ticket["key"]
    merge = ticket["merge_sha"]
    summary_path = RUN_DIR / key / "summary.md"
    if not summary_path.exists():
        return {"key": key, "skipped": "summary.md missing", "summary_path": str(summary_path)}

    # Read the ticket-level summary line from the YAML (one-liner the panel
    # prompt uses for context). Fall back to the summary.md title line.
    ticket_summary = _read_yaml_summary(key) or _read_summary_title(summary_path)

    base = f"{merge}^1"
    branch = merge  # the merge commit itself is the tip of feat-into-base

    log(f"[{key}] computing diff {base}..{branch}")
    diff = cfr.collect_diff(repo_root=EVENPLAY, base_branch=base, branch=branch)
    n_lines = diff.count("\n")
    log(f"[{key}] diff: {n_lines} lines")

    summary_md = summary_path.read_text(encoding="utf-8")

    started = time.monotonic()
    log(f"[{key}] running panel (timeout {timeout}s/reviewer)...")
    panel = cfr.run_panel(
        ticket_key=key,
        ticket_summary=ticket_summary or "",
        summary_md=summary_md,
        diff=diff,
        branch=branch,
        base_branch=base,
        reviewers=cfr.default_reviewers(timeout_seconds=timeout),
        log=log,
    )
    elapsed = time.monotonic() - started

    ticket_dir = results_dir / key
    ticket_dir.mkdir(parents=True, exist_ok=True)
    (ticket_dir / "panel.json").write_text(
        json.dumps(panel.to_dict(), indent=2), encoding="utf-8",
    )
    (ticket_dir / "panel.md").write_text(
        cfr.render_findings_markdown(panel), encoding="utf-8",
    )
    for r in panel.reviewers:
        (ticket_dir / f"raw_{r.family}.txt").write_text(
            r.raw_output or "", encoding="utf-8",
        )

    log(f"[{key}] panel.consensus={panel.consensus} dur={elapsed:.1f}s")
    return {
        "key": key,
        "consensus": panel.consensus,
        "summary": panel.summary,
        "auto_integrate_status": ticket["auto_integrate_status"],
        "elapsed_seconds": round(elapsed, 1),
        "blocking_findings": len(panel.blocking_findings),
        "per_family": {r.family: r.verdict.value for r in panel.reviewers},
        "per_family_errors": {r.family: r.error for r in panel.reviewers if r.error},
        "diff_lines": n_lines,
    }


def _read_yaml_summary(key: str) -> str | None:
    yaml_path = EVENPLAY / "bsa-followup-and-coverage-tasks.yaml"
    if not yaml_path.exists():
        return None
    lines = yaml_path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().startswith(f"- key: {key}") or ln.strip().startswith(f"-   key: {key}") or ln.strip() == f"- key: {key}":
            # Walk forward until we hit `summary:`
            for j in range(i + 1, min(i + 10, len(lines))):
                s = lines[j].strip()
                if s.startswith("summary:"):
                    return s.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def _read_summary_title(p: Path) -> str | None:
    try:
        first = p.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None
    if first.startswith("# "):
        return first[2:].strip()
    return None


def write_report(results: list[dict], results_dir: Path) -> Path:
    lines = [
        "# Cross-family panel retroactive validation report",
        "",
        f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}",
        "",
        f"Tickets surveyed: {len(results)}",
        "",
        "## Summary table",
        "",
        "| Ticket | auto_integrate | panel.consensus | claude | gemini | codex | findings | diff lines | wall (s) |",
        "|--------|----------------|-----------------|--------|--------|-------|----------|------------|----------|",
    ]
    for r in results:
        if r.get("skipped"):
            lines.append(f"| {r['key']} | – | SKIPPED ({r['skipped']}) | – | – | – | – | – | – |")
            continue
        pf = r["per_family"]
        lines.append(
            f"| {r['key']} | {r['auto_integrate_status']} | {r['consensus']} | "
            f"{pf.get('claude','–')} | {pf.get('gemini','–')} | {pf.get('codex','–')} | "
            f"{r['blocking_findings']} | {r['diff_lines']} | {r['elapsed_seconds']} |"
        )
    lines += ["", "## Agreement analysis", ""]
    agree_approve = 0
    agree_block = 0
    panel_caught_what_human_caught = 0
    panel_blocked_what_auto_approved = 0
    panel_approved_what_human_blocked = 0
    real_results = [r for r in results if not r.get("skipped")]
    for r in real_results:
        auto = r["auto_integrate_status"]
        consensus = r["consensus"]
        if auto == "integrated" and consensus == "approve":
            agree_approve += 1
        elif auto == "manual" and consensus in ("block", "incomplete"):
            agree_block += 1
            panel_caught_what_human_caught += 1
        elif auto == "integrated" and consensus in ("block", "incomplete"):
            panel_blocked_what_auto_approved += 1
        elif auto == "manual" and consensus == "approve":
            panel_approved_what_human_blocked += 1
    lines += [
        f"- Auto-integrate **integrated** AND panel **approve**: {agree_approve}",
        f"- Auto-integrate **manual** (human-gated) AND panel **block/incomplete**: {agree_block}",
        f"- Panel **caught what human caught** (manual + block): {panel_caught_what_human_caught}",
        f"- Panel **block on what auto-integrate approved** (false positives or NEW findings): {panel_blocked_what_auto_approved}",
        f"- Panel **approved what human blocked** (false negatives): {panel_approved_what_human_blocked}",
        f"- Total tickets evaluated: {len(real_results)}",
    ]
    lines += ["", "## Per-ticket detail", ""]
    for r in real_results:
        lines += [
            f"### {r['key']}",
            "",
            f"- auto_integrate_status: `{r['auto_integrate_status']}`",
            f"- panel.consensus: `{r['consensus']}`",
            f"- panel.summary: {r['summary']}",
            f"- elapsed: {r['elapsed_seconds']}s, diff: {r['diff_lines']} lines, blocking findings: {r['blocking_findings']}",
        ]
        if r.get("per_family_errors"):
            lines.append(f"- errors: `{r['per_family_errors']}`")
        lines += [
            f"- panel report: [panel.md](./{r['key']}/panel.md)",
            "",
        ]

    out = results_dir / "REPORT.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--results-dir", default="docs/retroactive_panel_results",
                   help="Where to write per-ticket panel outputs + REPORT.md (default: docs/retroactive_panel_results)")
    p.add_argument("--timeout", type=int, default=900,
                   help="Per-reviewer timeout in seconds (default: 900).")
    p.add_argument("--only", default=None,
                   help="Comma-separated ticket keys to run (others skipped).")
    args = p.parse_args(argv)

    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    only = set(args.only.split(",")) if args.only else None
    queue = [t for t in TICKETS if (only is None or t["key"] in only)]
    print(f"sweeping {len(queue)} ticket(s) into {results_dir}", file=sys.stderr)

    log_path = results_dir / "sweep.log"

    def log(msg: str) -> None:
        ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        line = f"{ts} {msg}"
        print(line, file=sys.stderr)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    log(f"sweep start: {len(queue)} tickets, timeout {args.timeout}s/reviewer")

    results: list[dict] = []
    for t in queue:
        try:
            results.append(run_one(t, results_dir, args.timeout, log))
        except Exception as e:
            log(f"[{t['key']}] FAILED: {e}")
            results.append({"key": t["key"], "skipped": f"exception: {e}"})

    report_path = write_report(results, results_dir)
    log(f"sweep complete. report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
