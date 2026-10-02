from __future__ import annotations

import hashlib
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .models import RateLimitBucket
from .utils import utcnow


def route_limit(path: str) -> int:
    s = get_settings()
    if path.startswith("/v1/admin/") or path.startswith("/v1/approval/policies") or path.startswith("/v1/detectors"):
        return s.rate_limit_admin_per_minute
    if path.startswith("/v1/responses") or path.startswith("/v1/approvals"):
        return s.rate_limit_response_per_minute
    if path.startswith("/v1/access/evaluate"):
        return s.rate_limit_access_per_minute
    if path.startswith("/v1/security/events"):
        return s.rate_limit_telemetry_per_minute
    return s.rate_limit_default_per_minute


def _bucket_id(service: str, tenant: str, route: str, window_key: str) -> str:
    raw = f"{service}|{tenant}|{route}|{window_key}".encode()
    return hashlib.sha256(raw).hexdigest()


def check_rate_limit(service: str, tenant: str, route: str) -> None:
    s = get_settings()
    if not s.rate_limit_enabled:
        return
    limit = route_limit(route)
    if limit <= 0:
        raise HTTPException(429, "RATE_LIMITED", headers={"Retry-After": "60"})

    now = utcnow()
    window = now.replace(second=0, microsecond=0)
    expires = window + timedelta(minutes=2)
    # Use an explicit UTC wall-clock window instead of naive_datetime.timestamp(),
    # whose interpretation depends on the host timezone.
    window_key = window.strftime("%Y-%m-%dT%H:%MZ")
    key = _bucket_id(service, tenant, route, window_key)

    with SessionLocal() as db:
        dialect = db.bind.dialect.name
        values = {
            "bucket_key": key,
            "window_started_at": window,
            "expires_at": expires,
            "count": 1,
        }
        if dialect == "postgresql":
            stmt = pg_insert(RateLimitBucket).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[RateLimitBucket.bucket_key],
                set_={"count": RateLimitBucket.count + 1, "expires_at": expires},
            ).returning(RateLimitBucket.count)
            count = db.execute(stmt).scalar_one()
        elif dialect == "sqlite":
            stmt = sqlite_insert(RateLimitBucket).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[RateLimitBucket.bucket_key],
                set_={"count": RateLimitBucket.count + 1, "expires_at": expires},
            )
            db.execute(stmt)
            count = db.scalar(select(RateLimitBucket.count).where(RateLimitBucket.bucket_key == key)) or 0
        else:
            row = db.get(RateLimitBucket, key)
            if row:
                row.count += 1
                count = row.count
            else:
                db.add(RateLimitBucket(**values))
                count = 1
        db.commit()

    if count > limit:
        raise HTTPException(429, "RATE_LIMITED", headers={"Retry-After": "60"})


def cleanup_expired(db: Session) -> int:
    result = db.execute(delete(RateLimitBucket).where(RateLimitBucket.expires_at < utcnow()))
    return int(result.rowcount or 0)
