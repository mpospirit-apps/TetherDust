# Contributing to TetherDust

Thanks for your interest in contributing. This guide covers bug fixes, new features, new database drivers, and documentation improvements.

## Getting started

```bash
git clone https://github.com/<your-fork>/TetherDust.git
cd TetherDust

# Run the full stack
docker compose up --build
```

For local linting and testing without Docker:

```bash
pip install -e ".[all-databases,web,dev]"
```

## What I accept

| Type | Notes |
|---|---|
| **Bug fixes** | Always welcome. Link the issue in your PR. |
| **New features** | Open an issue first to align on scope before writing code. |
| **New database drivers** | See [Adding a database driver](#adding-a-database-driver) below. |
| **Documentation** | Fixes, clarifications, and examples are always appreciated. |

## Workflow

1. Fork the repo and create a branch from `main`.
2. Make your changes.
3. Run the checks locally (see below) — CI will enforce these on your PR.
4. Add a changelog entry in `changelog/` if your change is user-visible.
5. Open a pull request against `main`.

## Checks (must pass)

```bash
# Lint
ruff check tetherdust/ docker/

# Format
ruff format tetherdust/ docker/

# Type check
mypy tetherdust/ docker/

# Tests
pytest tetherdust/tests/
```

### Pre-commit hooks

Install the hooks once so ruff lint/format runs automatically on every commit:

```bash
pip install pre-commit
pre-commit install
```

Run them against the whole repo at any time:

```bash
pre-commit run --all-files
```

The hooks cover lint, format, and basic file hygiene. Type checking (`mypy`) and the test suite (`pytest`) are **not** in the hooks — run those manually before pushing; CI enforces them on every PR.

## Adding a database driver

TetherDust uses SQLAlchemy for all database connections. To add support for a new engine:

1. Add the driver as an optional dependency in `pyproject.toml` (e.g. `snowflake = ["snowflake-sqlalchemy>=..."]`).
2. Add the engine to the `engine` choices in `web/core/models/connections.py`.
3. Verify the SQL validator in `mcp_server/utils/db_service.py` handles the new dialect (SQLGlot dialect name).
4. Add the driver to `all-databases` extras so CI installs it.
5. Test against a real instance and include a note in your PR about what was tested.

## Changelog

Every user-visible change needs an entry. Add or update `changelog/<version>.md` (use the next version if unreleased). The format is free-form Markdown.

## Code style

- Line length: 100
- Python 3.11+
- `ruff` enforces formatting and linting; `mypy --strict` enforces types.
- No comments that describe *what* the code does — only *why* when it's non-obvious.

## Questions?

Open a [GitHub Discussion](../../discussions) or file an issue.
