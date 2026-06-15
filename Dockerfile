FROM python:3.12-slim

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
COPY tetherdust/ tetherdust/
COPY tdmcp/ tdmcp/
COPY documentations/ documentations/

# Product release version + per-version changelog. Read at runtime by the
# Version console tab (core/version.py). These live at the repo root — outside
# the dev volume mount of tetherdust/web — so they must be copied explicitly.
COPY VERSION ./VERSION
COPY changelog/ changelog/

# Default agent system prompts read by the console when seeding a new or empty
# agent's system_prompt field (see console.views.agent._default_system_prompt_path).
# Only these two files are needed from docker/, not the rest of the build context.
COPY docker/codex/AGENTS.md docker/codex/AGENTS.md
COPY docker/claude/CLAUDE.md docker/claude/CLAUDE.md

# Create static directory so collectstatic doesn't warn
RUN mkdir -p tetherdust/web/static

# Collect static files into STATIC_ROOT for WhiteNoise to serve when DEBUG=False.
# Must succeed (no error swallowing) — a silent failure would leave production
# with no CSS/JS.
RUN DJANGO_SECRET_KEY=build-placeholder \
    python tetherdust/web/manage.py collectstatic --noinput

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
