# 05 — Response Engine et containment

## 1. Mission

Response Engine transforme des faits et signaux de risque en **réponses de sécurité gouvernées**, proportionnées et réversibles lorsque possible.

## 2. Séparation fondamentale

```text
Overwatch -> RiskSignal
Policy Runtime -> autorise/interdit la réponse
Response Engine -> coordonne
Local Enforcement -> exécute
Audit Broker -> conserve la preuve
```

Overwatch NE DOIT PAS appeler directement un agent privilégié.

## 3. Échelle de containment

Ordre recommandé de gravité :

1. `OBSERVE`
2. `STEP_UP_AUTH`
3. `RATE_LIMIT`
4. `REVOKE_SESSION`
5. `SUSPEND_GRANT`
6. `SUSPEND_ACCOUNT`
7. `ISOLATE_SERVICE`
8. `FREEZE_SECURITY_DOMAIN`
9. `FREEZE_TENANT`
10. `EMERGENCY_SHUTDOWN`

Le moteur choisit la **plus petite mesure** capable de contenir raisonnablement le risque selon policy.

## 4. ResponseProposal

```text
proposal_id
risk_signals[]
requested_action
target
scope
duration
rationale
policy_context
requires_approval
created_at
expires_at
```

Une proposition n'est pas une autorisation.

## 5. ResponseDecision

Après évaluation par Governance Policy Runtime :

```text
ALLOW_AUTOMATIC
APPROVAL_REQUIRED
STEP_UP_REQUIRED
DENY
BLOCKED
```

La réponse inclut :

- policy version;
- maximum scope;
- durée maximale;
- quorum éventuel;
- obligations d'audit;
- exigences de notification;
- rollback/closure requirements.

## 6. Exécution privilégiée

Toute action d'enforcement critique doit utiliser une commande typée et allowlistée :

```json
{
  "action_id": "ACT-7819",
  "operation": "SUSPEND_GRANT",
  "target": "grant:G-882",
  "scope": "tenant:ABC",
  "decision_ref": "PD-992",
  "expires_at": "...",
  "idempotency_key": "..."
}
```

L'agent privilégié vérifie :

- caller identity;
- opération autorisée;
- target et scope;
- decision receipt;
- fraîcheur/expiration;
- idempotency;
- version de contrat.

Aucun shell générique ne doit être exposé.

## 7. Idempotence

Chaque action possède un `action_id` stable. Si le réseau coupe après exécution, un retry retourne le receipt original plutôt que de répéter dangereusement l'opération.

Le modèle de livraison est :

**at-least-once + idempotence + receipts + reconciliation**, pas une promesse fragile de « exactly once » distribuée.

## 8. Transactional Outbox

Avant émission vers Interaction Kernel :

```text
transaction DB
  - créer ResponseAction
  - créer OutboxEvent
commit
```

Un worker publie ensuite l'événement. La perte du processus entre commit et publication ne perd donc pas l'intention.

## 9. Réconciliation

Une action sans receipt final passe dans un état explicite :

- `PENDING`;
- `DISPATCHED`;
- `EXECUTED`;
- `FAILED`;
- `UNKNOWN`;
- `RECONCILING`;
- `ROLLED_BACK`;
- `CLOSED`.

`UNKNOWN` ne doit jamais être traduit silencieusement en succès.

## 10. Durée et auto-expiration

Toute restriction temporaire doit avoir un TTL lorsque possible. Une suspension temporaire ne doit pas devenir permanente par oubli.

Les actions permanentes exigent une justification et une procédure de closure explicite.

## 11. Réponse à un export massif

Exemple :

```text
420 dossiers sensibles / 120 s
+ export immédiat
 -> RiskSignal critical
 -> suspend HR_EXPORT
 -> revoke current session
 -> require phishing-resistant reauth
 -> open security case in Orgo
 -> preserve evidence
```

Le tenant entier n'est pas gelé si le risque peut être contenu avec un scope plus petit.

## 12. Emergency shutdown

`EMERGENCY_SHUTDOWN` est la dernière mesure. Elle exige typiquement :

- preuve ou risque critique défini par policy;
- authentification forte récente;
- quorum multi-humain sauf scénario automatisé exceptionnel explicitement pré-approuvé;
- scope exact;
- receipt d'approbation;
- commande signée et expirante;
- plan de restauration;
- audit immédiat;
- revue post-incident.

## 13. Closure

Une réponse n'est pas terminée à l'exécution. Elle doit avoir une phase de fermeture :

- état du risque;
- action de restauration;
- révocation des accès temporaires;
- collecte de receipts;
- justification finale;
- classification true/false positive;
- lessons learned;
- changement de détecteur/policy séparé si nécessaire.
