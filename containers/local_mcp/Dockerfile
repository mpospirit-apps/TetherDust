FROM node:22-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Python + pip + venv + curl (for uvx bootstrap)
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip python3-venv curl && \
    rm -rf /var/lib/apt/lists/*

# Install uv (provides uvx for running Python-based MCP servers)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Create isolated venv for the proxy service
RUN python3 -m venv /opt/local-mcp
RUN /opt/local-mcp/bin/pip install --no-cache-dir \
    "fastapi>=0.111.0" \
    "uvicorn[standard]>=0.27.0" \
    "mcp>=1.0.0" \
    "psycopg2-binary>=2.9.0" \
    "cryptography>=41.0.0"

COPY containers/local_mcp/local_mcp_api.py /app/local_mcp_api.py

EXPOSE 8003

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD /opt/local-mcp/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/healthz')" || exit 1

CMD ["/opt/local-mcp/bin/uvicorn", "local_mcp_api:app", "--host", "0.0.0.0", "--port", "8003"]
