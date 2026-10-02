# ADR-0003 — Un détecteur ne peut pas exécuter directement une réponse

**Statut : Accepted**

## Décision

Overwatch produit des RiskSignals. Toute action de réponse passe par Response Engine et Governance Policy Runtime, avec approbations lorsque requises.

## Raisons

- limite le blast radius d'un faux positif;
- empêche un modèle compromis de devenir une primitive root;
- rend les réponses explicables et versionnées;
- permet le containment minimal.
