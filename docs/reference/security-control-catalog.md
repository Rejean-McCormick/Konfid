# Catalogue de contrôles de sécurité

| ID | Contrôle | Exigence |
|---|---|---|
| KF-ID-001 | Canonical principal | Toute action sensible est liée à un Principal stable. |
| KF-ID-002 | No email linking | Aucun linking silencieux par email. |
| KF-ID-003 | Multi-IdP | Support de plusieurs fournisseurs et break-glass souverain. |
| KF-AUTH-001 | No passwords | Aucun mot de passe humain stocké par Konfid. |
| KF-AUTH-002 | Step-up | Les actions critiques peuvent exiger une auth forte récente. |
| KF-AUTHZ-001 | Default deny | Autorité absente/indéterminée => pas d'allow. |
| KF-AUTHZ-002 | Scoped grants | Tout grant est borné. |
| KF-AUTHZ-003 | Delegation narrowing | Une délégation ne peut élargir l'autorité. |
| KF-AUTHZ-004 | Obligations | Une obligation non applicable bloque l'action. |
| KF-TEN-001 | Tenant isolation | Tenant context authentifié et tests anti-fuite. |
| KF-OW-001 | Detector separation | Détecteur sans credential d'enforcement. |
| KF-OW-002 | Versioned signals | RiskSignal référence detector/version. |
| KF-OW-003 | Safe learning | Aucun auto-tuning de policy. |
| KF-RESP-001 | Minimal containment | Plus petite réponse suffisante. |
| KF-RESP-002 | Typed operations | Commandes privilégiées allowlistées et typées. |
| KF-RESP-003 | Idempotency | Effets distribués idempotents. |
| KF-RESP-004 | Receipt | Action critique => receipt ou UNKNOWN. |
| KF-APP-001 | Distinct approvers | Support du quorum avec humains distincts. |
| KF-APP-002 | Fresh approval | TTL et revalidation avant exécution. |
| KF-APP-003 | Request binding | Approbation liée au digest de la demande. |
| KF-AUD-001 | Minimal evidence | Pas de contenu métier complet par défaut. |
| KF-AUD-002 | Integrity | Preuves critiques intègres/append-oriented. |
| KF-AUD-003 | Read auditing | Lecture de preuve restreinte auditée. |
| KF-OPS-001 | Bulkheads | Capacité réservée aux chemins P0/P1. |
| KF-OPS-002 | Degraded modes | Dégradation explicite et policy-driven. |
| KF-OPS-003 | Immutable release | Artifacts versionnés/provenance/qualification. |
| KF-SEC-001 | No wildcard root token | Aucun super-token universel. |
| KF-SEC-002 | Separation of duties | Les opérations extrêmes séparent les pouvoirs. |
| KF-SEC-003 | Local sovereignty | Le propriétaire de la ressource reste enforcement authority local. |
