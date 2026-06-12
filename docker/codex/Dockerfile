FROM node:22-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python for the FastAPI wrapper
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

# Install Codex CLI globally (pinned — newer versions change JSONL event shape)
RUN npm install -g @openai/codex@0.114.0

# Create isolated venv for the FastAPI wrapper
RUN python3 -m venv /opt/codex-api
RUN /opt/codex-api/bin/pip install --no-cache-dir \
    "fastapi>=0.111.0" \
    "uvicorn[standard]>=0.27.0" \
    "httpx>=0.27.0"

# Per-request Codex homes (must not be under /tmp — Codex CLI refuses to
# create helper binaries under temporary directories, breaking MCP discovery)
RUN mkdir -p /opt/codex-homes

# Persistent live-credential home (backed by the codex-home volume at runtime).
# Holds the default config.toml + the refreshed auth.json. Credentials never
# touch /root.
RUN mkdir -p /var/codex-home/.codex

COPY docker/codex/AGENTS.md /app/AGENTS.md
COPY docker/codex/codex_api.py /app/codex_api.py
COPY docker/codex/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8002

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD /opt/codex-api/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/healthz')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
