FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# uv — copied from the official image, pinned. uv.lock is the single source of
# truth; `--locked` fails the build if it has drifted from pyproject.toml (the
# direct analogue of `npm ci` for the frontend).
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /uvx /bin/
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# Install dependencies first, without the project itself, so this layer is cached
# and only rebuilt when pyproject.toml / uv.lock change — not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --extra web --extra all-databases

# Copy project files
COPY backend/ backend/
COPY tdmcp/ tdmcp/
COPY sources/docs/ sources/docs/

# Product release version + per-version changelog. Read at runtime by the
# Version management tab (engine/version.py). These live at the repo root — outside
# the dev volume mount of web — so they must be copied explicitly.
COPY VERSION ./VERSION
COPY changelog/ changelog/

# Default agent system prompts read by the management when seeding a new or empty
# agent's system_prompt field (see management.views.agent._default_system_prompt_path).
# Only these two files are needed from containers/, not the rest of the build context.
COPY containers/codex/AGENTS.md containers/codex/AGENTS.md
COPY containers/claude/CLAUDE.md containers/claude/CLAUDE.md

# Install the project itself (tdmcp) against the already-resolved, locked deps.
RUN uv sync --locked --no-dev --extra web --extra all-databases

# Create static directory so collectstatic doesn't warn
RUN mkdir -p backend/static

# Collect static files into STATIC_ROOT for WhiteNoise to serve when DEBUG=False.
# Must succeed (no error swallowing) — a silent failure would leave production
# with no CSS/JS.
RUN DJANGO_SECRET_KEY=build-placeholder \
    python backend/manage.py collectstatic --noinput

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
