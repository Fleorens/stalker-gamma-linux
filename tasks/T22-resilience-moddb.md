# T22 — Résilience ModDB : échec de téléchargement, dépôt manuel, reprise ciblée

**Modèle recommandé : Sonnet 5, effort élevé** — reconnaissance de marqueurs et reprise ; le
patron existe déjà dans `engine/runner.py`, il faut l'étendre à l'autre bout.
**Dépendances : T03, T07, T12.**

## Contexte

Relevé le 2026-09-07.

C'est ce qui casse une installation pour tout le monde, et l'amont y répond
mal. Les issues du moteur le disent :
[#282 « unable to use the CLI due to cloudflare captchas »](https://github.com/Mord3rca/gamma-launcher/issues/282)
(**ouverte**, mai 2026), #286 « Download link not found when requesting », #284
et #283 (`AttributeError: 'NoneType'` sur un lien ModDB expiré). Une install de
146 Gio qui s'arrête au mod 400 sur une page ModDB illisible, et l'utilisateur
reçoit une traceback Python.

Nous savons déjà traiter ce cas **d'un côté** : `engine.runner.verify` classe
`_UNVERIFIABLE_MARKERS` (« Could not find Filename in », « Download link not
found when requesting », « since ModDB info do not match download url »…) en
avertissement et non en échec, avec un commentaire qui explique exactement
pourquoi. Ce raisonnement n'a jamais été porté sur le chemin du
**téléchargement**, où il est autrement plus utile : là, ça bloque.

Nous savons aussi déjà **reprendre par mod** : `integrity/repair.py` supprime le
dossier d'un mod et son archive en cache, puis relance le moteur, qui ne
réinstalle que ce qui manque. La mécanique existe ; il manque de la brancher sur
l'échec de téléchargement.

**Périmètre explicite : on ne contourne rien.** Il n'est pas question de
résoudre un captcha, d'imiter un navigateur ni de tourner autour d'une
protection. On diagnostique, on explique, on rend la main à l'utilisateur —
qui, lui, a parfaitement le droit de télécharger le fichier depuis son
navigateur — et on reprend proprement là où on s'est arrêté.

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis
`src/stalker_gamma_linux/engine/process.py`,
`src/stalker_gamma_linux/engine/runner.py` — en particulier `_UNVERIFIABLE_MARKERS`,
`_CORRUPTION_MARKER` et `_gamma_downloads` —,
`src/stalker_gamma_linux/engine/errors.py`,
`src/stalker_gamma_linux/integrity/repair.py` et `src/stalker_gamma_linux/state.py`).

Objectif : qu'un échec de téléchargement produise une consigne exécutable au
lieu d'une trace, et qu'une reprise ne recommence pas les 400 mods déjà posés.

1. **Reconnaître.** Étends la reconnaissance de marqueurs au chemin
   d'installation : `ModDBDownloadError`, « Download link not found », réponses
   403 / page de challenge, `AttributeError` sur `unpackinfo` (le symptôme des
   issues #283/#284, qui est en réalité un lien expiré). Factorise avec les
   marqueurs déjà en place — une seule table, pas deux listes qui divergeront.

2. **Distinguer trois causes**, parce qu'elles n'appellent pas la même consigne :
   ModDB temporairement inaccessible (réessayer plus tard), lien d'un mod
   précis cassé ou déplacé en amont (dépôt manuel), archive locale corrompue
   (`_CORRUPTION_MARKER`, déjà géré côté `verify` — la supprimer et relancer).

3. **Le dépôt manuel, et c'est la vraie valeur.** Quand un mod précis échoue,
   affiche : le nom du mod, l'URL de sa page ModDB, le nom de fichier attendu,
   son MD5 si la modlist le donne, et **le dossier exact** où le déposer —
   `_gamma_downloads(paths)`, c'est-à-dire `<gamma>/downloads`, pas `cache/`
   (la distinction est déjà documentée dans le docstring, elle est régulièrement
   confondue). Puis : « relance la même commande, elle reprendra ici ». Vérifie
   le MD5 du fichier déposé avant de continuer.

4. **Mémoriser les échecs.** Consigne dans `state.py` les mods qui ont échoué,
   avec leur cause. C'est ce qui permet un compte rendu honnête en fin
   d'installation (« 573 mods installés, 4 en échec, les voici ») au lieu d'un
   arrêt brutal au premier problème — et c'est ce que l'utilisateur colle dans
   son issue.

5. **`install --retry-failed`.** Ne rejoue que les mods de cette liste, en
   réutilisant le mécanisme de `integrity/repair.py` (suppression du dossier et
   de l'archive, puis relance du moteur). Ne réinvente pas la reprise : appuie-toi
   sur ce qui existe, et note dans `docs/ARCHITECTURE.md` que le moteur
   réinstalle le modpack par-dessus — la même réserve mesurée que pour
   `verify --repair` (d'autres mods peuvent être mis à jour au passage).

6. **Aller au bout quand c'est possible.** Un mod qui ne se télécharge pas ne
   doit pas condamner les suivants si le moteur permet de continuer. Si son
   fonctionnement l'interdit, dis-le clairement à l'utilisateur plutôt que de
   faire semblant — et ouvre l'issue correspondante en amont.

7. **Ce qu'on ne fait pas.** Aucun contournement de protection, aucune
   simulation de navigateur, aucun miroir non officiel. Écris-le dans
   `docs/ARCHITECTURE.md` : c'est une limite assumée du projet, pas un oubli.

Contraintes : reconnaissance insensible à la casse ; ne jamais faire passer un
échec réel pour un avertissement (la nuance de `verify` était justifiée parce
que les archives locales avaient été vérifiées — ici, un mod manquant est
manquant) ; erreurs typées avec contexte ; messages via `i18n._` ; tests sur
des sorties réelles du moteur, capturées ou reprises des issues amont citées.

## Critères d'acceptation

- Un échec ModDB simulé produit un message nommant le mod, l'URL, le fichier et
  le dossier de dépôt — jamais une traceback.
- Fichier déposé manuellement puis commande relancée : l'installation reprend
  et ne retélécharge pas ce qui est déjà là.
- Un fichier déposé avec un mauvais MD5 est refusé avec un message clair.
- `install --retry-failed` ne rejoue que les mods en échec.
- Une install partielle produit un compte rendu final listant les échecs.
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
feat(engine): diagnostiquer les échecs ModDB et permettre le dépôt manuel
```
