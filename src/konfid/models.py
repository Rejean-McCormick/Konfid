from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .utils import utcnow


class Principal(Base):
    __tablename__ = "principals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    type: Mapped[str] = mapped_column(String(32), default="HUMAN")
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    risk_state: Mapped[str] = mapped_column(String(32), default="NORMAL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IdentityBinding(Base):
    __tablename__ = "identity_bindings"
    __table_args__ = (
        UniqueConstraint("tenant", "issuer", "subject", name="uq_identity_tenant_issuer_subject"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id", ondelete="CASCADE"), index=True)
    provider_type: Mapped[str] = mapped_column(String(32))
    issuer: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(512))
    email_hint: Mapped[str | None] = mapped_column(String(320), nullable=True)
    assurance_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    linked_by: Mapped[str] = mapped_column(String(128))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AccountBinding(Base):
    __tablename__ = "account_bindings"
    __table_args__ = (
        UniqueConstraint("tenant", "system", "external_account_id", name="uq_account_binding"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id", ondelete="CASCADE"), index=True)
    system: Mapped[str] = mapped_column(String(128))
    external_account_id: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContactEndpoint(Base):
    __tablename__ = "contact_endpoints"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    value_normalized: Mapped[str] = mapped_column(String(512))
    verification_state: Mapped[str] = mapped_column(String(32), default="UNVERIFIED")
    purpose: Mapped[list[str]] = mapped_column(JSON, default=list)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResourceClass(Base):
    __tablename__ = "resource_classes"
    __table_args__ = (
        UniqueConstraint("tenant", "owner_system", "name", name="uq_resource_class"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    owner_system: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(256))
    classification: Mapped[str] = mapped_column(String(64), default="INTERNAL")
    supported_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    attributes_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    policy_namespace: Mapped[str] = mapped_column(String(128), default="default")


class Grant(Base):
    __tablename__ = "grants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    subject_ref: Mapped[str] = mapped_column(String(64), index=True)
    role_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    resource_classes: Mapped[list[str]] = mapped_column(JSON, default=list)
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_by: Mapped[str] = mapped_column(String(128))
    policy_version: Mapped[str] = mapped_column(String(128), default="local/1")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)


class Delegation(Base):
    __tablename__ = "delegations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    from_principal: Mapped[str] = mapped_column(String(64), index=True)
    to_principal: Mapped[str] = mapped_column(String(64), index=True)
    actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    resource_classes: Mapped[list[str]] = mapped_column(JSON, default=list)
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_chain_depth: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(Text)
    issued_by: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)


class RoleMailbox(Base):
    __tablename__ = "role_mailboxes"
    __table_args__ = (UniqueConstraint("tenant", "address", name="uq_role_mailbox"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    address: Mapped[str] = mapped_column(String(320))
    role_ref: Mapped[str] = mapped_column(String(128))
    confidentiality_class: Mapped[str] = mapped_column(String(64), default="INTERNAL")
    delivery_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RoleMailboxAssignment(Base):
    __tablename__ = "role_mailbox_assignments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    mailbox_id: Mapped[str] = mapped_column(ForeignKey("role_mailboxes.id", ondelete="CASCADE"), index=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id", ondelete="CASCADE"), index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class DetectorDefinition(Base):
    __tablename__ = "detector_definitions"
    __table_args__ = (
        UniqueConstraint("tenant", "detector_id", "version", name="uq_detector_version"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    detector_id: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(64))
    input_schema: Mapped[str] = mapped_column(String(128))
    owner: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(32), default="SHADOW")
    rollout: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    package_digest: Mapped[str] = mapped_column(String(128))
    qualification_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)


class SecurityEvent(Base):
    __tablename__ = "security_events"
    __table_args__ = (Index("ix_event_subject_time", "tenant", "subject_ref", "occurred_at"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    subject_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    caller_service: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str | None] = mapped_column(String(256), nullable=True)
    resource_class: Mapped[str | None] = mapped_column(String(256), nullable=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RiskSignal(Base):
    __tablename__ = "risk_signals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    subject_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    target_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    detector_id: Mapped[str] = mapped_column(String(128))
    detector_version: Mapped[str] = mapped_column(String(64))
    reason_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")


class DetectionFeedback(Base):
    __tablename__ = "detection_feedback"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    risk_signal_id: Mapped[str] = mapped_column(ForeignKey("risk_signals.id", ondelete="CASCADE"), index=True)
    analyst_principal: Mapped[str] = mapped_column(String(64), index=True)
    classification: Mapped[str] = mapped_column(String(32), index=True)
    justification: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApprovalPolicy(Base):
    __tablename__ = "approval_policies"
    __table_args__ = (UniqueConstraint("tenant", "operation", name="uq_approval_operation"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    operation: Mapped[str] = mapped_column(String(128))
    threshold: Mapped[int] = mapped_column(Integer, default=1)
    eligible_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    distinct_humans: Mapped[bool] = mapped_column(Boolean, default=True)
    requester_may_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    operator_may_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    operator_required: Mapped[bool] = mapped_column(Boolean, default=False)
    required_assurance: Mapped[str] = mapped_column(String(64), default="mfa")
    max_auth_age_seconds: Mapped[int] = mapped_column(Integer, default=300)
    approval_ttl_seconds: Mapped[int] = mapped_column(Integer, default=900)
    justification_required: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[str] = mapped_column(String(64), default="1")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    requester_principal: Mapped[str] = mapped_column(String(64), index=True)
    operation: Mapped[str] = mapped_column(String(128))
    target: Mapped[str] = mapped_column(String(256))
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_digest: Mapped[str] = mapped_column(String(128), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    policy_ref: Mapped[str] = mapped_column(String(128))
    threshold: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32), default="OPEN", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ApprovalReceipt(Base):
    __tablename__ = "approval_receipts"
    __table_args__ = (
        UniqueConstraint("request_id", "approver_principal", name="uq_approval_approver"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("approval_requests.id", ondelete="CASCADE"), index=True)
    approver_principal: Mapped[str] = mapped_column(String(64), index=True)
    decision: Mapped[str] = mapped_column(String(16))
    request_digest: Mapped[str] = mapped_column(String(128))
    auth_assurance: Mapped[str] = mapped_column(String(64))
    auth_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    justification: Mapped[str] = mapped_column(Text)
    policy_ref: Mapped[str] = mapped_column(String(128))
    orgo_case_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)


class ResponseAction(Base):
    __tablename__ = "response_actions"
    __table_args__ = (UniqueConstraint("tenant", "idempotency_key", name="uq_response_idem"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    requester_principal: Mapped[str] = mapped_column(String(64), index=True)
    risk_signal_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    operation: Mapped[str] = mapped_column(String(128), index=True)
    target: Mapped[str] = mapped_column(String(256))
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rationale: Mapped[str] = mapped_column(Text)
    requester_auth_assurance: Mapped[str] = mapped_column(String(64), default="unknown")
    requester_auth_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="PROPOSED", index=True)
    decision_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approval_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    operator_principal: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_receipt: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("tenant", "topic", "aggregate_ref", name="uq_outbox_topic_aggregate"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    topic: Mapped[str] = mapped_column(String(256), index=True)
    aggregate_ref: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=12)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditHead(Base):
    __tablename__ = "audit_heads"
    tenant: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
    last_digest: Mapped[str] = mapped_column(String(128), default="GENESIS")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditRecord(Base):
    __tablename__ = "audit_records"
    __table_args__ = (UniqueConstraint("tenant", "sequence", name="uq_audit_tenant_sequence"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(128), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    format_version: Mapped[int] = mapped_column(Integer, default=3)
    actor_principal: Mapped[str | None] = mapped_column(String(64), nullable=True)
    caller_service: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(256), index=True)
    target_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    outcome: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[str] = mapped_column(String(128), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    event_digest: Mapped[str] = mapped_column(String(128))
    prev_digest: Mapped[str] = mapped_column(String(128))
    chain_digest: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    exported: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    export_attempts: Mapped[int] = mapped_column(Integer, default=0)
    export_next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=True, index=True)
    export_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    export_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    bucket_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
