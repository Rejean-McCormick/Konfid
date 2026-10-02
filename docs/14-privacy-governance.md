# 14 — Vie privée et gouvernance des données

## 1. Principe

Konfid doit obtenir assez d'information pour prendre une décision de sécurité, mais pas davantage. La minimisation est une propriété d'architecture, pas seulement une politique organisationnelle.

## 2. Catégories de données

Konfid manipule principalement :

- identifiants techniques de principal;
- bindings d'identité;
- références de comptes;
- grants/scopes;
- métadonnées d'accès;
- signaux de risque;
- receipts et références de preuve;
- configurations de policy/detector.

Il ne doit pas devenir la copie primaire des documents métier.

## 3. Purpose limitation

Chaque collecte significative doit avoir une finalité déclarée :

- authentication binding;
- authorization;
- security monitoring;
- incident response;
- audit/accountability;
- assurance/testing.

La réutilisation pour une finalité nouvelle exige une décision explicite de gouvernance.

## 4. Minimisation des événements

Préférer :

```text
resource_class=HR.MEDICAL
count=420
operation=READ
```

à la copie du contenu médical.

## 5. Pseudonymisation

Les analyses Overwatch peuvent utiliser des identifiants pseudonymes lorsque l'identité nominative n'est pas nécessaire. La table de ré-identification reste protégée par des permissions distinctes.

## 6. Role mailboxes

Les adresses de fonction sont traitées comme ressources organisationnelles. Leur mapping vers des personnes est temporel et auditable. Le transfert de rôle ne doit pas exposer automatiquement l'historique personnel hors policy.

## 7. Forensic mode

Le mode FORENSIC est exceptionnel. Il exige :

- incident/request ref;
- scope;
- durée;
- owner;
- approbation selon sensibilité;
- classification;
- purge date;
- audit de chaque accès.

## 8. Data residency

Les contrats et modèles doivent supporter la résidence régionale : l'URI d'une EvidenceReference et le placement d'une cellule peuvent être régionaux. Le cœur ne doit pas supposer qu'une preuve peut traverser librement toutes les juridictions.

## 9. Droit d'accès et suppression

Konfid doit permettre d'identifier quelles données de profil/liaison sont détenues pour un principal. La suppression doit distinguer :

- données de contact et métadonnées non nécessaires;
- bindings actifs;
- preuves de sécurité qui doivent être conservées selon policy;
- références pseudonymisées nécessaires à l'intégrité historique.

## 10. Exports

Tout export de données de sécurité sensibles est lui-même une opération protégée par Konfid, avec scope, raison, limite, classification et audit.

## 11. Analytics

Les tableaux de bord agrégés doivent privilégier l'agrégation. L'accès nominatif aux comportements individuels requiert une finalité de sécurité explicite et un droit approprié.

## 12. Compliance

Konfid peut fournir des contrôles et preuves utiles à la conformité, mais son existence ne constitue pas en soi une certification réglementaire. Les exigences légales précises dépendent du déploiement et de la juridiction.
