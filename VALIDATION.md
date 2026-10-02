# Validation status — Konfid 0.3.0

This file records what was **actually validated** in the generation environment and what still requires execution in the target CI/production environment. Konfid 0.3.0 is a **production-candidate reference implementation**, not an independent security certification.

## Locally validated

- Python security/invariant suite: **36 PASS / 2 SKIPPED**.
  - The two skipped tests require real PostgreSQL row/advisory locking and are wired into the PostgreSQL CI job.
- Python source compilation (`src` + `tests`): **PASS**.
- Fresh Alembic `upgrade head` on SQLite: **PASS**.
- Alembic `downgrade base -> upgrade head` structural round-trip: **PASS**.
- `alembic check` model/schema drift check at head: **PASS** (`No new upgrade operations detected`).
- Current migration head: **`e61c8a7d2f04`**.
- OpenAPI generation/parsing: **PASS**.
- OpenAPI surface: **41 paths / 45 HTTP operations**, version **0.3.0**.
- YAML/JSON parsing for repository deployment/workflow/example artifacts: **PASS**.
- Python wheel build: **PASS** (`konfid-0.3.0-py3-none-any.whl`).
- Wheel import smoke test from an isolated target path, outside the source tree: **PASS**.
- Production Settings validation tests: **PASS**, including fail-closed trust dependency requirements.

## Security invariants covered by the local suite

The suite includes checks for:

- email is not canonical identity;
- tenant-separated identity bindings;
- cross-tenant request rejection;
- human actor assertion enforcement;
- actor assertion binding to the calling workload;
- signed actor assurance overriding untrusted JSON assurance;
- production JWT lifetime/claim/algorithm restrictions;
- non-expanding grant/delegation scope behavior;
- route-template based rate limiting (resource IDs do not create separate buckets);
- self-approval rejection;
- distinct-human quorum;
- approver scope coverage;
- approval invalidation after policy supersession;
- approver/operator separation;
- response proposal/dispatch idempotence;
- asynchronous privileged execution through the durable outbox worker;
- outbox worker leasing and stale-worker fencing;
- outbox dead-letter behavior;
- stored outbox payload tampering rejected before enforcement;
- response worker emits verifiable chained audit;
- audit chain detects record tampering;
- security mutation + local audit rollback atomicity;
- timezone-stable audit timestamp canonicalization;
- audit export preserves strict per-tenant ordering and uses lease/fencing state;
- enforcement receipt minimization, validation and digest binding;
- secret-like telemetry/local-audit metadata rejection;
- bounded streaming HTTP response bodies;
- rejection of non-JSON contract responses;
- kOA malformed/unknown policy decisions fail closed;
- circuit-breaker half-open probe control;
- production PostgreSQL TLS policy requires `sslmode=verify-full`;
- production trust URLs reject userinfo/fragments and require HTTPS;
- outbound HTTP ignores ambient proxy environment (`trust_env=False`);
- secret-file/value size and NUL bounds.

## PostgreSQL concurrency tests included but not locally executed

`tests/test_postgres_concurrency.py` contains target-database tests for:

1. concurrent per-tenant audit writers preserving a single ordered hash chain using PostgreSQL locking; and
2. concurrent outbox workers claiming distinct rows under row/advisory locking.

These tests intentionally skip on SQLite and run in the repository's PostgreSQL CI job.

## CI gates included in the repository

GitHub Actions is configured to run:

- tests on Python 3.12, 3.13 and 3.14;
- source compilation;
- SQLite migration round-trip;
- OpenAPI generation;
- PostgreSQL 18 service migration round-trip;
- complete invariant suite against PostgreSQL (including concurrency tests);
- `pip check` in a clean CI environment;
- `pip-audit --strict` vulnerability scanning;
- CycloneDX SBOM generation/upload;
- wheel build;
- production container build and runtime UID verification;
- CodeQL v4 Python analysis.

These remote CI jobs are **configured but were not executed in this generation environment**.

## Production deployment controls now represented in the repo

The production reference includes:

- PostgreSQL `sslmode=verify-full` requirement;
- DB statement, lock and idle-in-transaction timeouts plus UTC/session application name;
- exact Linux runtime dependency constraints;
- asymmetric workload/human JWT requirements and caller binding;
- kOA Policy Runtime fail-closed semantics;
- local chained evidence plus ordered authoritative audit export;
- durable transactional outbox with leases, retry/backoff, DLQ, canonical command reconstruction and fencing;
- bounded/mTLS-capable outbound HTTP with retries only when safe and circuit breaking;
- non-root container target with a builder/runtime split;
- Kubernetes default-deny networking, explicit egress trust path, PDBs, topology spreading and HPA examples;
- image-digest placeholders deliberately preventing accidental use of an unreviewed image;
- a separate controlled migration Job example;
- production release checklist (`docs/RELEASE_CHECKLIST.md`).

## Environment limitations during generation

The execution environment did not provide:

- a Docker daemon for actually building/running the production image;
- a live PostgreSQL server for executing the PostgreSQL-only concurrency tests;
- a Kubernetes cluster/CNI for enforcement testing of NetworkPolicy, PDB, HPA and rollout behavior;
- internet-backed vulnerability database refresh for a trustworthy local `pip-audit` run;
- a clean dependency environment suitable for interpreting the host-level `pip check` (the shared tool environment contains unrelated packages/conflicts); therefore dependency integrity is delegated to the clean CI job;
- the real kOA Identity & Trust / Governance Policy Runtime / Audit Broker;
- the real Orgo deployment;
- the real Interaction Kernel / privileged enforcement agent;
- the organization's KMS/HSM/secret manager, ingress/service mesh, private PKI and egress gateway.

## Required pre-production acceptance

Before privileged production use, the deployment owner must complete `docs/RELEASE_CHECKLIST.md`, especially:

1. clean target-repository CI including PostgreSQL, CodeQL, dependency audit and container jobs;
2. contract tests against exact deployed kOA/Orgo/Interaction Kernel versions;
3. staging with production-equivalent TLS, workload identity, secret rotation and NetworkPolicy/CNI;
4. authorization/telemetry/outbox/audit load tests and overload isolation validation;
5. failure/chaos tests for IdP/JWKS, Policy Runtime, Audit Broker, Orgo, Interaction Kernel and PostgreSQL outages;
6. PostgreSQL backup/PITR restore followed by audit/outbox reconciliation;
7. tenant-isolation and confused-deputy penetration testing;
8. privileged-enforcement allowlist and receipt-schema review against real agents;
9. break-glass tabletop plus controlled live exercise;
10. image/SBOM/provenance signing and admission controls;
11. canary rollout before broad privileged enforcement.
