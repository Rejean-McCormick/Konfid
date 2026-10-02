from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..adapters.audit import AuditSink
from ..adapters.enforcement import get_enforcement_adapter
from ..adapters.orgo import OrgoAdapter
from ..config import get_settings
from ..metrics import OUTBOX_DEAD, OUTBOX_PENDING, RESPONSE_ACTIONS
from ..models import ApprovalRequest, OutboxEvent, ResponseAction
from ..rate_limit import cleanup_expired
from ..utils import digest, utcnow

_audit = AuditSink()


class PermanentOutboxError(RuntimeError):
    pass


def _approval_payload(r: ApprovalRequest) -> dict:
    return {
        "approval_request_id": r.id,
        "tenant": r.tenant,
        "requester_principal": r.requester_principal,
        "operation": r.operation,
        "target": r.target,
        "scope": r.scope,
        "request_digest": r.request_digest,
        "rationale": r.rationale,
        "policy_ref": r.policy_ref,
        "threshold": r.threshold,
        "expires_at": r.expires_at.isoformat(),
    }


def _response_command(a: ResponseAction) -> dict:
    return {
        "action_id": a.id,
        "operation": a.operation,
        "target": a.target,
        "tenant": a.tenant,
        "scope": a.scope,
        "decision_ref": a.decision_ref,
        "approval_request_id": a.approval_request_id,
        "expires_at": a.expires_at.isoformat(),
        "idempotency_key": a.idempotency_key,
        "operator_principal": a.operator_principal,
    }


def _validated_payload(db: Session, e: OutboxEvent) -> tuple[dict, ResponseAction | None]:
    if e.topic == "konfid.approval.request.v1":
        req = db.get(ApprovalRequest, e.aggregate_ref)
        if not req:
            raise PermanentOutboxError("APPROVAL_REQUEST_MISSING")
        if req.expires_at <= utcnow() or req.state in {"EXPIRED", "REJECTED", "CONSUMED"}:
            raise PermanentOutboxError("APPROVAL_REQUEST_CLOSED")
        expected = _approval_payload(req)
        action = None
    elif e.topic == "konfid.response.execute.v1":
        action = db.get(ResponseAction, e.aggregate_ref)
        if not action:
            raise PermanentOutboxError("RESPONSE_ACTION_MISSING")
        if action.expires_at <= utcnow():
            action.state = "BLOCKED"
            raise PermanentOutboxError("RESPONSE_ACTION_EXPIRED")
        if action.state not in {"DISPATCHED", "RECONCILING"}:
            raise PermanentOutboxError(f"RESPONSE_STATE_INVALID:{action.state}")
        expected = _response_command(action)
    else:
        raise PermanentOutboxError(f"UNSUPPORTED_OUTBOX_TOPIC:{e.topic}")

    expected_digest = digest(expected)
    if not e.payload_digest:
        raise PermanentOutboxError("OUTBOX_PAYLOAD_DIGEST_MISSING")
    if digest(e.payload) != e.payload_digest or expected_digest != e.payload_digest:
        raise PermanentOutboxError("OUTBOX_PAYLOAD_INTEGRITY_FAILURE")
    return expected, action


def _refresh_metrics(db: Session) -> None:
    OUTBOX_PENDING.set(
        db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.state == "PENDING")) or 0
    )
    OUTBOX_DEAD.set(
        db.scalar(select(func.count()).select_from(OutboxEvent).where(OutboxEvent.state == "DEAD_LETTER")) or 0
    )


def _claim(db: Session, worker_id: str, limit: int) -> list[OutboxEvent]:
    now = utcnow()
    q = (
        select(OutboxEvent)
        .where(
            OutboxEvent.state.in_(["PENDING", "PROCESSING"]),
            OutboxEvent.next_attempt_at <= now,
            or_(OutboxEvent.locked_until.is_(None), OutboxEvent.locked_until < now),
        )
        .order_by(OutboxEvent.created_at)
        .limit(limit)
    )
    if db.bind.dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    events = db.scalars(q).all()
    lease_until = now + timedelta(seconds=get_settings().outbox_lease_seconds)
    for e in events:
        e.state = "PROCESSING"
        e.locked_by = worker_id
        e.locked_until = lease_until
    db.commit()
    return events


def _final_state(receipt: dict) -> str:
    return {
        "EXECUTED": "EXECUTED",
        "FAILED": "FAILED",
        "REJECTED": "BLOCKED",
        "UNKNOWN": "UNKNOWN",
    }.get(receipt.get("status"), "UNKNOWN")


def process_pending(db: Session, limit: int | None = None, worker_id: str = "worker-local"):
    s = get_settings()
    events = _claim(db, worker_id, limit or s.worker_batch_size)
    done: list[str] = []
    for claimed in events:
        try:
            # Reload after claim commit so the processing transaction is independent.
            e = db.get(OutboxEvent, claimed.id)
            if not e or e.state != "PROCESSING" or e.locked_by != worker_id:
                continue
            payload, action = _validated_payload(db, e)
            if e.topic == "konfid.approval.request.v1":
                OrgoAdapter().create_approval_case(payload)
                receipt = {"status": "PUBLISHED"}
            else:
                receipt = get_enforcement_adapter().execute(payload)

            # End the read transaction before fencing. PostgreSQL READ COMMITTED
            # would see a newer row on the next statement, but explicitly ending
            # the transaction also makes the ownership check correct on SQLite/WAL
            # and keeps the semantics portable. No local state has been mutated yet.
            db.rollback()

            # Fencing: the external call can outlive our lease. Re-lock and refresh
            # the outbox row before committing any result. If another worker has
            # reclaimed the event, this worker is stale and must not overwrite the
            # new owner's state. Duplicate external delivery is safe because every
            # privileged command is idempotent.
            db.expire_all()
            owned = db.scalar(
                select(OutboxEvent)
                .where(OutboxEvent.id == claimed.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not owned or owned.state != "PROCESSING" or owned.locked_by != worker_id:
                db.rollback()
                continue

            # Reconstruct/verify from canonical state again after reacquiring the
            # lease so a concurrent state change cannot be finalized from stale data.
            _, action = _validated_payload(db, owned)
            owned.attempts += 1
            owned.state = "PUBLISHED"
            owned.published_at = utcnow()
            owned.last_error = None
            owned.locked_by = None
            owned.locked_until = None
            if action:
                action.final_receipt = receipt
                action.state = _final_state(receipt)
                if action.approval_request_id and action.state == "EXECUTED":
                    r = db.get(ApprovalRequest, action.approval_request_id)
                    if r:
                        r.state = "CONSUMED"
                _audit.record(
                    db,
                    tenant=action.tenant,
                    actor=action.operator_principal,
                    caller="svc:konfid-worker",
                    action="response.execute",
                    target=action.target,
                    outcome=action.state,
                    correlation_id=action.id,
                    details={"operation": action.operation, "receipt": receipt},
                )
                RESPONSE_ACTIONS.labels(operation=action.operation, state=action.state).inc()
            db.commit()
            done.append(owned.id)
        except Exception as exc:
            permanent = isinstance(exc, PermanentOutboxError)
            db.rollback()
            current = db.scalar(
                select(OutboxEvent)
                .where(OutboxEvent.id == claimed.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if not current or current.locked_by != worker_id or current.state != "PROCESSING":
                # Lease ownership moved to another worker; never clobber its state.
                db.rollback()
                continue
            current.attempts += 1
            current.last_error = f"{type(exc).__name__}:{str(exc)}"[:4000]
            current.locked_by = None
            current.locked_until = None
            if permanent or current.attempts >= current.max_attempts:
                current.state = "DEAD_LETTER"
                current.dead_lettered_at = utcnow()
                action = (
                    db.get(ResponseAction, current.aggregate_ref)
                    if current.topic == "konfid.response.execute.v1"
                    else None
                )
                if action and action.state not in {"BLOCKED", "FAILED"}:
                    action.state = "UNKNOWN"
            else:
                current.state = "PENDING"
                base = min(300, 2 ** min(current.attempts, 8))
                current.next_attempt_at = utcnow() + timedelta(seconds=base + random.uniform(0, 1))
            db.commit()
    cleanup_expired(db)
    db.commit()
    _refresh_metrics(db)
    return done
