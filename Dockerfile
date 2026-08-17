FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PHIGRAPH_ENV=production \
    PHIGRAPH_SHADOW_ONLY=true \
    PHIGRAPH_REAL_CONNECTORS_ENABLED=false \
    PHIGRAPH_DATA_DIR=/app/data

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# CACHE_BUST: bump when forcing Railway to rebuild pip layer (sklearn / __init__ fixes).
ARG CACHE_BUST=20260729-sklearn
RUN pip install --no-cache-dir ".[api,postgres,benchmark]"

RUN useradd --create-home --uid 10001 phigraph \
    && mkdir -p /app/data \
    && chown -R phigraph:phigraph /app

USER phigraph

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; port=os.getenv('PHIGRAPH_PORT') or os.getenv('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health/live', timeout=3)"

CMD ["phigraph-api"]
