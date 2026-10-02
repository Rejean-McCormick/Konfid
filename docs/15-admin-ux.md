# 15 — UX d'administration et opérations humaines

## 1. Objectif

L'interface doit rendre les décisions de sécurité compréhensibles sans exposer de raccourci qui contourne les policies.

## 2. Dashboard principal

Le dashboard affiche au minimum :

- état global des dépendances;
- incidents actifs;
- actions de containment actives;
- approval requests en attente;
- changements de policy/detector en rollout;
- risk signals critiques;
- backlog de reconciliation;
- modes dégradés.

Aucun score global « sécurité = 83% » ne doit masquer les causes concrètes.

## 3. Vue Principal

Affiche :

- principal id;
- identité(s) fédérée(s) masquées selon besoin;
- comptes Konnaxion/Orgo liés;
- rôles;
- role mailboxes;
- grants;
- délégations;
- sessions/révocations si disponibles;
- état de risque;
- dernières décisions sensibles.

Le lien entre identités ne se modifie pas par simple édition de texte; il suit une action gouvernée.

## 4. Vue Access Explanation

Pour toute décision :

```text
Decision: DENY
Action: employee.export
Resource: HR.EMPLOYEE.MEDICAL
Scope: project X
Actor: P123
Policy: access-hr/42
Reasons:
 - EXPORT_NOT_GRANTED
 - REQUEST_COUNT_EXCEEDS_LIMIT
Risk context: elevated
```

L'UI distingue clairement règle, signal de risque et obligation.

## 5. Vue Incident

Agrège chronologiquement :

- risk signals;
- décisions;
- demandes d'approbation;
- actions automatiques;
- receipts;
- état de restauration;
- evidence refs;
- classification finale.

## 6. Vue Approval

L'approbateur voit :

- action exacte;
- target;
- scope;
- impact attendu;
- durée;
- risque motivant la demande;
- policy/quorum;
- autres approbations sans favoriser aveuglément leur choix si la policy l'exige;
- expiration;
- justification requise.

Le bouton d'approbation n'est actif que si l'assurance d'auth requise est satisfaite.

## 7. Vue Policy

Une modification montre :

- diff sémantique;
- impact simulé;
- ressources/actions affectées;
- tests;
- qualification;
- approbateurs;
- rollout;
- rollback target.

Pas de modification directe non versionnée en production.

## 8. Vue Detector

Affiche :

- version;
- état shadow/canary/prod;
- métriques;
- false-positive classification;
- drift;
- ressources consommées;
- dernières alertes;
- qualification SecurityDiag;
- rollback.

## 9. Break-glass UX

L'interface d'urgence doit volontairement créer de la friction utile :

- réauthentification;
- raison obligatoire;
- scope explicite;
- durée;
- impact;
- confirmation forte;
- approbation additionnelle si policy;
- notification immédiate;
- compte à rebours d'expiration.

## 10. Accessibilité et erreurs

Les erreurs ne doivent pas révéler des informations sensibles à un utilisateur non autorisé. Les administrateurs autorisés reçoivent des reason codes et correlation ids suffisants pour diagnostiquer.

## 11. Pas d'autorité cachée dans l'UI

Les boutons ne sont jamais la sécurité. Toute action UI appelle les mêmes contrats et policies que les appels API.
