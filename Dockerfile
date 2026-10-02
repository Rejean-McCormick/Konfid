# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH
WORKDIR /build
RUN python -m venv "$VIRTUAL_ENV"
COPY pyproject.toml README.md ./
COPY constraints ./constraints
COPY src ./src
RUN python -m pip install --upgrade "pip==26.2.1" "build==1.6.1" \
    && python -m build --wheel --outdir /dist \
    && WHEEL="$(ls /dist/*.whl)" \
    && python -m pip install -c constraints/production-linux.txt "${WHEEL}[postgres]" \
    && python -m pip uninstall -y pip setuptools wheel

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    HOME=/nonexistent
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
RUN addgroup --system --gid 10001 konfid \
    && adduser --system --uid 10001 --ingroup konfid --home /nonexistent --no-create-home konfid
COPY --chown=10001:10001 migrations ./migrations
COPY --chown=10001:10001 alembic.ini ./alembic.ini
USER 10001:10001
EXPOSE 8080
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/live', timeout=2).read()" || exit 1
CMD ["uvicorn","konfid.app:app","--host","0.0.0.0","--port","8080","--no-server-header","--workers","1","--http","h11","--h11-max-incomplete-event-size","65536","--limit-concurrency","1000","--backlog","2048","--timeout-keep-alive","5","--timeout-graceful-shutdown","30"]
