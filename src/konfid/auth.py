from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import ssl
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request
from jwt import PyJWKClient

from .config import get_settings
from .logging import tenant_var
from .rate_limit import check_rate_limit

MAX_TOKEN_BYTES = 16_384
MAX_SCOPES = 64


@dataclass(frozen=True)
class CallerContext:
    service: str
    tenant: str
    scopes: frozenset[str]
    token_id: str | None = None
    issued_at: int | None = None
    expires_at: int | None = None


@lru_cache(maxsize=16)
def _jwk_client(url: str, ca_bundle: str | None) -> PyJWKClient:
    context = ssl.create_default_context(cafile=ca_bundle) if ca_bundle else ssl.create_default_context()
    return PyJWKClient(url, cache_keys=True, cache_jwk_set=True, lifespan=300, timeout=5, ssl_context=context)


def _decode(
    token: str,
    *,
    issuer: str,
    audience: str,
    jwks_url: str | None,
    algorithms: list[str],
    max_ttl_seconds: int,
):
    s = get_settings()
    if len(token.encode()) > MAX_TOKEN_BYTES:
        raise HTTPException(401, "TOKEN_TOO_LARGE")
    try:
        if s.dev_mode and not jwks_url:
            claims = jwt.decode(
                token,
                s.dev_signing_secret,
                algorithms=["HS256"],
                issuer=issuer,
                audience=audience,
                leeway=s.jwt_clock_skew_seconds,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        else:
            if not jwks_url:
                raise HTTPException(503, "JWKS_NOT_CONFIGURED")
            key = _jwk_client(jwks_url, s.outbound_ca_bundle).get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                issuer=issuer,
                audience=audience,
                leeway=s.jwt_clock_skew_seconds,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        iat = int(claims["iat"])
        exp = int(claims["exp"])
        now = int(datetime.now(timezone.utc).timestamp())
        effective_max_ttl = max_ttl_seconds if not s.dev_mode else max(max_ttl_seconds, 86400)
        if exp <= iat or exp - iat > effective_max_ttl:
            raise HTTPException(401, "TOKEN_TTL_INVALID")
        if iat > now + s.jwt_clock_skew_seconds:
            raise HTTPException(401, "TOKEN_IAT_IN_FUTURE")
        return claims
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(401, "INVALID_TOKEN") from exc


def caller_context(request: Request, authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "MISSING_WORKLOAD_TOKEN")
    s = get_settings()
    c = _decode(
        authorization[7:],
        issuer=s.workload_issuer,
        audience=s.workload_audience,
        jwks_url=s.workload_jwks_url,
        algorithms=s.workload_algorithms,
        max_ttl_seconds=s.workload_max_token_ttl_seconds,
    )
    service, tenant = c.get("sub"), c.get("tenant")
    raw = c.get("scope", [])
    scopes = raw.split() if isinstance(raw, str) else raw
    if not service or not tenant or not isinstance(scopes, list):
        raise HTTPException(401, "INVALID_WORKLOAD_IDENTITY")
    if len(scopes) > MAX_SCOPES or any(not isinstance(x, str) or len(x) > 128 for x in scopes):
        raise HTTPException(401, "INVALID_WORKLOAD_SCOPES")
    if not s.dev_mode:
        if "konfid:*" in scopes:
            raise HTTPException(403, "WILDCARD_SCOPE_FORBIDDEN")
        if not c.get("jti"):
            raise HTTPException(401, "WORKLOAD_JTI_REQUIRED")
    # Rate-limit by the canonical route template, not the concrete URL path.
    # Otherwise an attacker could rotate resource IDs (/responses/A, /responses/B, ...)
    # and obtain a fresh bucket for every object. FastAPI has already matched the
    # route before dependencies execute, so the route template is available here.
    route_obj = request.scope.get("route")
    route_key = getattr(route_obj, "path", None) or request.url.path
    check_rate_limit(str(service), str(tenant), str(route_key))
    tenant_var.set(str(tenant))
    return CallerContext(
        str(service), str(tenant), frozenset(scopes), c.get("jti"), int(c["iat"]), int(c["exp"])
    )


def require_scope(required: str):
    def dep(ctx: Annotated[CallerContext, Depends(caller_context)]):
        if required not in ctx.scopes and "konfid:*" not in ctx.scopes:
            raise HTTPException(403, "CALLER_SCOPE_DENIED")
        return ctx
    return dep


def verify_actor_assertion(token: str | None, *, expected_tenant: str, expected_principal: str | None, expected_caller: str | None = None):
    s = get_settings()
    if not token:
        if s.require_actor_assertion:
            raise HTTPException(401, "ACTOR_ASSERTION_REQUIRED")
        return None
    c = _decode(
        token,
        issuer=s.actor_issuer,
        audience=s.actor_audience,
        jwks_url=s.actor_jwks_url,
        algorithms=s.actor_algorithms,
        max_ttl_seconds=s.actor_max_token_ttl_seconds,
    )
    if c.get("tenant") != expected_tenant or (expected_principal is not None and c.get("sub") != expected_principal):
        raise HTTPException(403, "ACTOR_ASSERTION_MISMATCH")
    if not s.dev_mode:
        if "assurance" not in c or "auth_time" not in c:
            raise HTTPException(401, "ACTOR_ASSURANCE_CLAIMS_REQUIRED")
        if not c.get("jti"):
            raise HTTPException(401, "ACTOR_JTI_REQUIRED")
        if s.require_actor_authorized_party:
            authorized_party = c.get("azp") or c.get("client_id")
            if not expected_caller or authorized_party != expected_caller:
                raise HTTPException(403, "ACTOR_AUTHORIZED_PARTY_MISMATCH")
    if "auth_time" in c:
        try:
            auth_time = int(c["auth_time"])
        except Exception as exc:
            raise HTTPException(401, "ACTOR_AUTH_TIME_INVALID") from exc
        now = int(datetime.now(timezone.utc).timestamp())
        if auth_time > now + s.jwt_clock_skew_seconds:
            raise HTTPException(401, "ACTOR_AUTH_TIME_IN_FUTURE")
    return c


def make_dev_token(
    subject: str,
    tenant: str,
    scopes: list[str],
    ttl_seconds: int = 3600,
    *,
    actor: bool = False,
    extra: dict | None = None,
):
    s = get_settings()
    now = int(datetime.now(timezone.utc).timestamp())
    claims = {
        "sub": subject,
        "tenant": tenant,
        "scope": " ".join(scopes),
        "iss": s.actor_issuer if actor else s.workload_issuer,
        "aud": s.actor_audience if actor else s.workload_audience,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": f"dev-{subject}-{now}",
    }
    if extra:
        claims.update(extra)
    return jwt.encode(claims, s.dev_signing_secret, algorithm="HS256")
