# Konfid architecture

Konfid is a modular security control plane, not an identity provider or a universal administrator.

```text
IdP (Google/Entra/sovereign)
        |
        v
kOA Identity & Trust
        |
  stable Principal
     /       \
Konnaxion    Orgo
     \       /
       Konfid
  Directory / Access / Policy
  Overwatch / Response / Approval
  Evidence / Assurance
        |
kOA Policy + Audit
        |
Interaction Kernel
        |
local privileged enforcement
```

## Trust split

- IdPs authenticate humans.
- Applications own sessions and business data.
- Konfid maps principals to accounts, roles, grants, scopes and delegations.
- Governance Policy Runtime is the production policy authority when enabled.
- Overwatch creates risk signals only.
- Response Engine selects and coordinates minimal containment.
- Orgo coordinates human workflows; Konfid independently validates quorum.
- Local enforcement points execute allowlisted commands and return receipts.
- Audit Broker holds the authoritative evidence stream.

## Response ladder

`OBSERVE -> STEP_UP_AUTH -> RATE_LIMIT -> REVOKE_SESSION -> SUSPEND_GRANT -> SUSPEND_ACCOUNT -> ISOLATE_SERVICE -> FREEZE_SECURITY_DOMAIN -> FREEZE_TENANT -> EMERGENCY_SHUTDOWN`

Konfid should use the smallest response sufficient to contain the risk.

## Reliability

Distributed side effects use **at-least-once delivery + idempotency + receipts + reconciliation**. The transactional outbox persists approval requests and response commands before network delivery.
