# ADR-0006 — At-least-once + idempotence + receipts

**Statut : Accepted**

## Décision

Konfid ne dépend pas d'une garantie distribuée « exactly once ». Les effets durables utilisent idempotency keys, Transactional Outbox, retries et reconciliation.

## Raisons

Les duplications, timeouts et pertes de receipts sont normales dans un système distribué. La sûreté doit rester vraie malgré eux.
