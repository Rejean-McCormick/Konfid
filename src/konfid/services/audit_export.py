from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from ..adapters.http import JsonHttpAdapter
from ..config import get_settings
from ..metrics import AUDIT_PENDING
from ..models import AuditRecord
from ..utils import canonical_timestamp, utcnow


def _claim_one(db: Session, worker_id: str, blocked_tenants: set[str]) -> AuditRecord | None:
    """Lease the oldest exportable record while preserving per-tenant order.

    A record is eligible only when no earlier unexported record exists for the
    same tenant. PostgreSQL SKIP LOCKED lets multiple workers process different
    tenant heads without ever jumping over an in-flight predecessor.
    """
    s = get_settings()
    now = utcnow()
    prior = aliased(AuditRecord)
    q = select(AuditRecord).where(
        AuditRecord.exported.is_(False),
        or_(AuditRecord.export_next_attempt_at.is_(None), AuditRecord.export_next_attempt_at <= now),
        or_(AuditRecord.export_locked_until.is_(None), AuditRecord.export_locked_until < now),
        ~exists(
            select(1).where(
                prior.tenant == AuditRecord.tenant,
                prior.exported.is_(False),
                prior.sequence < AuditRecord.sequence,
            )
        ),
    )
    if blocked_tenants:
        q = q.where(~AuditRecord.tenant.in_(blocked_tenants))
    q = q.order_by(AuditRecord.created_at, AuditRecord.tenant).limit(1)
    if db.bind.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    row = db.scalar(q)
    if not row:
        db.rollback()
        return None
    row.export_locked_by = worker_id
    row.export_locked_until = now + timedelta(seconds=s.audit_export_lease_seconds)
    db.commit()
    return row


def _payload(r: AuditRecord) -> dict:
    return {
        "event_id": r.id,
        "tenant": r.tenant,
        "sequence": r.sequence,
        "format_version": r.format_version,
        "actor": r.actor_principal,
        "caller": r.caller_service,
        "action": r.action,
        "target": r.target_ref,
        "outcome": r.outcome,
        "correlation_id": r.correlation_id,
        "details": r.details,
        "event_digest": r.event_digest,
        "prev_digest": r.prev_digest,
        "chain_digest": r.chain_digest,
        "created_at": canonical_timestamp(r.created_at),
    }


def export_pending(db: Session, limit: int | None = None, worker_id: str = "audit-local"):
    """Export local evidence to the authoritative broker with leases + fencing.

    The broker receives events strictly in sequence per tenant. Delivery is
    at-least-once and idempotent by event id; a stale worker that lost its lease
    cannot finalize local export state.
    """
    s = get_settings()
    if not s.koa_audit_url:
        return []
    limit = min(max(int(limit or s.audit_export_batch_size), 1), 1000)
    http = JsonHttpAdapter(s.koa_audit_url, s.integration_secret("koa_audit"))
    done: list[str] = []
    blocked_tenants: set[str] = set()

    while len(done) < limit:
        claimed = _claim_one(db, worker_id, blocked_tenants)
        if not claimed:
            break
        claimed_id = claimed.id
        claimed_tenant = claimed.tenant
        try:
            current = db.get(AuditRecord, claimed_id)
            if not current or current.exported or current.export_locked_by != worker_id:
                db.rollback()
                continue
            http.post(
                "/v1/events",
                _payload(current),
                headers={"Idempotency-Key": current.id},
                idempotent=True,
            )

            # Fence finalization after the external call; another worker may have
            # reclaimed an expired lease while this request was in flight.
            db.rollback()
            current = db.scalar(
                select(AuditRecord)
                .where(AuditRecord.id == claimed_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not current or current.exported or current.export_locked_by != worker_id:
                db.rollback()
                continue
            current.exported = True
            current.exported_at = utcnow()
            current.export_attempts = int(current.export_attempts or 0) + 1
            current.export_last_error = None
            current.export_next_attempt_at = None
            current.export_locked_by = None
            current.export_locked_until = None
            db.commit()
            done.append(current.id)
        except Exception as exc:
            db.rollback()
            current = db.scalar(
                select(AuditRecord)
                .where(AuditRecord.id == claimed_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not current or current.export_locked_by != worker_id:
                db.rollback()
                continue
            current.export_attempts = int(current.export_attempts or 0) + 1
            current.export_last_error = f"{type(exc).__name__}:{str(exc)}"[:2000]
            base = min(300, 2 ** min(current.export_attempts, 8))
            current.export_next_attempt_at = utcnow() + timedelta(seconds=base + random.uniform(0, 1))
            current.export_locked_by = None
            current.export_locked_until = None
            db.commit()
            blocked_tenants.add(claimed_tenant)

    AUDIT_PENDING.set(
        db.scalar(select(func.count()).select_from(AuditRecord).where(AuditRecord.exported.is_(False))) or 0
    )
    return done
