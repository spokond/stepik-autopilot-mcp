PYPROJECT := pyproject.toml
SOURCE := src


.PHONY: all format lint typecheck test check


all: check


format:
	@echo "→ Formatting Python sources with ruff"
	@uv run ruff format --config $(PYPROJECT) .


lint:
	@echo "→ Running ruff"
	@uv run ruff check --fix --config $(PYPROJECT) .


typecheck:
	@echo "→ Running basedpyright"
	@uv run basedpyright $(SOURCE)


test:
	@echo "→ Running tests"
	@uv run pytest -sq


check: format lint typecheck test
	@echo "✓ All checks passed"
