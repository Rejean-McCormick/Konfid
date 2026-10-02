# 13 — Tests et assurance

## 1. Philosophie

Le test de Konfid vise surtout les **invariants**. Une feature qui fonctionne mais permet de contourner une frontière de sécurité est un échec.

## 2. Pyramide de tests

### Unit

- scope matching;
- grant expiration;
- delegation narrowing;
- quorum;
- idempotency;
- reason codes;
- state machines.

### Contract

- OIDC claims validation;
- Interaction Kernel schemas;
- Konnaxion adapter;
- Orgo approval adapter;
- Policy Runtime adapter;
- Audit Broker adapter;
- enforcement agent.

### Integration

- login → principal → session → access decision;
- approval → quorum → response;
- outbox → dispatch → receipt;
- revocation propagation;
- audit correlation.

### End-to-end

Scénarios réalistes multi-systèmes.

## 3. Tests obligatoires d'identité

- même email, deux `issuer+sub` différents ne fusionnent pas;
- email changé ne change pas le principal;
- compte Workspace réattribué ne reprend pas automatiquement les grants historiques;
- binding révoqué ne peut plus servir;
- linking concurrent ne crée pas de duplicate principal silencieux.

## 4. Tests d'autorisation

- deny par défaut;
- scope exact;
- cross-tenant deny;
- expired grant deny;
- obligation non supportée -> blocked;
- local app can further deny;
- app cannot override Konfid deny;
- bulk read distinct de single read;
- export distinct de read.

## 5. Property-based tests

Propriétés recommandées :

- délégation ne peut élargir le scope;
- intersection de contraintes n'élargit jamais l'autorité;
- ajout d'une restriction ne transforme jamais un deny en allow;
- duplicate ResponseCommand ne produit pas deux effets;
- quorum n'est pas satisfait par le même humain lorsque distinctness=true.

## 6. Fault injection

Injecter :

- timeout Policy Runtime;
- Audit Broker unavailable;
- Orgo down;
- duplicate event;
- reordered event;
- delayed approval;
- stale risk signal;
- lost response receipt;
- DB failover;
- queue overload.

Vérifier les modes dégradés et le fail-closed attendu.

## 7. Security tests

- auth bypass;
- confused deputy;
- tenant isolation;
- SSRF/command injection dans adapters;
- replay;
- forged actor;
- forged approval;
- privilege escalation;
- IDOR/resource reference confusion;
- audit injection;
- secret leakage;
- rate-limit bypass.

## 8. Detector assurance

Un detector candidat doit produire :

- dataset/replay reference;
- expected precision/recall ou métriques adaptées;
- false-positive analysis;
- known blind spots;
- drift behavior;
- resource cost;
- shadow results;
- qualification receipt;
- rollout plan;
- rollback plan.

Les métriques ML ne remplacent pas la revue de sécurité.

## 9. Policy assurance

Une nouvelle policy est testée sur :

- positive cases;
- negative cases;
- boundary scopes;
- unavailable attributes;
- stale context;
- emergency path;
- compatibility avec policies précédentes;
- simulation historique lorsque possible.

## 10. Canary

Les changements à fort impact sont canaryés avec critères d'arrêt explicites :

- augmentation deny inattendue;
- latence;
- false positives;
- approval backlog;
- response volume;
- cross-tenant anomalies.

## 11. SecurityDiag gate

Pour releases critiques, absence de preuve attendue ou résultat `UNKNOWN` bloque la promotion si la policy de release le requiert.

## 12. Chaos sécurité

Scénarios périodiques :

- Google down;
- Orgo compromised simulation;
- detector flooding;
- privileged agent unreachable;
- signing key rotation;
- one tenant attack;
- evidence store read-only;
- accidental wildcard grant attempt.

L'objectif est de démontrer que le blast radius reste borné.
