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

## Statut

✅ Implémenté le 2026-07-23, testé pour de vrai en conteneur avant de
committer (pas encore vérifié sur un vrai run GitHub Actions — voir
`docs/CI.md`, dernière section).

- `ci.yml` : matrice 3.11/3.12/3.13 validée pour de vrai dans des conteneurs
  `ubuntu:24.04` (3.12 natif, 3.11/3.13 via deadsnakes) — `ruff`, `mypy
  --strict`, `pytest` (260 tests) et `python -m build` tous verts sur les
  trois. Piège trouvé et corrigé : l'extra `dev` (`PyGObject-stubs`) tire
  `PyGObject` en dépendance dure, qui ne se compile pas sans en-têtes
  système (`libcairo2-dev`, `libgirepository-2.0-dev`, etc.) — ajoutées
  avant l'install Python.
- `upstream-watch.yml` : `Grokitach/Stalker_GAMMA` n'a ni tags ni releases
  (vérifié via l'API) → suivi par sha du dernier commit `main` ;
  `Mord3rca/gamma-launcher` a de vraies Releases → suivi normal. État dans
  `.github/upstream-state.json`, avancé seulement si le job d'intégration
  réussit. `scripts/check_upstream_state.py` (détection) et
  `scripts/upstream_smoke_test.py` (doctor + modlist + sous-ensemble de 2
  mods ModDB, dry-run) testés pour de vrai contre les vraies API/mirrors —
  téléchargement réel réussi (Cloudflare inclus), parsing de 486 entrées.
  Deux placeholders ModDB connus (déjà sautés par gamma-launcher lui-même)
  exclus de la sélection après avoir fait échouer un premier essai.
- `release.yml` : nouvelle cible Makefile `package-flatpak-bundle`
  (`flatpak build-bundle --runtime-repo=…` par-dessus le `package-flatpak`
  de T09) testée pour de vrai à partir du `.flatpak-repo` déjà construit en
  T09. Notes de release auto-générées (`gh release create --generate-notes`).
- Badge CI + concurrency (annule les runs `ci.yml` obsolètes du même ref) +
  aucun secret : seulement `GITHUB_TOKEN` par défaut, permissions scoppées
  par job.

Détails complets (pièges rencontrés, ce qui a été testé pour de vrai et
comment) dans `docs/CI.md`.
