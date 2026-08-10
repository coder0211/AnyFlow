.PHONY: install test lint check demo

install:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .

check: lint test