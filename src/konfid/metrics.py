from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "konfid_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "konfid_http_request_duration_seconds", "HTTP request latency", ["method", "route"]
)
AUTHZ_DECISIONS = Counter(
    "konfid_authorization_decisions_total", "Authorization decisions", ["decision"]
)
RISK_SIGNALS = Counter(
    "konfid_risk_signals_total", "Risk signals created", ["severity", "detector"]
)
RESPONSE_ACTIONS = Counter(
    "konfid_response_actions_total", "Response actions by state", ["operation", "state"]
)
OUTBOX_PENDING = Gauge("konfid_outbox_pending", "Pending outbox events")
OUTBOX_DEAD = Gauge("konfid_outbox_dead_letter", "Dead-lettered outbox events")
AUDIT_PENDING = Gauge("konfid_audit_pending_export", "Audit records awaiting export")
