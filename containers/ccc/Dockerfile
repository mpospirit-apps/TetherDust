FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/root \
    PATH="/opt/ccc-venv/bin:${PATH}"

WORKDIR /app

# git: ccc reads .gitignore files when walking a project. build tools kept minimal.
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/ccc-venv

# CPU-only torch first (avoids pulling the large CUDA stack), then the rest.
RUN /opt/ccc-venv/bin/pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu torch && \
    /opt/ccc-venv/bin/pip install --no-cache-dir \
        "cocoindex-code==0.2.31" \
        "sentence-transformers>=2.7.0" \
        "fastapi>=0.111.0" \
        "uvicorn[standard]>=0.27.0" \
        "httpx>=0.27.0"

# Fix the embedding config so `ccc init`/`ccc index` never prompt, then bake the
# model weights into the image so the service works offline at runtime.
COPY containers/ccc/global_settings.yml /opt/ccc/global_settings.yml
RUN mkdir -p /root/.cocoindex_code && \
    cp /opt/ccc/global_settings.yml /root/.cocoindex_code/global_settings.yml && \
    /opt/ccc-venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('Snowflake/snowflake-arctic-embed-xs')"

COPY containers/ccc/ccc_api.py /app/ccc_api.py
COPY containers/ccc/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8004

HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=3 \
    CMD /opt/ccc-venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/healthz')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
