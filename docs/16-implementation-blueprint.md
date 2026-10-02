# 16 — Blueprint d'implémentation

## 1. Structure de dépôt cible

```text
konfid/
├── README.md
├── SECURITY.md
├── docs/
├── cmd/ or apps/
│   ├── api/
│   ├── worker/
│   └── admin-ui/              # si co-localisée
├── internal/ or src/
│   ├── directory/
│   ├── access/
│   ├── policy/
│   ├── overwatch/
│   ├── response/
│   ├── approval/
│   ├── evidence/
│   ├── assurance/
│   ├── contracts/
│   └── adapters/
│       ├── koa_identity/
│       ├── koa_policy/
│       ├── koa_audit/
│       ├── interaction_kernel/
│       ├── konnaxion/
│       ├── orgo/
│       ├── capsule/
│       └── securitydiag/
├── migrations/
├── schemas/
├── policy-bundles/
├── detector-manifests/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── e2e/
│   ├── property/
│   └── chaos/
└── deploy/
```

Le nom exact des répertoires dépend du langage, mais les frontières logiques doivent rester.

## 2. API logique

Endpoints ou méthodes de service minimales :

```text
POST /v1/access/evaluate
POST /v1/capabilities/issue
POST /v1/capabilities/revoke
POST /v1/risk/signals
POST /v1/responses/propose
POST /v1/approvals/validate
POST /v1/responses/{id}/dispatch
POST /v1/responses/{id}/reconcile
POST /v1/identity/bindings
DELETE /v1/identity/bindings/{id}
POST /v1/delegations
DELETE /v1/delegations/{id}
```

Les admin APIs nécessitent une authorization Konfid comme n'importe quelle autre ressource.

## 3. Modules et ownership

### directory

Possède uniquement principals, bindings, contacts, role mailbox mappings.

### access

Possède grants, delegations, resource catalog, access context/capability metadata.

### policy

Possède l'adaptation à Governance Policy Runtime, policy refs, decision validation et cache borné.

### overwatch

Possède ingestion normalisée, detector registry, risk signals et rollout state.

### response

Possède response state machine, outbox, reconciliation et dispatch.

### approval

Possède approval policies, request digests, quorum calculation et receipt validation.

### evidence

Possède production d'événements et evidence refs, jamais le contenu métier arbitraire.

### assurance

Possède qualification workflows de policy/detector/release.

## 4. Transactions

Une transaction ne doit pas s'étendre sur plusieurs systèmes distribués. Utiliser :

- transaction locale;
- outbox;
- idempotency;
- state machine;
- reconciliation.

## 5. State machines

Les états importants sont explicites. Aucun booléen unique `approved=true`, `executed=true` ne remplace une state machine critique.

## 6. Policy artifacts

Les policies devraient être :

- déclaratives lorsque possible;
- versionnées;
- identifiables par digest;
- testables hors production;
- signées ou provenance-verifiable;
- référencées dans chaque décision critique.

## 7. Detector packages

Un detector package contient :

```text
manifest
version
input schema
runtime requirements
package digest
qualification ref
rollout policy
resource limits
```

Un detector ne reçoit aucun credential d'enforcement.

## 8. Data access

Chaque module utilise un repository/port. Les queries multi-tenant exigent un contexte de tenant authentifié. Éviter les helpers génériques permettant une query non scopée par accident.

## 9. Language/runtime

Le choix de langage n'est pas constitutionnel. Le runtime doit cependant offrir :

- types/validation fiables;
- crypto maintenue;
- observabilité;
- concurrence/backpressure;
- dependency management et SBOM;
- migrations transactionnelles;
- tests property/contract faciles;
- déploiement reproductible.

Il vaut mieux utiliser un langage bien maîtrisé par l'équipe qu'introduire une stack exotique uniquement au nom de la sécurité.

## 10. Séquence de réalisation recommandée

### Phase A — Trust foundation

- principal/identity/account model;
- kOA Identity & Trust adapter;
- workload identities;
- audit integration;
- resource catalog.

### Phase B — Authorization

- grants/scopes/delegations;
- Governance Policy Runtime adapter;
- Konnaxion/Orgo enforcement integration;
- step-up semantics.

### Phase C — Response foundation

- response state machine;
- outbox/idempotence;
- Capsule/privileged adapters;
- revocation and containment.

### Phase D — Human governance

- Orgo approval workflow;
- quorum;
- break-glass;
- closure.

### Phase E — Overwatch

- normalized telemetry;
- deterministic detectors first;
- risk aggregation;
- shadow/canary;
- SecurityDiag qualification.

### Phase F — Advanced assurance

- behavioral baselines;
- regional/cell deployment;
- richer forensic workflows;
- automated policy simulations.

Cette séquence réduit le risque : Overwatch n'est introduit qu'après l'existence des chemins sûrs de policy et response.

## 11. Definition of Done globale

Une feature de sécurité n'est terminée que si elle possède :

- authorization;
- tenant isolation;
- audit;
- failure behavior;
- retry/idempotency si effet durable;
- tests négatifs;
- observability;
- migration/recovery;
- documentation;
- threat model impact.
