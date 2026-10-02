from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DetectorDefinition
from ..utils import new_id

ALLOWED_TRANSITIONS = {
    "DRAFT": {"QUALIFYING", "REJECTED"},
    "QUALIFYING": {"SHADOW", "REJECTED"},
    "SHADOW": {"CANARY", "REJECTED"},
    "CANARY": {"ACTIVE", "SHADOW", "REJECTED"},
    "ACTIVE": {"SUPERSEDED", "SHADOW"},
    "REJECTED": set(),
    "SUPERSEDED": set(),
}


def create_detector(db: Session, d):
    old = db.scalar(
        select(DetectorDefinition).where(
            DetectorDefinition.tenant == d.tenant,
            DetectorDefinition.detector_id == d.detector_id,
            DetectorDefinition.version == d.version,
        )
    )
    if old:
        raise HTTPException(409, "DETECTOR_VERSION_EXISTS")
    x = DetectorDefinition(id=new_id("DET"), **d.model_dump())
    db.add(x)
    db.flush()
    return x


def transition(db: Session, tenant: str, detector_id: str, new_state: str):
    x = db.get(DetectorDefinition, detector_id)
    if not x or x.tenant != tenant:
        raise HTTPException(404, "DETECTOR_NOT_FOUND")
    if new_state not in ALLOWED_TRANSITIONS.get(x.state, set()):
        raise HTTPException(409, "INVALID_DETECTOR_TRANSITION")
    if new_state in {"CANARY", "ACTIVE"} and not x.qualification_ref:
        raise HTTPException(409, "QUALIFICATION_REQUIRED")
    x.state = new_state
    db.flush()
    return x


def qualify(db: Session, tenant: str, definition_id: str, qualification_ref: str):
    x = db.get(DetectorDefinition, definition_id)
    if not x or x.tenant != tenant:
        raise HTTPException(404, "DETECTOR_NOT_FOUND")
    if x.state not in {"DRAFT", "QUALIFYING", "SHADOW"}:
        raise HTTPException(409, "DETECTOR_NOT_QUALIFIABLE_IN_STATE")
    x.qualification_ref = qualification_ref
    db.flush()
    return x
