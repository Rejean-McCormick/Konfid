# Production deployment

This document describes the **production target** for Konfid 0.3.0. It is not a compliance certification. The deployment owner must validate the real IdP, kOA, Orgo, Interaction Kernel, PostgreSQL, KMS/secret manager and network environment.

## 1. Required trust dependencies

Production mode (`KONFID_DEV_MODE=false`) fails configuration closed unless all security-critical dependencies are explicit:

- PostgreSQL;
- asymmetric workload JWT verification through a trusted JWKS endpoint;
- asymmetric human actor assertions through a trusted JWKS endpoint;
- actor assertions bound to the calling service through `azp`/`client_id`;
- kOA Governance Policy Runtime;
- kOA Audit Broker;
- Interaction Kernel enforcement transport;
- rate limiting;
- authenticated or disabled Prometheus metrics;
- bearer credentials or outbound mTLS for required service integrations;
- HTTPS for remote trust endpoints.

The local HMAC token, wildcard `konfid:*`, local policy engine and local enforcement adapter are development facilities and are rejected on production paths.

## 2. Deployment topology

Run at least:

- multiple stateless API replicas;
- multiple durable worker replicas;
- PostgreSQL with HA/backups appropriate to the organization;
- a controlled migration job before application rollout;
- private connectivity to Identity & Trust, Policy Runtime, Audit Broker, Interaction Kernel and optionally Orgo;
- external secret management;
- a trusted outbound CA and preferably workload mTLS for internal systems.

API and worker can scale independently. Overwatch ingestion/analytics should use separate capacity from authorization/revocation paths at larger scale.

## 3. Database

### PostgreSQL

Use a dedicated database and least-privilege application role. TLS verification is mandatory across untrusted networks. The example DSN uses `sslmode=verify-full`.

Recommended operational controls:

- managed HA or tested primary/replica failover;
- point-in-time recovery;
- encrypted storage and backups;
- backup deletion protected by a distinct administrative role;
- connection limits aligned with `replicas × workers × pool_size`;
- statement timeout enabled;
- regular restore exercises.

### Migrations

Do **not** run migrations automatically in each API pod. Deploy in this order:

1. back up / confirm PITR readiness;
2. run the immutable-image migration Job once;
3. verify Alembic head;
4. roll API and workers;
5. observe readiness, error rate, outbox and audit backlog;
6. retain rollback artifacts.

The repository tests `upgrade -> downgrade base -> upgrade head` structurally. Production migrations must additionally be rehearsed on a representative PostgreSQL staging dataset before release.

## 4. Secrets and key material

Prefer mounted files from a secret manager/CSI driver to literal environment values:

- kOA policy credential;
- kOA audit credential;
- Interaction Kernel credential;
- Orgo credential;
- metrics token;
- private CA bundle;
- optional client certificate/key.

Konfid does not keep human passwords and does not sign production user identities. Human/workload verification keys are obtained from configured JWKS trust anchors.

Rotate service credentials without rebuilding the image. Rotation procedures must test overlapping validity when the upstream supports it.

## 5. Network

Expose Konfid only through the organization's authenticated ingress/API gateway. The included NetworkPolicy is intentionally fail-restrictive: client namespaces must be labelled `konfid-network-access=allowed`.

Vanilla Kubernetes NetworkPolicy cannot express FQDN allowlists portably. Add a platform-specific **egress policy** allowing only:

- PostgreSQL;
- DNS/resolver as required;
- workload/actor JWKS endpoints;
- kOA Policy Runtime;
- kOA Audit Broker;
- Interaction Kernel;
- Orgo when enabled.

Do not permit general internet egress from Konfid pods unless operationally justified.

## 6. HTTP and proxying

TLS terminates at a trusted ingress or service mesh, or directly in an organizational wrapper. If `--proxy-headers` is used, ensure only trusted proxies can reach the service; do not expose the pod directly to arbitrary clients that can forge forwarded headers.

Production configuration:

- exact `trusted_hosts`;
- no wildcard CORS;
- HTTPS-only allowed CORS origins;
- docs/OpenAPI disabled unless intentionally exposed internally;
- request body limits;
- HSTS at the effective HTTPS boundary;
- rate limits per service/tenant/route.

## 7. Workload identity

Every service calling Konfid uses a short-lived JWT with:

- expected issuer and audience;
- asymmetric signature;
- bounded lifetime;
- `jti` in production;
- service subject;
- tenant/scopes.

The human actor assertion is separate. It must be signed, short-lived, include assurance/authentication time, and be bound to the caller service with `azp` or `client_id`. A JSON field supplied by Konnaxion/Orgo cannot upgrade authentication assurance.

## 8. Response execution

HTTP `dispatch` **never executes a privileged operation synchronously**. It atomically records the response intent, chained local audit and outbox message. A worker then:

1. leases the outbox item;
2. reconstructs the command from canonical database state;
3. verifies the stored payload digest;
4. sends the typed idempotent command;
5. validates and minimizes the receipt;
6. records final state plus chained audit in one local transaction;
7. retries transient failures or dead-letters permanent/exhausted failures.

This design tolerates duplicate delivery and network uncertainty without assuming distributed exactly-once semantics.

## 9. Audit

Konfid keeps a per-tenant chained local journal so the state mutation and local evidence can commit atomically. Format v3 canonicalizes timestamps to avoid database timezone representation differences. A separate worker exports records to the authoritative kOA Audit Broker.

Operations must alert on:

- audit export backlog growth;
- chain verification failure;
- audit head mismatch;
- missing authoritative broker connectivity beyond policy limits.

Local chaining is tamper-evidence, not a substitute for the separately governed authoritative Audit Broker.

## 10. Outbox / dead-letter operations

Run at least two workers when HA is required. PostgreSQL uses row locking with `SKIP LOCKED` and explicit leases. Monitor:

- pending count;
- oldest pending age;
- processing leases older than threshold;
- dead-letter count;
- response actions stuck `UNKNOWN` / `RECONCILING`.

Requeue a dead-letter only after understanding the cause. Requeue is itself an audited privileged action.

## 11. Observability

Prometheus metrics are authenticated in production or disabled. Do not expose `/metrics` publicly.

Collect structured application logs, but never treat logs as the authoritative audit trail. Configure log pipeline filtering against credentials and PII.

Recommended alerts:

- readiness unavailable;
- 5xx rate;
- authorization latency/error rate;
- elevated DENY/BLOCKED changes after policy rollout;
- JWKS retrieval failures;
- circuit breakers open;
- DB pool exhaustion;
- outbox/audit backlog;
- dead letters;
- detector/risk flood;
- repeated break-glass activity.

## 12. Release and rollback

Release immutable image digests, not mutable tags, in production overlays. Recommended gate:

`tests -> PostgreSQL tests -> migration rehearsal -> dependency audit -> image build -> image/SBOM/provenance/signing -> staging -> SecurityDiag -> canary -> production`.

The CI in this repository covers the first code-level gates. Image signing, SBOM attestation and deployment admission should be implemented by the organization's supply-chain platform.

## 13. Backups and recovery

Exercise recovery for:

- PostgreSQL point-in-time restore;
- policy service outage;
- Audit Broker outage;
- Identity provider/JWKS outage;
- Orgo outage;
- Interaction Kernel outage;
- lost worker during an in-flight action;
- corrupt outbox payload;
- compromised tenant principal;
- signing/credential rotation.

A backup that has never been restored is not considered a validated recovery mechanism.

## 14. Runtime constraints and reproducibility

`constraints/production-linux.txt` pins the Python runtime dependency graph used by the reference Linux image and CI production jobs. It reduces dependency drift; it is **not** a substitute for artifact hashes, signed provenance or an organizational package mirror.

For a controlled release, build the wheel and image from the same commit, retain the resolved dependency/SBOM evidence, scan the result, sign the final image and deploy only the immutable image digest.

## 15. Kubernetes egress model

The reference NetworkPolicy uses a portable namespace-based allow model because standard Kubernetes NetworkPolicy does not provide portable FQDN filtering. The expected production topology is therefore one of:

- trusted dependencies running in explicitly labelled namespaces; or
- a labelled egress-gateway namespace through which approved external destinations are reached.

Do not label broad application namespaces merely to make connectivity work. Treat the label as a security grant and review it like any other firewall rule.

## 16. Release acceptance

Use [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) before enabling privileged enforcement in a real environment. Code-level validation is necessary but does not replace contract tests against the deployed kOA/Orgo/Interaction Kernel versions, load/failure testing, backup restoration, policy review and security assessment.
