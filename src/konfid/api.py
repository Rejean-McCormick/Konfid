from datetime import datetime, timezone
import logging
from typing import Annotated
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .adapters.audit import AuditSink
from .adapters.policy import get_policy_engine
from .auth import CallerContext, require_scope, verify_actor_assertion
from .config import get_settings
from .db import database_ready, get_db
from .models import AccountBinding, ApprovalPolicy, ApprovalRequest, AuditRecord, ContactEndpoint, Delegation, DetectorDefinition, Grant, IdentityBinding, OutboxEvent, Principal, ResponseAction, RiskSignal, RoleMailboxAssignment
from .schemas import (
    AccessRequest, AccessResponse, AccountBindingCreate, ApprovalPolicyCreate,
    ApprovalReceiptIn, ContactEndpointCreate, DelegationCreate, DetectionFeedbackIn, DetectorDefinitionCreate, DetectorQualificationIn,
    DispatchRequest, GrantCreate, IdentityBindingCreate, IdentityResolveRequest,
    PrincipalCreate, ResourceClassCreate, ResponseProposalIn, RiskSignalIn,
    RoleMailboxAssignmentCreate, RoleMailboxCreate, SecurityEventIn,
)
from .services import access, approval, detectors, directory, overwatch, response
from .services.audit_verify import verify_chain
from .services.bootstrap import bootstrap_tenant
from .utils import new_id

router = APIRouter(prefix="/v1")
log = logging.getLogger("konfid.api")
audit = AuditSink()
DB = Annotated[Session, Depends(get_db)]


def ensure_tenant(ctx: CallerContext, tenant: str) -> None:
    if ctx.tenant != tenant and "tenant:cross" not in ctx.scopes and "konfid:*" not in ctx.scopes:
        raise HTTPException(403, "TENANT_MISMATCH")


def _apply_actor_claims_to_access(body: AccessRequest, claims: dict | None) -> AccessRequest:
    if not claims:
        return body
    auth_ts = claims.get("auth_time", claims.get("iat"))
    age = max(0, int(datetime.now(timezone.utc).timestamp() - int(auth_ts))) if auth_ts is not None else None
    assurance = claims.get("assurance", claims.get("acr", "unknown"))
    return body.model_copy(update={"context": body.context.model_copy(update={"auth_assurance": assurance, "auth_age_seconds": age})})


def _apply_actor_claims_to_approval(body: ApprovalReceiptIn, claims: dict | None) -> ApprovalReceiptIn:
    if not claims:
        return body
    auth_ts = claims.get("auth_time", claims.get("iat"))
    auth_dt = datetime.fromtimestamp(int(auth_ts), timezone.utc) if auth_ts is not None else body.auth_time
    assurance = claims.get("assurance", claims.get("acr", "unknown"))
    return body.model_copy(update={"auth_assurance": assurance, "auth_time": auth_dt})


def _actor_assurance_age(claims: dict | None) -> tuple[str, int | None]:
    if not claims:
        return "unknown", None
    auth_ts = claims.get("auth_time", claims.get("iat"))
    age = max(0, int(datetime.now(timezone.utc).timestamp() - int(auth_ts))) if auth_ts is not None else None
    assurance = claims.get("assurance", claims.get("acr", "unknown"))
    return assurance, age


def _apply_actor_claims_to_response(body: ResponseProposalIn, claims: dict | None) -> ResponseProposalIn:
    if not claims:
        return body
    assurance, age = _actor_assurance_age(claims)
    return body.model_copy(update={"auth_assurance": assurance, "auth_age_seconds": age})


def _authorize_control_mutation(
    db: Session, ctx: CallerContext, token: str | None, *, tenant: str, action: str, target: str, scope: dict | None = None
) -> str | None:
    """Second authorization barrier for security/control-plane mutations.

    The workload scope gates which service may call the endpoint. In production,
    the signed actor assertion plus kOA policy independently gates which actor may
    perform this particular control-plane mutation.
    """
    claims = verify_actor_assertion(
        token, expected_tenant=tenant, expected_principal=None, expected_caller=ctx.service
    )
    if not claims:
        return None
    actor = str(claims["sub"])
    assurance, age = _actor_assurance_age(claims)
    decision, reasons = get_policy_engine().authorize_control(
        db, tenant, actor, action, target, scope or {"organization": tenant},
        auth_assurance=assurance, auth_age_seconds=age,
    )
    if decision == "BLOCKED":
        raise HTTPException(503, "CONTROL_POLICY_BLOCKED")
    if decision != "ALLOW":
        raise HTTPException(403, "CONTROL_POLICY_DENIED")
    return actor


@router.get("/health")
def health():
    return {"status": "ok", "service": "konfid", "version": get_settings().version}


@router.get("/ready")
def ready():
    ok, reason = database_ready()
    if not ok:
        log.warning("readiness_failed", extra={"reason": reason})
        raise HTTPException(503, "NOT_READY")
    return {"status": "ready", "schema": "head"}


@router.get("/version")
def version():
    s = get_settings()
    return {"service": "konfid", "version": s.version, "environment": s.env, "instance_id": s.instance_id}


@router.post("/admin/tenants/{tenant}/bootstrap")
def bootstrap(tenant: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("admin:write"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=tenant, action="tenant.bootstrap", target=tenant)
    policies = bootstrap_tenant(db, tenant)
    audit.record(db, tenant=tenant, actor=actor, caller=ctx.service, action="tenant.bootstrap", target=tenant, outcome="SUCCESS", correlation_id=new_id("CORR"), details={"approval_policies": [p.operation for p in policies]})
    db.commit()
    return {"tenant": tenant, "approval_policies": [p.operation for p in policies]}


@router.post("/principals")
def create_principal(body: PrincipalCreate, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:write"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="directory.principal.create", target="principal:new")
    p = directory.create_principal(db, body)
    audit.record(db, tenant=body.tenant, actor=actor, caller=ctx.service, action="principal.create", target=p.id, outcome="SUCCESS", correlation_id=new_id("CORR"), details={"type": p.type})
    db.commit()
    return p


@router.get("/principals/{pid}")
def get_principal(pid: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:read"))]):
    p = db.get(Principal, pid)
    if not p or p.tenant != ctx.tenant:
        raise HTTPException(404, "PRINCIPAL_NOT_FOUND")
    return p


@router.post("/identity/bindings")
def create_identity_binding(body: IdentityBindingCreate, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:write"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="directory.identity_binding.create", target=body.principal_id)
    item=directory.add_identity_binding(db, body, ctx.service)
    audit.record(db,tenant=body.tenant,actor=actor,caller=ctx.service,action="identity.binding.create",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"principal_id":item.principal_id,"provider_type":item.provider_type,"issuer":item.issuer})
    db.commit(); return item


@router.post("/identity/resolve")
def resolve_identity(body: IdentityResolveRequest, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:read"))]):
    ensure_tenant(ctx, body.tenant)
    p, b = directory.resolve_identity(db, body.tenant, body.issuer, body.subject)
    return {"principal": p, "binding": b}


@router.delete("/identity/bindings/{binding_id}")
def revoke_identity_binding(binding_id: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:write"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=ctx.tenant, action="directory.identity_binding.revoke", target=binding_id)
    item=directory.revoke_identity_binding(db,ctx.tenant,binding_id)
    audit.record(db,tenant=ctx.tenant,actor=actor,caller=ctx.service,action="identity.binding.revoke",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"principal_id":item.principal_id})
    db.commit(); return item


@router.post("/account/bindings")
def create_account_binding(body: AccountBindingCreate, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:write"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="directory.account_binding.create", target=body.principal_id)
    item=directory.add_account_binding(db, body)
    audit.record(db,tenant=body.tenant,actor=actor,caller=ctx.service,action="account.binding.create",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"principal_id":item.principal_id,"system":item.system})
    db.commit(); return item


@router.delete("/account/bindings/{binding_id}")
def revoke_account_binding(binding_id: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:write"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=ctx.tenant, action="directory.account_binding.revoke", target=binding_id)
    item=directory.revoke_account_binding(db,ctx.tenant,binding_id)
    audit.record(db,tenant=ctx.tenant,actor=actor,caller=ctx.service,action="account.binding.revoke",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"principal_id":item.principal_id,"system":item.system})
    db.commit(); return item


@router.post("/contacts")
def create_contact(body: ContactEndpointCreate, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:write"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="directory.contact.create", target=body.principal_id)
    item=directory.add_contact_endpoint(db, body)
    audit.record(db,tenant=body.tenant,actor=actor,caller=ctx.service,action="contact.create",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"principal_id":item.principal_id,"type":item.type,"verification_state":item.verification_state})
    db.commit(); return item


@router.delete("/contacts/{contact_id}")
def revoke_contact(contact_id: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:write"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=ctx.tenant, action="directory.contact.revoke", target=contact_id)
    item=directory.revoke_contact_endpoint(db,ctx.tenant,contact_id)
    audit.record(db,tenant=ctx.tenant,actor=actor,caller=ctx.service,action="contact.revoke",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"principal_id":item.principal_id,"type":item.type})
    db.commit(); return item


@router.post("/role-mailboxes")
def create_role_mailbox(body: RoleMailboxCreate, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:write"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="directory.role_mailbox.create", target=body.address)
    item=directory.create_role_mailbox(db, body)
    audit.record(db,tenant=body.tenant,actor=actor,caller=ctx.service,action="role_mailbox.create",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"role_ref":item.role_ref,"classification":item.confidentiality_class})
    db.commit(); return item


@router.post("/role-mailboxes/assignments")
def create_role_mailbox_assignment(body: RoleMailboxAssignmentCreate, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:write"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="directory.role_mailbox.assign", target=body.mailbox_id)
    item=directory.assign_role_mailbox(db, body, ctx.service)
    audit.record(db,tenant=body.tenant,actor=actor,caller=ctx.service,action="role_mailbox.assign",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"mailbox_id":item.mailbox_id,"principal_id":item.principal_id})
    db.commit(); return item


@router.delete("/role-mailboxes/assignments/{assignment_id}")
def revoke_role_mailbox_assignment(assignment_id: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("directory:write"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=ctx.tenant, action="directory.role_mailbox.assignment.revoke", target=assignment_id)
    item=directory.revoke_role_mailbox_assignment(db,ctx.tenant,assignment_id)
    audit.record(db,tenant=ctx.tenant,actor=actor,caller=ctx.service,action="role_mailbox.assignment.revoke",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"mailbox_id":item.mailbox_id,"principal_id":item.principal_id})
    db.commit(); return item


@router.post("/resources")
def create_resource(body: ResourceClassCreate, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("access:admin"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="access.resource_class.create", target=f"{body.owner_system}:{body.name}")
    item=access.create_resource_class(db, body)
    audit.record(db,tenant=body.tenant,actor=actor,caller=ctx.service,action="resource_class.create",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"owner_system":item.owner_system,"name":item.name})
    db.commit(); return item


@router.post("/grants")
def create_grant(body: GrantCreate, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("access:admin"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="access.grant.create", target=body.subject_ref, scope=body.scope)
    g = access.create_grant(db, body, ctx.service)
    audit.record(db, tenant=body.tenant, actor=actor, caller=ctx.service, action="grant.create", target=g.id, outcome="SUCCESS", correlation_id=new_id("CORR"), details={"subject": g.subject_ref, "actions": g.actions, "scope": g.scope})
    db.commit()
    return g


@router.delete("/grants/{gid}")
def revoke_grant(gid: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("access:admin"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    g = db.get(Grant, gid)
    if not g or g.tenant != ctx.tenant:
        raise HTTPException(404, "GRANT_NOT_FOUND")
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=g.tenant, action="access.grant.revoke", target=g.id, scope=g.scope)
    g.status = "REVOKED"
    audit.record(db,tenant=g.tenant,actor=actor,caller=ctx.service,action="grant.revoke",target=g.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"subject":g.subject_ref})
    db.commit()
    return {"id": g.id, "status": g.status}


@router.post("/delegations")
def create_delegation(body: DelegationCreate, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("access:admin"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="access.delegation.create", target=body.to_principal, scope=body.scope)
    item=access.create_delegation(db, body, ctx.service)
    audit.record(db,tenant=body.tenant,actor=actor,caller=ctx.service,action="delegation.create",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"from":item.from_principal,"to":item.to_principal,"actions":item.actions,"scope":item.scope})
    db.commit(); return item


@router.delete("/delegations/{delegation_id}")
def revoke_delegation(delegation_id: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("access:admin"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=ctx.tenant, action="access.delegation.revoke", target=delegation_id)
    item=access.revoke_delegation(db,ctx.tenant,delegation_id)
    audit.record(db,tenant=ctx.tenant,actor=actor,caller=ctx.service,action="delegation.revoke",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"from":item.from_principal,"to":item.to_principal})
    db.commit(); return item


@router.post("/access/evaluate", response_model=AccessResponse)
def evaluate_access(body: AccessRequest, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("access:evaluate"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    claims = verify_actor_assertion(x_konfid_actor_token, expected_tenant=body.tenant, expected_principal=body.actor, expected_caller=ctx.service)
    body = _apply_actor_claims_to_access(body, claims)
    result = access.evaluate_access(db, body)
    audit.record(db, tenant=body.tenant, actor=body.actor, caller=ctx.service, action=body.action, target=f"{body.resource.owner}:{body.resource.class_}:{body.resource.selector or ''}", outcome=result.decision, correlation_id=body.request_id, details={"policy": result.policy, "reasons": result.reason_codes, "scope": body.scope})
    db.commit()
    return result


@router.post("/security/events")
def create_security_event(body: SecurityEventIn, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("telemetry:write"))]):
    ensure_tenant(ctx, body.tenant)
    event, signals = overwatch.record_event(db, body, ctx.service)
    db.commit()
    return {"event_id": event.id, "risk_signal_ids": [s.id for s in signals]}


@router.post("/risk/signals")
def create_risk_signal(body: RiskSignalIn, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("risk:write"))]):
    ensure_tenant(ctx, body.tenant)
    item=overwatch.create_signal(db, body)
    audit.record(db,tenant=body.tenant,actor=body.subject_ref,caller=ctx.service,action="risk.signal.create",target=item.id,outcome=body.severity.upper(),correlation_id=new_id("CORR"),details={"detector":f"{body.detector_id}/{body.detector_version}","reason_codes":body.reason_codes})
    db.commit(); return item


@router.get("/risk/signals/{sid}")
def get_risk_signal(sid: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("risk:read"))]):
    sig = db.get(RiskSignal, sid)
    if not sig or sig.tenant != ctx.tenant:
        raise HTTPException(404, "RISK_SIGNAL_NOT_FOUND")
    return sig


@router.post("/risk/signals/{sid}/feedback")
def add_detection_feedback(sid: str, body: DetectionFeedbackIn, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("risk:review"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    verify_actor_assertion(x_konfid_actor_token, expected_tenant=body.tenant, expected_principal=body.analyst_principal, expected_caller=ctx.service)
    feedback=overwatch.add_feedback(db,sid,body)
    audit.record(db,tenant=body.tenant,actor=body.analyst_principal,caller=ctx.service,action="risk.feedback",target=sid,outcome=body.classification,correlation_id=new_id("CORR"),details={"feedback_id":feedback.id})
    db.commit()
    return feedback


@router.post("/detectors")
def create_detector(body: DetectorDefinitionCreate, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("risk:admin"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="risk.detector.create", target=f"{body.detector_id}/{body.version}")
    item=detectors.create_detector(db, body)
    audit.record(db,tenant=body.tenant,actor=actor,caller=ctx.service,action="detector.create",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"detector_id":item.detector_id,"version":item.version,"state":item.state})
    db.commit(); return item


@router.post("/detectors/{definition_id}/qualification")
def qualify_detector(definition_id: str, body: DetectorQualificationIn, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("risk:admin"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx,body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="risk.detector.qualify", target=definition_id)
    item=detectors.qualify(db,body.tenant,definition_id,body.qualification_ref)
    audit.record(db,tenant=body.tenant,actor=actor,caller=ctx.service,action="detector.qualify",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"qualification_ref":item.qualification_ref})
    db.commit(); return item


@router.post("/detectors/{definition_id}/state/{new_state}")
def transition_detector(definition_id: str, new_state: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("risk:admin"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=ctx.tenant, action="risk.detector.transition", target=definition_id)
    item=detectors.transition(db, ctx.tenant, definition_id, new_state)
    audit.record(db,tenant=ctx.tenant,actor=actor,caller=ctx.service,action="detector.transition",target=item.id,outcome=item.state,correlation_id=new_id("CORR"),details={"detector_id":item.detector_id,"version":item.version})
    db.commit(); return item


@router.post("/approval/policies")
def create_approval_policy(body: ApprovalPolicyCreate, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("approval:admin"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=body.tenant, action="approval.policy.upsert", target=body.operation)
    item=approval.upsert_policy(db, body)
    audit.record(db,tenant=body.tenant,actor=actor,caller=ctx.service,action="approval_policy.upsert",target=item.id,outcome="SUCCESS",correlation_id=new_id("CORR"),details={"operation":item.operation,"threshold":item.threshold,"version":item.version})
    db.commit(); return item


@router.post("/approvals/receipts")
def submit_approval(body: ApprovalReceiptIn, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("approval:submit"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    claims = verify_actor_assertion(x_konfid_actor_token, expected_tenant=body.tenant, expected_principal=body.approver_principal, expected_caller=ctx.service)
    body = _apply_actor_claims_to_approval(body, claims)
    receipt, req = approval.add_receipt(db, body)
    audit.record(db,tenant=body.tenant,actor=body.approver_principal,caller=ctx.service,action="approval.submit",target=req.id,outcome=body.decision,correlation_id=req.id,details={"receipt_id":receipt.id,"request_state":req.state,"policy_ref":req.policy_ref})
    db.commit(); return {"receipt": receipt, "request_state": req.state}


@router.get("/approvals/{rid}")
def get_approval(rid: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("approval:read"))]):
    req = db.get(ApprovalRequest, rid)
    if not req or req.tenant != ctx.tenant:
        raise HTTPException(404, "APPROVAL_REQUEST_NOT_FOUND")
    return req


@router.post("/responses/propose")
def propose_response(body: ResponseProposalIn, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("response:propose"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    ensure_tenant(ctx, body.tenant)
    claims = verify_actor_assertion(x_konfid_actor_token, expected_tenant=body.tenant, expected_principal=body.requester_principal, expected_caller=ctx.service)
    body = _apply_actor_claims_to_response(body, claims)
    action = response.propose(db, body)
    audit.record(db, tenant=body.tenant, actor=body.requester_principal, caller=ctx.service, action="response.propose", target=body.target, outcome=action.state, correlation_id=action.id, details={"operation": action.operation, "risk_signals": body.risk_signal_ids})
    db.commit()
    return action


@router.post("/responses/{aid}/dispatch")
def dispatch_response(aid: str, body: DispatchRequest, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("response:dispatch"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    claims = None
    if body.operator_principal:
        claims = verify_actor_assertion(x_konfid_actor_token, expected_tenant=ctx.tenant, expected_principal=body.operator_principal, expected_caller=ctx.service)
    operator_assurance, operator_age = _actor_assurance_age(claims)
    action = db.get(ResponseAction, aid)
    if not action or action.tenant != ctx.tenant:
        raise HTTPException(404, "RESPONSE_ACTION_NOT_FOUND")
    action = response.dispatch(
        db, aid, body.operator_principal,
        operator_assurance=operator_assurance,
        operator_auth_age_seconds=operator_age,
    )
    audit.record(db, tenant=action.tenant, actor=body.operator_principal, caller=ctx.service, action="response.dispatch.request", target=action.target, outcome=action.state, correlation_id=action.id, details={"operation": action.operation, "outbox": True})
    db.commit()
    return action


@router.post("/responses/{aid}/reconcile")
def reconcile_response(aid: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("response:dispatch"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    action = db.get(ResponseAction, aid)
    if not action or action.tenant != ctx.tenant:
        raise HTTPException(404, "RESPONSE_ACTION_NOT_FOUND")
    actor = _authorize_control_mutation(
        db, ctx, x_konfid_actor_token, tenant=action.tenant, action="response.reconcile",
        target=action.target, scope=action.scope,
    )
    action = response.reconcile(db, aid)
    audit.record(db, tenant=action.tenant, actor=actor, caller=ctx.service, action="response.reconcile.request", target=action.target, outcome=action.state, correlation_id=action.id, details={"operation": action.operation})
    db.commit()
    return action


@router.get("/grants")
def list_grants(db: DB, ctx: Annotated[CallerContext, Depends(require_scope("access:read"))], subject_ref: str | None = None, limit: int = 100):
    q=select(Grant).where(Grant.tenant==ctx.tenant)
    if subject_ref: q=q.where(Grant.subject_ref==subject_ref)
    return db.scalars(q.order_by(Grant.valid_from.desc()).limit(min(max(limit,1),500))).all()

@router.get("/delegations")
def list_delegations(db: DB, ctx: Annotated[CallerContext, Depends(require_scope("access:read"))], principal: str | None = None, limit: int = 100):
    q=select(Delegation).where(Delegation.tenant==ctx.tenant)
    if principal: q=q.where((Delegation.from_principal==principal)|(Delegation.to_principal==principal))
    return db.scalars(q.order_by(Delegation.valid_from.desc()).limit(min(max(limit,1),500))).all()

@router.get("/detectors")
def list_detectors(db: DB, ctx: Annotated[CallerContext, Depends(require_scope("risk:read"))], limit: int = 100):
    return db.scalars(select(DetectorDefinition).where(DetectorDefinition.tenant==ctx.tenant).limit(min(max(limit,1),500))).all()

@router.get("/approval/policies")
def list_approval_policies(db: DB, ctx: Annotated[CallerContext, Depends(require_scope("approval:read"))]):
    return db.scalars(select(ApprovalPolicy).where(ApprovalPolicy.tenant==ctx.tenant).order_by(ApprovalPolicy.operation)).all()

@router.get("/responses/{aid}")
def get_response(aid: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("response:read"))]):
    item=db.get(ResponseAction,aid)
    if not item or item.tenant!=ctx.tenant: raise HTTPException(404,"RESPONSE_ACTION_NOT_FOUND")
    return item

@router.get("/responses")
def list_responses(db: DB, ctx: Annotated[CallerContext, Depends(require_scope("response:read"))], state: str | None = None, limit: int = 100):
    q=select(ResponseAction).where(ResponseAction.tenant==ctx.tenant)
    if state: q=q.where(ResponseAction.state==state)
    return db.scalars(q.order_by(ResponseAction.created_at.desc()).limit(min(max(limit,1),500))).all()


@router.get("/audit")
def list_audit(db: DB, ctx: Annotated[CallerContext, Depends(require_scope("audit:read"))], limit: int = 100):
    return db.scalars(select(AuditRecord).where(AuditRecord.tenant == ctx.tenant).order_by(AuditRecord.created_at.desc()).limit(min(max(limit, 1), 500))).all()


@router.get("/outbox/dead-letter")
def list_dead_letter(db: DB, ctx: Annotated[CallerContext, Depends(require_scope("ops:read"))], limit: int = 100):
    return db.scalars(select(OutboxEvent).where(OutboxEvent.tenant == ctx.tenant, OutboxEvent.state == "DEAD_LETTER").order_by(OutboxEvent.dead_lettered_at.desc()).limit(min(max(limit, 1), 500))).all()


@router.post("/outbox/{event_id}/requeue")
def requeue_dead_letter(event_id: str, db: DB, ctx: Annotated[CallerContext, Depends(require_scope("ops:admin"))], x_konfid_actor_token: Annotated[str | None, Header()] = None):
    item = db.get(OutboxEvent, event_id)
    if not item or item.tenant != ctx.tenant:
        raise HTTPException(404, "OUTBOX_EVENT_NOT_FOUND")
    if item.state != "DEAD_LETTER":
        raise HTTPException(409, "OUTBOX_EVENT_NOT_DEAD_LETTER")
    actor = _authorize_control_mutation(db, ctx, x_konfid_actor_token, tenant=ctx.tenant, action="ops.outbox.requeue", target=event_id)
    from .utils import utcnow
    item.state = "PENDING"; item.attempts = 0; item.next_attempt_at = utcnow(); item.dead_lettered_at = None; item.locked_by = None; item.locked_until = None; item.last_error = None
    audit.record(db, tenant=ctx.tenant, actor=actor, caller=ctx.service, action="outbox.requeue", target=item.id, outcome="PENDING", correlation_id=new_id("CORR"), details={"topic": item.topic, "aggregate_ref": item.aggregate_ref})
    db.commit()
    return item


@router.get("/audit/verify")
def verify_audit(db: DB, ctx: Annotated[CallerContext, Depends(require_scope("audit:read"))]):
    return verify_chain(db, ctx.tenant)
