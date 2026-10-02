# 08 — Intégrations

## 1. Principe général

Toute intégration est un adapter autour d'un contrat canonique Konfid. Le domaine Konfid ne doit pas importer directement les modèles internes de Konnaxion, Orgo, Google ou d'un autre produit.

## 2. Konnaxion

### Rôle

Konnaxion est :

- relying party pour l'authentification;
- Policy Enforcement Point pour ses données;
- source d'événements de sécurité;
- consommateur de décisions Konfid;
- cible de révocation/session containment lorsque nécessaire.

### Flux d'accès

```text
Konnaxion session
 -> resolve principal
 -> build AuthorizationRequest
 -> Konfid EvaluateAccess
 -> Governance Policy Runtime
 -> decision + obligations
 -> Konnaxion applique aussi sa policy locale
 -> action
 -> security/audit event
```

### Interdictions

Konnaxion NE DOIT PAS :

- considérer une adresse email comme preuve d'identité Konfid;
- transformer un `DENY` Konfid en allow;
- envoyer son cookie utilisateur à Konfid;
- accorder un rôle Konfid sur la base d'un claim client non vérifié.

## 3. Orgo

### Rôle

Orgo est le moteur de workflow humain :

- incidents;
- cases;
- approval tasks;
- escalations;
- justification;
- closure process;
- notifications et coordination.

Orgo n'est pas l'autorité de policy finale.

### Flux d'approbation

Konfid crée une demande contenant un digest immuable des éléments critiques. Orgo présente le contexte à un approbateur. Konfid vérifie l'éligibilité de l'approbateur. Orgo retourne un receipt. Konfid valide le quorum et réévalue avant exécution.

### Compromission d'Orgo

Un Orgo compromis ne doit pas pouvoir :

- inventer un principal éligible;
- modifier silencieusement le scope de la demande;
- contourner le quorum;
- exécuter directement une opération privilégiée Konfid.

## 4. kOA Identity & Trust

### Rôle

- validation/fédération d'identités;
- stable subject mapping;
- assurance context;
- révocation de credentials selon intégration;
- support offline/recovery selon deployment.

Konfid utilise l'identité validée, mais ne duplique pas les mots de passe.

## 5. kOA Governance Policy Runtime

Autorité d'évaluation pour :

- accès;
- disclosure;
- privilèges;
- exceptions;
- response actions;
- approval eligibility;
- break-glass.

Konfid fournit le contexte métier de sécurité et interprète les obligations retournées.

## 6. kOA Audit Broker

Reçoit les événements critiques minimisés et les receipts nécessaires à l'accountability.

## 7. Interaction Kernel

Interaction Kernel est le transport recommandé pour les commandes et événements inter-systèmes importants.

Il fournit ou transporte conceptuellement :

- schémas versionnés;
- sender identity;
- idempotency key;
- correlation/causation;
- typed operation;
- receipt;
- retry/reconciliation semantics.

Profils recommandés :

```text
konfid.access.evaluate/1.0.0
konfid.security.signal/1.0.0
konfid.response.request/1.0.0
konfid.approval.submit/1.0.0
konfid.response.execute/1.0.0
konfid.response.receipt/1.0.0
konfid.identity.binding/1.0.0
konfid.revocation/1.0.0
```

## 8. Capsule Manager / privileged agent

Les agents locaux sont des Policy Enforcement Points privilégiés. Ils acceptent seulement des opérations bornées et versionnées.

Exemples :

- revoke service credential;
- disable network exposure;
- isolate process/service;
- freeze selected capability;
- restore known-safe configuration.

Ils n'offrent pas de shell général au Response Engine.

## 9. SecurityDiag

SecurityDiag joue le rôle de qualification indépendante :

- policy bundle validation;
- detector package checks;
- dependency/configuration checks;
- evidence completeness;
- release gate.

SecurityDiag détecte et qualifie; il ne modifie pas lui-même la production en réponse à son diagnostic.

## 10. Koali Spaces

Koali peut offrir :

- visualisation;
- configuration contrôlée;
- incident cockpit;
- approval UX;
- audit exploration.

L'UI n'est jamais l'autorité de décision.

## 11. Google / Microsoft / IdP

Ces fournisseurs authentifient. Ils ne décident jamais :

- des rôles Konfid;
- des data scopes;
- des permissions applicatives;
- des response actions.

Un domaine email ou groupe externe peut servir d'attribut d'admission uniquement si une policy explicite l'autorise et avec les validations appropriées.

## 12. Intégration d'une nouvelle application

Une application est prête pour Konfid lorsqu'elle implémente :

1. workload identity;
2. mapping de son utilisateur vers un principal stable;
3. resource/action catalog;
4. `EvaluateAccess`;
5. enforcement local des décisions/obligations;
6. security events minimisés;
7. revocation/session hooks si nécessaire;
8. health/reconciliation contract;
9. tenant isolation tests.
