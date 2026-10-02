# 11 — Threat Model

## 1. Objectifs de sécurité

Konfid protège :

- intégrité de l'identité;
- isolation tenant;
- confidentialité des scopes et données référencées;
- intégrité des décisions;
- disponibilité des fonctions de deny/revoke;
- intégrité des preuves;
- séparation des pouvoirs;
- impossibilité de transformer un détecteur compromis en root shell.

## 2. Actifs critiques

- mapping principal ↔ identities/accounts;
- grants/delegations;
- policy bundles;
- signing keys;
- workload credentials;
- approval receipts;
- response actions;
- audit evidence;
- detector packages;
- tenant boundaries.

## 3. Menaces principales

### 3.1 Compte utilisateur compromis

Risque : accès légitime utilisé à mauvais escient.

Mitigations : MFA/passkey, assurance context, step-up, scopes fins, Overwatch, rate limits, revocation, session invalidation, short-lived capabilities.

### 3.2 Email compromis ou réattribué

Risque : prise de rôle par possession d'une adresse.

Mitigation clé : email n'est pas l'identité canonique; RoleMailboxAssignment est séparé et borné.

### 3.3 Service Konnaxion compromis

Risque : fabrication de demandes d'accès ou événements.

Mitigations : workload identity, service scopes, owner-local enforcement, request validation, least privilege, audit, mTLS/signatures selon deployment, impossibilité pour Konnaxion d'exécuter des opérations Konfid privilégiées hors contrat.

### 3.4 Orgo compromis

Risque : faux approvals.

Mitigations : Konfid vérifie l'éligibilité, request digest, quorum, approbateurs distincts, auth freshness, réévaluation finale, receipt integrity.

### 3.5 Overwatch compromis

Risque : faux RiskSignals, DoS par réponse excessive.

Mitigation structurante : RiskSignal n'est jamais une commande; Policy Runtime et Response Engine bornent les actions.

### 3.6 Detector poisoning

Risque : normalisation progressive d'un comportement malveillant ou faux positifs massifs.

Mitigations : controlled learning, replay, qualification, shadow/canary, provenance, rollback, aucune modification automatique de policy.

### 3.7 Privileged agent compromis

Risque : contrôle local de système.

Mitigations : agent minimal, allowlist, pas de shell, identity pinning, short-lived commands, scope exact, receipts, sandboxing, least privilege host, independent monitoring.

### 3.8 Konfid application compromise

Risque : modification de grants/policies ou émission de commandes.

Mitigations : modules séparés, KMS/HSM, policy authority externe, privileged broker, approvals, append-oriented audit, release integrity, dual control pour changements critiques, restricted production access.

### 3.9 Database compromise

Risque : modification d'état de control plane.

Mitigations : encryption, DB least privilege, audit trail, versioning, signed policy artifacts, reconciliation, backups, immutable evidence outside same authority domain.

### 3.10 Replay

Mitigations : message id, nonce/expiration selon contrat, idempotency key, action state, signature context, exact scope and target, replay cache where required.

### 3.11 Duplicate delivery

Mitigation : idempotence; duplicate is expected, not exceptional.

### 3.12 Cross-tenant confusion

Mitigations : tenant bound to authenticated context; query scoping; policy evaluation; resource ownership; tests; no trust in client-provided tenant alone.

### 3.13 Audit tampering

Mitigations : Audit Broker separated authority, append orientation, integrity chain, export, access audit, no same actor delete path.

### 3.14 Google/IdP outage

Mitigations : local sessions bounded, break-glass sovereign identities, no dependency for already authorized machine revocation, multi-IdP readiness.

### 3.15 Google/IdP account disabled

Un compte SaaS désactivé ne doit pas supprimer l'identité institutionnelle historique ni rendre impossible un emergency response autorisé.

### 3.16 Insider administrateur

Mitigations : separation of duties, no wildcard authority, approvals, scoped audit access, reauthentication, justifications, short-lived elevation, peer review.

### 3.17 Denial of service par télémétrie

Mitigations : bulkheads, queues, backpressure, admission control, priorities P0-P3, independent capacity for authorization/revocation.

## 4. Hypothèses interdites

Konfid ne doit jamais supposer que :

- réseau interne = trusted;
- admin = omnipotent;
- email vérifié = rôle légitime;
- session valide = action autorisée;
- score ML élevé = culpabilité;
- message livré une fois = exactly once;
- Orgo approved = exécution permise;
- logs présents = logs intègres.

## 5. Revue continue

Le threat model est revu lors de :

- ajout d'un nouveau IdP;
- nouveau type de privileged action;
- nouveau tenant model;
- nouveau detector family;
- changement de key management;
- nouvelle intégration externe;
- incident majeur.
