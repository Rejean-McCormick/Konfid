from ..config import get_settings
from .http import JsonHttpAdapter

class OrgoAdapter:
    """Uses Orgo's existing generic Case API as the human coordination surface.

    Konfid remains the approval authority. An Orgo-side integration can submit the
    final human ApprovalReceipt back to Konfid; the case itself is never treated
    as authorization.
    """
    def __init__(self):
        s=get_settings(); self.url=s.orgo_url; self.org=s.orgo_organization_id; self.label=s.orgo_case_label
        self.http=JsonHttpAdapter(self.url,s.integration_secret("orgo"),{"X-Organization-ID":self.org}) if self.url and self.org else None
    def create_approval_case(self,request: dict):
        if not self.http: return None
        payload={
            "title":f"Konfid approval: {request['operation']}",
            "description":request.get("rationale","")[:20000],
            "label":self.label,
            "severity":"CRITICAL" if request["operation"] in {"FREEZE_TENANT","EMERGENCY_SHUTDOWN"} else "MAJOR",
            "source":"api",
            "metadata":{
                "konfid_approval_request_id":request["approval_request_id"],
                "request_digest":request["request_digest"],
                "operation":request["operation"],
                "target":request["target"],
                "threshold":request["threshold"],
                "policy_ref":request["policy_ref"],
                "expires_at":request["expires_at"],
            },
            "visibility":"RESTRICTED",
            "tags":["konfid","security","approval"],
            "location":{},
            "origin_role":"Konfid",
            "origin_vertical_level":0,
        }
        return self.http.post("/cases",payload,headers={"Idempotency-Key":request["approval_request_id"]})
