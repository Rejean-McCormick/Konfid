# Production runbook

## Readiness failure

1. Check `/live`; if it fails, treat as process/runtime failure.
2. Check API logs for `readiness_failed` and request/instance id.
3. Verify PostgreSQL connectivity and Alembic head.
4. Do not bypass `require_schema_head` to restore traffic.
5. If schema migration is incomplete, halt rollout and follow migration rollback/recovery procedure.

## Policy Runtime unavailable

- Critical authorization fails closed.
- Investigate outbound TLS/DNS/credential/circuit-breaker state.
- Do not switch production to the local policy engine.
- Existing bounded capabilities may only continue where an explicit policy permits it.

## Identity/JWKS unavailable

- New service/actor assertions that cannot be verified are rejected.
- Do not enable HMAC dev tokens.
- Use the separately governed break-glass identity procedure if the incident qualifies.

## Audit Broker unavailable

- Local chained audit continues while durable capacity exists.
- Monitor export backlog and retention pressure.
- For actions whose policy requires authoritative synchronous availability, keep them blocked.
- Verify the local chain with `konfid verify-audit TENANT`.

## Outbox backlog

1. Inspect pending/processing/dead-letter metrics.
2. Check worker health and database leases.
3. Check circuit breaker and upstream availability.
4. Do not mass-requeue without classifying the error.
5. Requeue only specific corrected items through the audited admin API.

## Response state UNKNOWN

`UNKNOWN` means the external effect cannot be proven. Do not simply resend an ad-hoc command.

1. query/reconcile through the defined enforcement channel;
2. use the same action/idempotency identity;
3. obtain authoritative target state/receipt;
4. close or rollback according to policy;
5. document the incident in Orgo when required.

## Dead-letter: payload integrity

`OUTBOX_PAYLOAD_INTEGRITY_FAILURE` is security-significant.

1. freeze automated requeue for the affected item;
2. preserve DB/audit evidence;
3. verify canonical `ResponseAction` / `ApprovalRequest` state;
4. investigate unauthorized DB modification or software defect;
5. rotate credentials if compromise is plausible;
6. create a new governed action rather than editing the dead-letter payload in place.

## Audit chain failure

1. stop treating the local journal as trustworthy evidence;
2. preserve the database snapshot and authoritative Audit Broker copy;
3. compare chain head and exported records;
4. investigate DB write access and application integrity;
5. escalate as a security incident.

## Emergency shutdown

Never issue a shell command manually as a substitute for Konfid governance. Use the emergency response operation, required strong authentication, quorum, exact scope, expiring command, receipt and closure workflow.

## Credential rotation

1. create new upstream credential/certificate;
2. deploy it alongside the old validity window where supported;
3. restart/roll pods to consume mounted secret updates as required;
4. verify calls and audit;
5. revoke old credential;
6. verify no stale workers remain.

## Database restore

1. stop writers;
2. restore to isolated environment first;
3. verify Alembic head and audit chains;
4. reconcile outbox/response actions against external target state;
5. only then restore production traffic.

A database restore can replay old intents; outbox reconciliation and idempotency are mandatory before workers resume unrestricted processing.
