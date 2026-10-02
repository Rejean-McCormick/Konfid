from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TENANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TOKENISH_KEYS = {"password", "passwd", "token", "access_token", "refresh_token", "authorization", "secret", "api_key", "private_key"}


def _tenant(v: str) -> str:
    if not TENANT_RE.fullmatch(v):
        raise ValueError("invalid tenant identifier")
    return v


def _bounded_json(value: Any, *, max_bytes: int = 65_536, max_depth: int = 5, forbid_secret_keys: bool = False) -> Any:
    encoded = json.dumps(value, default=str, separators=(",", ":"), ensure_ascii=False).encode()
    if len(encoded) > max_bytes:
        raise ValueError("structured field is too large")

    def walk(v: Any, depth: int) -> None:
        if depth > max_depth:
            raise ValueError("structured field is too deeply nested")
        if isinstance(v, dict):
            if len(v) > 64:
                raise ValueError("too many object keys")
            for k, x in v.items():
                if not isinstance(k, str) or len(k) > 128:
                    raise ValueError("invalid object key")
                if forbid_secret_keys and k.lower() in TOKENISH_KEYS:
                    raise ValueError(f"secret-like field forbidden: {k}")
                walk(x, depth + 1)
        elif isinstance(v, list):
            if len(v) > 256:
                raise ValueError("too many array items")
            for x in v:
                walk(x, depth + 1)
        elif isinstance(v, str) and len(v) > 4096:
            raise ValueError("string value too long")

    walk(value, 0)
    return value


class PrincipalCreate(BaseModel):
    tenant: str
    type: Literal["HUMAN", "WORKLOAD", "AGENT"] = "HUMAN"
    display_name: str | None = Field(default=None, max_length=256)
    _tenant_v = field_validator("tenant")(_tenant)


class IdentityBindingCreate(BaseModel):
    tenant: str
    principal_id: str = Field(min_length=3, max_length=64)
    provider_type: str = Field(min_length=2, max_length=32)
    issuer: str = Field(min_length=3, max_length=512)
    subject: str = Field(min_length=1, max_length=512)
    email_hint: str | None = Field(default=None, max_length=320)
    assurance_capabilities: list[str] = Field(default_factory=list, max_length=32)
    _tenant_v = field_validator("tenant")(_tenant)


class AccountBindingCreate(BaseModel):
    tenant: str
    principal_id: str = Field(min_length=3, max_length=64)
    system: str = Field(min_length=2, max_length=128)
    external_account_id: str = Field(min_length=1, max_length=256)
    _tenant_v = field_validator("tenant")(_tenant)


class ResourceClassCreate(BaseModel):
    tenant: str
    owner_system: str = Field(min_length=2, max_length=128)
    name: str = Field(min_length=2, max_length=256)
    classification: str = Field(default="INTERNAL", max_length=64)
    supported_actions: list[str] = Field(min_length=1, max_length=128)
    attributes_schema: dict[str, Any] = Field(default_factory=dict)
    policy_namespace: str = Field(default="default", max_length=128)
    _tenant_v = field_validator("tenant")(_tenant)

    @field_validator("attributes_schema")
    @classmethod
    def attributes_bounded(cls, v):
        return _bounded_json(v, max_bytes=65_536)


class GrantCreate(BaseModel):
    tenant: str
    subject_ref: str = Field(min_length=3, max_length=64)
    role_ref: str | None = Field(default=None, max_length=128)
    actions: list[str] = Field(min_length=1, max_length=128)
    resource_classes: list[str] = Field(min_length=1, max_length=128)
    scope: dict[str, Any]
    constraints: dict[str, Any] = Field(default_factory=dict)
    valid_until: datetime | None = None
    _tenant_v = field_validator("tenant")(_tenant)

    @field_validator("scope", "constraints")
    @classmethod
    def structured_bounded(cls, v):
        return _bounded_json(v, max_bytes=32_768)


class DelegationCreate(BaseModel):
    tenant: str
    from_principal: str = Field(min_length=3, max_length=64)
    to_principal: str = Field(min_length=3, max_length=64)
    actions: list[str] = Field(min_length=1, max_length=64)
    resource_classes: list[str] = Field(min_length=1, max_length=64)
    scope: dict[str, Any]
    constraints: dict[str, Any] = Field(default_factory=dict)
    valid_until: datetime
    max_chain_depth: int = Field(default=1, ge=0, le=4)
    reason: str = Field(min_length=3, max_length=2000)
    _tenant_v = field_validator("tenant")(_tenant)

    @field_validator("scope", "constraints")
    @classmethod
    def structured_bounded(cls, v):
        return _bounded_json(v, max_bytes=32_768)


class ResourceRef(BaseModel):
    owner: str = Field(min_length=2, max_length=128)
    class_: str = Field(alias="class", min_length=2, max_length=256)
    selector: str | None = Field(default=None, max_length=1024)
    model_config = {"populate_by_name": True}


class AuthorizationContext(BaseModel):
    auth_assurance: str = Field(default="unknown", max_length=64)
    auth_age_seconds: int | None = Field(default=None, ge=0, le=604800)
    requested_count: int = Field(default=1, ge=1, le=10_000_000)
    risk_state: str | None = Field(default=None, max_length=64)
    purpose: str | None = Field(default=None, max_length=256)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def attrs_bounded(cls, v):
        return _bounded_json(v, max_bytes=32_768, forbid_secret_keys=True)


class AccessRequest(BaseModel):
    request_id: str = Field(min_length=3, max_length=128)
    tenant: str
    actor: str = Field(min_length=3, max_length=64)
    action: str = Field(min_length=2, max_length=256, pattern=r"^[A-Za-z0-9._:-]+$")
    resource: ResourceRef
    scope: dict[str, Any]
    context: AuthorizationContext = Field(default_factory=AuthorizationContext)
    _tenant_v = field_validator("tenant")(_tenant)

    @field_validator("scope")
    @classmethod
    def scope_bounded(cls, v):
        return _bounded_json(v, max_bytes=32_768)


class AccessResponse(BaseModel):
    decision_id: str
    decision: Literal["ALLOW", "DENY", "BLOCKED", "STEP_UP_REQUIRED", "APPROVAL_REQUIRED"]
    policy: str
    valid_until: datetime | None = None
    obligations: list[dict[str, Any]] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


class SecurityEventIn(BaseModel):
    tenant: str
    subject_ref: str | None = Field(default=None, max_length=64)
    event_type: str = Field(min_length=2, max_length=128)
    action: str | None = Field(default=None, max_length=256)
    resource_class: str | None = Field(default=None, max_length=256)
    count: int = Field(default=1, ge=1, le=10_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None
    _tenant_v = field_validator("tenant")(_tenant)

    @field_validator("metadata")
    @classmethod
    def metadata_bounded(cls, v):
        return _bounded_json(v, max_bytes=32_768, forbid_secret_keys=True)


class RiskSignalIn(BaseModel):
    tenant: str
    subject_ref: str | None = Field(default=None, max_length=64)
    target_ref: str | None = Field(default=None, max_length=256)
    severity: Literal["low", "medium", "high", "critical"]
    score: float | None = Field(default=None, ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    detector_id: str = Field(min_length=2, max_length=128)
    detector_version: str = Field(min_length=1, max_length=64)
    reason_codes: list[str] = Field(min_length=1, max_length=64)
    evidence_refs: list[str] = Field(default_factory=list, max_length=64)
    ttl_seconds: int | None = Field(default=None, ge=30, le=86400)
    _tenant_v = field_validator("tenant")(_tenant)


class ResponseProposalIn(BaseModel):
    tenant: str
    requester_principal: str = Field(min_length=3, max_length=64)
    risk_signal_ids: list[str] = Field(default_factory=list, max_length=64)
    target: str = Field(min_length=2, max_length=256)
    scope: dict[str, Any]
    requested_operation: Literal[
        "OBSERVE", "STEP_UP_AUTH", "RATE_LIMIT", "REVOKE_SESSION", "SUSPEND_GRANT",
        "SUSPEND_ACCOUNT", "ISOLATE_SERVICE", "FREEZE_SECURITY_DOMAIN", "FREEZE_TENANT",
        "EMERGENCY_SHUTDOWN",
    ] | None = None
    auth_assurance: str = Field(default="unknown", max_length=64)
    auth_age_seconds: int | None = Field(default=None, ge=0, le=604800)
    rationale: str = Field(min_length=3, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    _tenant_v = field_validator("tenant")(_tenant)

    @field_validator("scope")
    @classmethod
    def scope_bounded(cls, v):
        return _bounded_json(v, max_bytes=32_768)


class ApprovalPolicyCreate(BaseModel):
    tenant: str
    operation: str = Field(min_length=2, max_length=128)
    threshold: int = Field(ge=1, le=10)
    eligible_roles: list[str] = Field(min_length=1, max_length=32)
    distinct_humans: bool = True
    requester_may_approve: bool = False
    operator_may_approve: bool = False
    operator_required: bool = False
    required_assurance: str = Field(default="mfa", max_length=64)
    max_auth_age_seconds: int = Field(default=300, ge=0, le=86400)
    approval_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    justification_required: bool = True
    version: str = Field(default="1", min_length=1, max_length=64)
    _tenant_v = field_validator("tenant")(_tenant)

    @model_validator(mode="after")
    def validate_separation(self):
        if self.threshold > 1 and not self.distinct_humans:
            raise ValueError("multi-approval policies must require distinct humans")
        return self


class ApprovalReceiptIn(BaseModel):
    tenant: str
    request_id: str = Field(min_length=3, max_length=64)
    approver_principal: str = Field(min_length=3, max_length=64)
    decision: Literal["APPROVE", "REJECT"]
    request_digest: str = Field(min_length=16, max_length=128)
    auth_assurance: str = Field(max_length=64)
    auth_time: datetime
    justification: str = Field(min_length=3, max_length=4000)
    orgo_case_ref: str | None = Field(default=None, max_length=256)
    _tenant_v = field_validator("tenant")(_tenant)


class DispatchRequest(BaseModel):
    operator_principal: str | None = Field(default=None, max_length=64)


class ContactEndpointCreate(BaseModel):
    tenant: str
    principal_id: str = Field(min_length=3, max_length=64)
    type: str = Field(min_length=2, max_length=32)
    value_normalized: str = Field(min_length=1, max_length=512)
    verification_state: str = Field(default="UNVERIFIED", max_length=32)
    purpose: list[str] = Field(default_factory=list, max_length=32)
    valid_until: datetime | None = None
    _tenant_v = field_validator("tenant")(_tenant)


class RoleMailboxCreate(BaseModel):
    tenant: str
    address: str = Field(min_length=3, max_length=320)
    role_ref: str = Field(min_length=2, max_length=128)
    confidentiality_class: str = Field(default="INTERNAL", max_length=64)
    delivery_policy: dict[str, Any] = Field(default_factory=dict)
    _tenant_v = field_validator("tenant")(_tenant)

    @field_validator("delivery_policy")
    @classmethod
    def delivery_bounded(cls, v):
        return _bounded_json(v, max_bytes=16_384)


class RoleMailboxAssignmentCreate(BaseModel):
    tenant: str
    mailbox_id: str = Field(min_length=3, max_length=64)
    principal_id: str = Field(min_length=3, max_length=64)
    valid_until: datetime | None = None
    _tenant_v = field_validator("tenant")(_tenant)


class DetectorDefinitionCreate(BaseModel):
    tenant: str
    detector_id: str = Field(min_length=2, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    input_schema: str = Field(min_length=2, max_length=128)
    owner: str = Field(min_length=2, max_length=128)
    state: Literal["DRAFT", "QUALIFYING", "SHADOW", "CANARY", "ACTIVE", "REJECTED", "SUPERSEDED"] = "SHADOW"
    rollout: dict[str, Any] = Field(default_factory=dict)
    package_digest: str = Field(min_length=16, max_length=128)
    qualification_ref: str | None = Field(default=None, max_length=256)
    _tenant_v = field_validator("tenant")(_tenant)

    @field_validator("rollout")
    @classmethod
    def rollout_bounded(cls, v):
        return _bounded_json(v, max_bytes=16_384)


class IdentityResolveRequest(BaseModel):
    tenant: str
    issuer: str = Field(min_length=3, max_length=512)
    subject: str = Field(min_length=1, max_length=512)
    _tenant_v = field_validator("tenant")(_tenant)


class DetectionFeedbackIn(BaseModel):
    tenant: str
    analyst_principal: str = Field(min_length=3, max_length=64)
    classification: Literal["TRUE_POSITIVE", "FALSE_POSITIVE", "BENIGN_AUTHORIZED", "DETECTOR_BUG"]
    justification: str = Field(min_length=3, max_length=4000)
    _tenant_v = field_validator("tenant")(_tenant)


class DetectorQualificationIn(BaseModel):
    tenant: str
    qualification_ref: str = Field(min_length=3, max_length=512)
    _tenant_v = field_validator("tenant")(_tenant)
