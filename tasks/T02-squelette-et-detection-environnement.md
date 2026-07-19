# T02 — Squelette Python + détection d'environnement

**Modèle recommandé : Sonnet 5.**
**Dépendances : T01 (`docs/INSTALL-MANUAL.md`).**

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md`, `docs/INSTALL-MANUAL.md`, `tasks/README.md`).

Crée le squelette du projet Python :
- `pyproject.toml` (nom `stalker-gamma-linux`, Python ≥ 3.11, entry point
  console `stalker-gamma-linux`), config `ruff` + `mypy` + `pytest`.
- Package `src/stalker_gamma_linux/` découpé en petits modules.

Puis implémente le module `environment` :
- Détection : distribution, Steam (native/Flatpak), umu-launcher,
  protontricks, 7z, libunrar, espace disque disponible vs requis (27 Go
  téléchargement + 76 Go installation), présence d'un GPU Vulkan.
- Résultat = objet immuable `EnvironmentReport` listant chaque prérequis avec
  statut (ok / manquant / version trop vieille) et la commande d'installation
  suggérée **par distribution** (dnf/pacman/apt/flatpak).
- Commande `doctor` branchée sur l'entry point qui affiche ce rapport
  lisiblement (codes retour : 0 ok, 1 prérequis manquants).
- Tests pytest avec les appels système mockés (aucun test ne doit toucher le
  vrai système).

Critères d'acceptation : `pip install -e . && stalker-gamma-linux doctor`
fonctionne ; `ruff check`, `mypy`, `pytest` passent ; aucun module > 400 lignes.
