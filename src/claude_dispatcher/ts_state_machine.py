"""TypeScript reader for declared state machines.

The RULES are not here and not in the .cjs. `state_machine.check_parsed` holds
them, so three readers cannot become three policies.

The node environment and the parser location come from `role_protocol`'s existing
contract — `ts_parser_home` and `_node_toolchain_environment` — rather than being
restated. That contract is load-bearing (every `NODE_*` and `NPM_CONFIG_*`
stripped, cwd set to the parser's own directory, `PATH`/`HOME` inherited) and a
second copy of it would be a second thing to get wrong. Reaching for one private
helper is the smaller sin: two copies of a security contract is the defect
`main.cjs` was written to avoid.

A missing node, a missing parser or a helper that will not run is a NAMED fault,
never "no declaration": a TypeScript repo we cannot read must not look like one
that declared nothing.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import role_protocol as rp
from . import state_machine as sm

#: TypeScript uses Python's spelling. Named here so callers ask the reader
#: rather than assuming the languages agree — Go does not.
DECLARATION_NAME = sm.DECLARATION_NAME

PACKAGE_DIR = "ts_state_machine"
RUN_TIMEOUT_SECONDS = 120


class TsHelperUnavailable(RuntimeError):
    """The helper could not run. Distinct from "no declaration"."""


def helper_dir() -> Path:
    return Path(__file__).parent / PACKAGE_DIR


def _entrypoint() -> Path:
    p = helper_dir() / "main.cjs"
    if not p.exists():
        raise TsHelperUnavailable(
            f"helper source missing at {p} — an install that dropped it is "
            "unusable, not clean"
        )
    return p


def _run(args: list[str]) -> dict:
    try:
        done = subprocess.run(
            ["node", str(_entrypoint()), *args],
            capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS,
            cwd=str(rp.ts_parser_home()),
            env=rp._node_toolchain_environment(),
        )
    except FileNotFoundError as exc:
        raise TsHelperUnavailable(f"no `node` on PATH: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise TsHelperUnavailable(
            f"helper exceeded {RUN_TIMEOUT_SECONDS}s") from exc
    try:
        return json.loads(done.stdout or "{}")
    except ValueError as exc:
        tail = (done.stderr or done.stdout or "")[-300:]
        raise TsHelperUnavailable(
            f"helper stdout is not JSON: {tail!r}") from exc


def probe() -> str | None:
    """The parser file node ACTUALLY loaded, read from the loader's own record.

    The absolute-path require and the env scrub are both unfalsifiable from
    outside the helper — on a machine with an ambient TypeScript a mutant that
    reached for it would still work. This is the one mechanism a caller can check.
    """
    return _run(["--probe"]).get("parser")


def read(path: str | Path) -> tuple[sm.Declaration | None, dict[str, tuple[str, ...]], str]:
    doc = _run([str(path)])
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
    """TypeScript reader + the SHARED check."""
    decl, enums, why = read(path)
    return sm.check_parsed(decl, enums, why)


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("check", "diagram", "probe"):
        print("usage: ts_state_machine check|diagram <file.ts> | probe",
              file=sys.stderr)
        return 2
    try:
        if argv[0] == "probe":
            print(probe())
            return 0
        if len(argv) < 2:
            return 2
        if argv[0] == "diagram":
            decl, _enums, why = read(argv[1])
            if decl is None:
                print(f"error: {why}", file=sys.stderr)
                return 1
            print(sm.to_mermaid(decl), end="")
            return 0
        rep = check(argv[1])
    except TsHelperUnavailable as exc:
        print(f"ts helper unavailable: {exc}", file=sys.stderr)
        return 3
    print(f"{'PASS' if rep.ok else 'FAIL'} {argv[1]}: {rep.detail()}")
    return 0 if rep.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
