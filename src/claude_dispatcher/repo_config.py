"""Per-repo dispatcher config: load and validate `.dispatcher.yaml`.

A repo opts into dispatcher verification gates by placing a `.dispatcher.yaml`
at its root. Current schema is a single key — `test:`, the shell command run
inside a task worktree (exit 0 = green). Future sections (`e2e:`, `risk:`)
will arrive in later phases, so this loader tolerates unknown top-level keys
rather than rejecting them: a repo configured for a newer dispatcher must
still load under an older one. Unknown keys are reported via
`RepoConfig.unknown_keys` so callers can journal a note.

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
    when the file or key is absent. `unknown_keys` lists top-level keys this
    loader doesn't understand, sorted, for the caller to journal.
    """

    test: str | None
    unknown_keys: tuple[str, ...] = field(default=())


def load(repo_root: str | Path) -> RepoConfig:
    """Load `<repo_root>/.dispatcher.yaml` into a RepoConfig.

    Absent file → RepoConfig(test=None). Empty or comments-only file →
    test=None. Anything structurally wrong — non-mapping root, unparseable
    YAML, a `test:` value that is not a non-blank string — raises
    RepoConfigError.
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

    unknown = tuple(sorted(str(key) for key in doc if key != "test"))
    return RepoConfig(test=test, unknown_keys=unknown)
