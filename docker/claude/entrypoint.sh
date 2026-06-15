#!/bin/bash
set -e

# Claude Code is configured per request (MCP config + OAuth token are passed on
# each /chat call), so there is no config file to write at startup.
echo "Claude Code gateway starting (MCP default url = ${MCP_URL:-http://tdmcp:8001/mcp})"

exec /opt/claude-api/bin/uvicorn claude_api:app \
    --host 0.0.0.0 \
    --port "${CLAUDE_API_PORT:-8002}" \
    --log-level "$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')"
