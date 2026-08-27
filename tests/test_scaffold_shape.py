"""Seals for scaffold_shape: the hole check must catch both phases' failures.

The hole check is the part that will later gate a branch, so its rows carry the
weight. `measure` is advisory and is sealed only for arithmetic and for the stub
forms it must recognise — a stub form it misses would read as "implemented" and
fail a scaffold that did the right thing.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from claude_dispatcher import scaffold_shape as ss


def _write(tmp_path: Path, body: str, name: str = "m.py") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_every_stub_form_is_recognised(tmp_path: Path) -> None:
    """`pass`, `...` and `raise NotImplementedError` (bare or called) are stubs.

    Measured under: drop any branch of `_is_stub_body` and the matching row here
    reddens. A missed stub form is the dangerous direction — it reads as
    "implemented" and would fail a scaffold that left the hole correctly.
    """
    p = _write(tmp_path, '''
        def a():
            pass

        def b():
            ...

        def c():
            raise NotImplementedError

        def d():
            raise NotImplementedError("W2-3-3 fills this")

        def e():
            """A docstring must not make a stub look implemented."""
            raise NotImplementedError

        def f():
            return 1
    ''')
    shape = ss.measure(p)
    stubs = {fn.qualname for fn in shape.stubs}
    assert stubs == {"a", "b", "c", "d", "e"}
    assert {fn.qualname for fn in shape.implemented} == {"f"}


def test_a_stub_with_a_second_statement_is_not_a_stub(tmp_path: Path) -> None:
    """Measured under: stop requiring exactly one statement and this reddens. A
    function that logs and then raises has behaviour, so it is not a hole.
    """
    p = _write(tmp_path, '''
        def a():
            print("side effect")
            raise NotImplementedError

        def b():
            if True:
                raise NotImplementedError
    ''')
    assert ss.measure(p).stubs == ()


def test_qualnames_carry_class_and_nesting(tmp_path: Path) -> None:
    """Holes are declared by qualified name, so `C.method` must not collide with a
    module-level `method`.

    Measured under: return bare `child.name` from `_walk_functions` and this
    reddens — two different functions would share one key and the hole check would
    silently verify the wrong one.
    """
    p = _write(tmp_path, '''
        def run():
            raise NotImplementedError

        class C:
            def run(self):
                return 1

            class D:
                def run(self):
                    raise NotImplementedError

        def outer():
            def inner():
                raise NotImplementedError
            return inner
    ''')
    got = {fn.qualname: fn.is_stub for fn in ss.measure(p).functions}
    assert got == {
        "run": True, "C.run": False, "C.D.run": True,
        "outer": False, "outer.inner": True,
    }


def test_line_accounting_classifies_every_line_exactly_once(tmp_path: Path) -> None:
    """The four buckets must sum to `total`.

    Measured under: count `blank` and `comment` over ALL lines instead of skipping
    docstring lines, and this reddens — a blank line INSIDE a docstring is counted
    twice, which understates `executable` and can drive it negative on exactly the
    prose-heavy modules this tool exists to measure. Found by this row.
    """
    p = _write(tmp_path, '''
        """Module doc.

        Has a blank line inside it, which must not also count as blank.
        """

        # a comment
        def f():
            """One line doc."""
            return 1
    ''')
    s = ss.measure(p)
    assert s.docstring + s.comment + s.blank + s.executable == s.total
    assert s.docstring == 5          # 4-line module doc + 1-line function doc
    assert s.comment == 1
    assert s.executable == 2         # `def f():` and `return 1`
    assert s.prose_ratio == pytest.approx(3.0)


def test_a_docstring_only_module_has_no_negative_executable(tmp_path: Path) -> None:
    """The degenerate case the double-count produced. Measured under: the old
    independent-count arithmetic returns a NEGATIVE executable here, and
    `prose_ratio` divides by the clamp instead of a real count.
    """
    p = _write(tmp_path, '''
        """All prose.

        Two blank lines follow inside the docstring.


        End.
        """
    ''')
    s = ss.measure(p)
    assert s.executable == 0
    assert s.docstring + s.comment + s.blank + s.executable == s.total


# --------------------------------------------------------------------------
# The check that will gate a branch.
# --------------------------------------------------------------------------

def test_scaffold_phase_fails_when_a_declared_hole_is_implemented(
    tmp_path: Path,
) -> None:
    """The wave-2 defect, sealed: a scaffold that filled its own holes leaves the
    seals nothing to redden against.

    Measured under: invert `want_stub` and this reddens.
    """
    p = _write(tmp_path, '''
        def contract_helper():
            return 1

        def decide():
            return "already implemented"

        def also_decide():
            raise NotImplementedError
    ''')
    report = ss.declared_holes_report(
        [f"{p}::decide", f"{p}::also_decide"],
        shapes=[ss.measure(p)], phase="scaffold",
    )
    assert report.passed is False
    assert report.wrong == (f"{p}::decide",)
    assert report.ok == (f"{p}::also_decide",)
    assert "have nothing to redden against" in report.detail()


def test_bodies_phase_fails_when_a_declared_hole_is_still_a_stub(
    tmp_path: Path,
) -> None:
    """The other end: P3 must leave no declared hole unfilled.

    Measured under: use `phase="scaffold"` semantics for bodies and this reddens.
    """
    p = _write(tmp_path, '''
        def decide():
            return 1

        def also_decide():
            raise NotImplementedError
    ''')
    report = ss.declared_holes_report(
        [f"{p}::decide", f"{p}::also_decide"],
        shapes=[ss.measure(p)], phase="bodies",
    )
    assert report.passed is False
    assert report.wrong == (f"{p}::also_decide",)
    assert "still stubs" in report.detail()


def test_a_declaration_naming_a_function_nobody_wrote_is_its_own_failure(
    tmp_path: Path,
) -> None:
    """A typo'd hole must not pass by matching nothing.

    Measured under: treat an unknown hole as ok and this reddens. Reported apart
    from a wrong body because the causes differ — a bad declaration versus a phase
    that did the wrong amount of work.
    """
    p = _write(tmp_path, "def real():\n    raise NotImplementedError\n")
    report = ss.declared_holes_report(
        [f"{p}::typo"], shapes=[ss.measure(p)], phase="scaffold",
    )
    assert report.passed is False
    assert report.missing == (f"{p}::typo",)
    assert "do not exist" in report.detail()


def test_holes_across_several_modules_are_checked_together(tmp_path: Path) -> None:
    a = _write(tmp_path, "def x():\n    raise NotImplementedError\n", "a.py")
    b = _write(tmp_path, "def y():\n    return 1\n", "b.py")
    report = ss.declared_holes_report(
        [f"{a}::x", f"{b}::y"],
        shapes=[ss.measure(a), ss.measure(b)], phase="scaffold",
    )
    assert report.ok == (f"{a}::x",) and report.wrong == (f"{b}::y",)


def test_an_unknown_phase_raises_rather_than_guessing() -> None:
    """Measured under: default to one phase instead of raising and this reddens.
    Guessing the phase would silently check the opposite property.
    """
    with pytest.raises(ValueError, match="phase must be"):
        ss.declared_holes_report([], shapes=[], phase="adjudicate")


def test_no_declared_holes_passes_and_says_so(tmp_path: Path) -> None:
    report = ss.declared_holes_report([], shapes=[], phase="scaffold")
    assert report.passed is True
    assert "all 0 declared hole(s)" in report.detail()


# --------------------------------------------------------------------------
# CLI: the operator-facing surface.
# --------------------------------------------------------------------------

def test_cli_holes_exits_nonzero_on_failure(tmp_path: Path, capsys) -> None:
    """Exit code is the whole verdict, so an operator can use this in a script
    before the gate ever calls it.
    """
    p = _write(tmp_path, "def decide():\n    return 1\n")
    assert ss.main(["holes", "--scaffold", f"{p}::decide"]) == 1
    assert "FAIL [scaffold]" in capsys.readouterr().out

    q = _write(tmp_path, "def decide():\n    raise NotImplementedError\n", "q.py")
    assert ss.main(["holes", "--scaffold", f"{q}::decide"]) == 0
    assert "PASS [scaffold]" in capsys.readouterr().out


def test_cli_measure_reports_the_shape(tmp_path: Path, capsys) -> None:
    p = _write(tmp_path, "def f():\n    return 1\n")
    assert ss.main(["measure", str(p)]) == 0
    assert "m.py" in capsys.readouterr().out


def test_cli_rejects_a_missing_or_unknown_command(capsys) -> None:
    assert ss.main([]) == 2
    assert ss.main(["nonsense"]) == 2
    assert ss.main(["holes"]) == 2
    assert ss.main(["holes", "--oops", "a::b"]) == 2


def test_the_wave2_scaffolds_reproduce_the_measurement_that_motivated_this(
) -> None:
    """This module measures itself, as the cheapest guard that the arithmetic is
    not nonsense: it is contract-light and mostly executable, so its own ratio
    must sit below the 2.5:1-6.1:1 band the wave-2 scaffolds produced.
    """
    me = ss.measure(Path(ss.__file__))
    assert me.executable > 100
    assert me.prose_ratio < 1.0, f"this module has drifted to {me.prose_ratio:.1f}:1"


# ── seal coverage ────────────────────────────────────────────────────────────
# What hid the W2 gap for nine days: three scaffolds merged carrying 23
# NotImplementedError stubs, their seals stranded on unmerged branches, and the
# suite reporting green throughout — because a module no test imports produces
# no signal at all. Not a failure, not a skip, nothing.


def _mod(tmp_path, name, body):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    (src / f"{name}.py").write_text(body, encoding="utf-8")
    return src


def _tests(tmp_path, files):
    t = tmp_path / "tests"
    t.mkdir(exist_ok=True)
    for fname, body in files.items():
        (t / fname).write_text(body, encoding="utf-8")
    return t


def test_a_module_no_test_mentions_is_unsealed(tmp_path):
    src = _mod(tmp_path, "lonely", "def f():\n    return 1\n")
    tst = _tests(tmp_path, {"test_other.py": "from x import y\n"})
    rows = ss.seal_coverage(src, tst)
    assert [r.module for r in rows] == ["lonely"]
    assert rows[0].unsealed


def test_a_mention_anywhere_counts_as_a_reference(tmp_path):
    """Generous on purpose: a mention is weak evidence of coverage, but its
    ABSENCE is strong evidence of none, and only the absence is acted on."""
    src = _mod(tmp_path, "seen", "def f():\n    return 1\n")
    tst = _tests(tmp_path, {"test_a.py": "from claude_dispatcher import seen\n"})
    rows = ss.seal_coverage(src, tst)
    assert not rows[0].unsealed
    assert rows[0].referencing_tests


def test_a_substring_match_is_not_a_reference(tmp_path):
    """`seen` must not be satisfied by `unseen_thing` — whole words only,
    or a module could look covered because another name contains it."""
    src = _mod(tmp_path, "seen", "def f():\n    return 1\n")
    tst = _tests(tmp_path, {"test_a.py": "from x import unseen_thing\n"})
    rows = ss.seal_coverage(src, tst)
    assert rows[0].unsealed


def test_stubs_without_seals_are_the_worst_case_and_sort_first(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "stubbed.py").write_text(
        "def f():\n    raise NotImplementedError('x')\n", encoding="utf-8")
    (src / "plain.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    tst = _tests(tmp_path, {"test_none.py": "pass\n"})
    rows = ss.seal_coverage(src, tst)
    assert rows[0].module == "stubbed", "unfinished AND unwatched must sort first"
    assert rows[0].unfinished_and_unwatched
    assert not rows[1].unfinished_and_unwatched, (
        "a module with no stubs is unsealed but not unfinished"
    )


def test_a_sealed_stub_is_not_flagged_as_unwatched(tmp_path):
    """A stub with seals is normal contract-first work in progress, not a gap."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "pending.py").write_text(
        "def f():\n    raise NotImplementedError('x')\n", encoding="utf-8")
    tst = _tests(tmp_path, {"test_p.py": "from claude_dispatcher import pending\n"})
    rows = ss.seal_coverage(src, tst)
    assert rows[0].stubs == 1
    assert not rows[0].unsealed
    assert not rows[0].unfinished_and_unwatched


def test_dunder_modules_are_skipped(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "__main__.py").write_text("", encoding="utf-8")
    (src / "real.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    rows = ss.seal_coverage(src, _tests(tmp_path, {"t.py": "pass\n"}))
    assert [r.module for r in rows] == ["real"]
