# 12 — Déploiement et opérations

## 1. Topologie de référence

Konfid peut être déployé avec :

- application/API core;
- base transactionnelle Control Plane;
- worker pools séparés;
- store télémétrie Overwatch;
- outbox publisher;
- adapters Interaction Kernel;
- evidence reference service;
- KMS/HSM;
- cache borné pour décisions non critiques;
- observabilité opérationnelle.

## 2. Séparation des stores

### Control DB

État transactionnel de principals, bindings, grants, delegations, policies refs, response state.

### Telemetry Store

Optimisé pour volume et analyses; compromission ou saturation ne doit pas bloquer le Control DB.

### Evidence Store / Audit Broker

Autorité de preuve, distincte du store analytique.

## 3. Secret management

Aucun secret de production dans :

- repo;
- image de conteneur;
- logs;
- messages d'erreur;
- variables visibles à des rôles non nécessaires.

Les credentials de service sont courts, rotatifs et liés au workload lorsque possible.

## 4. Keys

Les clés critiques sont :

- inventoriées;
- rotables;
- versionnées;
- restreintes par usage;
- protégées par KMS/HSM ou équivalent;
- auditées.

Une clé de signature de response ne doit pas nécessairement pouvoir déchiffrer des preuves.

## 5. Immutable infrastructure

Les composants critiques sont déployés depuis artifacts identifiables et vérifiables. Les changements manuels en production sont évités; toute exception est auditée et temporaire.

## 6. Release

Pipeline recommandé :

```text
source
 -> tests
 -> static/security checks
 -> SBOM/provenance
 -> signed artifact
 -> SecurityDiag qualification
 -> staging
 -> canary
 -> production
```

## 7. Migration de base

Les migrations :

- sont versionnées;
- supportent rollback ou recovery documenté;
- ne mélangent pas changement destructif et code dépendant sans phase de compatibilité;
- préservent tenant isolation;
- sont testées sur volume réaliste.

## 8. SLO de sécurité

Définir des objectifs spécifiques pour :

- latence `EvaluateAccess`;
- propagation de revocation;
- exécution P0;
- disponibilité du policy path;
- freshness des risk signals;
- audit ingestion;
- reconciliation backlog.

Les valeurs exactes dépendent du déploiement, mais les chemins P0/P1 ont priorité sur analytics.

## 9. Health

Chaque composant expose :

- liveness;
- readiness;
- dependency health;
- queue depth;
- stale policy/detector state;
- audit spool status;
- key/credential freshness;
- reconciliation state.

Ne jamais exposer de secrets dans health endpoints.

## 10. Backups

Les backups du Control Plane :

- chiffrés;
- testés par restauration;
- isolés des credentials ordinaires;
- associés à une politique de rétention;
- protégés contre suppression par le même rôle qu'un opérateur courant.

## 11. Disaster recovery

Le plan DR couvre :

- perte du Control DB;
- perte du Telemetry Store;
- perte réseau vers kOA;
- indisponibilité IdP;
- corruption de policy bundle;
- perte de clé;
- queue bloquée;
- tenant-specific compromise.

## 12. Degraded modes

Les modes doivent être explicites dans l'UI et l'audit :

- `NORMAL`;
- `RISK_DATA_STALE`;
- `AUDIT_SPOOLING`;
- `POLICY_DEGRADED`;
- `IDP_DEGRADED`;
- `INCIDENT_MODE`;
- `RECOVERY_MODE`.

Une dégradation ne doit pas être silencieuse.

## 13. Rate limiting

Rate limits distincts pour :

- user/API;
- service identity;
- tenant;
- action class;
- admin endpoints;
- export;
- login callback;
- telemetry ingestion.

Un tenant en abus ne doit pas épuiser toute la capacité.

## 14. Circuit breakers

Utiliser des circuit breakers pour les dépendances non critiques afin d'éviter les cascades. Pour les dépendances d'autorité, le circuit ouvert produit un état explicite `BLOCKED`/degraded selon policy, jamais un allow implicite.

## 15. Cell architecture

Konfid doit être compatible avec une future architecture par cellules si la taille ou la souveraineté l'exige : groupe de tenants isolés par runtime/store. Ce n'est pas obligatoire pour la première implémentation, mais aucun identifiant ou contrat ne doit supposer une base globale unique éternelle.
