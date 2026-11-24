# Visual Intelligence Engine — common tasks. No target removes data volumes.
SHELL := /bin/bash
TEST := docker compose -f docker-compose.yml -f docker-compose.test.yml --profile test
TEST_API := docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --no-build api >/dev/null && sleep 4

.PHONY: help install up down restart status logs pull-model lock samples test test-unit test-system \
        test-system-all test-e2e test-recovery test-persistence verify-isolation verify-offline verify backup restore

help:             ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}'

install:          ## INSTALL PHASE (Internet): build images, download models, generate samples
	@bash scripts/install.sh

up:               ## RUN PHASE (offline): start everything without pulling or building
	@bash scripts/start.sh

down:             ## Stop (data volumes are kept)
	@bash scripts/stop.sh

restart: down up  ## Restart the stack

status:           ## Services, health and resource usage
	@bash scripts/status.sh

logs:             ## Follow logs (S=service to filter)
	@docker compose logs -f --tail=100 $(S)

pull-model:       ## INSTALL PHASE: download another model, e.g. make pull-model MODEL=qwen3-vl:4b-instruct
	@test -n "$(MODEL)" || (echo "Use MODEL=<nombre>"; exit 1)
	@VIE_VLM_MODELS_TO_PULL=$(MODEL) docker compose --profile setup run --rm model-init && bash scripts/models-manifest.sh

lock:             ## Regenerate dependency lockfiles inside containers (needs Internet)
	@bash scripts/lock.sh

samples:          ## Regenerate synthetic sample documents
	@docker run --rm --user "$$(id -u):$$(id -g)" -v "$$PWD/examples/generated":/out vie/tests:1.0.0 python -m synthetic.generate --out /out --pdf --camera

test-unit:        ## Unit tests (backend, vision, frontend) in containers without network
	@docker build -q -f backend/Dockerfile --target test -t vie/backend:test . >/dev/null && docker run --rm --network none vie/backend:test
	@docker build -q -f services/vision/Dockerfile --target test -t vie/vision:test services/vision >/dev/null && docker run --rm --network none vie/vision:test
	@docker build -q --target test -t vie/frontend:test frontend >/dev/null && docker run --rm --network none vie/frontend:test

test-system:      ## System tests against the running stack (fast)
	@$(TEST_API)
	@$(TEST) run --rm --no-deps system-tests pytest -p no:cacheprovider -v system -m "not slow" --junitxml=/results/system-junit.xml

test-system-all:  ## System tests including the slow ones that use the model
	@$(TEST_API)
	@$(TEST) run --rm --no-deps system-tests pytest -p no:cacheprovider -v system --junitxml=/results/system-all-junit.xml

test-e2e:         ## Browser end-to-end tests (Playwright, simulated camera)
	@$(TEST_API)
	@$(TEST) run --rm --no-deps e2e

test-recovery:    ## Failure-recovery tests (stops/kills containers on purpose)
	@bash scripts/test-recovery.sh

test-persistence: ## Restart the stack and verify that data survives
	@bash scripts/test-persistence.sh

verify-isolation: ## Container hardening and network isolation checks
	@bash scripts/verify-isolation.sh

verify-offline:   ## No Internet access at runtime + full pipeline still works
	@bash scripts/verify-offline.sh

verify: verify-isolation verify-offline ## All verifications

test: test-unit test-system test-e2e ## Main test suites

backup:           ## Backup database and files to data/backups (ARGS=--with-models to include models)
	@bash scripts/backup.sh $(ARGS)

restore:          ## Restore a backup: make restore BACKUP=data/backups/vie-AAAAMMDD-HHMMSS
	@bash scripts/restore.sh $(BACKUP)
