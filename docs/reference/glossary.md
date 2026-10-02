# Glossaire

**AccountBinding** — Association entre un Principal Konfid et un compte local dans un système externe.

**ApprovalPolicy** — Règles déterminant qui peut approuver, combien d'approbateurs sont nécessaires, avec quelle assurance et pendant combien de temps.

**ApprovalReceipt** — Preuve structurée d'une décision humaine liée à une ApprovalRequest précise.

**Audit Broker** — Composant kOA faisant autorité pour les preuves d'audit minimisées, intègres et exportables.

**Capability** — Autorité bornée, souvent temporaire, portant sur une action et un scope précis.

**Containment** — Action réduisant la capacité d'un acteur ou système à causer un dommage.

**Control Plane** — État de configuration et d'autorité : identities, grants, policies, detectors, etc.

**Decision Plane** — Chemin d'évaluation faible latence des accès, risques et réponses.

**Delegation** — Autorité temporairement conférée par un principal à un autre, sans possibilité d'élargir l'autorité originale.

**Evidence Plane** — Preuves, receipts, traces et références forensiques.

**Governance Policy Runtime** — Moteur kOA qui évalue les politiques et renvoie allow/deny/blocked ainsi que les obligations.

**IdentityBinding** — Association entre un Principal et une identité externe stable, par exemple OIDC `issuer + subject`.

**Interaction Kernel** — Transport typé inter-systèmes avec identité, schémas, idempotence, correlation et receipts.

**Obligation** — Contrainte attachée à une décision ALLOW, par exemple journaliser, masquer des champs ou limiter le volume.

**Overwatch** — Sous-système Konfid d'observation et de production de RiskSignals.

**Policy Enforcement Point (PEP)** — Composant qui applique concrètement une décision, par exemple Konnaxion ou Capsule Agent.

**Principal** — Identité canonique d'un humain, workload ou agent dans Konfid.

**Response Engine** — Sous-système qui coordonne les réponses de sécurité autorisées.

**RiskSignal** — Observation structurée issue d'un détecteur; ce n'est pas une autorisation ni une commande.

**RoleMailbox** — Adresse de fonction organisationnelle dont l'affectation à un Principal est explicite et temporelle.

**Scope** — Périmètre dans lequel une autorité s'applique.

**Step-up authentication** — Réauthentification ou méthode plus forte requise pour une action spécifique.

**Workload identity** — Identité authentifiée d'un service ou processus, distincte de l'utilisateur humain au nom duquel il agit.
