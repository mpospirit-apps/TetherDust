FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies (gcc + libpq-dev for psycopg2)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install MCP server with SSE transport and all database drivers
COPY pyproject.toml ./
RUN mkdir -p tdmcp && touch tdmcp/__init__.py
RUN pip install --no-cache-dir -e ".[sse,all-databases]"

# Copy MCP server source
COPY tdmcp/ tdmcp/

COPY docker/tdmcp/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Run from /app so `python -m tdmcp.server` resolves correctly
WORKDIR /app

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/healthz')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
