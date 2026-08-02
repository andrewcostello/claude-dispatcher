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

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from claude_dispatcher import classification as cls_mod
from claude_dispatcher import risk
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


@pytest.mark.parametrize(
    "overrides, needle",
    [
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
    ],
)
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
# Path evidence from cmd/classify (GO-1)
#
# The contract under test is one-directional: a classification may raise a
# verdict to elevated and may never lower one to low, and an absent
# classification must leave today's verdict byte-for-byte alone. A classification
# that FAILED is a separate case with its own section further down — it elevates.
# --------------------------------------------------------------------------- #


LOW_CLASSIFICATION = cls_mod.Classification(risk="low")

# Each of the three signals the task names, in isolation.
ELEVATING_CLASSIFICATIONS = [
    (cls_mod.Classification(risk="high"), "path-derived risk tier high"),
    (cls_mod.Classification(risk="critical"), "path-derived risk tier critical"),
    (
        cls_mod.Classification(risk="low", financial_paths_touched=True),
        "financial path touched",
    ),
    (
        cls_mod.Classification(risk="low", gate_signals=("env-gate", "flag")),
        "gate/guard/flag signals in changed lines: env-gate, flag",
    ),
]


@pytest.mark.parametrize(
    "cls, needle", ELEVATING_CLASSIFICATIONS, ids=lambda v: getattr(v, "risk", v)
)
def test_elevated_classification_forces_elevated(cls, needle):
    """A task every existing rule calls low goes elevated on path evidence."""
    assert evaluate(**_low_kwargs()).level == LOW  # the rules alone say low

    verdict = evaluate(**_low_kwargs(), classification=cls)
    assert verdict.level == ELEVATED
    assert any(needle in r for r in verdict.reasons), verdict.reasons


@pytest.mark.parametrize(
    "overrides",
    [
        dict(size_label="XL", labels=["size:XL"]),
        dict(labels=["size:S", "financial"]),
        dict(changed_files=[_prod("internal/auth/token.go")]),
        dict(verified=False),
    ],
)
def test_low_classification_never_downgrades(overrides):
    """Path evidence is raise-only: a clean classification cannot clear a rule."""
    base = evaluate(**_low_kwargs(**overrides))
    assert base.level == ELEVATED

    verdict = evaluate(**_low_kwargs(**overrides), classification=LOW_CLASSIFICATION)
    assert verdict.level == ELEVATED
    assert verdict.reasons == base.reasons  # no reason dropped or rewritten


def test_low_classification_leaves_a_low_verdict_low():
    verdict = evaluate(**_low_kwargs(), classification=LOW_CLASSIFICATION)
    assert verdict.level == LOW
    assert verdict.reasons == ()
    # ...but the table that judged it is still on the record.
    assert verdict.classification_summary == "risk=low"


def test_docs_only_carve_out_is_raised_by_path_evidence():
    """docs-only is a statement about SIZE, not surface — path evidence outranks
    it in the raising direction, and both halves stay in the reasons."""
    docs = _low_kwargs(
        size_label="XL",
        labels=["size:XL"],
        changed_files=[_prod("docs/finance/wallet.md", 900, 200)],
    )
    assert evaluate(**docs).level == LOW  # carve-out, today

    verdict = evaluate(
        **docs,
        classification=cls_mod.Classification(risk="low", financial_paths_touched=True),
    )
    assert verdict.level == ELEVATED
    assert any("docs-only" in r for r in verdict.reasons)
    assert any("financial path touched" in r for r in verdict.reasons)


@pytest.mark.parametrize(
    "overrides",
    [
        dict(),                                                   # baseline low
        dict(size_label="M", labels=["size:M"]),
        dict(size_label=None, labels=["area:config"]),
        dict(labels=["size:S", "security"]),
        dict(changed_files=[_prod("db/migrations/001.sql")]),
        dict(changed_files=[_prod("src/big.py", 150, 60)]),
        dict(changed_files=[FileDiff("README.md", 400, 10)]),      # docs-only
        dict(verified=False),
        dict(verification_iterations=1),
    ],
)
def test_classification_none_reproduces_todays_verdict(overrides):
    """Passing no classification must be indistinguishable from not having the
    parameter at all — level, reasons and summary alike."""
    kwargs = _low_kwargs(**overrides)
    today = evaluate(**kwargs)
    assert evaluate(**kwargs, classification=None) == today
    assert today.classification_summary is None


def test_classify_consumes_the_binary_on_a_real_repo(git_repo: Path, classify_stub):
    """End-to-end: risk.classify shells out to cmd/classify, pipes the real diff,
    and folds the answer in."""
    classify_stub.install({
        "risk": "critical",
        "financial_paths_touched": True,
        "gate_signals": [{"signal": "env-gate"}],
    })
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})
    task_row = {"labels": ["size:S"], "verified": True, "verification_iterations": 0}

    verdict = risk.classify(task_row, git_repo, "main")

    assert verdict.level == ELEVATED
    assert any("path-derived risk tier critical" in r for r in verdict.reasons)
    assert verdict.classification_summary == "risk=critical financial gate-signals=env-gate"
    # The binary really received the unified diff, not a numstat or a path list.
    assert "diff --git a/src/app.py b/src/app.py" in classify_stub.stdin()


def test_classify_keeps_low_when_classification_is_clean(git_repo: Path, classify_stub):
    classify_stub.install({"risk": "medium"})  # below the high floor
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})
    task_row = {"labels": ["size:S"], "verified": True, "verification_iterations": 0}

    verdict = risk.classify(task_row, git_repo, "main")

    assert verdict.level == LOW
    assert verdict.classification_summary == "risk=medium"


# --------------------------------------------------------------------------- #
# Failing closed on a classification failure
#
# `low` on this seam means AUTO-MERGE WITHOUT HUMAN REVIEW. So the two ways a
# classification can go missing are not interchangeable: an absent binary
# degrades to the legacy rules, but a binary that was PRESENT and did not answer
# must elevate — otherwise a crashed binary, a broken rule table or a parser
# regression silently restores the weaker gating and a change self-approves.
# --------------------------------------------------------------------------- #


def test_classify_elevates_when_a_present_binary_exits_non_zero(
    git_repo: Path, classify_stub
):
    classify_stub.install({"risk": "low"}, exit_code=3)
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})
    task_row = {"labels": ["size:S"], "verified": True, "verification_iterations": 0}

    verdict = risk.classify(task_row, git_repo, "main")

    assert verdict.level == ELEVATED
    assert any("path classification failed" in r for r in verdict.reasons), (
        verdict.reasons
    )
    assert any("exited 3" in r for r in verdict.reasons), verdict.reasons
    # The failure is on the audit trail, distinguishable from "there was no table".
    assert verdict.classification_summary is not None
    assert verdict.classification_summary.startswith("unavailable:")


def test_classify_elevates_when_the_binary_emits_unparsable_output(
    git_repo: Path, classify_stub
):
    """Exit 0 with garbage on stdout — a parser regression, not a missing binary."""
    classify_stub.install()
    classify_stub.payload_path.write_text("not json at all", encoding="utf-8")
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})
    task_row = {"labels": ["size:S"], "verified": True, "verification_iterations": 0}

    verdict = risk.classify(task_row, git_repo, "main")

    assert verdict.level == ELEVATED
    assert any("unparsable JSON" in r for r in verdict.reasons), verdict.reasons


def test_classify_elevates_when_the_invocation_raises(
    git_repo: Path, classify_stub, monkeypatch
):
    """An exception anywhere under the shell-out is a failure, not a fallback —
    and it must not escape into the caller."""
    classify_stub.install({"risk": "low"})
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})
    task_row = {"labels": ["size:S"], "verified": True, "verification_iterations": 0}

    def _boom(**_kwargs):
        raise RuntimeError("classify blew up")

    monkeypatch.setattr(cls_mod, "classify_diff_result", _boom)

    verdict = risk.classify(task_row, git_repo, "main")

    assert verdict.level == ELEVATED
    assert any("classify blew up" in r for r in verdict.reasons), verdict.reasons


def test_classify_elevates_when_a_timeout_kills_the_binary(
    git_repo: Path, classify_stub, monkeypatch
):
    classify_stub.install({"risk": "low"})
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})
    task_row = {"labels": ["size:S"], "verified": True, "verification_iterations": 0}

    def _timeout(*_a, **_kw):
        raise subprocess.TimeoutExpired(cmd="classify", timeout=60)

    # Swap the module reference classification.py holds, NOT subprocess.run
    # itself — risk.py's git plumbing shares that module and would break too,
    # which would make this test pass down the wrong branch.
    monkeypatch.setattr(
        cls_mod,
        "subprocess",
        SimpleNamespace(run=_timeout, SubprocessError=subprocess.SubprocessError),
    )

    verdict = risk.classify(task_row, git_repo, "main")

    assert verdict.level == ELEVATED
    assert any("invocation failed" in r for r in verdict.reasons), verdict.reasons


def test_path_classification_fails_closed_on_a_bad_ref(git_repo: Path, classify_stub):
    """A git failure with the binary installed is a failure, not an absence: we
    were owed path evidence for this diff and did not get it."""
    classify_stub.install({"risk": "critical"})
    _branch_with_changes(git_repo, {"src/app.py": "one\n"})

    result = risk.path_classification(git_repo, "no-such-ref")

    assert result.failed
    assert result.classification is None
    assert "could not read the diff" in (result.detail or "")


def test_classify_without_the_binary_degrades_to_the_legacy_rules(git_repo: Path):
    """The conftest default (no CLASSIFY_BIN) is the no-binary production case:
    the expected state of a host without claude-workflow, so it degrades."""
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})
    task_row = {"labels": ["size:S"], "verified": True, "verification_iterations": 0}

    verdict = risk.classify(task_row, git_repo, "main")

    assert verdict == risk.RiskVerdict(LOW, ())
    assert verdict.classification_summary is None
    assert risk.path_classification(git_repo, "main").absent


def test_an_absent_result_leaves_the_rule_verdict_alone():
    absent = cls_mod.ClassifyResult(status=cls_mod.CLASSIFY_ABSENT, detail="no binary")
    assert evaluate(**_low_kwargs(), classification=absent) == evaluate(**_low_kwargs())


def test_an_empty_diff_result_is_not_a_failure():
    """Nothing to classify is not the same as failing to classify."""
    empty = cls_mod.ClassifyResult(status=cls_mod.CLASSIFY_EMPTY, detail="empty diff")
    assert evaluate(**_low_kwargs(), classification=empty).level == LOW


def test_a_failed_result_elevates_an_otherwise_low_verdict():
    failed = cls_mod.ClassifyResult(status=cls_mod.CLASSIFY_FAILED, detail="exit 3")
    verdict = evaluate(**_low_kwargs(), classification=failed)
    assert verdict.level == ELEVATED
    assert verdict.reasons == ("path classification failed: exit 3",)


def test_a_failed_result_keeps_the_existing_rule_reasons():
    failed = cls_mod.ClassifyResult(status=cls_mod.CLASSIFY_FAILED, detail="exit 3")
    kwargs = _low_kwargs(verified=False)
    base = evaluate(**kwargs)
    verdict = evaluate(**kwargs, classification=failed)
    assert verdict.level == ELEVATED
    assert verdict.reasons[: len(base.reasons)] == base.reasons


# --------------------------------------------------------------------------- #
# TOCTOU: both diff reads must describe the same commits
# --------------------------------------------------------------------------- #


def test_both_diff_reads_use_the_same_resolved_shas(
    git_repo: Path, classify_stub, monkeypatch
):
    """classify() resolves base and head ONCE; the numstat read and the unified
    diff read then reference those SHAs, not the mutable refs."""
    classify_stub.install({"risk": "low"})
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})
    task_row = {"labels": ["size:S"], "verified": True, "verification_iterations": 0}

    calls: list[tuple[str, str]] = []
    real = risk._git_diff

    def _spy(worktree, args, base_ref, head_ref):
        calls.append((base_ref, head_ref))
        return real(worktree, args, base_ref, head_ref)

    monkeypatch.setattr(risk, "_git_diff", _spy)
    risk.classify(task_row, git_repo, "main")

    assert len(calls) == 2, calls
    assert calls[0] == calls[1]
    for ref in calls[0]:
        assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), ref
    assert calls[0] == (
        risk.resolve_ref(git_repo, "main"),
        risk.resolve_ref(git_repo, "HEAD"),
    )


def test_a_branch_that_moves_mid_verdict_does_not_split_the_two_reads(
    git_repo: Path, classify_stub, monkeypatch
):
    """The regression itself: commit onto the branch between the numstat read and
    the classify read. The rules and cmd/classify must still see one commit."""
    classify_stub.install({"risk": "low"})
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n"})
    task_row = {"labels": ["size:S"], "verified": True, "verification_iterations": 0}

    real_collect = risk.collect_diff

    def _collect_then_move(worktree, base_ref, head_ref="HEAD"):
        files = real_collect(worktree, base_ref, head_ref)
        # A concurrent push/commit lands while we hold the numstat.
        (git_repo / "internal").mkdir(exist_ok=True)
        (git_repo / "internal" / "sneaky.py").write_text("late\n", encoding="utf-8")
        _git(["add", "."], git_repo)
        _git(["commit", "-q", "-m", "raced in"], git_repo)
        return files

    monkeypatch.setattr(risk, "collect_diff", _collect_then_move)
    risk.classify(task_row, git_repo, "main")

    piped = classify_stub.stdin()
    assert "diff --git a/src/app.py b/src/app.py" in piped
    assert "sneaky.py" not in piped


def test_resolve_ref_raises_for_an_unknown_ref(git_repo: Path):
    with pytest.raises(risk.RiskDiffError):
        risk.resolve_ref(git_repo, "no-such-ref")


def test_collect_raw_diff_is_untruncated_and_unified(git_repo: Path):
    _branch_with_changes(git_repo, {"src/app.py": "one\ntwo\n", "docs/x.md": "d\n"})
    diff = risk.collect_raw_diff(git_repo, "main")
    assert "diff --git a/src/app.py b/src/app.py" in diff
    assert "diff --git a/docs/x.md b/docs/x.md" in diff
    assert "+two" in diff


# --------------------------------------------------------------------------- #
# The classification boundary must not have a second binary lookup
# --------------------------------------------------------------------------- #


def test_path_classification_resolves_the_binary_once(monkeypatch, tmp_path):
    """Codex's GO-1 round-2 finding.

    path_classification() used to call classify_binary() as a preflight and
    then call classify_diff_result() WITHOUT the resolved path, causing a
    second lookup. Two lookups can disagree — a deployment swapping the binary
    between them, $CLASSIFY_BIN changing, a PATH edit — and the second one
    returning "absent" silently downgrades a FAILURE into a DEGRADATION, which
    is the exact fail-open this boundary exists to prevent.

    Asserts the resolved path is threaded through, so there is no second lookup
    to disagree with the first.
    """
    from claude_dispatcher import classification as classification_mod
    from claude_dispatcher import risk as risk_mod

    resolved = str(tmp_path / "classify")
    lookups: list[str] = []

    def _one_lookup() -> str:
        lookups.append("called")
        return resolved

    seen: dict[str, object] = {}

    def _fake_classify(*, diff, repo_root=None, config=None, binary=None,
                       timeout_seconds=60):
        seen["binary"] = binary
        return classification_mod.ClassifyResult(
            classification=classification_mod.parse_classification({"risk": "high"}),
            status=classification_mod.CLASSIFY_OK,
        )

    monkeypatch.setattr(classification_mod, "classify_binary", _one_lookup)
    monkeypatch.setattr(classification_mod, "classify_diff_result", _fake_classify)
    monkeypatch.setattr(risk_mod, "collect_raw_diff", lambda *a, **k: "diff --git a/x b/x\n")

    result = risk_mod.path_classification(tmp_path, "origin/main")

    assert result.status == classification_mod.CLASSIFY_OK
    assert seen["binary"] == resolved, (
        "the resolved binary path was not threaded through — classify_diff_result "
        "will look it up again and the two lookups can disagree"
    )
    assert len(lookups) == 1, f"binary resolved {len(lookups)} times, want exactly 1"
