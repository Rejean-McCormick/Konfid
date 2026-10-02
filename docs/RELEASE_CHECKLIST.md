# Konfid 0.3 — Production release checklist

A release is **not production-approved** merely because the repository tests pass. This checklist is the minimum acceptance gate for enabling privileged enforcement in a real environment.

## 1. Source and build

- [ ] Merge only reviewed commits from protected branches.
- [ ] CI passes on Python 3.12, 3.13 and 3.14.
- [ ] PostgreSQL concurrency/invariant suite passes.
- [ ] `alembic check` reports no model/schema drift.
- [ ] Migration `upgrade -> downgrade -> upgrade` is rehearsed on representative staging data.
- [ ] `pip check` and `pip-audit --strict` pass under the exact production constraints.
- [ ] Wheel, image, SBOM and provenance are generated from the same commit.
- [ ] Final container image is scanned, signed and deployed by immutable digest.
- [ ] Production manifest contains no `REPLACE_ME`, zero digest or development credential.

## 2. Trust configuration

- [ ] Workload JWT issuer, audience and JWKS endpoint are production values.
- [ ] Human actor JWT issuer, audience and JWKS endpoint are production values.
- [ ] Actor assertion is bound to the calling workload (`azp`/`client_id`).
- [ ] JWT algorithms are asymmetric and lifetimes comply with policy.
- [ ] JWKS/TLS trust anchors are installed from the organization's trust store.
- [ ] kOA Policy Runtime, Audit Broker and Interaction Kernel use authenticated TLS/mTLS.
- [ ] Orgo integration is authenticated when enabled.
- [ ] No local policy or local enforcement mode is enabled.
- [ ] No wildcard service credential or wildcard administrative grant exists.

## 3. PostgreSQL

- [ ] DSN uses `sslmode=verify-full` and the intended CA/root certificate.
- [ ] Application, migration and backup roles are separated where required.
- [ ] PITR is enabled and a restore has been demonstrated.
- [ ] Statement, lock and idle-in-transaction timeouts are active.
- [ ] Connection pool sizing is validated against replica count.
- [ ] HA/failover has been exercised.
- [ ] Audit/outbox concurrency tests pass on the target PostgreSQL major version.

## 4. Network and Kubernetes

- [ ] API/worker run as non-root with read-only root filesystem and dropped capabilities.
- [ ] Default-deny NetworkPolicy is enforced by the actual CNI.
- [ ] Client namespaces are explicitly labelled/allowed.
- [ ] Egress is limited through approved namespaces/gateways to DB, JWKS and trusted services.
- [ ] No arbitrary Internet egress is available from Konfid workloads.
- [ ] PDB, topology spreading and replica counts match availability requirements.
- [ ] HPA thresholds are load-tested, not copied blindly from examples.
- [ ] Migration Job is run once per release, separately from application startup.

## 5. Security policy and response

- [ ] Resource/action catalog is reviewed by each data owner.
- [ ] Critical response policies use appropriate quorum and actor separation.
- [ ] Requester/approver/operator separation is validated end-to-end.
- [ ] Break-glass credentials and process have been exercised in a controlled test.
- [ ] Privileged agents expose only the reviewed allowlisted operations.
- [ ] Duplicate/replayed response commands are verified idempotent against real agents.
- [ ] Receipt schemas from real agents pass Konfid validation/minimization.
- [ ] A stale worker cannot finalize after lease loss in target infrastructure.

## 6. Audit and evidence

- [ ] Local audit chain verification passes after PostgreSQL backup/restore.
- [ ] Audit Broker receives records in tenant sequence order.
- [ ] Audit export backlog, lease expiry and chain failure alerts are configured.
- [ ] Authoritative evidence cannot be modified/deleted by the same role that performs privileged actions.
- [ ] Forensic evidence storage/retention/access policy has been approved.

## 7. Overwatch

- [ ] Detectors are versioned and provenance-verifiable.
- [ ] No detector has privileged enforcement credentials.
- [ ] Candidate detectors complete replay, shadow and canary stages.
- [ ] False-positive feedback cannot directly change access policies.
- [ ] Telemetry flood does not starve authorization/revocation paths under load test.

## 8. Failure and recovery exercises

- [ ] IdP/JWKS unavailable.
- [ ] Governance Policy Runtime unavailable/slow/malformed response.
- [ ] Audit Broker unavailable.
- [ ] Orgo unavailable or returns forged/stale approval.
- [ ] Interaction Kernel/agent timeout after external effect.
- [ ] PostgreSQL failover during outbox processing.
- [ ] Worker death after lease and before/after external call.
- [ ] Corrupt/tampered outbox payload.
- [ ] One-tenant telemetry flood.
- [ ] Credential/key rotation.

## 9. Observability and incident response

- [ ] Alerts exist for readiness, 5xx, authorization latency, DB saturation and open circuit breakers.
- [ ] Alerts exist for outbox dead letters, stale leases, audit backlog and reconciliation backlog.
- [ ] Metrics endpoint is authenticated or disabled and not publicly exposed.
- [ ] Logs are filtered for secrets/PII and are explicitly not treated as authoritative audit evidence.
- [ ] Operational owners and escalation paths are documented.

## 10. Final authorization to enable privileged enforcement

Record:

- release commit SHA;
- image digest;
- SBOM/provenance references;
- migration head;
- policy bundle digest;
- detector bundle digests;
- production trust configuration version;
- approvers for the release;
- rollback image/policy versions;
- acceptance-test evidence references.

Only after these items are complete should privileged response actions be enabled beyond canary scope.
