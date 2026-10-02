from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..metrics import RISK_SIGNALS
from ..models import DetectionFeedback, DetectorDefinition, Principal, RiskSignal, SecurityEvent
from ..schemas import DetectionFeedbackIn, RiskSignalIn, SecurityEventIn
from ..utils import as_utc_naive, new_id, utcnow

SCORES = {"low": 20, "medium": 45, "high": 75, "critical": 95}


def _signal(tenant, subject, target, severity, detector, version, reasons, score=None, confidence=None, evidence=None, ttl=None):
    now = utcnow()
    sig = RiskSignal(
        id=new_id("RS"),
        tenant=tenant,
        subject_ref=subject,
        target_ref=target,
        severity=severity,
        score=score if score is not None else SCORES[severity],
        confidence=confidence,
        detector_id=detector,
        detector_version=version,
        reason_codes=reasons,
        evidence_refs=evidence or [],
        observed_at=now,
        expires_at=now + timedelta(seconds=ttl or get_settings().risk_signal_ttl_seconds),
    )
    return sig


def _detector_allowed(db: Session, d: RiskSignalIn) -> None:
    if get_settings().dev_mode:
        return
    detector = db.scalar(
        select(DetectorDefinition).where(
            DetectorDefinition.tenant == d.tenant,
            DetectorDefinition.detector_id == d.detector_id,
            DetectorDefinition.version == d.detector_version,
        )
    )
    if not detector:
        raise HTTPException(409, "DETECTOR_NOT_REGISTERED")
    if detector.state not in {"CANARY", "ACTIVE"}:
        raise HTTPException(409, "DETECTOR_NOT_ACTIVE")


def create_signal(db: Session, d: RiskSignalIn):
    _detector_allowed(db, d)
    s = _signal(
        d.tenant,
        d.subject_ref,
        d.target_ref,
        d.severity,
        d.detector_id,
        d.detector_version,
        d.reason_codes,
        d.score,
        d.confidence,
        d.evidence_refs,
        d.ttl_seconds,
    )
    db.add(s)
    db.flush()
    RISK_SIGNALS.labels(severity=s.severity, detector=s.detector_id).inc()
    return s


def record_event(db: Session, d: SecurityEventIn, caller: str):
    e = SecurityEvent(
        id=new_id("SE"),
        tenant=d.tenant,
        subject_ref=d.subject_ref,
        caller_service=caller,
        event_type=d.event_type,
        action=d.action,
        resource_class=d.resource_class,
        count=d.count,
        metadata_json=d.metadata,
        occurred_at=as_utc_naive(d.occurred_at) or utcnow(),
    )
    db.add(e)
    db.flush()
    signals = []
    if (
        d.subject_ref
        and d.action
        and d.action.endswith(".read")
        and d.resource_class
        and ("MEDICAL" in d.resource_class or "RESTRICTED" in d.resource_class)
    ):
        since = utcnow() - timedelta(seconds=120)
        total = db.scalar(
            select(func.coalesce(func.sum(SecurityEvent.count), 0)).where(
                SecurityEvent.tenant == d.tenant,
                SecurityEvent.subject_ref == d.subject_ref,
                SecurityEvent.resource_class == d.resource_class,
                SecurityEvent.action == d.action,
                SecurityEvent.occurred_at >= since,
            )
        ) or 0
        if total >= 400:
            s = _signal(
                d.tenant,
                d.subject_ref,
                None,
                "critical",
                "builtin.bulk-sensitive-read",
                "1",
                ["SENSITIVE_READ_BURST"],
                95,
                1.0,
            )
            db.add(s)
            signals.append(s)
            RISK_SIGNALS.labels(severity="critical", detector="builtin.bulk-sensitive-read").inc()
    db.flush()
    return e, signals


def add_feedback(db: Session, signal_id: str, d: DetectionFeedbackIn):
    sig = db.get(RiskSignal, signal_id)
    if not sig or sig.tenant != d.tenant:
        raise HTTPException(404, "RISK_SIGNAL_NOT_FOUND")
    analyst = db.get(Principal, d.analyst_principal)
    if not analyst or analyst.tenant != d.tenant or analyst.status != "ACTIVE" or analyst.type != "HUMAN":
        raise HTTPException(403, "ANALYST_NOT_ACTIVE_HUMAN")
    f = DetectionFeedback(
        id=new_id("DFB"),
        tenant=d.tenant,
        risk_signal_id=sig.id,
        analyst_principal=d.analyst_principal,
        classification=d.classification,
        justification=d.justification,
    )
    db.add(f)
    db.flush()
    return f
