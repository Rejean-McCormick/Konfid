import pytest
from fastapi import HTTPException
from sqlalchemy import select

from konfid.adapters.audit import AuditSink
from konfid.models import AuditRecord, OutboxEvent, Principal
from konfid.schemas import ApprovalPolicyCreate, ApprovalReceiptIn, GrantCreate, PrincipalCreate, ResponseProposalIn
from konfid.services import access, approval, directory, response
from konfid.services.audit_verify import verify_chain
from konfid.services.outbox import process_pending
from konfid.utils import new_id, utcnow


def test_audit_chain_detects_tampering(db):
    sink = AuditSink()
    sink.record(db, tenant="t", actor=None, caller="svc", action="a", target="x", outcome="SUCCESS", correlation_id="c1", details={"n": 1})
    sink.record(db, tenant="t", actor=None, caller="svc", action="b", target="y", outcome="SUCCESS", correlation_id="c2", details={"n": 2})
    db.commit()
    assert verify_chain(db, "t")["valid"] is True
    first = db.scalars(select(AuditRecord).where(AuditRecord.tenant == "t").order_by(AuditRecord.sequence)).first()
    first.details = {"n": 999}
    db.commit()
    result = verify_chain(db, "t")
    assert result["valid"] is False
    assert result["reason"] == "EVENT_DIGEST_MISMATCH"


def test_mutation_and_local_audit_can_rollback_together(db):
    sink = AuditSink()
    p = directory.create_principal(db, PrincipalCreate(tenant="t", display_name="Transient"))
    sink.record(db, tenant="t", actor=None, caller="svc", action="principal.create", target=p.id, outcome="SUCCESS", correlation_id="c", details={})
    db.rollback()
    assert db.get(Principal, p.id) is None
    assert db.scalar(select(AuditRecord).where(AuditRecord.tenant == "t")) is None


def test_outbox_dead_letters_after_max_attempts(db):
    event = OutboxEvent(
        id=new_id("OUT"), tenant="t", topic="unsupported.topic", aggregate_ref="x",
        payload={}, max_attempts=1,
    )
    db.add(event); db.commit()
    process_pending(db, worker_id="worker-test")
    db.refresh(event)
    assert event.state == "DEAD_LETTER"
    assert event.dead_lettered_at is not None


def _person(db, name):
    return directory.create_principal(db, PrincipalCreate(tenant="t", display_name=name))


def _role(db, p, role, scope):
    return access.create_grant(
        db,
        GrantCreate(
            tenant="t", subject_ref=p.id, role_ref=role, actions=["noop"],
            resource_classes=["SECURITY.RESPONSE"], scope=scope,
        ),
        "svc",
    )


def test_approver_role_must_cover_request_scope(db):
    approval.upsert_policy(db, ApprovalPolicyCreate(
        tenant="t", operation="FREEZE_TENANT", threshold=1,
        eligible_roles=["SECURITY_EXECUTIVE"], operator_required=False,
        required_assurance="phishing_resistant", version="1",
    ))
    requester = _person(db, "Requester")
    approver = _person(db, "Approver")
    _role(db, approver, "SECURITY_EXECUTIVE", {"organization": "t", "project": "A"})
    policy = approval.get_policy(db, "t", "FREEZE_TENANT")
    req = approval.create_request(
        db, tenant="t", requester=requester.id, operation="FREEZE_TENANT",
        target="tenant:t", scope={"organization": "t", "project": "B"},
        rationale="incident", policy=policy,
    )
    with pytest.raises(HTTPException) as exc:
        approval.add_receipt(db, ApprovalReceiptIn(
            tenant="t", request_id=req.id, approver_principal=approver.id,
            decision="APPROVE", request_digest=req.request_digest,
            auth_assurance="phishing_resistant", auth_time=utcnow(),
            justification="reviewed",
        ))
    assert exc.value.detail == "APPROVER_NOT_ELIGIBLE"


def test_policy_supersession_invalidates_open_approval_request(db):
    requester = _person(db, "Requester")
    approver = _person(db, "Approver")
    _role(db, approver, "SECURITY_EXECUTIVE", {"organization": "t"})
    p = approval.upsert_policy(db, ApprovalPolicyCreate(
        tenant="t", operation="FREEZE_TENANT", threshold=1,
        eligible_roles=["SECURITY_EXECUTIVE"], required_assurance="phishing_resistant",
        version="1",
    ))
    req = approval.create_request(
        db, tenant="t", requester=requester.id, operation="FREEZE_TENANT",
        target="tenant:t", scope={"organization": "t"}, rationale="incident", policy=p,
    )
    approval.upsert_policy(db, ApprovalPolicyCreate(
        tenant="t", operation="FREEZE_TENANT", threshold=2,
        eligible_roles=["SECURITY_EXECUTIVE"], required_assurance="phishing_resistant",
        version="2",
    ))
    with pytest.raises(HTTPException) as exc:
        approval.add_receipt(db, ApprovalReceiptIn(
            tenant="t", request_id=req.id, approver_principal=approver.id,
            decision="APPROVE", request_digest=req.request_digest,
            auth_assurance="phishing_resistant", auth_time=utcnow(),
            justification="reviewed",
        ))
    assert exc.value.detail == "APPROVAL_POLICY_SUPERSEDED"


def _authorized_suspend_action(db, idem: str):
    from konfid.schemas import RiskSignalIn
    from konfid.services import overwatch
    from konfid.services.bootstrap import bootstrap_tenant

    bootstrap_tenant(db, "t")
    requester = _person(db, f"Requester-{idem}")
    access.create_grant(
        db,
        GrantCreate(
            tenant="t",
            subject_ref=requester.id,
            role_ref="SECURITY_OPERATOR",
            actions=["security.response.suspend_grant"],
            resource_classes=["SECURITY.RESPONSE"],
            scope={"organization": "t"},
        ),
        "svc",
    )
    sig = overwatch.create_signal(
        db,
        RiskSignalIn(
            tenant="t",
            subject_ref=requester.id,
            severity="critical",
            detector_id="detector-prod-test",
            detector_version="1",
            reason_codes=["TEST"],
        ),
    )
    act = response.propose(
        db,
        ResponseProposalIn(
            tenant="t",
            requester_principal=requester.id,
            risk_signal_ids=[sig.id],
            target="grant:G-test",
            scope={"organization": "t"},
            requested_operation="SUSPEND_GRANT",
            rationale="production invariant test",
            idempotency_key=idem,
        ),
    )
    response.dispatch(db, act.id)
    db.commit()
    return act


def test_outbox_payload_tampering_is_dead_lettered_without_execution(db):
    act = _authorized_suspend_action(db, "tamper-0001")
    event = db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_ref == act.id,
            OutboxEvent.topic == "konfid.response.execute.v1",
        )
    )
    assert event is not None
    event.payload = {**event.payload, "target": "tenant:evil"}
    db.commit()

    process_pending(db, worker_id="worker-integrity")
    db.refresh(event)
    db.refresh(act)
    assert event.state == "DEAD_LETTER"
    assert "OUTBOX_PAYLOAD_INTEGRITY_FAILURE" in (event.last_error or "")
    assert act.final_receipt is None
    assert act.state == "UNKNOWN"


def test_response_worker_writes_verifiable_chained_audit(db):
    act = _authorized_suspend_action(db, "audit-worker-0001")
    process_pending(db, worker_id="worker-audit")
    db.refresh(act)
    assert act.state == "EXECUTED"
    record = db.scalar(
        select(AuditRecord).where(
            AuditRecord.tenant == "t",
            AuditRecord.action == "response.execute",
            AuditRecord.target_ref == act.target,
        )
    )
    assert record is not None
    assert verify_chain(db, "t")["valid"] is True


def test_security_event_rejects_secret_like_metadata():
    from pydantic import ValidationError
    from konfid.schemas import SecurityEventIn

    with pytest.raises(ValidationError):
        SecurityEventIn(
            tenant="t",
            event_type="access",
            metadata={"authorization": "Bearer secret"},
        )


def test_audit_timestamp_canonicalization_is_timezone_stable():
    from datetime import datetime, timedelta, timezone
    from konfid.utils import canonical_timestamp

    naive = datetime(2026, 10, 2, 12, 30, 0, 123456)
    aware_utc = naive.replace(tzinfo=timezone.utc)
    aware_offset = (naive + timedelta(hours=2)).replace(tzinfo=timezone(timedelta(hours=2)))
    assert canonical_timestamp(naive) == canonical_timestamp(aware_utc)
    assert canonical_timestamp(naive) == canonical_timestamp(aware_offset)


def test_enforcement_receipt_is_minimized_and_digest_bound():
    from konfid.adapters.enforcement import validate_receipt
    from konfid.utils import digest

    command = {"action_id": "ACT-123", "target": "svc:x", "operation": "ISOLATE_SERVICE"}
    receipt = validate_receipt(
        command,
        {
            "action_id": "ACT-123",
            "executor": "svc:agent-1",
            "status": "EXECUTED",
            "executed_at": "2026-10-02T12:30:00Z",
            "target_state_digest": digest({"state": "isolated"}),
            "software_version": "agent/1",
            "receipt_version": "1",
            "unexpected_secretish_field": "must-not-persist",
        },
    )
    assert "unexpected_secretish_field" not in receipt
    assert receipt["receipt_digest"].startswith("sha256:")


def test_local_audit_rejects_secret_like_details(db):
    sink = AuditSink()
    with pytest.raises(ValueError, match="AUDIT_SECRET_FIELD_FORBIDDEN"):
        sink.record(
            db, tenant="t", actor="P1", caller="svc", action="x", target="y",
            outcome="SUCCESS", correlation_id="c", details={"token": "must-not-log"},
        )


def test_stale_outbox_worker_cannot_finalize_after_lease_is_stolen(db, monkeypatch):
    from datetime import timedelta
    from konfid.adapters.enforcement import validate_receipt
    from konfid.db import SessionLocal
    from konfid.utils import digest
    import konfid.services.outbox as outbox_mod

    act = _authorized_suspend_action(db, "lease-fence-0001")

    class LeaseStealingAdapter:
        def execute(self, command):
            # Simulate another worker reclaiming the event while this worker is
            # blocked in the external privileged call.
            with SessionLocal() as other:
                event = other.scalar(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_ref == command["action_id"],
                        OutboxEvent.topic == "konfid.response.execute.v1",
                    )
                )
                event.locked_by = "worker-new-owner"
                event.locked_until = utcnow() + timedelta(seconds=60)
                event.state = "PROCESSING"
                other.commit()
            return validate_receipt(
                command,
                {
                    "action_id": command["action_id"],
                    "executor": "svc:test-agent",
                    "status": "EXECUTED",
                    "executed_at": utcnow().isoformat() + "Z",
                    "target_state_digest": digest({"target": command["target"], "state": "done"}),
                    "software_version": "test/1",
                    "receipt_version": "1",
                },
            )

    monkeypatch.setattr(outbox_mod, "get_enforcement_adapter", lambda: LeaseStealingAdapter())
    published = process_pending(db, worker_id="worker-stale")
    assert published == []

    db.expire_all()
    event = db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_ref == act.id,
            OutboxEvent.topic == "konfid.response.execute.v1",
        )
    )
    fresh_action = db.get(type(act), act.id)
    assert event.state == "PROCESSING"
    assert event.locked_by == "worker-new-owner"
    assert fresh_action.state == "DISPATCHED"
    assert fresh_action.final_receipt is None


def test_http_adapter_rejects_oversized_stream_without_parsing(monkeypatch):
    import httpx
    from konfid.adapters.http import JsonHttpAdapter, UpstreamUnavailable

    adapter = JsonHttpAdapter("https://oversize.example")
    adapter.max_response_bytes = 8
    adapter.retry_attempts = 1
    adapter.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=b'{"value":"this-is-too-large"}',
            )
        )
    )
    with pytest.raises(UpstreamUnavailable, match="UPSTREAM_UNAVAILABLE") as exc:
        adapter.post("/v1/test", {}, idempotent=False)
    assert isinstance(exc.value.__cause__, UpstreamUnavailable)
    assert "UPSTREAM_RESPONSE_TOO_LARGE" in str(exc.value.__cause__)
    adapter.client.close()


def test_http_adapter_requires_json_for_nonempty_success():
    import httpx
    from konfid.adapters.http import JsonHttpAdapter, UpstreamUnavailable

    adapter = JsonHttpAdapter("https://content-type.example")
    adapter.retry_attempts = 1
    adapter.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, headers={"content-type": "text/plain"}, content=b"ok")
        )
    )
    with pytest.raises(UpstreamUnavailable):
        adapter.post("/v1/test", {}, idempotent=False)
    adapter.client.close()


def test_audit_export_preserves_per_tenant_sequence(db, monkeypatch):
    from konfid.config import get_settings
    from konfid.services.audit_export import export_pending
    import konfid.services.audit_export as audit_export_mod

    sink = AuditSink()
    sink.record(db, tenant="tenant-order", actor="P1", caller="svc", action="a", target="x", outcome="SUCCESS", correlation_id="c1", details={})
    sink.record(db, tenant="tenant-order", actor="P1", caller="svc", action="b", target="y", outcome="SUCCESS", correlation_id="c2", details={})
    db.commit()

    sent = []
    settings = get_settings()
    old_url = settings.koa_audit_url
    settings.koa_audit_url = "https://audit-order.example"
    try:
        monkeypatch.setattr(
            audit_export_mod.JsonHttpAdapter,
            "post",
            lambda self, path, payload, headers=None, idempotent=False: sent.append(payload["sequence"]) or {"ok": True},
        )
        exported = export_pending(db, limit=10, worker_id="audit-order-worker")
    finally:
        settings.koa_audit_url = old_url
    assert len(exported) == 2
    assert sent == [1, 2]


def test_koa_policy_invalid_decision_fails_closed(monkeypatch):
    from konfid.adapters.policy import KoaPolicyEngine

    engine = KoaPolicyEngine("https://policy-invalid.example")
    monkeypatch.setattr(engine.http, "post", lambda *args, **kwargs: {"decision": "ALLOW_EVERYTHING", "reason_codes": []})
    decision, reasons = engine.authorize_control(
        None, "t", "P1", "access.grant.create", "G1", {"organization": "t"}
    )
    assert decision == "BLOCKED"
    assert reasons == ["POLICY_RESPONSE_INVALID"]


def test_koa_access_policy_malformed_payload_fails_closed(monkeypatch, db):
    from konfid.adapters.policy import KoaPolicyEngine
    from konfid.schemas import AccessRequest

    engine = KoaPolicyEngine("https://policy-malformed.example")
    monkeypatch.setattr(engine.http, "post", lambda *args, **kwargs: {"decision": "ALLOW"})
    result = engine.evaluate_access(
        db,
        AccessRequest(
            request_id="req-policy-invalid",
            tenant="t",
            actor="P123",
            action="employee.read",
            resource={"owner": "konnaxion", "class": "HR.BASIC"},
            scope={"organization": "t"},
        ),
    )
    assert result.decision == "BLOCKED"
    assert result.reason_codes == ["POLICY_RESPONSE_INVALID"]
