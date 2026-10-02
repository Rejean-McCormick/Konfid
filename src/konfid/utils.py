import hashlib, json, secrets
from datetime import datetime, timezone
from typing import Any

def utcnow(): return datetime.now(timezone.utc).replace(tzinfo=None)

def as_utc_naive(dt: datetime | None):
    if dt is None: return None
    if dt.tzinfo is None: return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)

def canonical_timestamp(dt: datetime) -> str:
    """Stable UTC representation across SQLite/PostgreSQL timezone round-trips."""
    normalized = as_utc_naive(dt)
    assert normalized is not None
    return normalized.isoformat(timespec="microseconds") + "Z"
def new_id(prefix: str): return f"{prefix}-{secrets.token_urlsafe(12)}"
def canonical_json(v: Any): return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
def digest(v: Any): return "sha256:" + hashlib.sha256(canonical_json(v).encode()).hexdigest()

def scope_contains(grant: dict[str, Any], requested: dict[str, Any]) -> bool:
    """Return True when *requested* is equal to or narrower than *grant*.

    Every restrictive dimension present in the grant must also be present in the
    request. Extra dimensions in the request make it narrower and are allowed.
    An empty grant scope therefore means intentionally global authority.
    """
    for key, allowed in grant.items():
        if key not in requested:
            return False
        if allowed == "*":
            continue
        req = requested[key]
        requested_values = req if isinstance(req, list) else [req]
        allowed_values = allowed if isinstance(allowed, list) else [allowed]
        if not all(value in allowed_values for value in requested_values):
            return False
    return True
