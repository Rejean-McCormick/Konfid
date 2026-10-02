from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.policy import ASSURANCE_ORDER
from ..models import ApprovalPolicy, ApprovalReceipt, ApprovalRequest, Grant, Principal
from ..schemas import ApprovalPolicyCreate, ApprovalReceiptIn
from ..utils import as_utc_naive, digest, new_id, scope_contains, utcnow


def upsert_policy(db: Session, d: ApprovalPolicyCreate):
    p = db.scalar(
        select(ApprovalPolicy).where(
            ApprovalPolicy.tenant == d.tenant,
            ApprovalPolicy.operation == d.operation,
        )
    )
    incoming = d.model_dump()
    if not p:
        p = ApprovalPolicy(id=new_id("APOL"), **incoming)
        db.add(p)
    else:
        current = {
            k: getattr(p, k)
            for k in incoming
            if k not in {"tenant", "operation", "version"}
        }
        changed = any(current[k] != incoming[k] for k in current)
        if changed and incoming["version"] == p.version:
            raise HTTPException(409, "POLICY_VERSION_MUST_CHANGE")
        for k, v in incoming.items():
            setattr(p, k, v)
    db.flush()
    return p


def get_policy(db: Session, tenant: str, operation: str):
    return db.scalar(
        select(ApprovalPolicy).where(
            ApprovalPolicy.tenant == tenant,
            ApprovalPolicy.operation == operation,
        )
    )


def create_request(db: Session, *, tenant, requester, operation, target, scope, rationale, policy):
    content = {
        "tenant": tenant,
        "requester": requester,
        "operation": operation,
        "target": target,
        "scope": scope,
        "rationale": rationale,
        "policy": f"{policy.id}/{policy.version}",
    }
    r = ApprovalRequest(
        id=new_id("APR"),
        tenant=tenant,
        requester_principal=requester,
        operation=operation,
        target=target,
        scope=scope,
        request_digest=digest(content),
        rationale=rationale,
        policy_ref=f"{policy.id}/{policy.version}",
        threshold=policy.threshold,
        expires_at=utcnow() + timedelta(seconds=policy.approval_ttl_seconds),
    )
    db.add(r)
    db.flush()
    return r


def approver_eligible(db: Session, tenant: str, principal: str, roles: list[str], scope: dict) -> bool:
    if not roles:
        return False
    p = db.get(Principal, principal)
    if not p or p.tenant != tenant or p.status != "ACTIVE" or p.type != "HUMAN":
        return False
    now = utcnow()
    grants = db.scalars(
        select(Grant).where(
            Grant.tenant == tenant,
            Grant.subject_ref == principal,
            Grant.status == "ACTIVE",
            Grant.role_ref.in_(roles),
            Grant.valid_from <= now,
            (Grant.valid_until.is_(None) | (Grant.valid_until > now)),
        )
    ).all()
    return any(scope_contains(g.scope, scope) for g in grants)


def operator_eligible(db: Session, r: ApprovalRequest, principal: str) -> bool:
    p = get_policy(db, r.tenant, r.operation)
    if not p:
        return False
    return approver_eligible(db, r.tenant, principal, p.eligible_roles, r.scope)


def _policy_is_current(r: ApprovalRequest, p: ApprovalPolicy) -> bool:
    return r.policy_ref == f"{p.id}/{p.version}"


def add_receipt(db: Session, d: ApprovalReceiptIn):
    r = db.get(ApprovalRequest, d.request_id)
    if not r or r.tenant != d.tenant:
        raise HTTPException(404, "APPROVAL_REQUEST_NOT_FOUND")
    now = utcnow()
    if r.expires_at <= now or r.state in {"EXPIRED", "REJECTED", "CONSUMED"}:
        if r.expires_at <= now:
            r.state = "EXPIRED"
            db.flush()
        raise HTTPException(409, "APPROVAL_EXPIRED_OR_CLOSED")
    if d.request_digest != r.request_digest:
        raise HTTPException(409, "REQUEST_DIGEST_MISMATCH")
    p = get_policy(db, r.tenant, r.operation)
    if not p:
        raise HTTPException(409, "APPROVAL_POLICY_MISSING")
    if not _policy_is_current(r, p):
        r.state = "EXPIRED"
        db.flush()
        raise HTTPException(409, "APPROVAL_POLICY_SUPERSEDED")
    if d.approver_principal == r.requester_principal and not p.requester_may_approve:
        raise HTTPException(403, "SELF_APPROVAL_FORBIDDEN")
    if not approver_eligible(db, r.tenant, d.approver_principal, p.eligible_roles, r.scope):
        raise HTTPException(403, "APPROVER_NOT_ELIGIBLE")
    if ASSURANCE_ORDER.get(d.auth_assurance, 0) < ASSURANCE_ORDER.get(p.required_assurance, 99):
        raise HTTPException(403, "AUTH_ASSURANCE_INSUFFICIENT")
    auth_time = as_utc_naive(d.auth_time)
    age = (now - auth_time).total_seconds()
    if age < -60 or age > p.max_auth_age_seconds:
        raise HTTPException(403, "APPROVER_AUTH_TOO_OLD")
    if p.justification_required and len(d.justification.strip()) < 3:
        raise HTTPException(400, "JUSTIFICATION_REQUIRED")
    existing = db.scalar(
        select(ApprovalReceipt).where(
            ApprovalReceipt.request_id == r.id,
            ApprovalReceipt.approver_principal == d.approver_principal,
        )
    )
    if existing:
        if existing.decision == d.decision and existing.request_digest == d.request_digest:
            return existing, r
        raise HTTPException(409, "APPROVAL_ALREADY_SUBMITTED")
    rec = ApprovalReceipt(
        id=new_id("APP"),
        tenant=d.tenant,
        request_id=r.id,
        approver_principal=d.approver_principal,
        decision=d.decision,
        request_digest=d.request_digest,
        auth_assurance=d.auth_assurance,
        auth_time=auth_time,
        justification=d.justification,
        policy_ref=r.policy_ref,
        orgo_case_ref=d.orgo_case_ref,
    )
    db.add(rec)
    db.flush()
    if d.decision == "REJECT":
        r.state = "REJECTED"
    else:
        xs = db.scalars(
            select(ApprovalReceipt).where(
                ApprovalReceipt.request_id == r.id,
                ApprovalReceipt.decision == "APPROVE",
            )
        ).all()
        count = len({x.approver_principal for x in xs}) if p.distinct_humans else len(xs)
        r.state = "APPROVED" if count >= r.threshold else "PARTIALLY_APPROVED"
    db.flush()
    return rec, r


def quorum_valid(db: Session, r: ApprovalRequest):
    if r.expires_at <= utcnow() or r.state != "APPROVED":
        return False
    p = get_policy(db, r.tenant, r.operation)
    if not p or not _policy_is_current(r, p):
        return False
    xs = db.scalars(
        select(ApprovalReceipt).where(
            ApprovalReceipt.request_id == r.id,
            ApprovalReceipt.decision == "APPROVE",
        )
    ).all()
    valid = []
    now = utcnow()
    for x in xs:
        auth_fresh = 0 <= (now - as_utc_naive(x.auth_time)).total_seconds() <= p.max_auth_age_seconds
        if (
            x.request_digest == r.request_digest
            and x.policy_ref == r.policy_ref
            and auth_fresh
            and approver_eligible(db, r.tenant, x.approver_principal, p.eligible_roles, r.scope)
        ):
            valid.append(x)
    return (len({x.approver_principal for x in valid}) if p.distinct_humans else len(valid)) >= r.threshold
