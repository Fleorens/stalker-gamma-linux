# Découpage des tâches

Chaque fichier est un **prompt autonome** à donner à Claude Code (nouvelle
session, dans le dossier du repo). L'ordre recommandé et le modèle le plus
adapté :

| # | Tâche | Modèle recommandé | Dépend de |
|---|-------|-------------------|-----------|
| T01 | Spec d'installation manuelle (recherche + doc) | **Fable 5** (recherche web + synthèse) | — |
| T02 | Squelette Python + détection environnement | **Sonnet 5** | T01 |
| T03 | Wrapper du moteur gamma-launcher | **Sonnet 5** | T02 |
| T04 | Gestion du préfixe Proton | **Fable 5** ou Opus 4.8 | T02 |
| T05 | MO2 sous Proton (le morceau dur) | **Fable 5** | T03, T04 |
| T06 | Raccourci bureau (`.desktop`) | **Sonnet 5** | T04, T05 |
| T07 | CLI orchestrateur | **Sonnet 5** | T03, T04, T05 |
| T08 | GUI GTK4/libadwaita | **Sonnet 5** | T07 |
| T09 | Packaging Flatpak / AppImage / AUR | **Sonnet 5** | T07 |
| T10 | CI GitHub Actions | **Sonnet 5** (itérations YAML : Haiku 4.5) | T07 |

## Règle de choix des modèles

- **Fable 5** : ce qui demande de la recherche, du raisonnement système ou du
  debug non documenté (Wine/Proton/USVFS, comportements de MO2, spec initiale).
  C'est là que le modèle le plus fort rapporte le plus.
- **Sonnet 5** : le développement bien cadré — une fois la spec écrite, ces
  tâches sont du code Python/YAML classique. Rapide et largement suffisant.
- **Haiku 4.5** : retouches mécaniques (YAML de CI, doc, renommages).
- En cas de blocage sur une tâche Sonnet (bug Wine bizarre, comportement
  Proton non documenté) : repasser la session en Fable 5 plutôt que d'insister.

## Hygiène commune à toutes les tâches

- Python ≥ 3.11, `pyproject.toml`, lint `ruff`, types `mypy`, tests `pytest`.
- Fichiers courts et cohésifs (200-400 lignes), pas de mutation d'objets,
  erreurs gérées explicitement, validation des entrées aux frontières.
- Aucun secret en dur ; aucun rehosting de contenu du jeu ou des mods.
- Commits : `<type>: <description>` (feat, fix, refactor, docs, test, chore).
