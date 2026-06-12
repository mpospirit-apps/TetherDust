FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies (gcc + libpq-dev for psycopg2)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install MCP server with SSE transport and all database drivers
COPY tetherdust/pyproject.toml tetherdust/
RUN pip install --no-cache-dir -e "./tetherdust[sse,all-databases]"

# Copy MCP server source
COPY tetherdust/ tetherdust/

COPY docker/mcp/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Run from tetherdust/ so `python -m mcp_server.server` resolves correctly
WORKDIR /app/tetherdust

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
