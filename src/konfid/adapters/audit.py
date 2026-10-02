from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import AuditHead, AuditRecord
from ..utils import canonical_json, canonical_timestamp, digest, new_id, utcnow

_FORBIDDEN_DETAIL_KEYS = {"password", "passwd", "token", "access_token", "refresh_token", "authorization", "secret", "api_key", "private_key"}

def _validate_details(details: dict) -> dict:
    if not isinstance(details, dict):
        raise ValueError("AUDIT_DETAILS_INVALID")
    if len(canonical_json(details).encode("utf-8")) > 32_768:
        raise ValueError("AUDIT_DETAILS_TOO_LARGE")
    def walk(value, depth=0):
        if depth > 5:
            raise ValueError("AUDIT_DETAILS_TOO_DEEP")
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str) or len(key) > 128:
                    raise ValueError("AUDIT_DETAIL_KEY_INVALID")
                if key.lower() in _FORBIDDEN_DETAIL_KEYS:
                    raise ValueError("AUDIT_SECRET_FIELD_FORBIDDEN")
                walk(child, depth + 1)
        elif isinstance(value, list):
            if len(value) > 256:
                raise ValueError("AUDIT_DETAILS_TOO_MANY_ITEMS")
            for child in value:
                walk(child, depth + 1)
        elif isinstance(value, str) and len(value) > 4096:
            raise ValueError("AUDIT_DETAIL_VALUE_TOO_LARGE")
    walk(details)
    return details


class AuditSink:
    """Append-oriented local audit journal.

    The local journal is chained per tenant and exported asynchronously to kOA
    Audit Broker. Mutations and their local audit record can therefore commit in
    the same database transaction.
    """

    def record(
        self,
        db: Session,
        *,
        tenant: str,
        actor: str | None,
        caller: str,
        action: str,
        target: str | None,
        outcome: str,
        correlation_id: str,
        details: dict,
    ) -> AuditRecord:
        details = _validate_details(details)
        # Serialize a tenant's chain in PostgreSQL. SQLite already serializes writes.
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:tenant))"), {"tenant": tenant})

        head = db.scalar(select(AuditHead).where(AuditHead.tenant == tenant).with_for_update())
        if not head:
            head = AuditHead(tenant=tenant, last_sequence=0, last_digest="GENESIS")
            db.add(head)
            db.flush()

        sequence = head.last_sequence + 1
        event_id = new_id("AUD")
        created_at = utcnow()
        payload = {
            "event_id": event_id,
            "created_at": canonical_timestamp(created_at),
            "tenant": tenant,
            "sequence": sequence,
            "actor": actor,
            "caller": caller,
            "action": action,
            "target": target,
            "outcome": outcome,
            "correlation_id": correlation_id,
            "details": details,
        }
        event_digest = digest(payload)
        chain_digest = digest(
            {
                "tenant": tenant,
                "sequence": sequence,
                "event": event_digest,
                "prev": head.last_digest,
            }
        )
        rec = AuditRecord(
            id=event_id,
            tenant=tenant,
            sequence=sequence,
            format_version=3,
            actor_principal=actor,
            caller_service=caller,
            action=action,
            target_ref=target,
            outcome=outcome,
            correlation_id=correlation_id,
            details=details,
            event_digest=event_digest,
            prev_digest=head.last_digest,
            chain_digest=chain_digest,
            created_at=created_at,
            exported=False,
        )
        db.add(rec)
        head.last_sequence = sequence
        head.last_digest = chain_digest
        head.updated_at = utcnow()
        db.flush()
        return rec
