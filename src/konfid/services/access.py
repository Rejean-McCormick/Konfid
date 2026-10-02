from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..adapters.policy import get_policy_engine
from ..config import get_settings
from ..models import Delegation, Grant, Principal, ResourceClass
from ..schemas import AccessRequest, DelegationCreate, GrantCreate, ResourceClassCreate
from ..utils import as_utc_naive, new_id, scope_contains, utcnow


def create_resource_class(db: Session, d: ResourceClassCreate):
    r = ResourceClass(id=new_id("RC"), **d.model_dump())
    db.add(r)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "RESOURCE_CLASS_EXISTS") from exc
    return r


def create_grant(db: Session, d: GrantCreate, issued_by: str):
    p = db.get(Principal, d.subject_ref)
    if not p or p.tenant != d.tenant:
        raise HTTPException(404, "PRINCIPAL_NOT_FOUND")
    if p.status != "ACTIVE":
        raise HTTPException(409, "PRINCIPAL_INACTIVE")
    if not get_settings().dev_mode and ("*" in d.actions or "*" in d.resource_classes):
        raise HTTPException(400, "WILDCARD_GRANT_FORBIDDEN")
    g = Grant(
        id=new_id("G"),
        tenant=d.tenant,
        subject_ref=d.subject_ref,
        role_ref=d.role_ref,
        actions=d.actions,
        resource_classes=d.resource_classes,
        scope=d.scope,
        constraints=d.constraints,
        valid_until=as_utc_naive(d.valid_until),
        issued_by=issued_by,
    )
    db.add(g)
    db.flush()
    return g


def create_delegation(db: Session, d: DelegationCreate, issued_by: str):
    if d.from_principal == d.to_principal:
        raise HTTPException(400, "SELF_DELEGATION_FORBIDDEN")
    if "*" in d.actions or "*" in d.resource_classes:
        raise HTTPException(400, "WILDCARD_DELEGATION_FORBIDDEN")
    source = db.get(Principal, d.from_principal)
    target = db.get(Principal, d.to_principal)
    if not source or source.tenant != d.tenant or not target or target.tenant != d.tenant:
        raise HTTPException(404, "DELEGATION_PRINCIPAL_NOT_FOUND")
    if source.status != "ACTIVE" or target.status != "ACTIVE":
        raise HTTPException(409, "DELEGATION_PRINCIPAL_INACTIVE")
    now = utcnow()
    valid_until = as_utc_naive(d.valid_until)
    if valid_until <= now:
        raise HTTPException(400, "DELEGATION_ALREADY_EXPIRED")
    grants = db.scalars(
        select(Grant).where(
            Grant.tenant == d.tenant,
            Grant.subject_ref == d.from_principal,
            Grant.status == "ACTIVE",
        )
    ).all()
    for action in d.actions:
        for rc in d.resource_classes:
            candidates = [
                g
                for g in grants
                if (action in g.actions or "*" in g.actions)
                and (rc in g.resource_classes or "*" in g.resource_classes)
                and scope_contains(g.scope, d.scope)
                and g.valid_from <= now
                and (not g.valid_until or g.valid_until > now)
            ]
            if not candidates:
                raise HTTPException(403, "DELEGATION_EXCEEDS_AUTHORITY")
            if all(g.valid_until and valid_until > g.valid_until for g in candidates):
                raise HTTPException(403, "DELEGATION_EXCEEDS_AUTHORITY_DURATION")
    x = Delegation(
        id=new_id("D"),
        tenant=d.tenant,
        from_principal=d.from_principal,
        to_principal=d.to_principal,
        actions=d.actions,
        resource_classes=d.resource_classes,
        scope=d.scope,
        constraints=d.constraints,
        valid_until=valid_until,
        max_chain_depth=d.max_chain_depth,
        reason=d.reason,
        issued_by=issued_by,
    )
    db.add(x)
    db.flush()
    return x


def evaluate_access(db: Session, req: AccessRequest):
    rc = db.scalar(
        select(ResourceClass).where(
            ResourceClass.tenant == req.tenant,
            ResourceClass.owner_system == req.resource.owner,
            ResourceClass.name == req.resource.class_,
        )
    )
    if not rc:
        from ..schemas import AccessResponse
        return AccessResponse(
            decision_id=new_id("PD"),
            decision="DENY",
            policy="resource-catalog/1",
            reason_codes=["RESOURCE_CLASS_UNKNOWN"],
        )
    if req.action not in rc.supported_actions:
        from ..schemas import AccessResponse
        return AccessResponse(
            decision_id=new_id("PD"),
            decision="DENY",
            policy="resource-catalog/1",
            reason_codes=["ACTION_UNSUPPORTED_BY_RESOURCE"],
        )
    return get_policy_engine().evaluate_access(db, req)


def revoke_delegation(db: Session, tenant: str, delegation_id: str):
    d = db.get(Delegation, delegation_id)
    if not d or d.tenant != tenant:
        raise HTTPException(404, "DELEGATION_NOT_FOUND")
    d.status = "REVOKED"
    db.flush()
    return d
