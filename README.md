# Konfid

**Konfid is a cross-system security control plane for identity bindings, scoped authorization,
risk detection, governed containment, approvals, and auditable response.** It integrates with
existing IdPs, kOA, Orgo, Konnaxion, and trusted enforcement agents without becoming a
universal super-admin.

> Current implementation: **0.3.0 production-candidate reference implementation**. The
> repository includes fail-closed production configuration, PostgreSQL migrations and tests,
> durable workers, chained audit, deployment manifests, and operational runbooks. A real
> deployment still requires organization-specific IdP, kOA, Orgo, and Interaction Kernel
> infrastructure; secret/KMS integration; network controls; staging, load, and chaos
> validation; and a security review.

## Core security model

Konfid deliberately separates powers:

```text
IdP / kOA Identity & Trust     -> who is authenticated?
Konfid + kOA Policy Runtime    -> what may this principal do now?
Overwatch                      -> what risk is observed?
Orgo                           -> how do humans coordinate/approve?
Konfid Response Engine         -> what containment is authorized?
Interaction Kernel / Agent     -> execute a typed local effect
kOA Audit Broker               -> preserve authoritative evidence
```

A detector never owns enforcement credentials. An Orgo approval is never blindly trusted.
An email address is never treated as canonical identity. A valid application session alone is
never sufficient authority for a sensitive operation.

## Implemented

- Stable tenant-scoped `Principal` identities with OIDC `issuer + subject` bindings.
- Application-account, contact, and role-mailbox bindings kept separate from identity.
- Resource catalog, scoped grants, contextual constraints, and non-expanding delegations.
- Asymmetric workload JWT verification in production.
- Signed human-actor assertions bound to the calling workload (`azp`/`client_id`).
- Explicit authentication-assurance and freshness semantics.
- Development reference policy engine, with a mandatory kOA Policy Runtime adapter in production.
- Overwatch security events, versioned detectors, `RiskSignal`s, and governed analyst feedback.
- Response ladder from observe/step-up through tenant freeze and emergency shutdown.
- Distinct-human quorum, no implicit self-approval, request-digest binding, and approval freshness.
- Independent operator checks for high-impact actions.
- Transactional outbox, worker leases, retry/backoff, dead-letter queue, and reconciliation.
- Canonical outbox-payload reconstruction so stored-payload tampering cannot alter an executed command.
- Typed, idempotent Interaction Kernel enforcement with minimized, validated receipts.
- Per-tenant chained local audit (format v3) with asynchronous export to the authoritative kOA Audit Broker.
- Atomic state mutation plus local evidence whenever security state changes.
- Request-body limits, structured-field limits, secret-like telemetry rejection, and DB-backed rate limiting.
- Outbound TLS/mTLS support, bounded timeouts/retries, and circuit breakers.
- Structured logs, request correlation, readiness/liveness checks, and authenticated Prometheus metrics.
- SQLite for development, PostgreSQL for production, Alembic migrations, and migration round-trip validation.
- Non-root/read-only container target and hardened Kubernetes production base manifests.
- CI across Python 3.12, 3.13, and 3.14, plus PostgreSQL invariant tests, dependency auditing, and image builds.
- Invariant-focused test suite.

## Quick start (development)

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
cp .env.example .env
alembic upgrade head
konfid bootstrap-tenant demo
TOKEN=$(konfid dev-token --subject svc:dev-admin --tenant demo --scopes 'konfid:*')
uvicorn konfid.app:app --reload --port 8080
```

Open `http://localhost:8080/docs` and use `Authorization: Bearer $TOKEN`.

`konfid:*`, the local HMAC development token, the local policy engine, and the local enforcement
adapter are **development-only**. Production configuration rejects these trust shortcuts.

## Production

Start with `.env.production.example` and [docs/PRODUCTION.md](docs/PRODUCTION.md).
Production requires PostgreSQL, trusted asymmetric JWKS endpoints, human-actor assertions,
the kOA Policy Runtime, the kOA Audit Broker, Interaction Kernel enforcement, HTTPS dependencies,
rate limiting, and metrics that are either authenticated or disabled.

The privileged response path is asynchronous by design:

```text
HTTP dispatch
   -> commit ResponseAction + audit + outbox
   -> worker leases item
   -> rebuild canonical command
   -> verify payload digest
   -> Interaction Kernel / local enforcement point
   -> validate/minimize receipt
   -> commit final state + chained audit
   -> export evidence to kOA Audit Broker
```

Run the API and worker separately:

```bash
uvicorn konfid.app:app --host 0.0.0.0 --port 8080 --no-server-header
konfid worker --interval 1
```

Migrations are a controlled deployment step:

```bash
alembic upgrade head
```

Do not run schema migrations independently in every API replica.

## Useful commands

```bash
make check
make migrate-check
make openapi
konfid doctor
konfid verify-audit TENANT
konfid process-outbox
konfid export-audit
```

## Repository map

```text
src/konfid/
  adapters/       kOA, Orgo, Interaction Kernel, HTTP, audit
  services/       directory, access, approval, Overwatch, response, outbox
  api.py          typed HTTP surface
  auth.py         workload + human-actor assertion verification
  config.py       fail-closed runtime configuration
  models.py       canonical control/evidence state
  rate_limit.py   abuse-control backstop
migrations/       Alembic schema history
tests/            security/invariant tests
deploy/k8s/       hardened production base manifests
docs/             architecture, threat model, production, and runbook
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Authentication & authorization](docs/AUTH.md)
- [Integrations](docs/INTEGRATIONS.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Production deployment](docs/PRODUCTION.md)
- [Operations runbook](docs/RUNBOOK.md)
- [Security policy](SECURITY.md)
- [Validation status](VALIDATION.md)
- [Production release checklist](docs/RELEASE_CHECKLIST.md)

## Fundamental invariant

No single component should be able to **identify + authorize + detect + approve + execute + erase the proof**
of a critical action.

## Tandem security tour (2026-10-18)

The scoped kOA access-decision lifetime hardening and remaining FakePlant integration gates are documented in [docs/TANDEM_TOUR_KONFID_2026-10-18.md](docs/TANDEM_TOUR_KONFID_2026-10-18.md). This is a source-only patch, not deployment or GO LIVE authorization.

## Vérification des intégrations satellites (27 octobre 2026)

Voir [le contrôle de compatibilité et les limites de qualification](docs/Integration-Verification-2026-10-27.md). Les versions et statuts externes doivent être vérifiés avant tout déploiement.

