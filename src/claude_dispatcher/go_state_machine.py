"""Go reader for declared state machines: build the helper once, run it per file.

The RULES are not here. `state_machine.check_parsed` holds them, so Go cannot
drift into a laxer answer than Python gives for the same declaration — one place
to change a rule, one place to seal it.

Build-once/run-per-file and a per-process in-memory cache, mirroring
`role_protocol._go_helper_binary`: a toolchain probe on every file would put a
`go build` on the gate's hot path.

A missing or unusable Go toolchain is a NAMED fault, never a pass. bay-session is
a Go repository, so "we could not read it" must never be reported as "it has no
declaration" — those route to different decisions.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import state_machine as sm

#: Go spells the declaration idiomatically, NOT as Python's `STATE_MACHINE`.
#: Must equal `declName` in go_state_machine/main.go — sealed, because a caller
#: that prefilters on the wrong spelling skips every Go file in silence.
DECLARATION_NAME = "StateMachine"

PACKAGE_DIR = "go_state_machine"
BUILD_TIMEOUT_SECONDS = 180
RUN_TIMEOUT_SECONDS = 60

#: (binary, failure) for this process; exactly one arm is set.
_PREPARED: tuple[Path | None, Exception | None] | None = None


class GoHelperUnavailable(RuntimeError):
    """The helper could not be built or run. Distinct from "no declaration"."""


def helper_dir() -> Path:
    return Path(__file__).parent / PACKAGE_DIR


def _build() -> Path:
    src = helper_dir()
    if not (src / "main.go").exists():
        raise GoHelperUnavailable(
            f"helper source missing at {src} — an install that dropped it is "
            "unusable, not clean (the same argument as the other Go helpers)"
        )
    out = src / ".build" / "go-state-machine"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        done = subprocess.run(
            ["go", "build", "-o", str(out), "."],
            cwd=str(src), capture_output=True, text=True,
            timeout=BUILD_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise GoHelperUnavailable(f"no `go` on PATH: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GoHelperUnavailable(
            f"go build exceeded {BUILD_TIMEOUT_SECONDS}s") from exc
    if done.returncode != 0:
        raise GoHelperUnavailable(
            f"go build failed: {(done.stderr or done.stdout)[-400:]}")
    return out


def binary() -> Path:
    global _PREPARED
    if _PREPARED is None:
        try:
            _PREPARED = (_build(), None)
        except GoHelperUnavailable as exc:
            _PREPARED = (None, exc)
    built, failure = _PREPARED
    if failure is not None:
        raise failure
    assert built is not None
    return built


def read(path: str | Path) -> tuple[sm.Declaration | None, dict[str, tuple[str, ...]], str]:
    """(declaration, enums, why-not) for one Go file.

    Raises :class:`GoHelperUnavailable` rather than returning "no declaration"
    when the toolchain is the problem — a Go repo whose reader is broken must not
    look like a Go repo with nothing declared.
    """
    try:
        done = subprocess.run(
            [str(binary()), str(path)], capture_output=True, text=True,
            timeout=RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise GoHelperUnavailable(
            f"helper exceeded {RUN_TIMEOUT_SECONDS}s on {path}") from exc
    try:
        doc = json.loads(done.stdout or "{}")
    except ValueError as exc:
        raise GoHelperUnavailable(
            f"helper stdout is not JSON: {(done.stdout or '')[:200]!r}") from exc

    enums = {
        str(k): tuple(str(m) for m in v)
        for k, v in (doc.get("enums") or {}).items()
    }
    raw, why = doc.get("declaration"), str(doc.get("why") or "")
    if raw is None:
        return None, enums, why or "no declaration"
    decl, mapping_why = sm.from_mapping(raw)
    return decl, enums, mapping_why


def check(path: str | Path) -> sm.Report:
    """Go reader + the SHARED check."""
    decl, enums, why = read(path)
    return sm.check_parsed(decl, enums, why)


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[0] not in ("check", "diagram"):
        print("usage: go_state_machine check|diagram <file.go>", file=sys.stderr)
        return 2
    try:
        if argv[0] == "diagram":
            decl, _enums, why = read(argv[1])
            if decl is None:
                print(f"error: {why}", file=sys.stderr)
                return 1
            print(sm.to_mermaid(decl), end="")
            return 0
        rep = check(argv[1])
    except GoHelperUnavailable as exc:
        print(f"go helper unavailable: {exc}", file=sys.stderr)
        return 3
    print(f"{'PASS' if rep.ok else 'FAIL'} {argv[1]}: {rep.detail()}")
    return 0 if rep.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
