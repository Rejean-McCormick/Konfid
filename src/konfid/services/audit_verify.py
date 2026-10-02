from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditHead, AuditRecord
from ..utils import canonical_timestamp, digest


def verify_chain(db: Session, tenant: str) -> dict:
    rows = db.scalars(
        select(AuditRecord).where(AuditRecord.tenant == tenant).order_by(AuditRecord.sequence)
    ).all()
    prev = "GENESIS"
    expected_sequence = 1
    for row in rows:
        if row.sequence != expected_sequence:
            return {"valid": False, "reason": "SEQUENCE_GAP", "record_id": row.id}
        if row.format_version >= 2:
            created_at = (
                canonical_timestamp(row.created_at)
                if row.format_version >= 3
                else row.created_at.isoformat()
            )
            payload = {
                "event_id": row.id,
                "created_at": created_at,
                "tenant": row.tenant,
                "sequence": row.sequence,
                "actor": row.actor_principal,
                "caller": row.caller_service,
                "action": row.action,
                "target": row.target_ref,
                "outcome": row.outcome,
                "correlation_id": row.correlation_id,
                "details": row.details,
            }
            if digest(payload) != row.event_digest:
                return {"valid": False, "reason": "EVENT_DIGEST_MISMATCH", "record_id": row.id}
        expected = digest(
            {
                "tenant": tenant,
                "sequence": row.sequence,
                "event": row.event_digest,
                "prev": prev,
            }
        )
        if row.prev_digest != prev or row.chain_digest != expected:
            return {"valid": False, "reason": "CHAIN_MISMATCH", "record_id": row.id}
        prev = row.chain_digest
        expected_sequence += 1
    head = db.get(AuditHead, tenant)
    if rows:
        if not head or head.last_sequence != rows[-1].sequence or head.last_digest != rows[-1].chain_digest:
            return {"valid": False, "reason": "HEAD_MISMATCH"}
    elif head and (head.last_sequence != 0 or head.last_digest != "GENESIS"):
        return {"valid": False, "reason": "EMPTY_HEAD_MISMATCH"}
    return {"valid": True, "records": len(rows), "last_digest": prev}
