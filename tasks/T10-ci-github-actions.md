# T10 — CI GitHub Actions

**Modèle recommandé : Sonnet 5** (retouches YAML ultérieures : Haiku 4.5).
**Dépendances : T07.**

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md` et `src/`).

Objectif : CI qui attrape les régressions **avant les utilisateurs**, y
compris celles causées par les mises à jour amont de GAMMA.

1. `ci.yml` (push/PR) : ruff + mypy + pytest sur une matrice Python
   (3.11-3.13), build du paquet.
2. `upstream-watch.yml` (cron quotidien) : détecte une nouvelle release/tag
   de `Grokitach/Stalker_GAMMA` et de `Mord3rca/gamma-launcher` ; si
   nouveauté, lance un job d'intégration dans un conteneur qui exécute les
   étapes non-graphiques du pipeline (doctor, téléchargement d'un
   sous-ensemble du modpack, parsing modlist, dry-run install) et ouvre une
   issue automatique en cas d'échec. Attention aux rate-limits ModDB : le
   job doit télécharger le minimum et mettre en cache.
3. `release.yml` (tag `v*`) : build des artefacts de packaging (T09),
   publication GitHub Release avec notes générées.
4. Badge CI dans le README ; concurrency pour annuler les runs obsolètes ;
   aucun secret requis (tout est public).

Critères d'acceptation : CI verte sur le repo ; un tag déclenche une release
avec artefacts ; le cron tourne et sait ouvrir une issue (testable par
workflow_dispatch).
