# 17 — Invariants finaux de Konfid

Ce document est la constitution technique de Konfid. Une modification qui viole un invariant nécessite une décision d'architecture explicite, une mise à jour du threat model et une justification supérieure au simple confort d'implémentation.

## I-01 — Pas de mots de passe utilisateurs

Konfid NE stocke PAS et NE vérifie PAS les mots de passe humains. L'authentification appartient aux fournisseurs d'identité et à Identity & Trust.

## I-02 — Email != identité

Une adresse email, un username ou un display name n'est jamais utilisé pour fusionner silencieusement des identities.

## I-03 — Principal stable

Toute décision sensible est attribuable à un principal stable ou workload identity authentifié.

## I-04 — Session != autorisation

Une session valide ne constitue jamais une autorité suffisante pour une action sensible.

## I-05 — Default deny

Une permission absente, ambiguë, stale ou indéterminée ne produit pas un allow implicite.

## I-06 — Scope obligatoire

Toute autorité est bornée par une portée explicite ou une définition globale intentionnelle et revue.

## I-07 — Pas d'escalade par délégation

Une délégation ne peut jamais élargir l'autorité du délégant.

## I-08 — App propriétaire souveraine

Le propriétaire de la ressource peut être plus restrictif que Konfid. Il ne peut pas contourner un deny Konfid sur un chemin gouverné.

## I-09 — Détection séparée de l'autorisation

Un detector produit un signal. Il ne modifie pas une policy et n'exécute pas directement une opération privilégiée.

## I-10 — Containment minimal

La réponse choisit la plus petite mesure raisonnablement suffisante pour contenir le risque.

## I-11 — Privileged operations allowlistées

Aucun agent d'enforcement n'expose un shell ou une exécution arbitraire au Response Engine.

## I-12 — Idempotence

Toute commande durable ou destructive distribuée possède une sémantique d'idempotence.

## I-13 — Receipt obligatoire

Toute action critique produit un receipt ou reste explicitement `UNKNOWN`/en reconciliation.

## I-14 — Pas d'exactly-once magique

La conception suppose duplicates, retries, reorder et perte temporaire de connectivité.

## I-15 — Séparation des pouvoirs

Pour les opérations définies critiques, demandeur, approbateur et opérateur sont distincts selon policy.

## I-16 — Pas d'auto-approbation implicite

Être administrateur ne confère pas le droit de satisfaire seul un quorum.

## I-17 — Approbations fraîches et liées au contenu

Une approbation est liée à un digest de la demande, un scope, une durée et une policy version.

## I-18 — Revalidation avant exécution

Konfid réévalue l'autorité au moment de l'exécution d'une action critique.

## I-19 — Audit minimal mais suffisant

Konfid journalise les métadonnées nécessaires à l'accountability, pas le contenu métier complet par défaut.

## I-20 — Preuve hors autorité de l'acteur

Un acteur ne peut pas supprimer ou réécrire seul la preuve de sa propre action critique.

## I-21 — Forensic borné

Toute observation forensique enrichie possède scope, motif, durée, autorité et purge.

## I-22 — Faux positif != affaiblissement automatique

Un faux positif ouvre un processus de changement de detector; il ne modifie pas automatiquement la policy d'accès.

## I-23 — Versionnage

Policy, detector, contrat et response mapping critiques sont versionnés et référencés dans les décisions pertinentes.

## I-24 — Canary et rollback

Les changements à blast radius élevé sont qualifiés, déployés progressivement et réversibles.

## I-25 — Bulkhead

La télémétrie et l'analytics ne peuvent pas épuiser la capacité réservée aux denies, revocations et authorization requests.

## I-26 — Multi-IdP

Aucun fournisseur SaaS unique ne constitue l'unique racine opérationnelle de tous les accès de sécurité.

## I-27 — Break-glass gouverné

Le break-glass est borné, temporaire, fortement authentifié, audité et clos explicitement.

## I-28 — Tenant isolation

Aucune donnée, décision ou preuve d'un tenant ne peut être accessible à un autre tenant sans policy explicite et vérifiable.

## I-29 — Workload != human actor

L'identité du service appelant et l'identité de l'humain au nom duquel il agit sont conservées séparément.

## I-30 — UI != autorité

Aucune interface graphique ne constitue une frontière de sécurité. Les APIs appliquent les mêmes policies.

## I-31 — Orgo != autorité finale

Orgo organise les humains. Konfid et Governance Policy Runtime valident l'autorité et le quorum.

## I-32 — Konfid != propriétaire des données métier

Konfid référence les ressources; il ne devient pas une copie générale des bases Konnaxion/Orgo.

## I-33 — Dégradation explicite

Un composant stale, indisponible ou indéterminé produit un état visible et une sémantique définie, jamais un allow silencieux.

## I-34 — Security changes require evidence

Toute modification critique de policy, detector, key ou privileged operation possède provenance, revue, tests et preuve de déploiement.

## I-35 — Aucun super-token universel

La production ne possède pas un credential applicatif unique permettant implicitement toute action sur tous les composants Konfid.
