# Security Policy

## Objectif

Konfid est un composant de sécurité critique. Une contribution fonctionnelle n'est acceptable que si elle respecte les invariants de confiance, d'autorisation, d'audit et de séparation des pouvoirs définis dans `docs/17-final-invariants.md`.

## Vulnérabilités

Les vulnérabilités de sécurité ne doivent pas être divulguées publiquement avant coordination avec les mainteneurs autorisés. Le canal de signalement doit être configuré par l'organisation qui exploite le dépôt.

Un rapport utile contient idéalement :

- composant et version affectés;
- scénario d'attaque;
- préconditions;
- impact;
- reproduction minimale;
- suggestion de mitigation si connue.

## Changements à haut risque

Les changements suivants exigent une revue sécurité explicite :

- authentication / federation / session validation;
- policy evaluation;
- grant, delegation, role ou scope semantics;
- privileged operations;
- response actions;
- approval quorum;
- audit/evidence retention;
- cryptography, keys, signing or verification;
- detector-to-response mapping;
- tenant isolation;
- service identities;
- break-glass behavior.

## Règles de base

Konfid NE DOIT PAS :

- stocker les mots de passe des utilisateurs;
- lier silencieusement deux identités parce qu'elles partagent un email;
- accepter un `organization_id`, `role`, `scope` ou `actor` fourni par le client comme preuve d'autorité;
- exposer un shell générique via un agent privilégié;
- autoriser un détecteur à modifier automatiquement une policy;
- autoriser l'auteur d'une demande critique à satisfaire seul son propre quorum;
- permettre à un acteur de supprimer ou réécrire les preuves de sa propre action critique;
- utiliser `permissions=["*"]` ou un équivalent non borné dans les chemins de sécurité de production.

## Cryptographie

Les algorithmes, tailles de clé, mécanismes de rotation et fournisseurs cryptographiques doivent être configurables et versionnés. Les secrets ne sont jamais stockés en clair dans le dépôt. Les clés de signature de production doivent être protégées par un KMS/HSM ou un mécanisme équivalent approprié au niveau de risque.

## Principe de défaillance

- Les opérations critiques échouent **fermées** si l'autorité ou la preuve requise est indisponible.
- Les opérations ordinaires peuvent utiliser des capacités déjà émises et non expirées lorsque la politique l'autorise explicitement.
- Une dépendance analytique non critique ne doit pas bloquer la révocation, le deny ou l'isolation.
