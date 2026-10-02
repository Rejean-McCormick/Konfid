from __future__ import annotations

import logging
import re
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api import router
from .adapters.http import close_http_clients
from .config import get_settings
from .db import database_ready, init_db
from .logging import configure_logging, request_id_var, tenant_var
from .metrics import HTTP_LATENCY, HTTP_REQUESTS
from .utils import new_id

log = logging.getLogger("konfid.api")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        try:
            content_length = int(headers.get(b"content-length", b"0") or b"0")
        except ValueError:
            content_length = 0
        if content_length > self.max_bytes:
            response = JSONResponse({"detail": "REQUEST_BODY_TOO_LARGE"}, status_code=413)
            return await response(scope, receive, send)

        chunks: list[bytes] = []
        total = 0
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.max_bytes:
                response = JSONResponse({"detail": "REQUEST_BODY_TOO_LARGE"}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(chunk)
            more = bool(message.get("more_body", False))
        body = b"".join(chunks)
        delivered = False

        async def replay_receive():
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        return await self.app(scope, replay_receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.dev_mode:
        init_db()
    else:
        ok, reason = database_ready()
        if not ok:
            raise RuntimeError(f"Konfid is not ready for production startup: {reason}")
    log.info("konfid_started", extra={"environment": s.env, "instance_id": s.instance_id, "version": s.version})
    try:
        yield
    finally:
        close_http_clients()
        log.info("konfid_stopped", extra={"instance_id": s.instance_id})


settings = get_settings()
configure_logging("INFO")
app = FastAPI(
    title="Konfid",
    version=settings.version,
    description="Cross-system security control plane",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)
app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)
if settings.trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-KONFID-ACTOR-TOKEN", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
app.include_router(router)


@app.middleware("http")
async def request_context_and_metrics(request: Request, call_next):
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if _REQUEST_ID_RE.fullmatch(incoming) else new_id("REQ")
    token = request_id_var.set(request_id)
    tenant_token = tenant_var.set(None)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled_request_error", extra={"method": request.method, "path": request.url.path})
        response = JSONResponse({"detail": "INTERNAL_ERROR", "request_id": request_id}, status_code=500)
    finally:
        tenant_var.reset(tenant_token)
        request_id_var.reset(token)
    route_obj = request.scope.get("route")
    route = getattr(route_obj, "path", "unmatched")
    HTTP_REQUESTS.labels(method=request.method, route=route, status=str(response.status_code)).inc()
    HTTP_LATENCY.labels(method=request.method, route=route).observe(time.perf_counter() - started)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not settings.dev_mode:
        response.headers["Strict-Transport-Security"] = f"max-age={settings.hsts_seconds}; includeSubDomains"
    return response


@app.get("/live", include_in_schema=False)
def live():
    return {"status": "alive"}


@app.get("/metrics", include_in_schema=False)
def metrics(request: Request):
    if not settings.metrics_enabled:
        raise HTTPException(404, "NOT_FOUND")
    required = settings.metrics_secret
    if required:
        supplied = request.headers.get("X-Metrics-Token", "")
        if not supplied or not secrets.compare_digest(supplied, required):
            raise HTTPException(401, "METRICS_AUTH_REQUIRED")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
