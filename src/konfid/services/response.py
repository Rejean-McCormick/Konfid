from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..adapters.policy import ASSURANCE_ORDER, get_policy_engine
from ..config import get_settings
from ..models import ApprovalReceipt, ApprovalRequest, OutboxEvent, Principal, ResponseAction, RiskSignal
from ..schemas import ResponseProposalIn
from ..utils import digest, new_id, utcnow
from .approval import create_request, get_policy, operator_eligible, quorum_valid

SEVERITY_DEFAULT = {
    "low": "OBSERVE",
    "medium": "STEP_UP_AUTH",
    "high": "REVOKE_SESSION",
    "critical": "SUSPEND_GRANT",
}
HIGH_IMPACT = {"ISOLATE_SERVICE", "FREEZE_SECURITY_DOMAIN", "FREEZE_TENANT", "EMERGENCY_SHUTDOWN"}


def _approval_context(db: Session, a: ResponseAction) -> dict | None:
    if not a.approval_request_id:
        return None
    r = db.get(ApprovalRequest, a.approval_request_id)
    if not r:
        return None
    receipts = db.scalars(
        select(ApprovalReceipt).where(
            ApprovalReceipt.request_id == r.id, ApprovalReceipt.decision == "APPROVE"
        ).order_by(ApprovalReceipt.approver_principal, ApprovalReceipt.id)
    ).all()
    evidence = [
        {
            "receipt_id": x.id,
            "approver": x.approver_principal,
            "request_digest": x.request_digest,
            "policy_ref": x.policy_ref,
            "approved_at": x.approved_at.isoformat(),
        }
        for x in receipts
    ]
    return {
        "request_id": r.id,
        "request_digest": r.request_digest,
        "policy_ref": r.policy_ref,
        "request_state": r.state,
        "threshold": r.threshold,
        "approval_count": len(receipts),
        "approval_set_digest": digest(evidence),
        "approver_principals": [x.approver_principal for x in receipts],
        "quorum_satisfied": True,
    }


def propose(db: Session, d: ResponseProposalIn):
    old = db.scalar(
        select(ResponseAction).where(
            ResponseAction.tenant == d.tenant,
            ResponseAction.idempotency_key == d.idempotency_key,
        )
    )
    if old:
        return old

    now = utcnow()
    signals = []
    for sid in d.risk_signal_ids:
        s = db.get(RiskSignal, sid)
        if not s or s.tenant != d.tenant:
            raise HTTPException(404, f"RISK_SIGNAL_NOT_FOUND:{sid}")
        if s.status != "ACTIVE" or s.expires_at <= now:
            raise HTTPException(409, f"RISK_SIGNAL_STALE:{sid}")
        signals.append(s)

    requester = db.get(Principal, d.requester_principal)
    if not requester or requester.tenant != d.tenant or requester.status != "ACTIVE":
        raise HTTPException(403, "REQUESTER_NOT_ACTIVE")

    op = d.requested_operation
    if not op:
        order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        sev = max(signals, key=lambda x: order[x.severity]).severity if signals else "low"
        op = SEVERITY_DEFAULT[sev]

    decision, reasons = get_policy_engine().authorize_response(
        db,
        d.tenant,
        d.requester_principal,
        op,
        d.target,
        d.scope,
        d.auth_assurance,
        d.auth_age_seconds,
    )
    a = ResponseAction(
        id=new_id("ACT"),
        tenant=d.tenant,
        requester_principal=d.requester_principal,
        risk_signal_ids=d.risk_signal_ids,
        operation=op,
        target=d.target,
        scope=d.scope,
        rationale=d.rationale,
        requester_auth_assurance=d.auth_assurance,
        requester_auth_at=(now - timedelta(seconds=d.auth_age_seconds)) if d.auth_age_seconds is not None else None,
        idempotency_key=d.idempotency_key,
        expires_at=now + timedelta(seconds=get_settings().response_action_ttl_seconds),
        decision_ref=";".join(reasons) or "response-policy/unknown",
    )

    if decision not in {"ALLOW", "APPROVAL_REQUIRED"}:
        a.state = "BLOCKED"
    else:
        p = get_policy(db, d.tenant, op)
        requires_approval = decision == "APPROVAL_REQUIRED" or op in HIGH_IMPACT or p is not None
        if requires_approval:
            if not p:
                a.state = "BLOCKED"
                a.decision_ref = "APPROVAL_POLICY_MISSING"
            else:
                r = create_request(
                    db,
                    tenant=d.tenant,
                    requester=d.requester_principal,
                    operation=op,
                    target=d.target,
                    scope=d.scope,
                    rationale=d.rationale,
                    policy=p,
                )
                a.approval_request_id = r.id
                a.state = "APPROVAL_PENDING"
                approval_payload = {
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
                db.add(
                    OutboxEvent(
                        id=new_id("OUT"),
                        tenant=d.tenant,
                        topic="konfid.approval.request.v1",
                        aggregate_ref=r.id,
                        payload=approval_payload,
                        payload_digest=digest(approval_payload),
                        max_attempts=get_settings().outbox_max_attempts,
                    )
                )
        else:
            a.state = "AUTHORIZED"

    try:
        with db.begin_nested():
            db.add(a)
            db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ResponseAction).where(
                ResponseAction.tenant == d.tenant,
                ResponseAction.idempotency_key == d.idempotency_key,
            )
        )
        if existing:
            return existing
        raise
    return a


def authorize_after_approval(db: Session, a: ResponseAction):
    if not a.approval_request_id:
        return a
    r = db.get(ApprovalRequest, a.approval_request_id)
    if not r or not quorum_valid(db, r):
        return a
    age = int((utcnow() - a.requester_auth_at).total_seconds()) if a.requester_auth_at else None
    decision, reasons = get_policy_engine().authorize_response(
        db,
        a.tenant,
        a.requester_principal,
        a.operation,
        a.target,
        a.scope,
        a.requester_auth_assurance,
        age,
        _approval_context(db, a),
    )
    if decision == "ALLOW":
        a.state = "AUTHORIZED"
        a.decision_ref = ";".join(reasons) or a.decision_ref
        db.flush()
    return a


def _validate_operator(
    db: Session,
    a: ResponseAction,
    operator: str | None,
    operator_assurance: str,
    operator_auth_age_seconds: int | None,
) -> None:
    if not a.approval_request_id:
        return
    req = db.get(ApprovalRequest, a.approval_request_id)
    pol = get_policy(db, a.tenant, a.operation) if req else None
    if not req or not pol:
        raise HTTPException(409, "APPROVAL_POLICY_MISSING")
    if pol.operator_required and not operator:
        raise HTTPException(400, "OPERATOR_REQUIRED")
    if not operator:
        return
    p = db.get(Principal, operator)
    if not p or p.tenant != a.tenant or p.status != "ACTIVE" or p.type != "HUMAN":
        raise HTTPException(403, "OPERATOR_NOT_ACTIVE_HUMAN")
    if not operator_eligible(db, req, operator):
        raise HTTPException(403, "OPERATOR_NOT_ELIGIBLE")
    if ASSURANCE_ORDER.get(operator_assurance, 0) < ASSURANCE_ORDER.get(pol.required_assurance, 99):
        raise HTTPException(403, "OPERATOR_AUTH_ASSURANCE_INSUFFICIENT")
    if operator_auth_age_seconds is None or operator_auth_age_seconds > pol.max_auth_age_seconds:
        raise HTTPException(403, "OPERATOR_AUTH_TOO_OLD")
    if not pol.operator_may_approve:
        already_approved = db.scalar(
            select(ApprovalReceipt.id).where(
                ApprovalReceipt.request_id == a.approval_request_id,
                ApprovalReceipt.approver_principal == operator,
                ApprovalReceipt.decision == "APPROVE",
            )
        )
        if already_approved:
            raise HTTPException(403, "OPERATOR_APPROVER_SEPARATION_REQUIRED")


def dispatch(
    db: Session,
    action_id: str,
    operator: str | None = None,
    *,
    operator_assurance: str = "unknown",
    operator_auth_age_seconds: int | None = None,
):
    a = db.get(ResponseAction, action_id)
    if not a:
        raise HTTPException(404, "RESPONSE_ACTION_NOT_FOUND")
    if a.state == "APPROVAL_PENDING":
        a = authorize_after_approval(db, a)
    if a.state in {"DISPATCHED", "EXECUTED"}:
        return a
    if a.state != "AUTHORIZED":
        raise HTTPException(409, f"RESPONSE_NOT_AUTHORIZED:{a.state}")

    if a.approval_request_id:
        req = db.get(ApprovalRequest, a.approval_request_id)
        if not req or not quorum_valid(db, req):
            a.state = "BLOCKED"
            db.flush()
            raise HTTPException(409, "APPROVAL_QUORUM_NO_LONGER_VALID")

    _validate_operator(db, a, operator, operator_assurance, operator_auth_age_seconds)

    age = int((utcnow() - a.requester_auth_at).total_seconds()) if a.requester_auth_at else None
    decision, _ = get_policy_engine().authorize_response(
        db,
        a.tenant,
        a.requester_principal,
        a.operation,
        a.target,
        a.scope,
        a.requester_auth_assurance,
        age,
        _approval_context(db, a),
    )
    if decision != "ALLOW":
        a.state = "BLOCKED"
        db.flush()
        raise HTTPException(409, "RESPONSE_REVALIDATION_FAILED")
    if a.expires_at <= utcnow():
        a.state = "BLOCKED"
        db.flush()
        raise HTTPException(409, "ACTION_EXPIRED")

    a.operator_principal = operator
    cmd = {
        "action_id": a.id,
        "operation": a.operation,
        "target": a.target,
        "tenant": a.tenant,
        "scope": a.scope,
        "decision_ref": a.decision_ref,
        "approval_request_id": a.approval_request_id,
        "expires_at": a.expires_at.isoformat(),
        "idempotency_key": a.idempotency_key,
        "operator_principal": operator,
    }
    out = db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant == a.tenant,
            OutboxEvent.topic == "konfid.response.execute.v1",
            OutboxEvent.aggregate_ref == a.id,
        )
    )
    if not out:
        out = OutboxEvent(
            id=new_id("OUT"),
            tenant=a.tenant,
            topic="konfid.response.execute.v1",
            aggregate_ref=a.id,
            payload=cmd,
            payload_digest=digest(cmd),
            max_attempts=get_settings().outbox_max_attempts,
        )
        db.add(out)
    elif out.state in {"DEAD_LETTER", "PUBLISHED"}:
        if out.state == "PUBLISHED" and a.state == "EXECUTED":
            return a
        raise HTTPException(409, f"OUTBOX_NOT_REUSABLE:{out.state}")
    else:
        out.payload = cmd
        out.payload_digest = digest(cmd)
        out.state = "PENDING"
        out.next_attempt_at = utcnow()
        out.locked_by = None
        out.locked_until = None
    a.state = "DISPATCHED"
    a.dispatched_at = utcnow()
    db.flush()
    return a


def reconcile(db: Session, action_id: str):
    a = db.get(ResponseAction, action_id)
    if not a:
        raise HTTPException(404, "RESPONSE_ACTION_NOT_FOUND")
    if a.state == "EXECUTED":
        return a
    out = db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant == a.tenant,
            OutboxEvent.topic == "konfid.response.execute.v1",
            OutboxEvent.aggregate_ref == a.id,
        )
    )
    if not out:
        raise HTTPException(409, "RESPONSE_OUTBOX_MISSING")
    if a.expires_at <= utcnow():
        a.state = "BLOCKED"
        db.flush()
        raise HTTPException(409, "ACTION_EXPIRED")
    if out.state == "PUBLISHED" and a.final_receipt:
        a.state = "EXECUTED" if a.final_receipt.get("status") == "EXECUTED" else "UNKNOWN"
        db.flush()
        return a
    out.state = "PENDING"
    out.next_attempt_at = utcnow()
    out.locked_by = None
    out.locked_until = None
    out.dead_lettered_at = None
    a.state = "RECONCILING"
    db.flush()
    return a
