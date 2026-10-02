# 03 — Autorisation, scopes et délégations

## 1. Objectif

Konfid fournit une autorisation transversale fine sans remplacer les règles métier locales. Toute décision est fondée sur un contexte explicite et borné.

## 2. Modèle canonique

Une décision d'accès prend la forme :

```text
subject + action + resource + scope + context + policy_state -> decision + obligations
```

### Subject

Peut être :

- `Principal` humain;
- `WorkloadPrincipal`;
- groupe ou rôle résolu en contexte;
- délégation active;
- capability explicitement émise.

### Action

Les actions sont normalisées et versionnées, par exemple :

- `employee.read`;
- `employee.export`;
- `case.approve`;
- `security.policy.modify`;
- `security.account.suspend`;
- `security.tenant.freeze`.

### Resource

Une ressource est identifiée par :

- système propriétaire;
- classe de ressource;
- identifiant ou selector borné;
- classification;
- tenant/organisation.

### Scope

Le scope borne l'autorité. Exemples :

- organisation;
- world;
- département;
- projet;
- site;
- dossier;
- environnement;
- plage temporelle;
- finalité déclarée.

### Context

Peut inclure :

- assurance d'authentification;
- âge de l'auth;
- device trust;
- risk state;
- heure;
- réseau;
- justification;
- délégation;
- quantité demandée;
- sensibilité de la ressource;
- état de l'incident.

## 3. Décisions

Konfid expose au minimum :

- `ALLOW`;
- `DENY`;
- `BLOCKED`;
- `STEP_UP_REQUIRED`;
- `APPROVAL_REQUIRED`.

`BLOCKED` signifie qu'une précondition de sécurité manque ou est indéterminée; ce n'est pas équivalent à un deny métier permanent.

## 4. Obligations

Une décision `ALLOW` peut inclure des obligations exécutoires :

```json
{
  "decision": "ALLOW",
  "obligations": [
    {"type": "audit", "level": "security"},
    {"type": "max_rows", "value": 100},
    {"type": "mask_fields", "fields": ["medical_detail"]},
    {"type": "no_export"},
    {"type": "expires_in", "seconds": 900}
  ]
}
```

Une application qui ne sait pas appliquer une obligation obligatoire DOIT traiter la décision comme `BLOCKED`.

## 5. RBAC + ABAC + capabilities

Konfid utilise un modèle hybride :

### RBAC

Pour exprimer la structure compréhensible : rôle de directeur, analyste RH, responsable sécurité.

### ABAC / context policy

Pour exprimer les contraintes : organisation, classification, finalité, risque, assurance, heure, quantité.

### Capabilities

Pour déléguer ponctuellement une autorité très précise, courte et vérifiable sans créer un rôle global.

## 6. Grants

Un grant minimal contient :

```text
subject
role_or_capability
actions[]
resource_classes[]
scope
constraints
valid_from
valid_until
issued_by
policy_version
status
```

Les grants DOIVENT avoir un scope explicite. Un grant global est réservé aux cas où le domaine fonctionnel est réellement global et doit être justifié.

## 7. Délégations

Une délégation contient :

```text
from_principal
to_principal
actions
scope
resource_constraints
valid_from
valid_until
max_chain_depth
reason
issued_by
revocable
```

Les actions réalisées sous délégation sont attribuées à l'acteur réel :

```text
actor = P782
authority_source = delegation:D-91
delegator = P123
```

Konfid NE DOIT PAS journaliser l'action comme si le délégant l'avait lui-même effectuée.

## 8. Chaînes de délégation

La profondeur maximale est bornée. Les politiques critiques peuvent interdire toute re-délégation.

Exemple :

```text
P123 -> P782 -> P991
```

n'est valide que si :

- le grant d'origine autorise la redélégation;
- chaque délégation réduit ou conserve le scope, jamais ne l'élargit;
- toutes sont actives et non révoquées;
- la profondeur maximale n'est pas dépassée.

## 9. Ressources appartenant aux applications

Konfid ne lit pas directement les données métier pour prendre une décision sauf nécessité explicitement conçue. Les applications fournissent des attributs minimaux ou des références vérifiables.

Le propriétaire de la ressource applique ensuite :

```text
final_decision = konfid_allows AND local_policy_allows
```

L'application peut être plus restrictive; elle ne peut pas transformer un `DENY` Konfid en `ALLOW` pour une opération soumise à Konfid.

## 10. Data scopes

Les classes de données doivent être explicites :

```text
HR.EMPLOYEE.BASIC
HR.EMPLOYEE.COMPENSATION
HR.EMPLOYEE.MEDICAL
FINANCE.INVOICE
FINANCE.PAYROLL
SECURITY.AUDIT.RESTRICTED
```

Les permissions ne doivent pas reposer seulement sur des modules UI ou des routes HTTP.

## 11. Quantité et agrégation

Une permission de lire un objet ne signifie pas nécessairement permission de lire 100 000 objets.

Les policies peuvent limiter :

- nombre d'objets;
- débit;
- export;
- agrégation;
- période;
- combinaison de champs.

## 12. Policy evaluation

Konfid construit un `AuthorizationContext` canonique puis appelle Governance Policy Runtime.

La policy response DOIT inclure :

- décision;
- policy id/version;
- raisons structurées;
- obligations;
- expiration/freshness;
- exigences d'approbation ou step-up;
- decision id corrélable.

## 13. Cache

Les décisions peuvent être cachées uniquement si :

- TTL court et explicite;
- scope exact;
- politique cacheable;
- invalidation possible par révocation;
- action non critique ou capability signée bornée.

Les opérations critiques de sécurité ne doivent pas dépendre d'un cache long.
