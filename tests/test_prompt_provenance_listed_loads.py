"""W2-1-2c seals: every prompt load is a listed load.

Grep-level. A *site* is one line in ``src/``, ``tools/`` or ``scripts/``,
outside the seam module, that spells a qualified call on a seam name
(``cfr.run_panel(``) or imports a seam name from the seam module. The register
``prompt_provenance.UNANCHORED_ENTRY_POINTS`` must equal the set of sites,
less the files pinned here as anchored. Nothing asks whether a site executes,
declares or is reachable — W2-1-2b drives the entry points.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from claude_dispatcher import prompt_provenance as pp

ROOT = Path(__file__).resolve().parent.parent

SEAM_MODULE = "src/claude_dispatcher/cross_family_reviewer.py"
SEAM_DOTTED = "claude_dispatcher.cross_family_reviewer"
#: The load, and the two functions in the seam module that a caller reaches it
#: through. Pinned: the seal below checks each is still defined there.
SEAMS = ("_load_prompt", "build_review_prompt", "run_panel")
SCAN_DIRS = ("src", "tools", "scripts")
#: Files whose seam calls run under a journal the run itself opened. They owe
#: no declaration and stay off the register. Pinned, not inferred.
ANCHORED_CALLERS = ("src/claude_dispatcher/orchestrator.py",)

_SEAM_ALT = "|".join(re.escape(s) for s in SEAMS)
# `x.y.run_panel(` — at least one qualifier, so a module's own `_load_prompt(`
# (verifier.py) and `def run_panel(` are not sites.
_QUALIFIED_CALL = re.compile(rf"(?P<sym>(?:[A-Za-z_]\w*\.)+(?:{_SEAM_ALT}))\s*\(")
_FROM_IMPORT = re.compile(rf"^\s*from\s+{re.escape(SEAM_DOTTED)}\s+import\b")
_ROW = re.compile(r"^(?P<file>\S+):(?P<line>\d+) (?P<symbol>\S+)$")


@dataclass(frozen=True, order=True)
class Site:
    file: str
    line: int
    symbol: str

    def row(self) -> str:
        return f"{self.file}:{self.line} {self.symbol}"


def parse_row(raw: str) -> Site:
    m = _ROW.match(raw)
    if not m:
        raise ValueError(f"malformed register row {raw!r}; want 'file:line symbol'")
    return Site(m["file"], int(m["line"]), m["symbol"])


def _import_names(lines: list[str], start: int) -> str:
    # Text after `import`, spanning a parenthesised list to its `)`.
    text = lines[start].split("import", 1)[1]
    if "(" not in text:
        return text
    i = start
    while ")" not in text and i + 1 < len(lines):
        i += 1
        text += "\n" + lines[i]
    return text


def sites_in(source: str, file: str) -> list[Site]:
    out: list[Site] = []
    lines = source.splitlines()
    for n, line in enumerate(lines):
        for m in _QUALIFIED_CALL.finditer(line):
            out.append(Site(file, n + 1, m["sym"]))
        if _FROM_IMPORT.match(line):
            names = _import_names(lines, n)
            if "*" in names:
                out.append(Site(file, n + 1, "import *"))
            for seam in SEAMS:
                if re.search(rf"\b{re.escape(seam)}\b", names):
                    out.append(Site(file, n + 1, f"import {seam}"))
    return out


def sites_under(root: Path, scan_dirs: tuple[str, ...] = SCAN_DIRS) -> set[Site]:
    found: set[Site] = set()
    for d in scan_dirs:
        for path in sorted((root / d).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if rel == SEAM_MODULE:
                continue
            found.update(sites_in(path.read_text(encoding="utf-8"), rel))
    return found


@dataclass(frozen=True)
class Audit:
    rows: frozenset[Site]
    sites: frozenset[Site]  # excluding anchored callers

    @property
    def unlisted(self) -> list[Site]:
        return sorted(self.sites - self.rows)

    @property
    def dead_rows(self) -> list[Site]:
        return sorted(self.rows - self.sites)


def audit(
    root: Path,
    register: tuple[str, ...],
    anchored: tuple[str, ...] = ANCHORED_CALLERS,
    scan_dirs: tuple[str, ...] = SCAN_DIRS,
) -> Audit:
    rows = frozenset(parse_row(r) for r in register)
    sites = frozenset(s for s in sites_under(root, scan_dirs) if s.file not in anchored)
    return Audit(rows=rows, sites=sites)


def _lines(items) -> str:
    return "\n".join(f"  {s.row()}" for s in items)


# --- the repo ----------------------------------------------------------------


@pytest.fixture(scope="module")
def repo_audit() -> Audit:
    return audit(ROOT, pp.UNANCHORED_ENTRY_POINTS)


def test_the_pinned_seams_are_still_defined_in_the_seam_module():
    source = (ROOT / SEAM_MODULE).read_text(encoding="utf-8")
    missing = [s for s in SEAMS if not re.search(rf"^def {re.escape(s)}\(", source, re.M)]
    assert not missing, f"{SEAM_MODULE} no longer defines {missing}; re-pin SEAMS"


def test_every_register_row_names_a_seam():
    for raw in pp.UNANCHORED_ENTRY_POINTS:
        site = parse_row(raw)
        assert site.symbol.rsplit(".", 1)[-1] in SEAMS, raw


def test_every_prompt_load_is_a_listed_load(repo_audit: Audit):
    assert not repo_audit.unlisted, (
        "seam calls with no row in UNANCHORED_ENTRY_POINTS:\n"
        + _lines(repo_audit.unlisted)
    )


def test_every_register_row_still_names_a_live_call(repo_audit: Audit):
    assert not repo_audit.dead_rows, (
        "register rows whose file:line no longer spells that call:\n"
        + _lines(repo_audit.dead_rows)
        + "\nlive sites:\n"
        + _lines(sorted(repo_audit.sites))
    )


def test_anchored_callers_do_call_the_seam_and_stay_off_the_register(repo_audit: Audit):
    everything = sites_under(ROOT)
    for file in ANCHORED_CALLERS:
        assert any(s.file == file for s in everything), f"{file} no longer calls a seam"
        assert not any(r.file == file for r in repo_audit.rows), f"{file} is on the register"


# --- the seal, on synthetic trees --------------------------------------------


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    (root / SEAM_MODULE).parent.mkdir(parents=True, exist_ok=True)
    (root / SEAM_MODULE).write_text("def _load_prompt():\n    return ''\n", encoding="utf-8")
    return root


_CALL = "from claude_dispatcher import cross_family_reviewer as cfr\n\npanel = cfr.run_panel(\n    x=1,\n)\n"


def test_a_call_site_not_on_the_register_turns_the_row_red(tmp_path: Path):
    root = _tree(tmp_path, {"tools/new_tool.py": _CALL})
    assert audit(root, ()).unlisted == [Site("tools/new_tool.py", 3, "cfr.run_panel")]
    listed = audit(root, ("tools/new_tool.py:3 cfr.run_panel",))
    assert listed.unlisted == [] and listed.dead_rows == []


def test_a_row_rots_when_the_call_moves_off_its_line(tmp_path: Path):
    root = _tree(tmp_path, {"tools/t.py": "# added above\n" + _CALL})
    rotted = audit(root, ("tools/t.py:3 cfr.run_panel",))
    assert rotted.dead_rows == [Site("tools/t.py", 3, "cfr.run_panel")]
    assert rotted.unlisted == [Site("tools/t.py", 4, "cfr.run_panel")]


def test_a_row_naming_the_wrong_symbol_is_dead(tmp_path: Path):
    root = _tree(tmp_path, {"tools/t.py": _CALL})
    a = audit(root, ("tools/t.py:3 cfr.build_review_prompt",))
    assert a.dead_rows and a.unlisted


def test_only_the_pinned_anchored_file_is_excused(tmp_path: Path):
    root = _tree(tmp_path, {
        "src/claude_dispatcher/orchestrator.py": _CALL,
        "src/claude_dispatcher/other.py": _CALL,
    })
    a = audit(root, ())
    assert [s.file for s in a.unlisted] == ["src/claude_dispatcher/other.py"]


@pytest.mark.parametrize("body", [
    "def _load_prompt():\n    return ''\n\nx = _load_prompt().format()\n",
    "def resolve(cfg, run_panel: str = 'auto'):\n    return run_panel if run_panel else 'x'\n",
    "# see cross_family_reviewer._load_prompt for the seam\n",
    "def run_panel(**kw):\n    pass\n",
    "from claude_dispatcher.cross_family_reviewer import PanelVerdict\n",
], ids=["local-def", "parameter", "prose", "same-name-def", "non-seam-import"])
def test_decoys_are_not_sites(tmp_path: Path, body: str):
    root = _tree(tmp_path, {"src/claude_dispatcher/decoy.py": body})
    assert audit(root, ()).unlisted == []


@pytest.mark.parametrize("body,symbol", [
    ("import claude_dispatcher.cross_family_reviewer as m\nm.build_review_prompt(family='x')\n",
     "m.build_review_prompt"),
    ("import claude_dispatcher\nclaude_dispatcher.cross_family_reviewer._load_prompt('a')\n",
     "claude_dispatcher.cross_family_reviewer._load_prompt"),
    ("from claude_dispatcher.cross_family_reviewer import run_panel\nrun_panel()\n",
     "import run_panel"),
    ("from claude_dispatcher.cross_family_reviewer import (\n    collect_diff,\n    run_panel,\n)\n",
     "import run_panel"),
    ("from claude_dispatcher.cross_family_reviewer import *\n", "import *"),
], ids=["module-alias", "full-dotted", "from-import", "from-import-paren", "star"])
def test_each_spelling_is_a_site(tmp_path: Path, body: str, symbol: str):
    root = _tree(tmp_path, {"scripts/s.py": body})
    assert audit(root, ()).unlisted == [Site("scripts/s.py", 1 if symbol.startswith("import") else 2, symbol)]


def test_two_calls_in_one_file_need_two_rows(tmp_path: Path):
    root = _tree(tmp_path, {"tools/t.py": _CALL + "again = cfr.run_panel(x=2)\n"})
    assert audit(root, ("tools/t.py:3 cfr.run_panel",)).unlisted == [
        Site("tools/t.py", 6, "cfr.run_panel")
    ]


def test_test_files_under_scan_dirs_are_scanned(tmp_path: Path):
    root = _tree(tmp_path, {"src/claude_dispatcher/test_helper.py": _CALL})
    assert audit(root, ()).unlisted == [Site("src/claude_dispatcher/test_helper.py", 3, "cfr.run_panel")]


@pytest.mark.parametrize("raw", [
    "tools/x.py cfr.run_panel",
    "tools/x.py:abc cfr.run_panel",
    "tools/x.py:3",
    "tools/x.py:3 cfr.run_panel extra",
])
def test_a_malformed_register_row_is_refused_not_skipped(raw: str):
    with pytest.raises(ValueError):
        parse_row(raw)
