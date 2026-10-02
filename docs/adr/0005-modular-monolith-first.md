# ADR-0005 — Modular monolith strict pour le cœur

**Statut : Accepted**

## Décision

Le cœur transactionnel Konfid commence comme modular monolith avec frontières internes explicites. Les composants sont extraits en services seulement pour une justification de charge, isolation ou disponibilité.

## Raisons

- moins de transactions distribuées;
- invariants plus simples;
- moins de surfaces réseau;
- migrations cohérentes;
- extraction future conservée par ports/contracts.

## Exceptions naturelles

Télémétrie Overwatch, evidence store, worker pools ou agents d'enforcement peuvent être physiquement séparés dès que leur profil de risque/charge le justifie.
