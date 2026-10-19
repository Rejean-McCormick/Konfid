# Konfid — Tandem security tour 3/8 (2026-10-18)

## Source and authority

Based on the user-provided Konfid 0.3.0 snapshot; preserves the cross-system trust control plane and its development/production boundary. The common OIDC provider is external; Konfid is **not** an IdP. Konnaxion and Orgo keep their independent sessions and local authorization. A governed operation cannot override a Konfid/kOA deny.

## Confirmed in the source

- Tenant-scoped `Principal`, `IdentityBinding` by `(tenant, issuer, subject)` and `AccountBinding` by `(tenant, system, external_account_id)` already exist. Email is metadata, not the canonical identity key.
- Production validates separate asymmetric workload and actor JWTs, with caller-bound authorized party (`azp`/`client_id`), assurance and freshness. Development HMAC/wildcard shortcuts are rejected in production.
- The kOA Governance Policy Runtime is required in production; local policy is development-only. The audit/export/approval/outbox systems are already implemented.
- **Fixed here:** acceptance of kOA access `ALLOW` responses with no expiry or invalid/unbounded expiry. Positive results now require a future timezone-aware expiry within 60 seconds and nonempty decision/policy references; invalid replies become `BLOCKED`.

## Still to qualify on real tandem runtime (NOT claimed complete)

1. Determine one canonical mapping from FakePlant's Orgo organization UUID to Konfid `tenant`, and keep Konnaxion Universe/World identifiers separate.
2. Configure and test the actual shared external OIDC issuer; provision **one human test principal** and explicit bindings to the two apps. Do not auto-provision the 900 synthetic personas as interactive humans.
3. Test the two distinct workload JWTs and signed actor assertions (tenant, issuer, sub, jti, assurance, auth_time, azp/client_id) with real JWKS trust anchors. Keep production enforcement **disabled** until qualification.
4. Verify kOA decisions `ALLOW`, `DENY`, `STEP_UP_REQUIRED`, `APPROVAL_REQUIRED`, `BLOCKED`, obligations and failure behavior through the actual application PEPs.
5. Verify kOA Audit Broker export and IK receipts for governed operations, with scoped least-privilege tokens.
6. Run PostgreSQL concurrency tests, real staging policy integration, authorization-boundary tests and security review before claiming production readiness.

This patch does not create Principals, bindings, grants, tenants, secrets, configurations or migrations. No Orgo, Konnaxion, Neon or FakePlant database is touched. Version remains 0.3.0 pending independent release management.
