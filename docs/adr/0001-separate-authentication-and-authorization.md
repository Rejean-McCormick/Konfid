# ADR-0001 — Séparer authentification et autorisation

**Statut : Accepted**

## Décision

Konfid ne devient pas un fournisseur de mots de passe. L'authentification humaine est déléguée aux IdP via kOA Identity & Trust. Konfid consomme une identité validée et décide ensuite de l'autorité contextuelle.

## Raisons

- évite de dupliquer password/MFA/session recovery;
- permet Google/Entra/IdP souverain;
- réduit la surface d'attaque;
- maintient une séparation claire entre « qui es-tu ? » et « que peux-tu faire ? ».

## Conséquences

Chaque application conserve sa session locale et soumet les actions sensibles à Konfid. Une session valide n'est pas un grant.
