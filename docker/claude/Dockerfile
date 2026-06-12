FROM node:26-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Python for the FastAPI wrapper
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

# Install the Claude Code CLI globally (pinned — newer versions can change the
# stream-json event shape and the `setup-token` login I/O this wrapper parses).
# 2.1.153 is the npm `stable` dist-tag at time of writing. Bump deliberately
# after re-verifying claude_api.py against the new version.
RUN npm install -g @anthropic-ai/claude-code@2.1.153

# Isolated venv for the FastAPI wrapper
RUN python3 -m venv /opt/claude-api
RUN /opt/claude-api/bin/pip install --no-cache-dir \
    "fastapi>=0.111.0" \
    "uvicorn[standard]>=0.27.0" \
    "httpx>=0.27.0"

# Writable CLI config/home + a neutral empty working dir (never /root).
RUN mkdir -p /var/claude-home/.claude /var/claude-home/work

COPY docker/claude/CLAUDE.md /app/CLAUDE.md
COPY docker/claude/claude_api.py /app/claude_api.py
COPY docker/claude/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8002

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD /opt/claude-api/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/healthz')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
