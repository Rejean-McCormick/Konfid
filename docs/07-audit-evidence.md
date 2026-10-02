# 07 — Audit, preuve et confidentialité

## 1. Principe

Konfid applique **accountability without indiscriminate surveillance** : enregistrer le minimum nécessaire pour expliquer et vérifier les décisions de sécurité, sans transformer Audit Broker en copie généralisée du contenu métier.

## 2. Audit faisant autorité

Les événements critiques sont transmis à kOA Audit Broker, qui fournit :

- intégrité;
- orientation append-only;
- chaîne de garde;
- rétention bornée;
- continuité locale lorsque prévue;
- export indépendant;
- séparation entre preuve publique et preuve restreinte.

## 3. Événement minimal

Un événement de sécurité critique contient au minimum :

```text
event_id
timestamp
actor_principal
caller_service
action
target_ref
resource_class
tenant
policy_ref
decision_ref
outcome
correlation_id
software_version
disclosure_class
```

Selon le cas :

```text
delegation_ref
risk_signal_refs[]
approval_refs[]
response_action_ref
detector_version
justification_ref
```

## 4. Ce qui ne doit pas être enregistré par défaut

- contenu d'emails;
- documents métier complets;
- mots de passe;
- tokens bearer;
- secrets;
- données médicales détaillées;
- payloads complets lorsqu'une référence suffit.

## 5. Claim Check

Les preuves volumineuses ou très sensibles sont stockées hors événement :

```text
SecurityEvent
  evidence_ref = sealed://evidence/9282
  digest = sha256:...
  classification = restricted
```

Le store de preuve applique sa propre autorisation. L'audit conserve une référence et un digest d'intégrité.

## 6. Correlation et causation

Tous les flux significatifs utilisent :

- `correlation_id` — même processus logique;
- `causation_id` — événement/commande qui a causé celui-ci;
- `request_id` — demande locale;
- `decision_id` — décision de policy;
- `action_id` — action de response.

Cela permet de reconstruire :

```text
login -> access request -> risk signal -> policy decision -> approval -> containment -> receipt -> closure
```

## 7. Niveaux de divulgation

Exemple :

- `PUBLIC_SECURITY_METADATA`;
- `INTERNAL`;
- `RESTRICTED`;
- `FORENSIC_RESTRICTED`;
- `SEALED`.

La classification commande qui peut consulter et exporter la preuve.

## 8. Lecture de l'audit

Lire des preuves restreintes est lui-même une action auditable. Les administrateurs de système n'obtiennent pas automatiquement le droit de lire les éléments forensiques.

## 9. Intégrité et horodatage

Les preuves critiques doivent pouvoir démontrer :

- ordre logique;
- digest;
- identité de l'émetteur;
- version du logiciel;
- policy/detector version;
- timestamp fiable ou source de temps;
- absence de modification non détectée.

Le mécanisme précis peut employer signatures, MAC, hash chaining, transparency log ou service d'attestation selon le déploiement.

## 10. Rétention

Chaque classe d'événement possède :

```text
retention_period
legal_or_policy_basis
minimum_required
maximum_allowed
purge_method
archive_policy
```

Une rétention « pour toujours » n'est pas la valeur par défaut.

## 11. Export d'audit

Les exports sont :

- scoped;
- filtrés par classification;
- limités en volume;
- watermarkés/identifiés lorsque pertinent;
- enregistrés comme événement;
- accompagnés d'un manifest et d'un digest si nécessaire.

## 12. Non-répudiation pragmatique

Konfid vise une preuve forte de provenance et d'intégrité. Il ne prétend pas résoudre abstraitement toute non-répudiation juridique. Les garanties exactes dépendent des clés, identités, politiques et infrastructures de l'organisation.

## 13. Audit indisponible

Les opérations à très haut impact dont la policy exige une preuve synchronisée doivent échouer fermées si aucun mécanisme durable d'audit n'est disponible.

Les opérations ordinaires peuvent utiliser un spool local durable signé/chaîné si la policy le permet, suivi d'une réconciliation obligatoire.
