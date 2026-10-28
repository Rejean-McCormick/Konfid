# Vérification des intégrations satellites — 27 octobre 2026

**Portée :** vérification statique des instantanés de code et de documentation datés du 27 octobre 2026. **Aucune qualification runtime, CI distante, publication ni autorisation de production n’est déduite de cet audit.**

## Limites des preuves fournies pour les dépendances

- Le dépôt Konfid se présente comme **implémentation de référence 0.3.0 candidate production**, pas comme un service déjà qualifié en production.
- Les documents Konfid exigent en production notamment un **Policy Runtime**, un **Audit Broker**, une authentification de workload de confiance, un Enforcement Interaction Kernel et PostgreSQL ; une permission provenant seulement d'un contexte d'interface ou d'un identifiant de World n'est pas une admission.
- Les dépôts voisins `Konnaxion_Worlds` et `Konnaxion_Capsule_Manager` précisent leurs propres frontières Worlds et de release. Leur présence **ne démontre pas** que Konfid est branché, autorisé ou opérationnel avec ces services.
- Éléments examinés : `konfid/README.md`, `konfid/docs/PRODUCTION.md`, `konfid/docs/INTEGRATIONS.md`, `Konnaxion_Worlds/README.md`, `Konnaxion_Capsule_Manager/README.md`.

**Qualification restante :** environnement de test jetable avec les vrais adaptateurs Policy/Audit/IK et l'identité de workload. Les archives des satellites ne suffisent pas pour une preuve d'intégration Konfid de bout en bout.

## Mise à jour et preuve

Cette page décrit un état vérifié **sur fichiers**. Si le code, les contrats ou les captures de tests ont évolué depuis le snapshot, réexécuter les tests et réviser cette page avant publication.
