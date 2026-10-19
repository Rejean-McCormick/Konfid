"""Tandem tour 3/8: fail-closed handling of positive kOA policy decisions.

No network, no kOA service, no Orgo/Konnaxion database access.
"""
from datetime import datetime, timedelta, timezone

import pytest

from konfid.adapters.policy import KoaPolicyEngine
from konfid.schemas import AccessRequest


def _request():
    return AccessRequest(
        request_id="tandem-read-1", tenant="fakeplant-test", actor="P-demo",
        action="world.read", resource={"owner": "konnaxion", "class": "WORLD"},
        scope={"organization": "fakeplant-test"},
    )


def _decision(decision="ALLOW", valid_until=None):
    body = {
        "decision_id": "PD-tandem-test", "decision": decision,
        "policy": "koa/governance-test/1", "reason_codes": ["TEST_POLICY"],
    }
    if valid_until is not None:
        body["valid_until"] = valid_until.isoformat() if isinstance(valid_until, datetime) else valid_until
    return body


def _evaluate(monkeypatch, body):
    engine = KoaPolicyEngine("https://policy.example.test")
    monkeypatch.setattr(engine.http, "post", lambda *args, **kwargs: body)
    return engine.evaluate_access(None, _request())


def test_short_lived_koa_policy_allow_is_preserved(monkeypatch):
    expiry = datetime.now(timezone.utc) + timedelta(seconds=30)
    result = _evaluate(monkeypatch, _decision(valid_until=expiry))
    assert result.decision == "ALLOW"
    assert result.valid_until is not None


@pytest.mark.parametrize("expiry", [
    None,
    "2020-01-01T00:00:00+00:00",
    "2100-01-01T00:00:00+00:00",
    "2030-01-01T00:00:00",  # naive timestamps are not an authenticated expiry
    "not-a-date",
])
def test_malformed_or_unbounded_allow_is_blocked(monkeypatch, expiry):
    result = _evaluate(monkeypatch, _decision(valid_until=expiry))
    assert result.decision == "BLOCKED"
    assert result.reason_codes == ["POLICY_RESPONSE_INVALID"]


def test_allow_expiring_beyond_one_minute_is_blocked(monkeypatch):
    expiry = datetime.now(timezone.utc) + timedelta(seconds=61)
    result = _evaluate(monkeypatch, _decision(valid_until=expiry))
    assert result.decision == "BLOCKED"


def test_regular_deny_does_not_require_expiry(monkeypatch):
    result = _evaluate(monkeypatch, _decision(decision="DENY"))
    assert result.decision == "DENY"


def test_nonempty_decision_id_and_policy_required(monkeypatch):
    body = _decision(valid_until=datetime.now(timezone.utc) + timedelta(seconds=30))
    body["policy"] = ""
    assert _evaluate(monkeypatch, body).decision == "BLOCKED"
    body["policy"] = "koa/1"
    body["decision_id"] = ""
    assert _evaluate(monkeypatch, body).decision == "BLOCKED"


def test_extra_long_reason_codes_are_blocked(monkeypatch):
    body = _decision(decision="DENY")
    body["reason_codes"] = ["x" * 129]
    assert _evaluate(monkeypatch, body).decision == "BLOCKED"


def test_koa_response_does_not_expand_scope(monkeypatch):
    expiry = datetime.now(timezone.utc) + timedelta(seconds=20)
    body = _decision(valid_until=expiry)
    result = _evaluate(monkeypatch, body)
    assert result.decision == "ALLOW"
    assert result.policy == "koa/governance-test/1"
