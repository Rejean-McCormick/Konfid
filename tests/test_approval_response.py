import pytest
from fastapi import HTTPException

from konfid.models import ApprovalRequest
from konfid.schemas import ApprovalReceiptIn, GrantCreate, PrincipalCreate, ResponseProposalIn, RiskSignalIn
from konfid.services import access, approval, directory, overwatch, response
from konfid.services.bootstrap import bootstrap_tenant
from konfid.services.outbox import process_pending
from konfid.utils import utcnow


def make_person(db, name):
    return directory.create_principal(db, PrincipalCreate(tenant="t", display_name=name))


def grant_role(db, p, role, actions):
    return access.create_grant(
        db,
        GrantCreate(
            tenant="t",
            subject_ref=p.id,
            role_ref=role,
            actions=actions,
            resource_classes=["SECURITY.RESPONSE"],
            scope={"organization": "t"},
        ),
        "svc",
    )


def approve(db, req, principal):
    return approval.add_receipt(
        db,
        ApprovalReceiptIn(
            tenant="t",
            request_id=req.id,
            approver_principal=principal.id,
            decision="APPROVE",
            request_digest=req.request_digest,
            auth_assurance="phishing_resistant",
            auth_time=utcnow(),
            justification="independent review",
        ),
    )


def test_self_approval_forbidden_and_two_distinct_approvers_required(db):
    bootstrap_tenant(db, "t")
    requester = make_person(db, "Requester")
    a = make_person(db, "A")
    b = make_person(db, "B")
    operator = make_person(db, "Operator")
    grant_role(db, requester, "SECURITY_OPERATOR", ["security.response.freeze_tenant"])
    for p in (a, b, operator):
        grant_role(db, p, "SECURITY_EXECUTIVE", ["noop"])

    act = response.propose(
        db,
        ResponseProposalIn(
            tenant="t",
            requester_principal=requester.id,
            target="tenant:t",
            scope={"organization": "t"},
            requested_operation="FREEZE_TENANT",
            rationale="credible compromise",
            idempotency_key="freeze-one",
        ),
    )
    assert act.state == "APPROVAL_PENDING"
    req = db.get(ApprovalRequest, act.approval_request_id)

    with pytest.raises(HTTPException) as exc:
        approval.add_receipt(
            db,
            ApprovalReceiptIn(
                tenant="t",
                request_id=req.id,
                approver_principal=requester.id,
                decision="APPROVE",
                request_digest=req.request_digest,
                auth_assurance="phishing_resistant",
                auth_time=utcnow(),
                justification="approve",
            ),
        )
    assert exc.value.detail == "SELF_APPROVAL_FORBIDDEN"

    _, r1 = approve(db, req, a)
    assert r1.state == "PARTIALLY_APPROVED"
    _, r2 = approve(db, req, b)
    assert r2.state == "APPROVED"

    queued = response.dispatch(
        db,
        act.id,
        operator=operator.id,
        operator_assurance="phishing_resistant",
        operator_auth_age_seconds=10,
    )
    assert queued.state == "DISPATCHED"
    db.commit()
    process_pending(db, worker_id="test-worker")
    db.refresh(queued)
    assert queued.state == "EXECUTED"
    assert queued.final_receipt["action_id"] == act.id


def test_response_proposal_and_dispatch_are_idempotent(db):
    bootstrap_tenant(db, "t")
    p = make_person(db, "Requester")
    grant_role(db, p, "SECURITY_OPERATOR", ["security.response.suspend_grant"])
    sig = overwatch.create_signal(
        db,
        RiskSignalIn(
            tenant="t",
            subject_ref=p.id,
            severity="critical",
            detector_id="detector-d",
            detector_version="1",
            reason_codes=["X"],
        ),
    )
    body = ResponseProposalIn(
        tenant="t",
        requester_principal=p.id,
        risk_signal_ids=[sig.id],
        target="grant:G1",
        scope={"organization": "t"},
        requested_operation="SUSPEND_GRANT",
        rationale="contain",
        idempotency_key="idem-0001",
    )
    a = response.propose(db, body)
    b = response.propose(db, body)
    assert a.id == b.id and a.state == "AUTHORIZED"
    first = response.dispatch(db, a.id)
    second = response.dispatch(db, a.id)
    assert first.id == second.id
    assert second.state == "DISPATCHED"
    db.commit()
    process_pending(db, worker_id="test-worker")
    db.refresh(second)
    assert second.state == "EXECUTED"


def test_operator_cannot_be_an_approver_when_policy_forbids_it(db):
    bootstrap_tenant(db, "t")
    requester = make_person(db, "Requester")
    a = make_person(db, "A")
    b = make_person(db, "B")
    operator = make_person(db, "Independent Operator")
    grant_role(db, requester, "SECURITY_OPERATOR", ["security.response.freeze_tenant"])
    for p in (a, b, operator):
        grant_role(db, p, "SECURITY_EXECUTIVE", ["noop"])
    act = response.propose(
        db,
        ResponseProposalIn(
            tenant="t",
            requester_principal=requester.id,
            target="tenant:t",
            scope={"organization": "t"},
            requested_operation="FREEZE_TENANT",
            rationale="credible compromise",
            idempotency_key="operator-separation",
        ),
    )
    req = db.get(ApprovalRequest, act.approval_request_id)
    for approver in (a, b):
        approve(db, req, approver)

    with pytest.raises(HTTPException) as exc:
        response.dispatch(
            db,
            act.id,
            operator=a.id,
            operator_assurance="phishing_resistant",
            operator_auth_age_seconds=10,
        )
    assert exc.value.detail == "OPERATOR_APPROVER_SEPARATION_REQUIRED"

    assert response.dispatch(
        db,
        act.id,
        operator=operator.id,
        operator_assurance="phishing_resistant",
        operator_auth_age_seconds=10,
    ).state == "DISPATCHED"


def test_quorum_is_revalidated_at_dispatch_after_approver_authority_revoked(db):
    bootstrap_tenant(db, "t")
    requester = make_person(db, "Requester-Q")
    a = make_person(db, "Approver-A-Q")
    b = make_person(db, "Approver-B-Q")
    operator = make_person(db, "Operator-Q")
    grant_role(db, requester, "SECURITY_OPERATOR", ["security.response.freeze_tenant"])
    grant_role(db, a, "SECURITY_EXECUTIVE", ["noop"])
    b_grant = grant_role(db, b, "SECURITY_EXECUTIVE", ["noop"])
    grant_role(db, operator, "SECURITY_EXECUTIVE", ["noop"])

    act = response.propose(
        db,
        ResponseProposalIn(
            tenant="t", requester_principal=requester.id, target="tenant:t",
            scope={"organization": "t"}, requested_operation="FREEZE_TENANT",
            rationale="quorum revalidation", idempotency_key="quorum-revalidate",
        ),
    )
    req = db.get(ApprovalRequest, act.approval_request_id)
    approve(db, req, a)
    approve(db, req, b)
    response.authorize_after_approval(db, act)
    assert act.state == "AUTHORIZED"

    b_grant.status = "REVOKED"
    db.flush()
    with pytest.raises(HTTPException) as exc:
        response.dispatch(
            db, act.id, operator=operator.id,
            operator_assurance="phishing_resistant", operator_auth_age_seconds=10,
        )
    assert exc.value.detail == "APPROVAL_QUORUM_NO_LONGER_VALID"
