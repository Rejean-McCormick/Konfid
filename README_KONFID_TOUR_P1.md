# KONFID — Tournée P1 3/8, patch kOA POLICY TTL

Cible **exacte** selon ce snapshot : `C:\mycode\Konfid\konfid` (racine contenant `src/konfid`). Ne pas copier dans le dossier parent `C:\mycode\Konfid` sans le sous-dossier.

Copier le contenu du ZIP à la racine réelle **sans copier directement les fichiers `payload` à leur destination** : le paquet les garde sous `tools/tandem_konfid_tour/payload`. Puis exécuter sous PS7 :

```powershell
cd 'C:\mycode\Konfid\konfid'
.\PREVIEW_KONFID_TOUR_P1.cmd
.\INSTALL_KONFID_TOUR_P1.cmd
.\VERIFY_KONFID_TOUR_P1.cmd
```

`ROLLBACK_KONFID_TOUR_P1.cmd` revient à la sauvegarde locale si aucun fichier patché n'a été modifié depuis. Les fichiers `tools/tandem_konfid_tour` sont des outils permanents.

## Objectif / limites

Le client de politique kOA refuse désormais les `ALLOW` sans date d'expiration, expirés, en temps local non qualifié (naive) ou valables plus de 60 secondes; il retourne `BLOCKED`, en conservant les autres décisions. Il s'agit d'un correctif au code source de Konfid, pas d'une intégration réelle de kOA/Konnaxion/Orgo ou d'une qualification de production. Aucun secret, `.env`, base, migration ni conteneur n'est modifié.

L'installateur vérifie les empreintes du snapshot; les tests natifs sont exécutés sur **une copie temporaire isolée** si l'interpréteur possède `pytest` et les dépendances Konfid. Sinon, il réalise les contrôles portables et inscrit explicitement `[ATTENTE]` pour les tests natifs, sans proclamer leur réussite. Sur le snapshot de référence dans l'environnement de génération : **47 PASS / 2 SKIPPED (PostgreSQL)**.

En cas de `DRIFT` ou d'erreur, ne pas forcer; renvoyer le diagnostic. La sauvegarde est écrite hors du dépôt dans `C:\mycode\Konfid\Tandem_Local\konfid_tour_p1\backups`.
