# 00 — Définition du produit

## 1. Définition

Konfid est un **Security Control Plane** transverse. Il unifie l'identité institutionnelle, les autorisations bornées, la connaissance de risque et la coordination des réponses de sécurité entre plusieurs applications sans absorber l'autorité métier de ces applications.

Konfid vise un environnement où une même personne peut posséder :

- plusieurs identités fédérées;
- plusieurs comptes applicatifs;
- plusieurs rôles simultanés;
- des adresses personnelles et des adresses de fonction;
- des délégations temporaires;
- des droits variant par organisation, projet, unité, environnement ou finalité.

## 2. Problèmes résolus

### 2.1 Correspondance personne ↔ comptes ↔ rôles

Konfid maintient un graphe explicite entre :

- `Principal` — personne ou workload stable;
- `IdentityBinding` — identité authentifiée auprès d'un fournisseur;
- `AccountBinding` — compte dans Konnaxion, Orgo ou autre système;
- `RoleAssignment` — fonction organisationnelle;
- `RoleMailboxAssignment` — contrôle d'une adresse de rôle;
- `Delegation` — transfert d'autorité borné et temporaire.

L'email n'est jamais la clé canonique d'identité.

### 2.2 Permission fine des données et actions

Konfid modélise l'autorité comme une relation entre :

`subject + action + resource + scope + context + policy`.

Le système supporte notamment :

- RBAC pour la lisibilité organisationnelle;
- ABAC/context rules pour le contexte;
- capabilities temporaires pour certaines opérations;
- délégations explicites;
- obligations de décision : masquage, no-export, journalisation, step-up, limites quantitatives.

### 2.3 Overwatch

Overwatch collecte des événements de sécurité normalisés, calcule des signaux de risque et détecte des comportements inhabituels sans devenir l'autorité d'autorisation.

### 2.4 Réponse graduée

Konfid coordonne des mesures de contention proportionnées :

`OBSERVE → STEP_UP_AUTH → RATE_LIMIT → REVOKE_SESSION → SUSPEND_GRANT → SUSPEND_ACCOUNT → ISOLATE_SERVICE → FREEZE_DOMAIN → FREEZE_TENANT → EMERGENCY_SHUTDOWN`.

### 2.5 Intervention humaine gouvernée

Les opérations nécessitant une intervention humaine sont orchestrées dans Orgo, avec politique de quorum, séparation des rôles, justification, durée, réauthentification et receipt vérifiable.

### 2.6 Réduction sûre des faux positifs

Les faux positifs alimentent un processus d'amélioration des détecteurs, jamais un affaiblissement automatique des règles de sécurité.

## 3. Non-objectifs

Konfid n'est pas :

- un gestionnaire universel de mots de passe;
- un SIEM généraliste destiné à stocker toute la télémétrie brute de l'entreprise;
- un ERP de rôles RH;
- un outil de surveillance du contenu des utilisateurs;
- un orchestrateur métier général;
- un remplacement du système d'autorisation métier interne de chaque application;
- un moyen de contourner la souveraineté des systèmes propriétaires.

## 4. Personas

### Utilisateur

S'authentifie via Google, Entra, un IdP souverain ou un autre fournisseur approuvé. N'a pas besoin de connaître Konfid pour la majorité des opérations.

### Administrateur de sécurité

Gère les politiques, scopes, délégations sensibles, mappings institutionnels, incidents et réponses.

### Propriétaire de ressource

Définit les classes de ressources, actions et contraintes locales d'une application protégée.

### Approbateur

Autorise certaines actions exceptionnelles selon une policy d'approbation. Son rôle est borné; il n'est pas nécessairement administrateur global.

### Opérateur

Exécute une action privilégiée si le système ne peut pas l'automatiser. L'opérateur peut être distinct du demandeur et de l'approbateur.

### Auditeur

Accède à des preuves minimisées et immuables selon un scope explicitement autorisé.

## 5. Propriétés de succès

Une version achevée de Konfid doit permettre :

- SSO sans duplication de mots de passe;
- révocation transversale rapide;
- autorisation contextuelle inter-applications;
- preuve complète d'une décision sensible;
- confinement sans shutdown global inutile;
- fonctionnement de sécurité en mode dégradé;
- absence de dépendance à un fournisseur d'identité unique;
- limitation stricte du blast radius d'un composant compromis;
- apprentissage des anomalies sans auto-modification non gouvernée;
- intégration d'une nouvelle application via contrats stables, sans modifier le cœur.
