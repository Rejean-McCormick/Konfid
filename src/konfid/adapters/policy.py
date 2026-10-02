from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import ValidationError

from ..config import get_settings
from ..metrics import AUTHZ_DECISIONS
from ..models import Delegation, Grant, Principal, RiskSignal
from ..schemas import AccessRequest, AccessResponse
from ..utils import new_id, scope_contains, utcnow
from .http import JsonHttpAdapter, UpstreamUnavailable

ASSURANCE_ORDER = {"unknown": 0, "password": 1, "mfa": 2, "phishing_resistant": 3, "hardware": 4}

_ACCESS_DECISIONS = {"ALLOW", "DENY", "BLOCKED", "STEP_UP_REQUIRED", "APPROVAL_REQUIRED"}
_CONTROL_DECISIONS = {"ALLOW", "DENY", "BLOCKED"}
_RESPONSE_DECISIONS = {"ALLOW", "DENY", "BLOCKED", "STEP_UP_REQUIRED", "APPROVAL_REQUIRED"}


def _simple_policy_result(value: dict, allowed: set[str]) -> tuple[str, list[str]]:
    if not isinstance(value, dict):
        raise ValueError("POLICY_RESPONSE_INVALID")
    decision = value.get("decision")
    reasons = value.get("reason_codes", [])
    if decision not in allowed:
        raise ValueError("POLICY_DECISION_INVALID")
    if not isinstance(reasons, list) or len(reasons) > 64:
        raise ValueError("POLICY_REASON_CODES_INVALID")
    if any(not isinstance(item, str) or not item or len(item) > 128 for item in reasons):
        raise ValueError("POLICY_REASON_CODES_INVALID")
    return decision, reasons



class PolicyEngine(ABC):
    @abstractmethod
    def evaluate_access(self, db: Session, req: AccessRequest) -> AccessResponse:
        ...

    @abstractmethod
    def authorize_control(
        self, db: Session, tenant: str, actor: str, action: str, target: str, scope: dict,
        auth_assurance: str = "unknown", auth_age_seconds: int | None = None,
    ) -> tuple[str, list[str]]:
        ...

    @abstractmethod
    def authorize_response(
        self,
        db: Session,
        tenant: str,
        requester: str,
        operation: str,
        target: str,
        scope: dict,
        auth_assurance: str = "unknown",
        auth_age_seconds: int | None = None,
        approval_context: dict | None = None,
    ) -> tuple[str, list[str]]:
        ...


class LocalPolicyEngine(PolicyEngine):
    """Development/reference engine only. Production is required to use kOA."""

    policy_ref = "local-policy/2"

    @staticmethod
    def _constraints_allow(constraints: dict, req: AccessRequest):
        obligations: list[dict] = []
        required = constraints.get("required_assurance")
        if required and ASSURANCE_ORDER.get(req.context.auth_assurance, 0) < ASSURANCE_ORDER.get(required, 99):
            return False, ["AUTH_ASSURANCE_INSUFFICIENT"], []
        max_age = constraints.get("max_auth_age_seconds")
        if max_age is not None and (
            req.context.auth_age_seconds is None or req.context.auth_age_seconds > int(max_age)
        ):
            return False, ["AUTH_TOO_OLD"], []
        max_rows = constraints.get("max_rows")
        if max_rows is not None:
            if req.context.requested_count > int(max_rows):
                return False, ["REQUEST_COUNT_EXCEEDS_LIMIT"], []
            obligations.append({"type": "max_rows", "value": int(max_rows)})
        if constraints.get("no_export"):
            obligations.append({"type": "no_export"})
        if constraints.get("audit_level"):
            obligations.append({"type": "audit", "level": constraints["audit_level"]})
        return True, [], obligations

    def _grant_allows(self, g: Grant, req: AccessRequest):
        now = utcnow()
        if g.status != "ACTIVE" or g.valid_from > now or (g.valid_until and g.valid_until <= now):
            return False, ["GRANT_EXPIRED_OR_INACTIVE"], []
        if req.action not in g.actions and "*" not in g.actions:
            return False, ["ACTION_NOT_GRANTED"], []
        if req.resource.class_ not in g.resource_classes and "*" not in g.resource_classes:
            return False, ["RESOURCE_CLASS_DENIED"], []
        if not scope_contains(g.scope, req.scope):
            return False, ["SCOPE_MISMATCH"], []
        ok, reasons, obligations = self._constraints_allow(g.constraints or {}, req)
        return (ok, ["GRANT_MATCH"] if ok else reasons, obligations)

    def evaluate_access(self, db: Session, req: AccessRequest):
        now = utcnow()
        p = db.get(Principal, req.actor)
        if not p or p.tenant != req.tenant or p.status != "ACTIVE":
            result = AccessResponse(
                decision_id=new_id("PD"), decision="DENY", policy=self.policy_ref,
                reason_codes=["IDENTITY_REVOKED_OR_UNKNOWN"],
            )
            AUTHZ_DECISIONS.labels(decision=result.decision).inc()
            return result

        risk = db.scalar(
            select(RiskSignal).where(
                RiskSignal.tenant == req.tenant,
                RiskSignal.subject_ref == req.actor,
                RiskSignal.status == "ACTIVE",
                RiskSignal.expires_at > now,
                RiskSignal.severity.in_(["high", "critical"]),
            )
        )
        if risk and req.action.endswith((".export", ".admin", ".modify")):
            result = AccessResponse(
                decision_id=new_id("PD"),
                decision="STEP_UP_REQUIRED",
                policy=self.policy_ref,
                reason_codes=["RISK_TOO_HIGH"],
                obligations=[{"type": "required_assurance", "value": "phishing_resistant"}],
            )
            AUTHZ_DECISIONS.labels(decision=result.decision).inc()
            return result

        for g in db.scalars(select(Grant).where(Grant.tenant == req.tenant, Grant.subject_ref == req.actor)).all():
            ok, reasons, obs = self._grant_allows(g, req)
            if ok:
                result = AccessResponse(
                    decision_id=new_id("PD"),
                    decision="ALLOW",
                    policy=g.policy_version or self.policy_ref,
                    valid_until=now + timedelta(seconds=60),
                    obligations=obs,
                    reason_codes=reasons,
                )
                AUTHZ_DECISIONS.labels(decision=result.decision).inc()
                return result

        delegations = db.scalars(
            select(Delegation).where(
                Delegation.tenant == req.tenant,
                Delegation.to_principal == req.actor,
                Delegation.status == "ACTIVE",
                Delegation.valid_from <= now,
                Delegation.valid_until > now,
            )
        ).all()
        for d in delegations:
            if req.action not in d.actions:
                continue
            if req.resource.class_ not in d.resource_classes:
                continue
            if not scope_contains(d.scope, req.scope):
                continue
            ok_d, reasons_d, obs_d = self._constraints_allow(d.constraints or {}, req)
            if not ok_d:
                continue
            delegated = req.model_copy(update={"actor": d.from_principal})
            for g in db.scalars(
                select(Grant).where(Grant.tenant == req.tenant, Grant.subject_ref == d.from_principal)
            ).all():
                ok, _, obs = self._grant_allows(g, delegated)
                if ok:
                    obs.extend(obs_d)
                    obs.append({"type": "authority_source", "value": f"delegation:{d.id}"})
                    result = AccessResponse(
                        decision_id=new_id("PD"),
                        decision="ALLOW",
                        policy=g.policy_version or self.policy_ref,
                        valid_until=min(d.valid_until, now + timedelta(seconds=60)),
                        obligations=obs,
                        reason_codes=["DELEGATION_MATCH", "GRANT_MATCH"],
                    )
                    AUTHZ_DECISIONS.labels(decision=result.decision).inc()
                    return result

        result = AccessResponse(
            decision_id=new_id("PD"), decision="DENY", policy=self.policy_ref,
            reason_codes=["NO_MATCHING_GRANT"],
        )
        AUTHZ_DECISIONS.labels(decision=result.decision).inc()
        return result

    def authorize_control(self, db, tenant, actor, action, target, scope, auth_assurance="unknown", auth_age_seconds=None):
        # Development-only convenience. Workload scopes remain the local gate;
        # production is forced to kOA by configuration validation.
        return "ALLOW", ["LOCAL_CONTROL_POLICY"]

    def authorize_response(self, db, tenant, requester, operation, target, scope, auth_assurance="unknown", auth_age_seconds=None, approval_context=None):
        req = AccessRequest(
            request_id=new_id("AR"), tenant=tenant, actor=requester,
            action=f"security.response.{operation.lower()}",
            resource={"owner": "konfid", "class": "SECURITY.RESPONSE", "selector": target},
            scope=scope,
            context={"auth_assurance": auth_assurance, "auth_age_seconds": auth_age_seconds, "requested_count": 1},
        )
        r = self.evaluate_access(db, req)
        return r.decision, r.reason_codes


class KoaPolicyEngine(PolicyEngine):
    def __init__(self, url: str):
        self.http = JsonHttpAdapter(url, get_settings().integration_secret("koa_policy"))

    def evaluate_access(self, db, req):
        try:
            result = AccessResponse.model_validate(
                self.http.post(
                    "/v1/evaluate",
                    {"kind": "access", "context": req.model_dump(by_alias=True, mode="json")},
                    idempotent=True,
                )
            )
            if result.decision not in _ACCESS_DECISIONS:
                raise ValueError("POLICY_DECISION_INVALID")
            if len(result.reason_codes) > 64 or any(
                not isinstance(item, str) or not item or len(item) > 128 for item in result.reason_codes
            ):
                raise ValueError("POLICY_REASON_CODES_INVALID")
        except UpstreamUnavailable:
            result = AccessResponse(
                decision_id=new_id("PD"), decision="BLOCKED", policy="koa/unavailable",
                reason_codes=["POLICY_UNAVAILABLE"],
            )
        except (ValidationError, ValueError, TypeError):
            result = AccessResponse(
                decision_id=new_id("PD"), decision="BLOCKED", policy="koa/invalid-response",
                reason_codes=["POLICY_RESPONSE_INVALID"],
            )
        AUTHZ_DECISIONS.labels(decision=result.decision).inc()
        return result

    def authorize_control(self, db, tenant, actor, action, target, scope, auth_assurance="unknown", auth_age_seconds=None):
        try:
            d = self.http.post(
                "/v1/evaluate",
                {
                    "kind": "control",
                    "tenant": tenant,
                    "actor": actor,
                    "action": action,
                    "target": target,
                    "scope": scope,
                    "auth_assurance": auth_assurance,
                    "auth_age_seconds": auth_age_seconds,
                },
                idempotent=True,
            )
            return _simple_policy_result(d, _CONTROL_DECISIONS)
        except UpstreamUnavailable:
            return "BLOCKED", ["POLICY_UNAVAILABLE"]
        except (ValueError, TypeError):
            return "BLOCKED", ["POLICY_RESPONSE_INVALID"]

    def authorize_response(self, db, tenant, requester, operation, target, scope, auth_assurance="unknown", auth_age_seconds=None, approval_context=None):
        try:
            d = self.http.post(
                "/v1/evaluate",
                {
                    "kind": "response",
                    "tenant": tenant,
                    "requester": requester,
                    "operation": operation,
                    "target": target,
                    "scope": scope,
                    "auth_assurance": auth_assurance,
                    "auth_age_seconds": auth_age_seconds,
                    "approval_context": approval_context,
                },
                idempotent=True,
            )
            return _simple_policy_result(d, _RESPONSE_DECISIONS)
        except UpstreamUnavailable:
            return "BLOCKED", ["POLICY_UNAVAILABLE"]
        except (ValueError, TypeError):
            return "BLOCKED", ["POLICY_RESPONSE_INVALID"]


def get_policy_engine():
    s = get_settings()
    return KoaPolicyEngine(s.koa_policy_url) if s.policy_mode == "koa" else LocalPolicyEngine()
