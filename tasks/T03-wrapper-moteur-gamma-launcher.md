# T03 — Wrapper du moteur gamma-launcher

**Modèle recommandé : Sonnet 5.**
**Dépendances : T02.**

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md`, `docs/INSTALL-MANUAL.md`).

Objectif : intégrer https://github.com/Mord3rca/gamma-launcher comme moteur de
téléchargement/installation, sans dupliquer sa logique.

1. Étudie d'abord le code de gamma-launcher (clone-le en local hors repo) :
   comment s'invoquent `anomaly-install`, `full-install`, `update`,
   `check-md5` ; est-il importable comme bibliothèque Python ou seulement
   utilisable en CLI ? Choisis le mode d'intégration le plus robuste
   (import direct si l'API interne est stable, sinon subprocess avec parsing
   de sortie) et documente ce choix dans `docs/ARCHITECTURE.md`.
2. Déclare la dépendance proprement dans `pyproject.toml` (git dependency
   épinglée sur un tag de release, pas sur master).
3. Module `engine/` : fonctions `install_anomaly(paths)`,
   `install_gamma(paths)`, `update_gamma(paths)`, `verify(paths)` qui
   pilotent le moteur avec l'arborescence de `docs/ARCHITECTURE.md`
   (`anomaly/`, `gamma/`, `cache/`), remontent la progression (callback) et
   transforment les erreurs moteur en exceptions typées du projet avec un
   message actionnable.
4. Gestion de la reprise : un téléchargement interrompu puis relancé ne
   retélécharge pas ce qui est déjà en cache et vérifié.
5. Tests : mocks du moteur ; un test d'intégration optionnel marqué
   `@pytest.mark.network` (exclu par défaut).

Critères d'acceptation : `ruff`/`mypy`/`pytest` passent ; aucune logique de
résolution ModDB réécrite ici ; le choix import-vs-subprocess est justifié
par écrit.
