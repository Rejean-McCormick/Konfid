"""The kOA native typed policy API is not an implicit /v1/evaluate adapter.

These tests deliberately do not declare that a live bilateral transport exists.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from konfid.adapters.policy import KoaPolicyEngine
from konfid.schemas import AccessRequest


def _request():
    return AccessRequest(
        request_id="req-branch08", tenant="tenant-branch08", actor="principal-branch08",
        action="world.read", resource={"owner": "konnaxion", "class": "WORLD"},
        scope={"organization": "tenant-branch08"},
    )


def test_native_governance_policy_response_is_not_misread_as_an_access_allow(monkeypatch):
    # Source shape from kOA-Linux GovernancePolicyRuntimeApi.dispatch; it is
    # deliberately not Konfid's AccessResponse envelope.
    raw = {
        "request_id": "req-branch08", "correlation_id": "corr-branch08",
        "interface_id": "evaluate_decision", "outcome": "succeeded", "version": "1.0.0",
        "terminal": True,
        "result": {"result": "allow", "policy_set_ref": "set-demo", "authority_version": "v1"},
    }
    engine = KoaPolicyEngine("https://policy.invalid")
    monkeypatch.setattr(engine.http, "post", lambda *_args, **_kwargs: raw)
    result = engine.evaluate_access(None, _request())
    assert result.decision == "BLOCKED"
    assert result.reason_codes == ["POLICY_RESPONSE_INVALID"]


def test_konfid_requires_short_lived_policy_allow_after_any_future_adapter(monkeypatch):
    raw = {
        "decision_id": "decision-branch08", "decision": "ALLOW", "policy": "policy-branch08",
        "valid_until": (datetime.now(timezone.utc) + timedelta(seconds=65)).isoformat(),
        "reason_codes": [], "obligations": [],
    }
    engine = KoaPolicyEngine("https://policy.invalid")
    monkeypatch.setattr(engine.http, "post", lambda *_args, **_kwargs: raw)
    assert engine.evaluate_access(None, _request()).decision == "BLOCKED"
