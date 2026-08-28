"""W2-1-2c seals: every prompt load is a listed load.

Grep-level: every place outside ``cross_family_reviewer.py`` that NAMES a
function on the load chain (``_load_prompt`` and everything in the module that
transitively calls it) is a site, and a site is either a row of
``prompt_provenance.UNANCHORED_ENTRY_POINTS`` or lives in a file this seal
lists as opening the run's journal. Nothing here asks whether a site executes,
declares, or is reachable — that is W2-1-2b's, by driving each entry point.

A site is any of: an attribute ``x.<seam>`` on ANY object (called, bound,
passed to ``partial``…); a bare name imported from the seam module (renamed
or not, star-imported, imported inside a function); a ``from`` import of a
seam name; a string literal equal to a seam name (``getattr``) or to the
module's dotted name (``import_module``). Names the file defines itself do
not count. Over-reporting is the safe direction: a false site costs a
register row, a missed site is a load nothing gated.

The scan covers ``src/``, ``tools/`` and ``scripts/``. ``tests/`` is not a
process that loads the prompt for a reviewer and is excluded.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from claude_dispatcher import prompt_provenance as pp

ROOT = Path(__file__).resolve().parent.parent

SEAM_MODULE = "src/claude_dispatcher/cross_family_reviewer.py"
SEAM_MODULE_NAME = "cross_family_reviewer"
SEAM_DOTTED = "claude_dispatcher.cross_family_reviewer"
ROOT_SEAM = "_load_prompt"
SCAN_DIRS = ("src", "tools", "scripts")

#: Files whose load goes through the gate WITH an anchor: the process opened the
#: journal whose genesis the gate compares against. A file here must open one
#: (``Journal.create``/``Journal.resume`` by name) and must not be registered as
#: journal-less. Membership is asserted, not inferred.
ANCHORED_CALLERS: tuple[str, ...] = ("src/claude_dispatcher/orchestrator.py",)
JOURNAL_OPENERS = ("Journal.create", "Journal.resume")

_ROW = re.compile(r"^(?P<file>\S+):(?P<line>\d+) (?P<symbol>\S+)$")


# --------------------------------------------------------------------------- #
# The scanner
# --------------------------------------------------------------------------- #


def load_chain(seam_source: str, root_seam: str = ROOT_SEAM) -> frozenset[str]:
    """Module-level definitions that name ``root_seam`` transitively."""
    tree = ast.parse(seam_source)
    named: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
                elif isinstance(sub, ast.Attribute):
                    names.add(sub.attr)
            named[node.name] = names
    chain = {root_seam}
    grew = True
    while grew:
        grew = False
        for name, names in named.items():
            if name not in chain and names & chain:
                chain.add(name)
                grew = True
    return frozenset(chain)


@dataclass(frozen=True)
class Site:
    file: str
    seam: str
    lineno: int
    end_lineno: int
    spelling: str

    def __str__(self) -> str:
        return f"{self.file}:{self.lineno} {self.seam} ({self.spelling})"


@dataclass(frozen=True)
class Row:
    raw: str
    file: str
    line: int
    seam: str

    def covers(self, site: Site) -> bool:
        return (
            self.file == site.file
            and self.seam == site.seam
            and site.lineno <= self.line <= site.end_lineno
        )


def parse_row(raw: str) -> Row:
    m = _ROW.match(raw)
    if m is None:
        raise ValueError(f"register row {raw!r} is not '<path>:<line> <symbol>'")
    return Row(
        raw=raw, file=m["file"], line=int(m["line"]),
        seam=m["symbol"].rsplit(".", 1)[-1],
    )


def _is_seam_module(module: str | None) -> bool:
    return (module or "").split(".")[-1] == SEAM_MODULE_NAME


def _bound_names(tree: ast.AST, seams: frozenset[str]) -> tuple[dict[str, str], bool]:
    """Local names bound to a seam by an import, and whether a star import
    from the seam module makes every seam name local."""
    seam_names: dict[str, str] = {}
    star = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and _is_seam_module(node.module):
            for alias in node.names:
                if alias.name == "*":
                    star = True
                elif alias.name in seams:
                    seam_names[alias.asname or alias.name] = alias.name
    return seam_names, star


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return None if head is None else f"{head}.{node.attr}"
    return None


def sites_in(source: str, file: str, seams: frozenset[str]) -> list[Site]:
    tree = ast.parse(source, filename=file)
    seam_names, star = _bound_names(tree, seams)
    found: dict[tuple[str, int, int], Site] = {}

    def add(stmt: ast.stmt, seam: str, spelling: str) -> None:
        key = (seam, stmt.lineno, stmt.end_lineno or stmt.lineno)
        found.setdefault(key, Site(file, seam, key[1], key[2], spelling))

    def visit(node: ast.AST, stmt: ast.stmt | None) -> None:
        if isinstance(node, ast.stmt):
            stmt = node
        if stmt is not None:
            if isinstance(node, ast.Attribute) and node.attr in seams:
                add(stmt, node.attr, "attribute")
            elif isinstance(node, ast.Name):
                if node.id in seam_names:
                    add(stmt, seam_names[node.id], "imported name")
                elif star and node.id in seams:
                    add(stmt, node.id, "star-imported name")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in seams:
                    add(stmt, node.value, "string")
                elif node.value == SEAM_DOTTED:
                    add(stmt, SEAM_MODULE_NAME, "module string")
            elif isinstance(node, ast.ImportFrom) and _is_seam_module(node.module):
                for alias in node.names:
                    if alias.name in seams:
                        add(stmt, alias.name, "import")
        for child in ast.iter_child_nodes(node):
            visit(child, stmt)

    visit(tree, None)
    return sorted(found.values(), key=lambda s: (s.lineno, s.seam))


def opens_journal(source: str) -> bool:
    return any(
        (_dotted(node) or "").endswith(JOURNAL_OPENERS)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute)
    )


def scannable(root: Path, scan_dirs: tuple[str, ...] = SCAN_DIRS) -> list[str]:
    files = []
    for top in scan_dirs:
        for path in sorted((root / top).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            parts = path.relative_to(root).parts
            if rel == SEAM_MODULE or "tests" in parts or "__pycache__" in parts:
                continue
            if path.name == "conftest.py" or path.name.startswith("test_"):
                continue
            files.append(rel)
    return files


@dataclass(frozen=True)
class Audit:
    seams: frozenset[str]
    sites: tuple[Site, ...]
    rows: tuple[Row, ...]
    #: Sites in a non-anchored file no row covers — the loads nothing listed.
    unlisted: tuple[Site, ...]
    #: Rows covering no site — a register pointing at a world that is not there.
    phantom: tuple[Row, ...]
    #: Anchored files that never open a journal, or excuse no site at all.
    anchored_faults: tuple[str, ...]
    #: Rows that register a file the anchored list already excuses.
    listed_anchored: tuple[Row, ...]


def audit(
    root: Path,
    *,
    register: tuple[str, ...],
    anchored: tuple[str, ...] = ANCHORED_CALLERS,
    scan_dirs: tuple[str, ...] = SCAN_DIRS,
) -> Audit:
    seams = load_chain((root / SEAM_MODULE).read_text(encoding="utf-8"))
    rows = tuple(parse_row(r) for r in register)
    sites: list[Site] = []
    anchored_faults: list[str] = []
    for rel in scannable(root, scan_dirs):
        source = (root / rel).read_text(encoding="utf-8")
        here = sites_in(source, rel, seams)
        sites.extend(here)
        if rel in anchored and (not here or not opens_journal(source)):
            anchored_faults.append(rel)
    anchored_faults.extend(f for f in anchored if not (root / f).is_file())
    unlisted = tuple(
        s for s in sites
        if s.file not in anchored and not any(r.covers(s) for r in rows)
    )
    phantom = tuple(r for r in rows if not any(r.covers(s) for s in sites))
    listed_anchored = tuple(r for r in rows if r.file in anchored)
    return Audit(
        seams=seams, sites=tuple(sites), rows=rows, unlisted=unlisted,
        phantom=phantom, anchored_faults=tuple(sorted(set(anchored_faults))),
        listed_anchored=listed_anchored,
    )


def _lines(items) -> str:
    return "\n  ".join(str(i) for i in items) or "(none)"


# --------------------------------------------------------------------------- #
# The repository
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def repo_audit() -> Audit:
    return audit(ROOT, register=pp.UNANCHORED_ENTRY_POINTS)


def test_the_load_chain_is_exactly_the_three_seams(repo_audit: Audit):
    """A fourth function that reaches ``_load_prompt`` is a new external seam
    and a review-time event, even before anything outside calls it."""
    assert repo_audit.seams == {"_load_prompt", "build_review_prompt", "run_panel"}


def test_every_register_row_is_well_formed_and_names_a_seam(repo_audit: Audit):
    for row in repo_audit.rows:
        assert (ROOT / row.file).is_file(), row.raw
        assert row.seam in repo_audit.seams, (
            f"{row.raw!r} names {row.seam!r}, which is not on the load chain "
            f"{sorted(repo_audit.seams)}"
        )
    assert len({r.raw for r in repo_audit.rows}) == len(repo_audit.rows)


def test_every_prompt_load_is_a_listed_load(repo_audit: Audit):
    """THE row. A site in a file that neither the register nor
    ``ANCHORED_CALLERS`` names is a load that bypasses the register: it fails
    closed at run time (constraint 3) and turns this red at review time."""
    def why(site: Site) -> str:
        near = [r.line for r in repo_audit.rows if (r.file, r.seam) == (site.file, site.seam)]
        return f"{site} — " + (
            f"the register's row for this file points at line {near}; update it"
            if near else "no register row names this file and seam"
        )

    assert not repo_audit.unlisted, (
        "load-chain references no register row covers:\n  "
        f"{_lines(why(s) for s in repo_audit.unlisted)}\n"
        "Add a row to prompt_provenance.UNANCHORED_ENTRY_POINTS for each "
        "(and a declare_unanchored call on its path), or — only if the process "
        "opened the run's journal — add the file to ANCHORED_CALLERS here."
    )


def test_every_register_row_points_at_a_live_site(repo_audit: Audit):
    """A row is quoted verbatim in every load record its declaration produces;
    one that points past the site it names is provenance pointing at nothing."""
    assert not repo_audit.phantom, (
        "register rows covering no site (the site moved, or never was):\n  "
        f"{_lines(r.raw for r in repo_audit.phantom)}\n"
        f"sites seen:\n  {_lines(repo_audit.sites)}"
    )


def test_anchored_callers_open_a_journal_and_stay_off_the_register(repo_audit: Audit):
    assert not repo_audit.anchored_faults, (
        f"anchored callers that open no journal or excuse no site: "
        f"{repo_audit.anchored_faults}"
    )
    assert not repo_audit.listed_anchored, (
        "a file cannot be both journal-less and anchored: "
        f"{[r.raw for r in repo_audit.listed_anchored]}"
    )


def test_the_scan_reaches_every_file_the_register_could_name(repo_audit: Audit):
    """The register's three files and the anchored file are all inside the
    scanned set, so a site in any of them is seen — and the seam module
    itself is not, so the chain's own internal calls are not sites."""
    seen = set(scannable(ROOT))
    for f in (*ANCHORED_CALLERS, *(r.file for r in repo_audit.rows)):
        assert f in seen, f
    assert SEAM_MODULE not in seen
    assert not any(f.startswith("tests/") for f in seen)


# --------------------------------------------------------------------------- #
# The scanner, on synthetic trees: what it sees and what it ignores
# --------------------------------------------------------------------------- #


_SYNTHETIC_SEAM_MODULE = '''\
_PROMPTS_DIR = "reviewer_prompts"


def _load_prompt(family, domain=None):
    return family


def build_review_prompt(*, family, **kw):
    return _load_prompt(family)


def run_panel(**kw):
    return build_review_prompt(family="codex")


def collect_diff(**kw):
    return ""
'''


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in {SEAM_MODULE: _SYNTHETIC_SEAM_MODULE, **files}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


#: (id, path, source, seams referenced — one entry per site expected).
PROBES = (
    (
        "attribute call",
        "tools/probe.py",
        "from claude_dispatcher import cross_family_reviewer as cfr\n\n"
        "def main():\n    return cfr.run_panel(diff='')\n",
        ("run_panel",),
    ),
    (
        "import-rename then call",
        "tools/probe.py",
        "from claude_dispatcher.cross_family_reviewer import run_panel as rp\n\n"
        "def main():\n    return rp(diff='')\n",
        ("run_panel", "run_panel"),
    ),
    (
        "bind then call",
        "tools/probe.py",
        "from claude_dispatcher import cross_family_reviewer as cfr\n\n"
        "def main():\n    go = cfr.run_panel\n    return go(diff='')\n",
        ("run_panel",),
    ),
    (
        "functools.partial",
        "tools/probe.py",
        "import functools\n"
        "from claude_dispatcher import cross_family_reviewer as cfr\n\n"
        "run = functools.partial(cfr.run_panel, diff='')\n",
        ("run_panel",),
    ),
    (
        "getattr with a string",
        "tools/probe.py",
        "from claude_dispatcher import cross_family_reviewer as cfr\n\n"
        "def main():\n    return getattr(cfr, 'run_panel')(diff='')\n",
        ("run_panel",),
    ),
    (
        "import_module with the dotted name",
        "tools/probe.py",
        "import importlib\n\n"
        "def main():\n"
        "    mod = importlib.import_module('claude_dispatcher.cross_family_reviewer')\n"
        "    return mod.run_panel(diff='')\n",
        ("cross_family_reviewer", "run_panel"),
    ),
    (
        "dotted module attribute",
        "tools/probe.py",
        "import claude_dispatcher.cross_family_reviewer\n\n"
        "def main():\n"
        "    return claude_dispatcher.cross_family_reviewer.build_review_prompt(family='x')\n",
        ("build_review_prompt",),
    ),
    (
        "star import",
        "tools/probe.py",
        "from claude_dispatcher.cross_family_reviewer import *\n\n"
        "def main():\n    return _load_prompt('codex')\n",
        ("_load_prompt",),
    ),
    (
        "relative import inside the package",
        "src/claude_dispatcher/probe.py",
        "from . import cross_family_reviewer as cfr\n\n"
        "def main():\n    return cfr._load_prompt('codex')\n",
        ("_load_prompt",),
    ),
    (
        "relative from-import of a seam",
        "src/claude_dispatcher/probe.py",
        "from .cross_family_reviewer import build_review_prompt\n\n"
        "def main():\n    return build_review_prompt(family='x')\n",
        ("build_review_prompt", "build_review_prompt"),
    ),
    (
        "import inside a function",
        "tools/probe.py",
        "def main():\n"
        "    from claude_dispatcher import cross_family_reviewer as cfr\n"
        "    return cfr.run_panel(diff='')\n",
        ("run_panel",),
    ),
    (
        "attribute on an object the file did not import",
        "tools/probe.py",
        "def main(mod):\n    return mod.run_panel(diff='')\n",
        ("run_panel",),
    ),
    (
        "a second call in one file",
        "tools/probe.py",
        "from claude_dispatcher import cross_family_reviewer as cfr\n\n"
        "def first():\n    return cfr.run_panel(diff='')\n\n"
        "def second():\n    return cfr.run_panel(diff='')\n",
        ("run_panel", "run_panel"),
    ),
    (
        "a multi-line call",
        "tools/probe.py",
        "from claude_dispatcher import cross_family_reviewer as cfr\n\n"
        "def main():\n    return cfr.run_panel(\n        diff='',\n    )\n",
        ("run_panel",),
    ),
)


@pytest.mark.parametrize(
    "path, source, expected", [p[1:] for p in PROBES], ids=[p[0] for p in PROBES]
)
def test_the_spelling_is_unlisted_until_its_row_exists(
    tmp_path: Path, path: str, source: str, expected: tuple[str, ...],
):
    root = _tree(tmp_path, {path: source})

    bare = audit(root, register=(), anchored=())
    assert tuple(s.seam for s in bare.unlisted) == expected, _lines(bare.sites)
    assert all(s.file == path for s in bare.unlisted)

    # The row covers the statement: its first line and its last both list it.
    for pick in (lambda s: s.lineno, lambda s: s.end_lineno):
        rows = tuple(f"{s.file}:{pick(s)} probe.{s.seam}" for s in bare.unlisted)
        listed = audit(root, register=rows, anchored=())
        assert not listed.unlisted and not listed.phantom, _lines(listed.unlisted)

    # A row that names the file and seam but not the statement lists nothing.
    stale = tuple(f"{s.file}:{s.end_lineno + 50} probe.{s.seam}" for s in bare.unlisted)
    moved = audit(root, register=stale, anchored=())
    assert tuple(s.seam for s in moved.unlisted) == expected
    assert tuple(r.raw for r in moved.phantom) == stale

    # A row naming the right line but another seam lists nothing either.
    other = tuple(f"{s.file}:{s.lineno} probe.collect_diff" for s in bare.unlisted)
    assert tuple(s.seam for s in audit(root, register=other, anchored=()).unlisted) == expected


_CONTROL = '''\
"""A file that mentions cross_family_reviewer._load_prompt in prose only."""
import functools
from claude_dispatcher import cross_family_reviewer as cfr


def _load_prompt():
    return "verifier prompt"


def render():
    return _load_prompt().format(run_panel="auto")


def resolve(cfg, run_panel: str = "auto"):
    run_panel = (cfg or run_panel).lower()
    return functools.partial(resolve, run_panel=run_panel)


def prompts_dir():
    return getattr(cfr, "_PROMPTS_DIR", None), cfr.collect_diff()
'''


def test_the_scanner_ignores_same_named_local_definitions_and_prose(tmp_path: Path):
    """``verifier._load_prompt``, ``orchestrator``'s ``run_panel`` local and
    ``quality_levels``' ``run_panel`` parameter are the repo's own decoys."""
    root = _tree(tmp_path, {"src/claude_dispatcher/verifier.py": _CONTROL})
    result = audit(root, register=(), anchored=())
    assert result.sites == (), _lines(result.sites)


def test_a_seam_that_joins_the_chain_is_seen_without_editing_this_file(tmp_path: Path):
    """The chain is computed from the seam module, not pinned in the scanner:
    a new function calling ``build_review_prompt`` makes its callers sites."""
    module = _SYNTHETIC_SEAM_MODULE + (
        "\n\ndef render_for(family):\n    return build_review_prompt(family=family)\n"
    )
    caller = (
        "from claude_dispatcher import cross_family_reviewer as cfr\n\n"
        "def main():\n    return cfr.render_for('codex')\n"
    )
    root = _tree(tmp_path, {SEAM_MODULE: module, "tools/probe.py": caller})
    result = audit(root, register=(), anchored=())
    assert "render_for" in result.seams
    assert [s.seam for s in result.unlisted] == ["render_for"]

    root2 = _tree(tmp_path / "plain", {"tools/probe.py": caller})
    assert audit(root2, register=(), anchored=()).sites == ()


_ANCHORED = (
    "from . import cross_family_reviewer as cfr_mod\n"
    "from . import journal as journal_mod\n\n"
    "def open_journal(path):\n    return journal_mod.Journal.create(path)\n\n"
    "def panel():\n    return cfr_mod.run_panel(diff='')\n"
)
_ORCHESTRATOR = "src/claude_dispatcher/orchestrator.py"


def test_an_anchored_caller_is_excused_only_while_it_opens_a_journal(tmp_path: Path):
    root = _tree(tmp_path, {_ORCHESTRATOR: _ANCHORED})

    excused = audit(root, register=(), anchored=(_ORCHESTRATOR,))
    assert not excused.unlisted and not excused.anchored_faults
    assert [s.seam for s in excused.sites] == ["run_panel"]

    unexcused = audit(root, register=(), anchored=())
    assert [s.seam for s in unexcused.unlisted] == ["run_panel"]

    listed = audit(
        root, register=(f"{_ORCHESTRATOR}:8 cfr_mod.run_panel",),
        anchored=(_ORCHESTRATOR,),
    )
    assert [r.file for r in listed.listed_anchored] == [_ORCHESTRATOR]

    no_journal = _tree(
        tmp_path / "nj",
        {_ORCHESTRATOR: _ANCHORED.replace("journal_mod.Journal.create", "open")},
    )
    assert audit(no_journal, register=(), anchored=(_ORCHESTRATOR,)).anchored_faults == (
        _ORCHESTRATOR,
    )

    idle = _tree(
        tmp_path / "idle",
        {_ORCHESTRATOR: _ANCHORED.replace("cfr_mod.run_panel", "cfr_mod.collect_diff")},
    )
    assert audit(idle, register=(), anchored=(_ORCHESTRATOR,)).anchored_faults == (
        _ORCHESTRATOR,
    )


@pytest.mark.parametrize(
    "raw", ["tools/x.py:12", "tools/x.py cfr.run_panel", "tools/x.py:ab cfr.run_panel", ""]
)
def test_a_malformed_register_row_is_refused_not_skipped(raw: str):
    with pytest.raises(ValueError):
        parse_row(raw)
