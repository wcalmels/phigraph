FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PHIGRAPH_ENV=staging \
    PHIGRAPH_SHADOW_ONLY=true \
    PHIGRAPH_REAL_CONNECTORS_ENABLED=false \
    PHIGRAPH_DATA_DIR=/app/data \
    PHIGRAPH_DATABASE_URL=sqlite:////app/data/phigraph.db

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir ".[api,benchmark,auth]"

RUN useradd --create-home --uid 10001 phigraph \
    && mkdir -p /app/data \
    && chown -R phigraph:phigraph /app

USER phigraph

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["phigraph-api"]
