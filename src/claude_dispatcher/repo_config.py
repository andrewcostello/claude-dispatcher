"""Per-repo dispatcher config: load and validate `.dispatcher.yaml`.

A repo opts into dispatcher verification gates by placing a `.dispatcher.yaml`
at its root. Current schema:

  * `test:` — the shell command run inside a task worktree (exit 0 = green).
  * `panel:` — cross-family panel options. Its only known key today is
    `advisory:`, a list of advisory (probationary, non-blocking) reviewer
    family names — e.g. ``panel: {advisory: [grok]}`` — consumed by the
    orchestrator's cross-family panel.

Future sections (`e2e:`, `risk:`) will arrive in later phases, so this
loader tolerates unknown top-level keys rather than rejecting them: a repo
configured for a newer dispatcher must still load under an older one.
Unknown keys are reported via `RepoConfig.unknown_keys` so callers can
journal a note; unknown keys nested inside `panel:` are reported there as
``panel.<key>``.

The loader is read-only and goes through yaml_io's round-trip mode, so any
future writer inherits comment/ordering preservation for free. An absent
file is not an error — the caller journals that mechanical tests are
skipped; notes flow through return values, never logging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml.error import YAMLError

from claude_dispatcher import yaml_io

CONFIG_FILENAME = ".dispatcher.yaml"


class RepoConfigError(ValueError):
    """Raised when .dispatcher.yaml exists but is malformed or invalid.

    The message always includes the config file path so the failure is
    diagnosable from the journal alone.
    """


@dataclass(frozen=True)
class RepoConfig:
    """Parsed per-repo dispatcher configuration.

    `test` is the verification command verbatim (never stripped), or None
    when the file or key is absent. `panel_advisory` is the tuple of
    advisory reviewer family names from `panel.advisory` (empty when the
    file, the `panel` key, or the `advisory` key is absent). `unknown_keys`
    lists keys this loader doesn't understand — top-level keys verbatim,
    keys nested under `panel` as ``panel.<key>`` — sorted, for the caller
    to journal.
    """

    test: str | None
    unknown_keys: tuple[str, ...] = field(default=())
    panel_advisory: tuple[str, ...] = ()
    # Repo-default integration mode (PRF-1): "branch" (today's behavior) or
    # "pr" (run-level feature branch + auto PRs). None when the key is absent
    # — the orchestrator then falls back to the built-in "branch" default. The
    # `dispatcher run --integration` CLI flag always wins over this.
    integration: str | None = None


def load(repo_root: str | Path) -> RepoConfig:
    """Load `<repo_root>/.dispatcher.yaml` into a RepoConfig.

    Absent file → RepoConfig(test=None). Empty or comments-only file →
    test=None. Anything structurally wrong — non-mapping root, unparseable
    YAML, a `test:` value that is not a non-blank string, a `panel:` value
    that is not a mapping, a `panel.advisory` that is not a list of
    non-empty strings — raises RepoConfigError.
    """
    path = Path(repo_root) / CONFIG_FILENAME
    if not path.exists():
        return RepoConfig(test=None)

    try:
        doc = yaml_io.load(path)
    except YAMLError as exc:
        raise RepoConfigError(f"malformed YAML in {path}: {exc}") from exc

    if doc is None:  # empty or comments-only document
        return RepoConfig(test=None)
    if not isinstance(doc, dict):
        raise RepoConfigError(
            f"root of {path} must be a mapping, got {type(doc).__name__}"
        )

    test = doc.get("test")
    if "test" in doc:
        # Strict on purpose: a bool/int/list here means the YAML didn't say
        # what the author thought it said, and silently skipping the gate
        # would defeat its purpose. Note bool is not a str subclass, so bare
        # `true` is rejected by the isinstance check like any other non-str.
        if not isinstance(test, str) or not test.strip():
            raise RepoConfigError(
                f"'test' in {path} must be a non-empty string command, "
                f"got {test!r}"
            )

    panel_advisory: tuple[str, ...] = ()
    panel_unknown: list[str] = []
    if "panel" in doc:
        panel = doc.get("panel")
        if not isinstance(panel, dict):
            raise RepoConfigError(
                f"'panel' in {path} must be a mapping, "
                f"got {type(panel).__name__}"
            )
        if "advisory" in panel:
            advisory = panel.get("advisory")
            if not isinstance(advisory, list):
                raise RepoConfigError(
                    f"'panel.advisory' in {path} must be a list of reviewer "
                    f"names, got {advisory!r}"
                )
            for entry in advisory:
                # Same strictness rationale as `test:` — and bool is not a
                # str subclass, so a bare `true` entry is rejected too.
                if not isinstance(entry, str) or not entry.strip():
                    raise RepoConfigError(
                        f"entries of 'panel.advisory' in {path} must be "
                        f"non-empty strings, got {entry!r}"
                    )
            panel_advisory = tuple(advisory)
        # Unknown keys INSIDE panel are tolerated (same forward-compat
        # stance as the top level) and reported as "panel.<key>".
        panel_unknown = [
            f"panel.{key}" for key in panel if key != "advisory"
        ]

    integration: str | None = None
    if "integration" in doc:
        integration = doc.get("integration")
        # Strict, same rationale as `test:`: an unrecognized value here means
        # the repo asked for a mode the dispatcher doesn't have, and silently
        # falling back to "branch" would hide that. bool is not a str subclass,
        # so bare `true` is rejected by the membership check.
        if integration not in ("branch", "pr"):
            raise RepoConfigError(
                f"'integration' in {path} must be 'branch' or 'pr', "
                f"got {integration!r}"
            )

    known_top_level = ("test", "panel", "integration")
    unknown = tuple(sorted(
        [str(key) for key in doc if key not in known_top_level]
        + panel_unknown
    ))
    return RepoConfig(
        test=test,
        unknown_keys=unknown,
        panel_advisory=panel_advisory,
        integration=integration,
    )
