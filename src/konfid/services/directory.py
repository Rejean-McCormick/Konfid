from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    AccountBinding,
    ContactEndpoint,
    IdentityBinding,
    Principal,
    RoleMailbox,
    RoleMailboxAssignment,
)
from ..schemas import AccountBindingCreate, IdentityBindingCreate, PrincipalCreate
from ..utils import as_utc_naive, new_id, utcnow


def create_principal(db: Session, d: PrincipalCreate):
    p = Principal(id=new_id("P"), tenant=d.tenant, type=d.type, display_name=d.display_name)
    db.add(p)
    db.flush()
    return p


def add_identity_binding(db: Session, d: IdentityBindingCreate, actor: str):
    p = db.get(Principal, d.principal_id)
    if not p or p.tenant != d.tenant:
        raise HTTPException(404, "PRINCIPAL_NOT_FOUND")
    old = db.scalar(
        select(IdentityBinding).where(
            IdentityBinding.tenant == d.tenant,
            IdentityBinding.issuer == d.issuer,
            IdentityBinding.subject == d.subject,
        )
    )
    if old:
        if old.principal_id == d.principal_id and old.status == "ACTIVE":
            return old
        raise HTTPException(409, "IDENTITY_ALREADY_BOUND")
    b = IdentityBinding(
        id=new_id("IDB"),
        tenant=d.tenant,
        principal_id=d.principal_id,
        provider_type=d.provider_type,
        issuer=d.issuer,
        subject=d.subject,
        email_hint=d.email_hint,
        assurance_capabilities=d.assurance_capabilities,
        linked_by=actor,
    )
    db.add(b)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "IDENTITY_ALREADY_BOUND") from exc
    return b


def add_account_binding(db: Session, d: AccountBindingCreate):
    p = db.get(Principal, d.principal_id)
    if not p or p.tenant != d.tenant:
        raise HTTPException(404, "PRINCIPAL_NOT_FOUND")
    a = AccountBinding(
        id=new_id("ACB"),
        tenant=d.tenant,
        principal_id=d.principal_id,
        system=d.system,
        external_account_id=d.external_account_id,
    )
    db.add(a)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "ACCOUNT_ALREADY_BOUND") from exc
    return a


def add_contact_endpoint(db: Session, d):
    p = db.get(Principal, d.principal_id)
    if not p or p.tenant != d.tenant:
        raise HTTPException(404, "PRINCIPAL_NOT_FOUND")
    c = ContactEndpoint(
        id=new_id("CON"),
        tenant=d.tenant,
        principal_id=d.principal_id,
        type=d.type,
        value_normalized=d.value_normalized,
        verification_state=d.verification_state,
        purpose=d.purpose,
        valid_until=as_utc_naive(d.valid_until),
    )
    db.add(c)
    db.flush()
    return c


def create_role_mailbox(db: Session, d):
    m = RoleMailbox(
        id=new_id("MBX"),
        tenant=d.tenant,
        address=d.address.lower().strip(),
        role_ref=d.role_ref,
        confidentiality_class=d.confidentiality_class,
        delivery_policy=d.delivery_policy,
    )
    db.add(m)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "ROLE_MAILBOX_EXISTS") from exc
    return m


def assign_role_mailbox(db: Session, d, actor: str):
    m = db.get(RoleMailbox, d.mailbox_id)
    p = db.get(Principal, d.principal_id)
    if not m or m.tenant != d.tenant:
        raise HTTPException(404, "ROLE_MAILBOX_NOT_FOUND")
    if not p or p.tenant != d.tenant:
        raise HTTPException(404, "PRINCIPAL_NOT_FOUND")
    a = RoleMailboxAssignment(
        id=new_id("MBA"),
        tenant=d.tenant,
        mailbox_id=d.mailbox_id,
        principal_id=d.principal_id,
        valid_until=as_utc_naive(d.valid_until),
        assigned_by=actor,
    )
    db.add(a)
    db.flush()
    return a


def resolve_identity(db: Session, tenant: str, issuer: str, subject: str):
    b = db.scalar(
        select(IdentityBinding).where(
            IdentityBinding.tenant == tenant,
            IdentityBinding.issuer == issuer,
            IdentityBinding.subject == subject,
            IdentityBinding.status == "ACTIVE",
        )
    )
    if not b:
        raise HTTPException(404, "IDENTITY_NOT_BOUND")
    p = db.get(Principal, b.principal_id)
    if not p or p.status != "ACTIVE":
        raise HTTPException(403, "PRINCIPAL_INACTIVE")
    return p, b


def revoke_identity_binding(db: Session, tenant: str, binding_id: str):
    b = db.get(IdentityBinding, binding_id)
    if not b or b.tenant != tenant:
        raise HTTPException(404, "IDENTITY_BINDING_NOT_FOUND")
    b.status = "REVOKED"
    db.flush()
    return b


def revoke_account_binding(db: Session, tenant: str, binding_id: str):
    b = db.get(AccountBinding, binding_id)
    if not b or b.tenant != tenant:
        raise HTTPException(404, "ACCOUNT_BINDING_NOT_FOUND")
    b.status = "REVOKED"
    db.flush()
    return b


def revoke_contact_endpoint(db: Session, tenant: str, contact_id: str):
    c = db.get(ContactEndpoint, contact_id)
    if not c or c.tenant != tenant:
        raise HTTPException(404, "CONTACT_NOT_FOUND")
    c.verification_state = "REVOKED"
    c.valid_until = utcnow()
    db.flush()
    return c


def revoke_role_mailbox_assignment(db: Session, tenant: str, assignment_id: str):
    a = db.get(RoleMailboxAssignment, assignment_id)
    if not a or a.tenant != tenant:
        raise HTTPException(404, "ROLE_MAILBOX_ASSIGNMENT_NOT_FOUND")
    a.status = "REVOKED"
    db.flush()
    return a
