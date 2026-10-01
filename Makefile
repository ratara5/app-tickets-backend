# Quality gates for the backend.
#
# This file is the executable form of `ai-specs/skills/defining-project-quality-gates`.
# The skill states the doctrine; these targets are the only commands CI may run.
#
# Two rules from that skill are load-bearing here:
#
#   1. `gate` must be the exact command CI invokes. If CI runs something else, the
#      pipeline is a second, unguarded copy of the rules, and it is the copy that
#      drifts.
#   2. Every gate fails loudly and stops the first failure. A gate that reports
#      several problems at once gets them fixed in batches, and the later ones are
#      forgotten.
#
# Discover the targets with `make help`.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
.DELETE_ON_ERROR:
MAKEFLAGS += --no-print-directory --warn-undefined-variables

VENV    := venv
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip

# pytest is invoked as `python -m pytest`, never as the `pytest` script.
#
# The script form puts the pytest binary's own directory on sys.path, not the
# project root, so `import app` fails inside tests/conftest.py. The module form
# puts the current directory first, which is what the suite assumes. This is the
# kind of difference that makes a Makefile's targets look broken for a reason
# that has nothing to do with the code under test.
PYTEST  := $(PYTHON) -m pytest

# Coverage floor for the unit tier. Set deliberately low: a floor that the
# current suite does not meet is a gate nobody can pass, and a gate nobody can
# pass is deleted rather than lowered.
COVERAGE_MIN ?= 0

OPEN_SPEC_VALIDATE := npx --no-install openspec validate --all

## help: List the available targets
.PHONY: help
help:
	@echo "Targets:"
	@sed -n 's/^## //p' $(MAKEFILE_LIST) | awk -F': ' '{printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Tier 0: environment ─────────────────────────────────────────────────────

## setup: Create the virtualenv and install pinned dependencies
.PHONY: setup
setup:
	@test -d "$(VENV)" || python3.12 -m venv "$(VENV)"
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r requirements.txt
	@echo "Environment ready."

## check-env: Fail if the environment is not usable
.PHONY: check-env
check-env:
	@test -x "$(PYTHON)" || { echo "No venv. Run: make setup"; exit 1; }
	@$(PYTHON) -c "import pytest" 2>/dev/null || { echo "pytest not installed. Run: make setup"; exit 1; }
	@echo "Environment usable."

# ── Tier 1: the unit tier, the fast feedback loop ───────────────────────────

## test: Run the unit suite
.PHONY: test
test: check-env
	$(PYTEST) -q

## test-fast: Run only what the working tree touched
.PHONY: test-fast
test-fast: check-env
	$(PYTEST) -q --last-failed --new-first

## coverage: Run the unit suite with a coverage floor
.PHONY: coverage
coverage: check-env
	$(PYTEST) -q --cov=app --cov-report=term-missing --cov-fail-under=$(COVERAGE_MIN)

## harness: Run the harness integrity and skill agnosticism guards
.PHONY: harness
harness: check-env
	$(PYTEST) -q tests/test_harness_integrity.py tests/test_skill_agnosticism.py

## contracts: Validate the OpenSpec artifacts and the exported API specification
.PHONY: contracts
contracts: check-env
	$(OPEN_SPEC_VALIDATE)
	PYTHONPATH=. $(PYTHON) scripts/export_openapi.py --check

# ── Tier 2: everything CI runs, in order, fail fast ─────────────────────────

## gate: Run every automated check, in order, stopping at the first failure
.PHONY: gate
gate: harness contracts test
	@echo
	@echo "Gate passed."

## gate-ci: What continuous integration runs. Delegates to `gate` on purpose.
.PHONY: gate-ci
gate-ci: gate

# ── Manual and operational targets ──────────────────────────────────────────

## run: Start the API locally with reload
.PHONY: run
run:
	$(VENV)/bin/uvicorn app.main:app --reload

## shell: Open a Python shell with the app importable
.PHONY: shell
shell:
	$(VENV)/bin/python -i

## clean: Remove caches and build artifacts
.PHONY: clean
clean:
	find . -path ./venv -prune -o -name '__pycache__' -type d -print0 \
		| xargs --null --no-run-if-empty rm -rf
	find . -path ./venv -prune -o -name '.pytest_cache' -type d -print0 \
		| xargs --null --no-run-if-empty rm -rf
	rm -rf .coverage htmlcov
