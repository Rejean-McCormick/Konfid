# 09 — Contrats, commandes et événements

## 1. Règles de contrat

Tous les contrats inter-systèmes sont :

- versionnés;
- typés;
- backward compatible dans une version majeure;
- validés avant traitement;
- bornés en taille;
- corrélables;
- explicites sur tenant, caller et actor;
- idempotents lorsque l'opération produit un effet durable.

## 2. Enveloppe canonique

```json
{
  "schema": "konfid.envelope/1.0",
  "message_id": "MSG-...",
  "correlation_id": "CORR-...",
  "causation_id": "MSG-previous",
  "sent_at": "...",
  "caller": {
    "principal": "svc:konnaxion-prod",
    "instance": "..."
  },
  "actor": {
    "principal": "P123",
    "delegation_ref": null
  },
  "tenant": "ABC",
  "payload_type": "konfid.access.evaluate/1.0.0",
  "payload": {}
}
```

Le transport doit authentifier le `caller`; le champ `actor` seul n'est jamais une preuve cryptographique du service appelant.

## 3. EvaluateAccess Request

```json
{
  "request_id": "AR-1",
  "actor": "P123",
  "action": "employee.export",
  "resource": {
    "owner": "konnaxion",
    "class": "HR.EMPLOYEE.MEDICAL",
    "selector": "project:X"
  },
  "scope": {
    "organization": "ABC",
    "project": "X"
  },
  "context": {
    "auth_assurance": "phishing_resistant",
    "auth_age_seconds": 80,
    "requested_count": 240
  }
}
```

## 4. EvaluateAccess Response

```json
{
  "decision_id": "PD-92",
  "decision": "ALLOW",
  "policy": "access-hr/42",
  "valid_until": "...",
  "obligations": [
    {"type": "max_rows", "value": 100},
    {"type": "audit", "level": "security"}
  ],
  "reason_codes": ["ROLE_ALLOWED", "SCOPE_MATCH"]
}
```

Les reason codes sont structurés; les messages humains sont secondaires et localisables.

## 5. RiskSignal

```json
{
  "risk_signal_id": "RS-9921",
  "subject": "P123",
  "severity": "critical",
  "score": 92,
  "confidence": 0.96,
  "detector": "bulk-sensitive-read/17",
  "reason_codes": ["VOLUME_BASELINE_18X", "EXPORT_AFTER_BULK_READ"],
  "observed_at": "...",
  "expires_at": "..."
}
```

## 6. ApprovalRequest

```json
{
  "approval_request_id": "APR-33",
  "operation": "FREEZE_TENANT",
  "target": "tenant:ABC",
  "scope_digest": "sha256:...",
  "rationale": "...",
  "policy": "response-freeze/12",
  "threshold": 2,
  "eligible_pool": "security.executive",
  "expires_at": "..."
}
```

## 7. ApprovalReceipt

```json
{
  "approval_id": "APP-77",
  "approval_request_id": "APR-33",
  "approver": "P450",
  "decision": "APPROVE",
  "scope_digest": "sha256:...",
  "auth_assurance": "phishing_resistant",
  "auth_time": "...",
  "approved_at": "...",
  "justification_ref": "orgo://case/SEC-91/comment/42",
  "policy": "response-freeze/12"
}
```

## 8. ResponseCommand

```json
{
  "action_id": "ACT-7819",
  "operation": "ISOLATE_SERVICE",
  "target": "service:payments-worker-3",
  "tenant": "ABC",
  "decision_ref": "PD-992",
  "approval_set_digest": "sha256:...",
  "expires_at": "...",
  "idempotency_key": "..."
}
```

## 9. ResponseReceipt

```json
{
  "action_id": "ACT-7819",
  "executor": "svc:capsule-agent-node-8",
  "status": "EXECUTED",
  "executed_at": "...",
  "target_state_digest": "sha256:...",
  "software_version": "...",
  "receipt_version": "1"
}
```

## 10. Event naming

Convention :

```text
konfid.<domain>.<event-name>.v<major>
```

Exemples :

```text
konfid.identity.binding-created.v1
konfid.access.grant-revoked.v1
konfid.security.risk-signal-raised.v1
konfid.response.action-executed.v1
konfid.approval.quorum-satisfied.v1
```

## 11. Schema evolution

- Ajouter un champ optionnel : compatible.
- Renommer/supprimer/changer la sémantique d'un champ : nouvelle version majeure.
- Les consumers ignorent les champs inconnus seulement si le contrat l'autorise.
- Les security-critical enums utilisent une valeur `UNKNOWN` traitée de façon fail-safe.

## 12. DLQ

Un message invalide ou non traitable est placé en DLQ avec :

- cause structurée;
- message id;
- schema version;
- retry count;
- tenant;
- digest du payload;
- date;
- classification.

La DLQ ne doit pas devenir un stockage en clair de secrets ou de payloads sensibles.
