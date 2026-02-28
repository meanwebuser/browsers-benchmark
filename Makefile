SHELL := /bin/bash

PYTHON ?= ./venv/bin/python
PID_FILE ?= .install_state/benchmark.pid
LOG_FILE ?= .install_state/benchmark.log

.PHONY: install test test-fast start status stop

install:
	./install.sh

test-fast:
	NUM_WORKERS_MAX=$${NUM_WORKERS_MAX:-10} $(PYTHON) -m pytest -v

test:
	RUN_ENGINE_TESTS=1 NUM_WORKERS_MAX=$${NUM_WORKERS_MAX:-10} $(PYTHON) -m pytest -v

start:
	@mkdir -p .install_state
	@if [[ -f "$(PID_FILE)" ]] && kill -0 "$$(cat "$(PID_FILE)")" 2>/dev/null; then \
		echo "Benchmark already running (pid $$(cat "$(PID_FILE)"))"; \
		exit 0; \
	fi
	@nohup $(PYTHON) main.py > "$(LOG_FILE)" 2>&1 & echo $$! > "$(PID_FILE)"
	@echo "Benchmark started (pid $$(cat "$(PID_FILE)"))"
	@echo "Log: $(LOG_FILE)"

status:
	@if [[ -f "$(PID_FILE)" ]] && kill -0 "$$(cat "$(PID_FILE)")" 2>/dev/null; then \
		echo "Benchmark running (pid $$(cat "$(PID_FILE)"))"; \
		echo "Log: $(LOG_FILE)"; \
	else \
		echo "Benchmark is not running"; \
		exit 1; \
	fi

stop:
	@{ \
		if [[ ! -f "$(PID_FILE)" ]]; then \
			echo "Benchmark is not running"; \
			exit 0; \
		fi; \
		PID="$$(cat "$(PID_FILE)")"; \
		if [[ -n "$$PID" ]] && kill -0 "$$PID" 2>/dev/null; then \
			kill "$$PID" 2>/dev/null || true; \
			sleep 1; \
			if kill -0 "$$PID" 2>/dev/null; then \
				kill -9 "$$PID" 2>/dev/null || true; \
			fi; \
			echo "Benchmark stopped (pid $$PID)"; \
		else \
			echo "Stale pid file found (pid $$PID)"; \
		fi; \
		rm -f "$(PID_FILE)"; \
	}
