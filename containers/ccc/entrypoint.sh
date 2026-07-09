#!/bin/bash
set -e

# ccc reads its embedding config from ~/.cocoindex_code/global_settings.yml.
# It is baked into the image (see Dockerfile); this just guarantees it exists
# even if HOME differs at runtime.
mkdir -p "${HOME:-/root}/.cocoindex_code"
if [ ! -f "${HOME:-/root}/.cocoindex_code/global_settings.yml" ]; then
    cp /opt/ccc/global_settings.yml "${HOME:-/root}/.cocoindex_code/global_settings.yml"
fi

exec /opt/ccc-venv/bin/uvicorn ccc_api:app \
    --host 0.0.0.0 \
    --port "${CCC_API_PORT:-8004}" \
    --log-level "$(echo "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')"
