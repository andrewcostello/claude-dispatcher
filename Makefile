# PR0 verification gates (classification→gating boundary).
#
# `make verify` runs PR0's boundary seals plus the doc lint with citations
# REQUIRED — the pre-push gate for boundary work. (The plan's per-PR seal
# tables cite individual test paths and revert-falsify commands; this target
# is the umbrella, not their replacement.)
# `make test` is the repo-wide mechanical gate — a thin alias for
# scripts/test.sh, the SAME script .dispatcher.yaml's test: command runs,
# so the two definitions cannot drift.

PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

.PHONY: verify verify-boundary verify-t26 test

verify: verify-boundary verify-t26

verify-boundary:
	PYTHONPATH=src $(PY) -m pytest tests/boundary -q

verify-t26:
	$(PY) tools/t26_lint.py

test:
	bash scripts/test.sh
