"""Tests for the deterministic risk classifier (Phase 3).

Three layers:
  * pure rule coverage via ``evaluate`` — table-driven, each rule flipped
    individually low->elevated with the violated rule named in the reasons;
  * effective-diff counting via ``effective_diff_lines`` — proves test and
    generated globs are excluded from the count;
  * config merge via ``risk_config_from_mapping`` / ``load_risk_config`` —
    defaults when absent, partial sections merge over defaults;
  * git plumbing via ``collect_diff`` / ``classify`` against a real tiny repo.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import classification, risk
from claude_dispatcher.risk import (
    DEFAULT_RISK_CONFIG,
    ELEVATED,
    LOW,
    FileDiff,
    RiskConfig,
    RiskConfigError,
    effective_diff_lines,
    evaluate,
    risk_config_from_mapping,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _prod(path: str, ins: int = 10, dels: int = 0) -> FileDiff:
    return FileDiff(path=path, insertions=ins, deletions=dels)


# A baseline set of inputs that classifies LOW. Each rule test mutates exactly
# one of these to prove that rule alone flips the verdict.
def _low_kwargs(**overrides):
    base = dict(
        size_label="S",
        labels=["size:S", "area:config"],
        changed_files=[_prod("src/app/handler.py", 20, 5)],
        verified=True,
        verification_iterations=0,
        config=DEFAULT_RISK_CONFIG,
    )
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Baseline
# --------------------------------------------------------------------------- #


def test_baseline_is_low_with_no_reasons():
    verdict = evaluate(**_low_kwargs())
    assert verdict.level == LOW
    assert verdict.is_low
    assert verdict.reasons == ()


# --------------------------------------------------------------------------- #
# Each rule individually flips low -> elevated, naming the violated rule
# --------------------------------------------------------------------------- #


# Every rule, each flipping the low baseline on its own. Shared with the
# classification sweep below.
_RULE_CASES = [
        # size threshold (max_size defaults to S)
        (dict(size_label="M", labels=["size:M"]), "size M exceeds max_size S"),
        (dict(size_label="XL", labels=["size:XL"]), "size XL exceeds max_size S"),
        # missing/unknown size
        (dict(size_label=None, labels=["area:config"]), "size label missing"),
        (dict(size_label="HUGE", labels=["size:HUGE"]), "missing or unrecognised"),
        # forbidden labels
        (dict(labels=["size:S", "security"]), "forbidden label: security"),
        (dict(labels=["size:S", "critical"]), "forbidden label: critical"),
        (dict(labels=["size:S", "financial"]), "forbidden label: financial"),
        # forbidden paths
        (
            dict(changed_files=[_prod("db/migrations/001_init.sql")]),
            "forbidden path touched: db/migrations/001_init.sql",
        ),
        (
            dict(changed_files=[_prod("api/order.proto")]),
            "matches **/*.proto",
        ),
        (
            dict(changed_files=[_prod("internal/auth/token.go")]),
            "matches **/auth/**",
        ),
        (
            dict(changed_files=[_prod(".github/workflows/ci.yml")]),
            "matches .github/**",
        ),
        (dict(changed_files=[_prod("go.mod")]), "matches go.mod"),
        (dict(changed_files=[_prod("Dockerfile.prod")]), "matches Dockerfile*"),
        (
            dict(changed_files=[_prod("compose.prod.yaml")]),
            "matches compose*.y*ml",
        ),
        (dict(changed_files=[_prod("pyproject.toml")]), "matches pyproject.toml"),
        # effective diff size
        (
            dict(changed_files=[_prod("src/big.py", 150, 60)]),
            "effective diff 210 lines exceeds max_effective_diff_lines 200",
        ),
        # first-pass verification
        (dict(verified=False), "first-pass verification not satisfied"),
        (dict(verified=None), "first-pass verification not satisfied"),
        (dict(verification_iterations=1), "first-pass verification not satisfied"),
]


@pytest.mark.parametrize("overrides, needle", _RULE_CASES)
def test_each_rule_flips_to_elevated(overrides, needle):
    verdict = evaluate(**_low_kwargs(**overrides))
    assert verdict.level == ELEVATED
    assert any(needle in r for r in verdict.reasons), verdict.reasons


def test_multiple_violations_all_reported():
    """The classifier collects every violated rule, not just the first."""
    verdict = evaluate(
        **_low_kwargs(
            size_label="L",
            labels=["size:L", "security"],
            verified=False,
        )
    )
    assert verdict.level == ELEVATED
    joined = " | ".join(verdict.reasons)
    assert "size L exceeds" in joined
    assert "forbidden label: security" in joined
    assert "first-pass verification" in joined


# --------------------------------------------------------------------------- #
# Effective-diff counting excludes test/generated globs
# --------------------------------------------------------------------------- #


def test_effective_diff_excludes_test_and_generated():
    files = [
        _prod("src/app/handler.py", 100, 50),  # counted: 150
        _prod("internal/svc/svc_test.go", 900, 100),  # test glob -> excluded
        _prod("pkg/foo/foo.pb.go", 900, 100),  # generated glob -> excluded
        _prod("tests/test_app.py", 500, 0),  # test glob (tests/**) -> excluded
        _prod("pkg/db/sqlc/queries.go", 400, 0),  # generated (**/sqlc/**) -> excluded
        _prod("src/util/data.spec.ts", 300, 0),  # test glob (*.spec.*) -> excluded
        _prod("app/internal/testdata/big.json", 999, 0),  # **/testdata/** excluded
    ]
    assert effective_diff_lines(files, DEFAULT_RISK_CONFIG) == 150


def test_effective_diff_counts_binary_as_zero():
    files = [_prod("assets/logo.png", 0, 0), _prod("src/x.py", 5, 5)]
    assert effective_diff_lines(files, DEFAULT_RISK_CONFIG) == 10


def test_test_heavy_change_stays_under_threshold():
    """A small production change with a huge test file is still under 200."""
    files = [
        _prod("src/app/small.py", 30, 10),  # counted: 40
        _prod("tests/test_small.py", 5000, 0),  # excluded
    ]
    verdict = evaluate(
        **_low_kwargs(changed_files=files, labels=["size:S"], size_label="S")
    )
    assert verdict.level == LOW


# --------------------------------------------------------------------------- #
# docs-only is low at any size; test-only is NOT auto-low
# --------------------------------------------------------------------------- #


def test_docs_only_is_low_at_any_size():
    files = [_prod("README.md", 800, 200), _prod("docs/guide.md", 300, 0)]
    # Huge diff, XL size, and even no verification — still low for docs-only.
    verdict = evaluate(
        size_label="XL",
        labels=["size:XL"],
        changed_files=files,
        verified=False,
        verification_iterations=5,
        config=DEFAULT_RISK_CONFIG,
    )
    assert verdict.level == LOW
    assert any("docs-only" in r for r in verdict.reasons)


def test_docs_only_under_forbidden_path_is_still_low():
    """Pinned behavior: a *.md-only diff overrides the forbidden-path guard.

    The plan says docs are "always low-risk"; the denylist guards code/config in
    those trees, not prose. A Markdown file under a forbidden path stays low.
    """
    files = [_prod(".github/SECURITY.md", 30, 0), _prod("internal/auth/NOTES.md", 5, 0)]
    verdict = evaluate(**_low_kwargs(changed_files=files, size_label="M", labels=["size:M"]))
    assert verdict.level == LOW
    assert any("docs-only" in r for r in verdict.reasons)


def test_mixed_docs_and_code_is_not_docs_only():
    files = [_prod("README.md", 10, 0), _prod("src/app.py", 250, 0)]
    verdict = evaluate(**_low_kwargs(changed_files=files))
    # The .md does not rescue it; the oversized code diff flips it.
    assert verdict.level == ELEVATED
    assert any("effective diff" in r for r in verdict.reasons)


def test_docs_only_respects_disable_flag():
    cfg = RiskConfig(docs_only_low_risk=False)
    files = [_prod("README.md", 800, 0)]  # 800 effective lines, > 200
    verdict = evaluate(
        size_label="S",
        labels=["size:S"],
        changed_files=files,
        verified=True,
        verification_iterations=0,
        config=cfg,
    )
    assert verdict.level == ELEVATED
    assert any("effective diff" in r for r in verdict.reasons)


def test_test_only_diff_is_not_auto_low():
    """A test-only diff that fails another condition stays elevated.

    Unlike docs-only, a test-only diff is never short-circuited to low — it
    goes through the normal rule set, so a verification failure still flips it.
    """
    files = [_prod("tests/test_app.py", 40, 0)]
    verdict = evaluate(
        **_low_kwargs(changed_files=files, verified=False)
    )
    assert verdict.level == ELEVATED
    assert any("first-pass verification" in r for r in verdict.reasons)


def test_test_only_diff_can_still_be_low_via_normal_rules():
    """When every condition holds, a test-only diff classifies low — it is the
    *automatic* low-risk that's withheld, not low-risk itself."""
    files = [_prod("tests/test_app.py", 40, 0)]
    verdict = evaluate(**_low_kwargs(changed_files=files))
    assert verdict.level == LOW


# --------------------------------------------------------------------------- #
# Glob matching edge cases
# --------------------------------------------------------------------------- #


def test_migrations_glob_matches_at_root_and_nested():
    assert risk.matches_any_glob("migrations/001.sql", DEFAULT_RISK_CONFIG.forbidden_paths)
    assert risk.matches_any_glob(
        "a/b/migrations/c/001.sql", DEFAULT_RISK_CONFIG.forbidden_paths
    )


def test_go_mod_anchored_to_root_only():
    assert risk.matches_any_glob("go.mod", ("go.mod",))
    assert not risk.matches_any_glob("vendor/lib/go.mod", ("go.mod",))


def test_star_test_glob_matches_at_any_depth():
    assert risk.matches_any_glob("a/b/c_test.go", ("*_test.go",))
    assert risk.matches_any_glob("c_test.go", ("*_test.go",))


# --------------------------------------------------------------------------- #
# Config: defaults when absent, partial merge over defaults
# --------------------------------------------------------------------------- #


def test_defaults_when_section_absent():
    assert risk_config_from_mapping(None) == DEFAULT_RISK_CONFIG


def test_partial_section_merges_over_defaults():
    cfg = risk_config_from_mapping({"max_effective_diff_lines": 50})
    assert cfg.max_effective_diff_lines == 50
    # everything else is unchanged from the defaults
    assert cfg.max_size == DEFAULT_RISK_CONFIG.max_size
    assert cfg.forbidden_labels == DEFAULT_RISK_CONFIG.forbidden_labels
    assert cfg.forbidden_paths == DEFAULT_RISK_CONFIG.forbidden_paths
    assert cfg.test_globs == DEFAULT_RISK_CONFIG.test_globs
    assert cfg.generated_globs == DEFAULT_RISK_CONFIG.generated_globs
    assert cfg.docs_only_low_risk is True


def test_partial_section_overrides_lists():
    cfg = risk_config_from_mapping(
        {"forbidden_labels": ["secret"], "test_globs": ["*.spec.ts"]}
    )
    assert cfg.forbidden_labels == ("secret",)
    assert cfg.test_globs == ("*.spec.ts",)
    assert cfg.max_size == "S"  # untouched default


def test_unknown_keys_in_section_are_ignored():
    cfg = risk_config_from_mapping({"future_knob": 7, "max_size": "M"})
    assert cfg.max_size == "M"


@pytest.mark.parametrize(
    "section, needle",
    [
        ({"max_size": "HUGE"}, "max_size"),
        ({"max_size": 3}, "max_size"),
        ({"max_effective_diff_lines": -1}, "non-negative"),
        ({"max_effective_diff_lines": True}, "non-negative"),
        ({"max_effective_diff_lines": "200"}, "non-negative"),
        ({"docs_only_low_risk": "yes"}, "boolean"),
        ({"forbidden_paths": "go.mod"}, "must be a list"),
        ({"forbidden_labels": [""]}, "non-empty strings"),
        ({"forbidden_labels": [True]}, "non-empty strings"),
    ],
)
def test_malformed_section_raises(section, needle):
    with pytest.raises(RiskConfigError) as exc:
        risk_config_from_mapping(section)
    assert needle in str(exc.value)


def test_non_mapping_section_raises():
    with pytest.raises(RiskConfigError):
        risk_config_from_mapping(["not", "a", "mapping"])


def test_load_risk_config_absent_file_returns_defaults(tmp_path: Path):
    assert risk.load_risk_config(tmp_path) == DEFAULT_RISK_CONFIG


def test_load_risk_config_no_risk_key_returns_defaults(tmp_path: Path):
    (tmp_path / ".dispatcher.yaml").write_text('test: "pytest -q"\n', encoding="utf-8")
    assert risk.load_risk_config(tmp_path) == DEFAULT_RISK_CONFIG


def test_load_risk_config_merges_partial_section(tmp_path: Path):
    (tmp_path / ".dispatcher.yaml").write_text(
        'test: "pytest -q"\nrisk:\n  max_size: M\n  max_effective_diff_lines: 75\n',
        encoding="utf-8",
    )
    cfg = risk.load_risk_config(tmp_path)
    assert cfg.max_size == "M"
    assert cfg.max_effective_diff_lines == 75
    assert cfg.forbidden_paths == DEFAULT_RISK_CONFIG.forbidden_paths


# --------------------------------------------------------------------------- #
# Git plumbing: collect_diff and classify against a real repo
# --------------------------------------------------------------------------- #


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A repo on `main` with one base commit; tests branch and add files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "T"], repo)
    (repo / "base.txt").write_text("seed\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base"], repo)
    return repo


def _branch_with_changes(repo: Path, files: dict[str, str]) -> None:
    _git(["checkout", "-q", "-b", "feat/x"], repo)
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "work"], repo)


def test_collect_diff_counts_lines_and_excludes_via_caller(git_repo: Path):
    _branch_with_changes(
        git_repo,
        {
            "src/app.py": "a\nb\nc\n",  # 3 insertions
            "tests/test_app.py": "x\ny\n",  # 2 insertions (test glob)
        },
    )
    files = risk.collect_diff(git_repo, "main")
    by_path = {f.path: f for f in files}
    assert by_path["src/app.py"].insertions == 3
    assert by_path["tests/test_app.py"].insertions == 2
    # The counting rule excludes the test file.
    assert effective_diff_lines(files, DEFAULT_RISK_CONFIG) == 3


def test_classify_low_on_real_repo(git_repo: Path):
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})
    task_row = {
        "labels": ["size:S", "area:config"],
        "verified": True,
        "verification_iterations": 0,
    }
    verdict = risk.classify(task_row, git_repo, "main")
    assert verdict.level == LOW


def test_classify_elevated_on_forbidden_path(git_repo: Path):
    _branch_with_changes(git_repo, {"internal/auth/token.py": "secret\n"})
    task_row = {
        "labels": ["size:S"],
        "verified": True,
        "verification_iterations": 0,
    }
    verdict = risk.classify(task_row, git_repo, "main")
    assert verdict.level == ELEVATED
    assert any("**/auth/**" in r for r in verdict.reasons)


def test_classify_elevated_when_not_first_pass_verified(git_repo: Path):
    _branch_with_changes(git_repo, {"src/app.py": "one\n"})
    task_row = {"labels": ["size:S"], "verified": True, "verification_iterations": 2}
    verdict = risk.classify(task_row, git_repo, "main")
    assert verdict.level == ELEVATED
    assert any("first-pass verification" in r for r in verdict.reasons)


def test_classify_fails_closed_on_bad_base_ref(git_repo: Path):
    _branch_with_changes(git_repo, {"src/app.py": "one\n"})
    task_row = {"labels": ["size:S"], "verified": True, "verification_iterations": 0}
    verdict = risk.classify(task_row, git_repo, "no-such-ref")
    assert verdict.level == ELEVATED
    assert any("could not compute effective diff" in r for r in verdict.reasons)


# --------------------------------------------------------------------------- #
# GO-1: cmd/classify as an additional ELEVATING signal (pure evaluate)
# --------------------------------------------------------------------------- #


def _cls(**kw) -> classification.Classification:
    return classification.Classification(**kw)


@pytest.mark.parametrize(
    "cls, needle",
    [
        (_cls(risk="high"), "classification risk tier high"),
        (_cls(risk="critical"), "classification risk tier critical"),
        (_cls(risk="CRITICAL"), "classification risk tier CRITICAL"),
        (_cls(risk="low", financial_paths_touched=True), "financial path touched"),
        (_cls(risk="low", gate_signals=("env-gate",)), "gate signals in changed lines: env-gate"),
    ],
)
def test_elevated_classification_forces_elevated_on_a_low_task(cls, needle):
    assert evaluate(**_low_kwargs()).level == LOW
    verdict = evaluate(**_low_kwargs(), classification=cls)
    assert verdict.level == ELEVATED
    assert any(needle in r for r in verdict.reasons), verdict.reasons


@pytest.mark.parametrize(
    "cls",
    [
        _cls(risk="low"),
        _cls(risk="medium"),
        _cls(risk="low", panel_reduced=True, client_only=True, panel_seats=1),
        _cls(risk="", components=("web",)),
    ],
)
def test_non_elevating_classification_leaves_a_low_verdict_low(cls):
    assert evaluate(**_low_kwargs(), classification=cls) == evaluate(**_low_kwargs())


@pytest.mark.parametrize("overrides, needle", _RULE_CASES)
def test_low_classification_never_downgrades_an_elevated_verdict(overrides, needle):
    """One-directional: path evidence may raise, never lower."""
    legacy = evaluate(**_low_kwargs(**overrides))
    assert legacy.level == ELEVATED
    for cls in (_cls(risk="low"), _cls(risk="low", panel_reduced=True)):
        verdict = evaluate(**_low_kwargs(**overrides), classification=cls)
        assert verdict.level == ELEVATED
        assert verdict.reasons == legacy.reasons
        assert any(needle in r for r in verdict.reasons)


def test_elevating_classification_keeps_the_rule_reasons_and_adds_its_own():
    verdict = evaluate(
        **_low_kwargs(labels=["size:S", "security"]),
        classification=_cls(risk="high", financial_paths_touched=True),
    )
    assert verdict.level == ELEVATED
    joined = " | ".join(verdict.reasons)
    assert "forbidden label: security" in joined
    assert "classification risk tier high" in joined
    assert "financial path touched" in joined


@pytest.mark.parametrize(
    "kwargs",
    [_low_kwargs()]
    + [_low_kwargs(**o) for o, _ in _RULE_CASES]
    + [
        _low_kwargs(changed_files=[_prod("docs/big.md", 5000, 0)]),
        _low_kwargs(changed_files=[_prod(".github/SECURITY.md", 3, 0)]),
        _low_kwargs(changed_files=[]),
        _low_kwargs(size_label="L", labels=["size:L", "security"], verified=False),
    ],
)
def test_none_classification_reproduces_the_legacy_verdict_exactly(kwargs):
    """``classification=None`` (and omitting it) IS today's verdict."""
    legacy = risk._evaluate_rules(**kwargs)
    assert evaluate(**kwargs) == legacy
    assert evaluate(**kwargs, classification=None) == legacy
    assert evaluate(**kwargs).classification is None


def test_path_evidence_elevates_even_a_docs_only_diff():
    """The carve-out bypasses the RULES, not path evidence — a classification
    is allowed to add review anywhere, and only ever add."""
    docs = _low_kwargs(changed_files=[_prod("docs/big.md", 5000, 0)])
    assert evaluate(**docs).level == LOW
    assert evaluate(**docs, classification=_cls(risk="low")).level == LOW
    verdict = evaluate(**docs, classification=_cls(risk="high"))
    assert verdict.level == ELEVATED
    # The docs-only note is a LOW explanation; it does not survive an elevation.
    assert verdict.reasons == ("classification risk tier high",)


def test_classification_reasons_is_empty_for_none_and_for_low():
    assert risk.classification_reasons(None) == ()
    assert risk.classification_reasons(_cls(risk="low")) == ()
    assert risk.classification_reasons(_cls(risk="medium")) == ()


# --------------------------------------------------------------------------- #
# GO-1: classify() shells out to the binary — absent / present / failing
# --------------------------------------------------------------------------- #


_LOW_ROW = {
    "labels": ["size:S", "area:config"],
    "verified": True,
    "verification_iterations": 0,
}

HIGH_PAYLOAD = {
    "risk": "high",
    "components": ["wallet"],
    "financial_paths_touched": True,
    "panel": {"seats": 5, "reduced": False},
    "gate_signals": [{"signal": "env-gate", "file": "src/app.py"}],
}

LOW_PAYLOAD = {"risk": "low", "panel": {"seats": 1, "reduced": True}}


def _fake_classify(tmp_path: Path, monkeypatch, script: str, *, executable=True) -> Path:
    """Install ``script`` as the ``classify`` binary via CLASSIFY_BIN."""
    bin_path = tmp_path / "bin" / "classify"
    bin_path.parent.mkdir(exist_ok=True)
    bin_path.write_text(script, encoding="utf-8")
    if executable:
        bin_path.chmod(0o755)
    monkeypatch.setenv("CLASSIFY_BIN", str(bin_path))
    assert classification.classify_binary() == str(bin_path)
    return bin_path


def _emitting(payload: dict, capture: Path | None = None) -> str:
    sink = f"cat > '{capture}'" if capture else "cat > /dev/null"
    return f"#!/bin/sh\n{sink}\nprintf '%s' '{json.dumps(payload)}'\n"


def test_classify_absent_binary_degrades_to_the_legacy_rules(git_repo: Path):
    """The conftest pin makes the binary ABSENT; that is the legacy path."""
    assert classification.classify_binary() is None
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})
    verdict = risk.classify(_LOW_ROW, git_repo, "main")
    assert verdict.level == LOW
    assert verdict.reasons == ()
    assert verdict.classification == "classification unavailable: classify binary absent"


def test_classify_present_binary_elevates_a_task_the_rules_call_low(
    git_repo: Path, tmp_path: Path, monkeypatch
):
    """The cheapest proof that a worktree can shell out to cmd/classify and
    parse the result: the diff reaches the binary, and its verdict lands."""
    received = tmp_path / "received.diff"
    _fake_classify(tmp_path, monkeypatch, _emitting(HIGH_PAYLOAD, received))
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})

    verdict = risk.classify(_LOW_ROW, git_repo, "main")

    assert verdict.level == ELEVATED
    joined = " | ".join(verdict.reasons)
    assert "classification risk tier high" in joined
    assert "financial path touched" in joined
    assert "env-gate" in joined
    # summary_line() is what the merge engine journals.
    assert verdict.classification == classification.parse_classification(HIGH_PAYLOAD).summary_line()
    assert verdict.classification == "risk=high components=wallet financial gate-signals=env-gate"
    diff = received.read_text(encoding="utf-8")
    assert "+++ b/src/app.py" in diff and "+one" in diff


def test_classify_present_low_classification_never_downgrades(
    git_repo: Path, tmp_path: Path, monkeypatch
):
    _fake_classify(tmp_path, monkeypatch, _emitting(LOW_PAYLOAD))
    _branch_with_changes(git_repo, {"internal/auth/token.py": "secret\n"})
    verdict = risk.classify(_LOW_ROW, git_repo, "main")
    assert verdict.level == ELEVATED
    assert any("**/auth/**" in r for r in verdict.reasons)
    assert verdict.classification == "risk=low"


def test_classify_present_low_classification_leaves_low_low(
    git_repo: Path, tmp_path: Path, monkeypatch
):
    _fake_classify(tmp_path, monkeypatch, _emitting(LOW_PAYLOAD))
    _branch_with_changes(git_repo, {"src/app.py": "one\n"})
    verdict = risk.classify(_LOW_ROW, git_repo, "main")
    assert verdict.level == LOW and verdict.reasons == ()
    assert verdict.classification == "risk=low"


@pytest.mark.parametrize(
    "script, executable, needle",
    [
        # non-zero exit (what a missing rule table produces)
        ("#!/bin/sh\ncat >/dev/null\necho 'no risk-paths config found' >&2\nexit 3\n",
         True, "classify exited 3: no risk-paths config found"),
        ("#!/bin/sh\ncat >/dev/null\nexit 1\n", True, "classify exited 1"),
        # unparsable JSON
        ("#!/bin/sh\ncat >/dev/null\necho 'not json at all'\n", True, "unusable output"),
        # exception while invoking: present-but-not-executable raises OSError
        ("#!/bin/sh\nexit 0\n", False, "classify invocation failed (PermissionError"),
    ],
)
def test_classify_present_but_failing_binary_fails_closed(
    git_repo: Path, tmp_path: Path, monkeypatch, script, executable, needle
):
    """A host that HAS the binary must not have a failure look like never
    having had it: ``low`` is auto-merge, so a crash is ``elevated`` — and it
    is a verdict, not an exception."""
    _fake_classify(tmp_path, monkeypatch, script, executable=executable)
    _branch_with_changes(git_repo, {"src/app.py": "one\n"})
    assert risk.classify(_LOW_ROW, git_repo, "main") is not None  # no raise
    verdict = risk.classify(_LOW_ROW, git_repo, "main")
    assert verdict.level == ELEVATED
    assert len(verdict.reasons) == 1
    assert verdict.reasons[0].startswith("classification failed with classify binary present: ")
    assert needle in verdict.reasons[0], verdict.reasons
    assert verdict.classification == verdict.reasons[0]


def test_classify_present_binary_raising_arbitrary_exception_fails_closed(
    git_repo: Path, tmp_path: Path, monkeypatch
):
    _fake_classify(tmp_path, monkeypatch, _emitting(LOW_PAYLOAD))
    _branch_with_changes(git_repo, {"src/app.py": "one\n"})

    def _boom(**_kw):
        raise RuntimeError("parser regression")

    monkeypatch.setattr(classification, "classify_diff_strict", _boom)
    verdict = risk.classify(_LOW_ROW, git_repo, "main")
    assert verdict.level == ELEVATED
    assert "parser regression" in verdict.reasons[0]


def test_classify_present_binary_is_not_invoked_on_an_empty_diff(
    git_repo: Path, tmp_path: Path, monkeypatch
):
    bin_path = _fake_classify(tmp_path, monkeypatch, "#!/bin/sh\nexit 1\n")
    verdict = risk.classify(_LOW_ROW, git_repo, "main", head_ref="main")
    assert verdict.classification == "classification skipped: empty diff"
    assert verdict.level == LOW
    assert bin_path.exists()


# --------------------------------------------------------------------------- #
# GO-1: TOCTOU — every read is pinned to SHAs resolved once
# --------------------------------------------------------------------------- #


def _sha(repo: Path, ref: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", ref], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def test_classify_reads_both_diffs_against_the_same_resolved_shas(
    git_repo: Path, tmp_path: Path, monkeypatch
):
    _fake_classify(tmp_path, monkeypatch, _emitting(LOW_PAYLOAD))
    _branch_with_changes(git_repo, {"src/app.py": "one\n"})
    base_sha, head_sha = _sha(git_repo, "main"), _sha(git_repo, "feat/x")
    assert base_sha != head_sha

    real_run = subprocess.run
    diff_specs: list[str] = []

    def _spy(argv, **kw):
        if argv[:2] == ["git", "diff"]:
            diff_specs.append(argv[-1])
        return real_run(argv, **kw)

    monkeypatch.setattr(risk.subprocess, "run", _spy)
    verdict = risk.classify(_LOW_ROW, git_repo, "main", head_ref="feat/x")

    assert verdict.level == LOW
    # numstat + unified: two reads, one spec, and it is SHAs, not names.
    assert len(diff_specs) == 2
    assert diff_specs == [f"{base_sha}...{head_sha}"] * 2


def test_classify_is_immune_to_the_branch_moving_between_reads(
    git_repo: Path, tmp_path: Path, monkeypatch
):
    """The branch gains a forbidden-path commit after the numstat read. Both
    the rules and cmd/classify must still describe the commit judged, so the
    verdict stays low and the binary never sees the auth file."""
    received = tmp_path / "received.diff"
    _fake_classify(tmp_path, monkeypatch, _emitting(LOW_PAYLOAD, received))
    _branch_with_changes(git_repo, {"src/app.py": "one\n"})
    judged = _sha(git_repo, "feat/x")

    real_run = subprocess.run
    state = {"diffs": 0}

    def _mover(argv, **kw):
        out = real_run(argv, **kw)
        if argv[:2] == ["git", "diff"]:
            state["diffs"] += 1
            if state["diffs"] == 1:
                p = git_repo / "internal" / "auth" / "token.py"
                p.parent.mkdir(parents=True)
                p.write_text("secret\n", encoding="utf-8")
                real_run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
                real_run(["git", "commit", "-q", "-m", "moved"], cwd=git_repo,
                         check=True, capture_output=True)
        return out

    monkeypatch.setattr(risk.subprocess, "run", _mover)
    verdict = risk.classify(_LOW_ROW, git_repo, "main")  # head_ref=HEAD

    assert _sha(git_repo, "feat/x") != judged  # the branch really moved
    assert verdict.level == LOW, verdict.reasons
    assert "internal/auth" not in received.read_text(encoding="utf-8")


def test_resolve_commit_fails_closed_on_a_bad_ref(git_repo: Path):
    with pytest.raises(risk.RiskDiffError, match="does not name a commit"):
        risk.resolve_commit(git_repo, "no-such-ref")
    assert len(risk.resolve_commit(git_repo, "main")) == 40
