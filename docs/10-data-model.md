# 10 — Modèle de données canonique

## 1. Principes

Le modèle canonique représente la sécurité, pas les données métier. Les IDs Konfid sont opaques et stables.

Toutes les entités critiques possèdent :

- `id`;
- `tenant` ou portée explicite;
- `version` ou mécanisme de concurrence;
- `created_at`;
- `updated_at` si mutable;
- provenance/owner lorsque pertinent;
- état explicite.

## 2. Principal

```text
Principal
- id
- type: HUMAN | WORKLOAD | AGENT
- status: ACTIVE | RESTRICTED | SUSPENDED | REVOKED
- home_tenant?
- risk_state
- created_at
```

Les noms et emails ne sont pas la clé.

## 3. IdentityBinding

```text
IdentityBinding
- id
- principal_id
- provider_type
- issuer
- subject
- tenant_context?
- assurance_capabilities[]
- status
- linked_at
- linked_by
- last_verified_at
```

Contrainte unique recommandée : `(issuer, subject)` dans l'espace de confiance applicable.

## 4. AccountBinding

```text
AccountBinding
- id
- principal_id
- system
- external_account_id
- tenant
- status
- verified_at
```

## 5. ContactEndpoint

```text
ContactEndpoint
- id
- principal_id
- type
- value_normalized
- verification_state
- purpose[]
- valid_from
- valid_until?
```

Il sert à contacter, pas à identifier silencieusement.

## 6. RoleMailbox

```text
RoleMailbox
- id
- tenant
- address
- role_ref
- confidentiality_class
- delivery_policy
```

## 7. RoleMailboxAssignment

```text
RoleMailboxAssignment
- id
- mailbox_id
- principal_id
- valid_from
- valid_until
- assigned_by
- approval_ref?
- status
```

## 8. ResourceClass

```text
ResourceClass
- id
- owner_system
- name
- classification
- supported_actions[]
- attributes_schema
- policy_namespace
```

## 9. Grant

```text
Grant
- id
- subject_ref
- role_ref?
- capabilities[]
- resource_classes[]
- scope
- constraints
- valid_from
- valid_until?
- issued_by
- policy_version
- status
```

## 10. Delegation

```text
Delegation
- id
- from_principal
- to_principal
- capabilities[]
- scope
- constraints
- valid_from
- valid_until
- max_chain_depth
- reason
- issued_by
- status
```

## 11. AccessDecision

```text
AccessDecision
- id
- request_digest
- actor
- caller
- tenant
- action
- resource_ref/class
- scope_digest
- decision
- obligations
- policy_ref
- risk_context_ref?
- valid_until
- decided_at
```

Les décisions peuvent être stockées durablement selon criticité; le détail complet peut être minimisé dans le store principal et référencé dans Audit Broker.

## 12. DetectorDefinition

```text
DetectorDefinition
- id
- version
- input_schema
- owner
- state
- rollout
- package_digest
- qualification_ref
- approved_by
```

## 13. RiskSignal

```text
RiskSignal
- id
- subject_ref?
- target_ref?
- detector_ref
- severity
- score?
- confidence?
- reason_codes[]
- evidence_refs[]
- observed_at
- expires_at
- status
```

## 14. ResponseAction

```text
ResponseAction
- id
- proposal_ref
- operation
- target
- scope
- state
- decision_ref
- approval_set_ref?
- idempotency_key
- expires_at
- dispatched_at?
- final_receipt_ref?
```

## 15. ApprovalRequest / ApprovalReceipt

`ApprovalRequest` capture l'intention immutable et son digest. `ApprovalReceipt` capture une décision humaine liée exactement à cette intention.

## 16. EvidenceReference

```text
EvidenceReference
- id
- uri
- digest
- classification
- owner_system
- retention_class
- access_policy_ref
```

## 17. Tenant isolation

Toute table multi-tenant doit rendre le tenant explicite ou le dériver de façon impossible à confondre. Les queries ne doivent jamais prendre un tenant client non validé comme seule barrière.

Les tests de cross-tenant leakage sont obligatoires.

## 18. Suppression

La suppression d'un principal ne doit pas détruire les preuves nécessaires à l'accountability. Les données personnelles non nécessaires peuvent être pseudonymisées ou supprimées selon policy, tandis que les receipts conservent des références stables minimisées.
