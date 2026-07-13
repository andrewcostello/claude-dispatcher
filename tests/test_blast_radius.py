"""Blast-radius artifact: symbol extraction, reference grep, rendering."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import blast_radius as br

GO_DIFF = """\
diff --git a/svc/accept.go b/svc/accept.go
index 111..222 100644
--- a/svc/accept.go
+++ b/svc/accept.go
@@ -10,6 +10,9 @@ func AcceptWager(ctx context.Context) error {
+\tif err := freezeBonus(ctx); err != nil {
+\t\treturn err
+\t}
@@ -30,2 +33,2 @@ func helperTiny() {
-func computeHoleInOneBonus(amount int64) int64 {
+func computeHoleInOneBonus(amount int64, freeze bool) int64 {
"""


def test_extract_symbols_from_hunk_headers_and_defs() -> None:
    syms = br.extract_symbols(GO_DIFF)
    # Enclosing decl from the hunk header + the modified definition line.
    assert "AcceptWager" in syms
    assert "computeHoleInOneBonus" in syms


def test_extract_symbols_filters_noise() -> None:
    diff = (
        "diff --git a/x.go b/x.go\n"
        "@@ -1,1 +1,1 @@ func main() {\n"
        "+func run() {}\n"
        "+func TestSomething(t *testing.T) {}\n"
        "+func get() {}\n"
    )
    assert br.extract_symbols(diff) == []


def test_changed_files_parses_b_side_paths() -> None:
    assert br.changed_files(GO_DIFF) == ["svc/accept.go"]


def test_extract_symbols_bounded() -> None:
    diff = "diff --git a/x.go b/x.go\n" + "\n".join(
        f"+func GeneratedFunc{i:03d}() {{}}" for i in range(50)
    )
    assert len(br.extract_symbols(diff, max_symbols=10)) == 10


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    d = tmp_path / "br-repo"
    d.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(d)],
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d,
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=d,
                   check=True, capture_output=True)
    (d / "svc").mkdir()
    (d / "svc" / "accept.go").write_text(
        "package svc\n\nfunc AcceptWager() {}\n", encoding="utf-8")
    # A sibling surface OUTSIDE the diff that references the symbol.
    (d / "svc" / "autoplay.go").write_text(
        "package svc\n\nfunc autoAccept() { AcceptWager() }\n",
        encoding="utf-8")
    # Test + generated references must be excluded.
    (d / "svc" / "accept_test.go").write_text(
        "package svc\n\nfunc TestX(t *T) { AcceptWager() }\n",
        encoding="utf-8")
    (d / "svc" / "pb").mkdir()
    (d / "svc" / "pb" / "gen.go").write_text(
        "package pb\n\n// AcceptWager wire\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=d, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=d,
                   check=True, capture_output=True)
    return d


def test_build_blast_radius_names_sibling_not_test_or_generated(repo: Path) -> None:
    diff = (
        "diff --git a/svc/accept.go b/svc/accept.go\n"
        "@@ -3,1 +3,1 @@ func AcceptWager() {\n"
        "+\t// touched\n"
    )
    art = br.build_blast_radius(repo_root=repo, branch="main", diff=diff)
    assert "AcceptWager" in art
    assert "svc/autoplay.go" in art          # the sibling surface
    assert "accept_test.go" not in art       # tests excluded
    assert "pb/gen.go" not in art            # generated excluded
    assert "svc/accept.go" not in art        # the diff's own file excluded


def test_build_blast_radius_empty_when_no_symbols(repo: Path) -> None:
    assert br.build_blast_radius(
        repo_root=repo, branch="main",
        diff="diff --git a/README.md b/README.md\n+docs only\n") == ""


def test_build_blast_radius_fails_open_on_missing_repo(tmp_path: Path) -> None:
    art = br.build_blast_radius(
        repo_root=tmp_path / "nope", branch="main", diff=GO_DIFF)
    assert art == ""  # no refs found anywhere -> empty, never raises


def test_build_blast_radius_respects_char_cap(repo: Path) -> None:
    diff = (
        "diff --git a/svc/accept.go b/svc/accept.go\n"
        "@@ -3,1 +3,1 @@ func AcceptWager() {\n+x\n"
    )
    art = br.build_blast_radius(
        repo_root=repo, branch="main", diff=diff, max_chars=80)
    assert len(art) <= 80 + len("\n... [blast radius truncated]")
