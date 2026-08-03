# PR0 verification gate (classification→gating boundary, implementation
# plan §2): the boundary seals + the design doc's own lint. `make verify`
# is the command the plan's per-PR seal tables reference.

PY ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

.PHONY: verify verify-boundary verify-t26 test

verify: verify-boundary verify-t26

verify-boundary:
	PYTHONPATH=src $(PY) -m pytest tests/boundary -q

verify-t26:
	$(PY) tools/t26_lint.py

# Full suite (what .dispatcher.yaml's test: command runs).
test:
	PYTHONPATH=src $(PY) -m pytest tests/ -q
	$(PY) tools/t26_lint.py
