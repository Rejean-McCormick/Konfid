from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ApprovalPolicy
from ..utils import new_id

DEFAULTS = [
    ("ISOLATE_SERVICE", 1, ["SECURITY_OFFICER"], True),
    ("FREEZE_SECURITY_DOMAIN", 2, ["SECURITY_OFFICER", "SECURITY_EXECUTIVE"], True),
    ("FREEZE_TENANT", 2, ["SECURITY_EXECUTIVE"], True),
    ("EMERGENCY_SHUTDOWN", 2, ["SECURITY_EXECUTIVE"], True),
]


def bootstrap_tenant(db: Session, tenant: str):
    out = []
    for op, n, roles, operator_required in DEFAULTS:
        p = db.scalar(
            select(ApprovalPolicy).where(
                ApprovalPolicy.tenant == tenant,
                ApprovalPolicy.operation == op,
            )
        )
        if not p:
            p = ApprovalPolicy(
                id=new_id("APOL"),
                tenant=tenant,
                operation=op,
                threshold=n,
                eligible_roles=roles,
                distinct_humans=True,
                requester_may_approve=False,
                operator_may_approve=False,
                operator_required=operator_required,
                required_assurance="phishing_resistant",
                max_auth_age_seconds=300,
                approval_ttl_seconds=900,
                justification_required=True,
                version="1",
            )
            db.add(p)
        out.append(p)
    db.flush()
    return out
