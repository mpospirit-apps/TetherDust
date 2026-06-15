#!/bin/bash
set -e

# Write the default (unrestricted) Codex MCP config at runtime into the
# persistent credential home so MCP_URL can be injected via env. Credentials
# live here (on the codex-home volume), never under /root.
MCP_URL="${MCP_URL:-http://tdmcp:8001/mcp}"
CODEX_HOME_DIR="${CODEX_HOME_DIR:-/var/codex-home/.codex}"
mkdir -p "${CODEX_HOME_DIR}"
cat > "${CODEX_HOME_DIR}/config.toml" <<EOF
[mcp_servers.tetherdust]
url = "${MCP_URL}"
EOF

echo "Codex MCP config written: ${CODEX_HOME_DIR}/config.toml (url = ${MCP_URL})"

exec /opt/codex-api/bin/uvicorn codex_api:app \
    --host 0.0.0.0 \
    --port "${CODEX_API_PORT:-8002}" \
    --log-level "$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')"
