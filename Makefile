# Makefile – project helper commands

# Run the test suite
.PHONY: test
test:
	PYTHONPATH=. ./venv/bin/pytest -q

# Run linting with ruff
.PHONY: lint
lint:
	./venv/bin/ruff check src tests

# Auto-format code with ruff (or black)
.PHONY: format
format:
	./venv/bin/ruff format src tests

# Build and start Docker services
.PHONY: up
up:
	docker compose up -d

# Stop Docker services
.PHONY: down
down:
	docker compose down

# Start the loopback-only API runtime
.PHONY: serve
serve:
	PYTHONPATH=. ./venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8000

# Install development dependencies (venv assumed)
.PHONY: install
install:
	python -m venv venv
	./venv/bin/pip install -r requirements.txt

# Run pre-commit hooks
.PHONY: precommit
precommit:
	pre-commit run --all-files
