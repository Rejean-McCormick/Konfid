# Security policy

Konfid is security-critical software. Do not disclose suspected vulnerabilities in a public issue before coordinated disclosure with the deployment owner/maintainers.

## Non-negotiable invariants

- Konfid does not store or verify human passwords.
- Email is not canonical identity; federated identity uses stable `issuer + subject` bindings.
- Workload identity and human actor identity are separate and preserved together.
- Production human actor assertions are cryptographically verified and bound to the caller service.
- Session validity is not equivalent to authorization.
- Unknown, stale or unavailable critical authority never becomes implicit allow.
- Grants and delegations are scoped; delegation cannot expand authority.
- A detector emits a `RiskSignal`; it has no enforcement credential.
- False-positive feedback cannot directly weaken policy or detector configuration.
- Privileged actions are typed, allowlisted by the enforcement boundary, scoped, expiring and idempotent.
- High-impact actions use governed approval policies, distinct humans where configured, request-digest binding and fresh authorization.
- The operator is independently validated for policies that require one.
- HTTP dispatch records intent; a durable worker performs external effects.
- Outbox workers reconstruct privileged commands from canonical state and reject payload-integrity mismatches.
- Critical external effects produce a validated receipt or remain explicitly uncertain.
- No production wildcard `konfid:*` credential is allowed.
- Audit/evidence must not contain bearer tokens, passwords or arbitrary sensitive payloads.
- Security mutations and local audit evidence should commit atomically.
- Local audit is hash-chained per tenant and exported to a separately governed authoritative Audit Broker.

## Production fail-closed requirements

`KONFID_DEV_MODE=false` requires, at minimum:

- PostgreSQL;
- non-development environment designation;
- exact trusted-host configuration (no `*`);
- asymmetric workload and actor JWT algorithms;
- workload + actor JWKS trust endpoints over HTTPS;
- actor assertion and caller-binding requirements;
- kOA Policy Runtime;
- kOA Audit Broker;
- Interaction Kernel enforcement;
- rate limiting;
- authenticated or disabled metrics;
- authenticated service integration using a bearer secret and/or mTLS;
- valid configured TLS files.

The development HMAC token, local policy engine and local enforcement adapter must never be enabled as production fallback.

## Changes requiring explicit security review

- authentication/JWKS validation;
- principal linking;
- tenant isolation;
- grant/delegation semantics;
- policy adapter/decision handling;
- approval/quorum/operator rules;
- response state machine;
- outbox/reconciliation/idempotence;
- privileged command or receipt schema;
- audit chaining/export;
- detector-to-response mappings;
- key/credential/TLS handling;
- database migrations affecting security state.

## Operational security

See `docs/PRODUCTION.md` and `docs/RUNBOOK.md`. Production deployment is not complete until the real organization has validated network isolation, IdP and service trust anchors, secret rotation, PostgreSQL backup/restore, kOA/Orgo/Interaction Kernel contracts, load/fault behavior and incident procedures.
