"""Measure what a scaffold left undone, and check its declared holes.

A SCAFFOLD is contract and stubs; the decision logic its seals will judge belongs
to the body. Nothing enforced that: the role gate checks paths and signatures,
and SuiteExpectation[SCAFFOLD] is GREEN, so a fully-implemented scaffold passes
more easily than a stub-based one. All three wave-2 scaffolds over-built
unprompted (32/32, 18/27 and 8/9 functions implemented).

Two entry points, and the difference matters:

  * `measure` is ADVISORY. A stub ratio has no defensible threshold — a
    contract-heavy scaffold legitimately implements dataclasses, enums and
    `__post_init__` validation. Use it to see the shape, never to pass a verdict.
  * `declared_holes_report` is the CHECK. The scaffold names the functions that
    are the body's to fill; P1 must leave each raising NotImplementedError and P3
    must leave none of them doing so. Named functions, so no threshold and no
    false positives.

Advisory today: nothing calls this from a gate. Wiring it into one makes it part
of a gate decision, and it must join FLOOR_GLOBS at that point for the reason
known_red.py did — a check a branch can edit is not a check.

Protocol members and @abstractmethod bodies read as stubs. Harmless for
`measure`; irrelevant for the hole check, which only looks at named functions.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

#: Bodies that mean "not implemented": `pass`, `...`, `raise NotImplementedError`.
_STUB_RAISE = "NotImplementedError"


@dataclass(frozen=True)
class FunctionShape:
    """One function's qualified name and whether its body is a stub."""

    qualname: str
    lineno: int
    is_stub: bool


@dataclass(frozen=True)
class ModuleShape:
    """Line accounting and per-function stub state for one module.

    ``executable`` excludes docstrings, comments and blank lines, so
    ``prose_ratio`` compares what a reader must scroll past against what runs.
    """

    path: str
    total: int
    docstring: int
    comment: int
    blank: int
    executable: int
    functions: tuple[FunctionShape, ...]

    @property
    def prose_ratio(self) -> float:
        return (self.docstring + self.comment) / max(self.executable, 1)

    @property
    def stubs(self) -> tuple[FunctionShape, ...]:
        return tuple(f for f in self.functions if f.is_stub)

    @property
    def implemented(self) -> tuple[FunctionShape, ...]:
        return tuple(f for f in self.functions if not f.is_stub)


def _is_stub_body(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = [
        s for s in fn.body
        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                and isinstance(s.value.value, str))
    ]
    if len(body) != 1:
        return False
    stmt = body[0]
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
        return stmt.value.value is Ellipsis
    if isinstance(stmt, ast.Raise):
        exc = stmt.exc
        if isinstance(exc, ast.Call):
            exc = exc.func
        return isinstance(exc, ast.Name) and exc.id == _STUB_RAISE
    return False


def _walk_functions(tree: ast.Module) -> list[FunctionShape]:
    out: list[FunctionShape] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                out.append(FunctionShape(name, child.lineno, _is_stub_body(child)))
                visit(child, f"{name}.")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")

    visit(tree, "")
    return out


def measure(path: str | Path, *, source: str | None = None) -> ModuleShape:
    """Line accounting and stub state for one Python file.

    ``source`` overrides reading from disk, so a caller can measure a blob out of
    a git revision without materialising it.
    """
    text = source if source is not None else Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    tree = ast.parse(text)

    # Each line is classified ONCE. Counting independently double-counts a blank
    # line inside a docstring, which understates `executable` and can drive it
    # negative on a prose-heavy module — the exact files this tool is for.
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        if ast.get_docstring(node, clean=False) is None:
            continue
        expr = node.body[0]
        doc_lines.update(range(expr.lineno, (expr.end_lineno or expr.lineno) + 1))

    comment = blank = executable = 0
    for i, ln in enumerate(lines, start=1):
        if i in doc_lines:
            continue
        if not ln.strip():
            blank += 1
        elif ln.strip().startswith("#"):
            comment += 1
        else:
            executable += 1

    return ModuleShape(
        path=str(path),
        total=len(lines),
        docstring=len(doc_lines),
        comment=comment,
        blank=blank,
        executable=executable,
        functions=tuple(_walk_functions(tree)),
    )


@dataclass(frozen=True)
class HoleReport:
    """Verdict on one unit's declared holes.

    ``missing`` names holes that do not exist in the module at all — a declaration
    naming a function nobody wrote. Reported separately from a wrong body, because
    the two have different causes: a typo in the declaration versus a phase that
    did the wrong amount of work.
    """

    phase: str
    ok: tuple[str, ...] = ()
    wrong: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.wrong and not self.missing

    def detail(self) -> str:
        parts = []
        if self.missing:
            parts.append(
                f"{len(self.missing)} declared hole(s) do not exist: "
                + ", ".join(self.missing)
            )
        if self.wrong and self.phase == "scaffold":
            parts.append(
                f"{len(self.wrong)} declared hole(s) are already implemented, so "
                "the seals have nothing to redden against: " + ", ".join(self.wrong)
            )
        elif self.wrong:
            parts.append(
                f"{len(self.wrong)} declared hole(s) are still stubs: "
                + ", ".join(self.wrong)
            )
        return "; ".join(parts) or f"all {len(self.ok)} declared hole(s) as expected"


def declared_holes_report(
    holes: Iterable[str],
    *,
    shapes: Iterable[ModuleShape],
    phase: str,
) -> HoleReport:
    """Check declared holes against measured modules.

    ``holes`` are ``path::qualname`` strings. ``phase`` is ``"scaffold"`` (every
    hole must be a stub) or ``"bodies"`` (none may be).
    """
    if phase not in ("scaffold", "bodies"):
        raise ValueError(f"phase must be 'scaffold' or 'bodies', got {phase!r}")
    want_stub = phase == "scaffold"

    index = {
        f"{s.path}::{f.qualname}": f.is_stub
        for s in shapes for f in s.functions
    }
    ok: list[str] = []
    wrong: list[str] = []
    missing: list[str] = []
    for hole in holes:
        if hole not in index:
            missing.append(hole)
        elif index[hole] is want_stub:
            ok.append(hole)
        else:
            wrong.append(hole)
    return HoleReport(phase=phase, ok=tuple(ok), wrong=tuple(wrong),
                      missing=tuple(missing))


def _cmd_measure(paths: list[str]) -> int:
    print(f"{'file':52} {'total':>6} {'code':>6} {'prose':>7} {'fn':>4} "
          f"{'stub':>5} {'impl':>5}")
    for p in paths:
        s = measure(p)
        print(f"{Path(p).name[:52]:52} {s.total:6} {s.executable:6} "
              f"{s.prose_ratio:6.1f}:1 {len(s.functions):4} "
              f"{len(s.stubs):5} {len(s.implemented):5}")
    return 0


def _cmd_holes(phase: str, holes: list[str]) -> int:
    paths = sorted({h.split("::", 1)[0] for h in holes})
    report = declared_holes_report(
        holes, shapes=[measure(p) for p in paths], phase=phase,
    )
    print(f"{'PASS' if report.passed else 'FAIL'} [{phase}] {report.detail()}")
    return 0 if report.passed else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("measure", "holes"):
        print(
            "usage:\n"
            "  scaffold_shape measure <file.py>...\n"
            "  scaffold_shape holes --scaffold|--bodies <file.py::qualname>...",
            file=sys.stderr,
        )
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "measure":
        return _cmd_measure(rest) if rest else 2
    if not rest or rest[0] not in ("--scaffold", "--bodies"):
        print("holes: need --scaffold or --bodies", file=sys.stderr)
        return 2
    return _cmd_holes(rest[0].lstrip("-"), rest[1:])


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
