"""W2-1-2c seal: every row of ``UNANCHORED_ENTRY_POINTS`` names a call that
is there.

A row is ``<file>:<line> <symbol>``. Green means ``<file>``, parsed, has a call
whose callee is spelled exactly ``<symbol>`` and starts on ``<line>``. Nothing
else is claimed — not that the registry is complete, and not that no other
file calls the seam; that claim is not decidable from source text and is out
of this file on purpose (W2-1-2c).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from claude_dispatcher import prompt_provenance as pp

ROOT = Path(__file__).resolve().parent.parent

_ROW = re.compile(r"^(?P<file>[^\s:]+):(?P<line>\d+) (?P<symbol>\S+)$")


def row_fault(row: str, root: Path) -> str | None:
    """Why ``row`` does not name a call that is there, or ``None`` if it does.

    Decided by the AST, not the text: a mention in a comment, a string, or a
    bare ``x = cfr.run_panel`` alias is not a call. The line is the one the
    call STARTS on, which for ``cfr.run_panel(`` is the line spelling ``cfr``.
    """
    m = _ROW.match(row)
    if m is None:
        return f"{row!r} is not of the form '<file>:<line> <symbol>'"
    rel, line, symbol = m["file"], int(m["line"]), m["symbol"]
    path = root / rel
    if not path.is_file():
        return f"{rel} is not a file under {root}"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except SyntaxError as e:
        return f"{rel} does not parse: {e}"
    calls = [
        (node.lineno, ast.unparse(node.func))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    ]
    if (line, symbol) in calls:
        return None
    on_line = sorted(callee for ln, callee in calls if ln == line)
    elsewhere = sorted(ln for ln, callee in calls if callee == symbol)
    return (
        f"{rel}:{line} does not call {symbol}; calls starting on that line: "
        f"{on_line or 'none'}; {symbol} is called at lines: {elsewhere or 'none'}"
    )


# --------------------------------------------------------------------------- #
# The seal: one row of the live registry per test
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("row", pp.UNANCHORED_ENTRY_POINTS, ids=str)
def test_every_row_names_a_call_that_is_there(row: str):
    fault = row_fault(row, ROOT)
    assert fault is None, fault


# --------------------------------------------------------------------------- #
# Non-vacuity: the check must reject a row that names a call that is not there
# --------------------------------------------------------------------------- #


_SCRATCH_SOURCE = """\
import cfr
loader = cfr.run_panel
panel = cfr.run_panel(
    ticket_key="x",
)
# cfr.run_panel(
s = "cfr.run_panel("
"""


@pytest.fixture
def scratch_root(tmp_path: Path) -> Path:
    (tmp_path / "entry.py").write_text(_SCRATCH_SOURCE, encoding="utf-8")
    return tmp_path


def test_a_row_naming_the_call_where_it_is_passes(scratch_root: Path):
    assert row_fault("entry.py:3 cfr.run_panel", scratch_root) is None


@pytest.mark.parametrize(
    "row",
    [
        "entry.py:3 cfr.run_pane",  # symbol not there
        "entry.py:3 run_panel",  # a different spelling of the callee
        "entry.py:2 cfr.run_panel",  # the alias, not a call
        "entry.py:4 cfr.run_panel",  # inside the call, not its start
        "entry.py:6 cfr.run_panel",  # a comment
        "entry.py:7 cfr.run_panel",  # a string
        "entry.py:0 cfr.run_panel",  # no such line
        "entry.py:99 cfr.run_panel",  # past the end
        "missing.py:3 cfr.run_panel",  # no such file
        "entry.py cfr.run_panel",  # no line
        "entry.py:3cfr.run_panel",  # no separator
        "entry.py:three cfr.run_panel",  # not a line number
    ],
    ids=str,
)
def test_a_row_naming_a_call_that_is_not_there_fails(row: str, scratch_root: Path):
    assert row_fault(row, scratch_root) is not None


def test_a_file_that_does_not_parse_is_a_fault(scratch_root: Path):
    (scratch_root / "broken.py").write_text("def (:\n", encoding="utf-8")
    assert row_fault("broken.py:1 cfr.run_panel", scratch_root) is not None


@pytest.mark.parametrize("row", pp.UNANCHORED_ENTRY_POINTS, ids=str)
def test_an_altered_copy_of_a_live_row_fails(row: str):
    """A scratch copy of the registry with one row altered — symbol renamed,
    or line moved to one that exists in no file — must be rejected whatever
    the state of the original row."""
    m = _ROW.match(row)
    assert m is not None, row
    renamed = f"{m['file']}:{m['line']} {m['symbol']}_not_there"
    moved = f"{m['file']}:0 {m['symbol']}"
    assert row_fault(renamed, ROOT) is not None
    assert row_fault(moved, ROOT) is not None
