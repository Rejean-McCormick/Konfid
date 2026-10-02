# ADR-0002 — L'email n'est pas une identité

**Statut : Accepted**

## Décision

Les identités fédérées utilisent un identifiant stable tel que OIDC `issuer + subject`. Email, username et display name sont des attributs descriptifs/contacts.

## Raisons

Les emails changent, peuvent être réattribués, partagés ou fonctionnels. Les utiliser comme clé d'identité crée des prises de compte et des erreurs de fusion.

## Conséquences

Les role mailboxes sont modélisées séparément et leur affectation à un Principal est explicite, temporelle et auditée.
