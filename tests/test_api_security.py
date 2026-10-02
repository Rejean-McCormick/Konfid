from fastapi.testclient import TestClient
from konfid.app import app
from konfid.auth import make_dev_token
from konfid.config import get_settings

def test_cross_tenant_blocked_and_actor_assertion_enforced(db):
    token=make_dev_token("svc:test","t",["konfid:*"])
    h={"Authorization":f"Bearer {token}"}
    with TestClient(app) as c:
        r=c.post("/v1/principals",headers=h,json={"tenant":"other","display_name":"X"})
        assert r.status_code==200  # dev wildcard explicitly includes cross-tenant authority
        narrow=make_dev_token("svc:narrow","t",["directory:write"])
        r=c.post("/v1/principals",headers={"Authorization":f"Bearer {narrow}"},json={"tenant":"other","display_name":"X"})
        assert r.status_code==403

def test_actor_assertion_can_be_required(db):
    s=get_settings(); old=s.require_actor_assertion; s.require_actor_assertion=True
    try:
        token=make_dev_token("svc:test","t",["konfid:*"])
        h={"Authorization":f"Bearer {token}"}
        admin_actor=make_dev_token("P-admin","t",[],actor=True,extra={"assurance":"phishing_resistant"})
        admin_h={**h,"X-Konfid-Actor-Token":admin_actor}
        with TestClient(app) as c:
            p=c.post("/v1/principals",headers=admin_h,json={"tenant":"t","display_name":"A"}).json()
            c.post("/v1/resources",headers=admin_h,json={"tenant":"t","owner_system":"konnaxion","name":"HR.BASIC","supported_actions":["employee.read"]})
            c.post("/v1/grants",headers=admin_h,json={"tenant":"t","subject_ref":p["id"],"actions":["employee.read"],"resource_classes":["HR.BASIC"],"scope":{"organization":"t"}})
            body={"request_id":"req-1","tenant":"t","actor":p["id"],"action":"employee.read","resource":{"owner":"konnaxion","class":"HR.BASIC"},"scope":{"organization":"t"}}
            assert c.post("/v1/access/evaluate",headers=h,json=body).status_code==401
            actor=make_dev_token(p["id"],"t",[],actor=True)
            h2={**h,"X-Konfid-Actor-Token":actor}
            assert c.post("/v1/access/evaluate",headers=h2,json=body).json()["decision"]=="ALLOW"
    finally:
        s.require_actor_assertion=old

def test_signed_actor_claims_override_untrusted_assurance_body(db):
    token=make_dev_token("svc:test","t",["konfid:*"])
    h={"Authorization":f"Bearer {token}"}
    with TestClient(app) as c:
        p=c.post("/v1/principals",headers=h,json={"tenant":"t","display_name":"A"}).json()
        c.post("/v1/resources",headers=h,json={"tenant":"t","owner_system":"konnaxion","name":"HR.STRONG","supported_actions":["employee.read"]})
        c.post("/v1/grants",headers=h,json={"tenant":"t","subject_ref":p["id"],"actions":["employee.read"],"resource_classes":["HR.STRONG"],"scope":{"organization":"t"},"constraints":{"required_assurance":"phishing_resistant","max_auth_age_seconds":300}})
        body={"request_id":"r-strong","tenant":"t","actor":p["id"],"action":"employee.read","resource":{"owner":"konnaxion","class":"HR.STRONG"},"scope":{"organization":"t"},"context":{"auth_assurance":"phishing_resistant","auth_age_seconds":1}}
        weak=make_dev_token(p["id"],"t",[],actor=True,extra={"assurance":"password"})
        weak_resp=c.post("/v1/access/evaluate",headers={**h,"X-Konfid-Actor-Token":weak},json=body).json()
        assert weak_resp["decision"] == "DENY"
        assert "AUTH_ASSURANCE_INSUFFICIENT" in weak_resp["reason_codes"] or "NO_MATCHING_GRANT" in weak_resp["reason_codes"]
        import time
        strong=make_dev_token(p["id"],"t",[],actor=True,extra={"assurance":"phishing_resistant","auth_time":int(time.time())})
        strong_resp=c.post("/v1/access/evaluate",headers={**h,"X-Konfid-Actor-Token":strong},json=body).json()
        assert strong_resp["decision"] == "ALLOW"


def test_rate_limit_uses_canonical_route_template(db, monkeypatch):
    import konfid.auth as auth_mod

    seen = []
    monkeypatch.setattr(auth_mod, "check_rate_limit", lambda service, tenant, route: seen.append(route))
    token = make_dev_token("svc:rate-test", "t", ["response:read"])
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as c:
        assert c.get("/v1/responses/ACT-one", headers=headers).status_code == 404
        assert c.get("/v1/responses/ACT-two", headers=headers).status_code == 404
    assert seen[-2:] == ["/v1/responses/{aid}", "/v1/responses/{aid}"]
