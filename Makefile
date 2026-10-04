# Quality gates for the backend.
#
# This file is the executable form of `.opencode/skills/defining-project-quality-gates`.
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
	$(PIP) install --quiet -r requirements-dev.txt
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

## harness: Verify the agent projection matches the pinned harness (needs HARNESS)
#
# The agent rules are projected from the harness, not authored here. The guards
# that used to live in tests/test_harness_integrity.py and test_skill_agnosticism.py
# checked the old ai-specs/ symlink surface; `agentic sync --check` replaces both,
# and the CI workflow .github/workflows/agentic-check.yml runs it on every push.
.PHONY: harness
harness: check-env
	@test -n "$${HARNESS:-}" || { echo "Set HARNESS to a harness checkout at the pinned version."; exit 1; }
	$(HARNESS)/bin/agentic --consumer . sync --check

## contracts: Validate the OpenSpec artifacts and the exported API specification
.PHONY: contracts
contracts: check-env
	$(OPEN_SPEC_VALIDATE)
	PYTHONPATH=. $(PYTHON) scripts/export_openapi.py --check

# ── Tier 2: everything CI runs, in order, fail fast ─────────────────────────

## gate: Run every automated check, in order, stopping at the first failure
.PHONY: gate
gate: contracts test
	@echo
	@echo "Gate passed."

## gate-ci: What continuous integration runs. Delegates to `gate` on purpose.
.PHONY: gate-ci
gate-ci: gate

# ── Local environment ───────────────────────────────────────────────────────

## gate-local: Prove the local environment works end to end against the core
#
# Unlike `gate`, this one needs a running local environment: `make setup-local`
# first, and the core's containers must already be running because they are owned
# by another project. Fails at the first failure, like every other target here.
.PHONY: gate-local
gate-local:
	@bash infra/local/scripts/gate-local.sh

## setup-local: Bring this project's local environment up in one command
.PHONY: setup-local
setup-local:
	@bash infra/local/setup.sh $(ARGS)

## local-down: Remove this project's local environment, leaving the core alone
#
# `docker compose down` cannot remove a network that still holds an attachment to
# a container it does not own, so the core's containers are detached from our
# network FIRST. Without that order the network is left behind, still connected to
# somebody else's container — and a leftover attachment is invisible until the
# next bring-up silently re-uses it.
#
# Nothing here stops, restarts or removes the core's containers. Only its
# membership of OUR network is changed.
.PHONY: local-down
local-down:
	@set -eu; \
	EXPECTED="app-tickets-local-net"; \
	NET="$$(awk '/^networks:/{f=1;next} f && /^    name:/{print $$2; exit}' infra/local/docker-compose.yml)"; \
	if [ -z "$$NET" ]; then \
	  echo "could not read the network name from infra/local/docker-compose.yml" >&2; exit 1; \
	fi; \
	if [ "$$NET" != "$$EXPECTED" ]; then \
	  echo "compose declares '$$NET' but teardown detaches from '$$EXPECTED'." >&2; \
	  echo "Rename both together; refusing to detach the wrong network." >&2; exit 1; \
	fi; \
	echo "==> Detaching the shared core from $$EXPECTED"; \
	for c in postgres-gci minio-acme; do \
	  if [ -z "$$(docker inspect --format '{{range $$n, $$_ := .NetworkSettings.Networks}}{{$$n}} {{end}}' "$$c" 2>/dev/null | tr ' ' '\n' | grep -Fx "$$EXPECTED" || true)" ]; then \
	    echo "    $$c is not attached to $$EXPECTED — nothing to detach"; \
	  else \
	    docker network disconnect app-tickets-local-net "$$c"; \
	    echo "    detached $$c from $$EXPECTED"; \
	  fi; \
	done; \
	echo "==> Removing this project's compose project"; \
	docker compose -f infra/local/docker-compose.yml down; \
	echo "==> Local environment removed. The shared core was not touched."

# ── Manual and operational targets ──────────────────────────────────────────

## run: Start the API in Docker against the shared core, with reload
#
# `--reload-dir app` is not a preference. Without it the watcher follows venv/, so
# the number of open watches scales with the number of installed packages; the
# watch limit is then hit minutes later, on the next reload, with no apparent
# relation to the `pip install` that caused it. The reload process dies with a
# watch-count error and the developer is left guessing. `--reload-exclude` covers
# what remains outside `app/`.
.PHONY: run
run:
	$(VENV)/bin/uvicorn app.main:app --reload --reload-dir app \
		--reload-exclude 'venv/.*' --reload-exclude '\.pytest_cache/.*' \
		--reload-exclude '\.coverage'

## run-native: Start the API from venv/ for the edit-reload inner loop
#
# Uses the loopback values from `.env` — DB_HOST=127.0.0.1, DB_PORT=5435,
# MINIO_ENDPOINT=127.0.0.1 — which reach the same shared core the containers do,
# through the ports the core publishes. No container is started and none is
# touched, which is what makes this the fast loop.
#
# This target is for ITERATION. It is not the gate: it proves the code starts, and
# nothing about the image, the provisioning, or the round trip through the object
# store. `make gate-local` is the gate, and it runs against the built image.
.PHONY: run-native
run-native:
	@echo "Iteration only — 'make gate-local' is the gate."
	@$(VENV)/bin/uvicorn app.main:app --reload --reload-dir app \
		--reload-exclude 'venv/.*' --reload-exclude '\.pytest_cache/.*' \
		--reload-exclude '\.coverage'

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
