FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml ./
RUN mkdir -p tdmcp && touch tdmcp/__init__.py
RUN pip install --no-cache-dir -e ".[web,all-databases]"

# Copy project files
COPY backend/ backend/
COPY tdmcp/ tdmcp/
COPY documentations/ documentations/

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
