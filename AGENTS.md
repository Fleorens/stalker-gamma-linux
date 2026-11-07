# stalker-gamma-linux — règles communes des agents

Ce fichier est lu par OpenCode (AGENTS.md) et par Claude Code (CLAUDE.md, lien
symbolique vers ce fichier). Une seule source de vérité : on ne modifie que lui.
Le dépôt est **public** : rien de ce qui est écrit ici, dans le code ou dans un
message de commit ne doit être confidentiel.

## Rôles

- **OpenCode**, sur le modèle local de l'aibox : génère le code. En job, il
  travaille seul dans un worktree, sur une branche `gen/<id>-*`.
- **Claude Code** : relit, corrige, tranche. Rien n'arrive sur `main` sans
  relecture : fusion automatique quand les checks et la revue de Claude Code
  sont bons, sinon par Florian (`dev merge`).

## Règles

- Jamais de `git push`, jamais de réécriture d'historique, jamais de commit sur `main`.
- Commits petits et atomiques, au format Conventional Commits, **en français** :
  `type(portée): description` — types `feat`, `fix`, `perf`, `refactor`, `test`,
  `docs`, `style`, `chore`, `ci` ; portée = module touché (`prefix`, `gui`,
  `engine`, `doctor`…) ; `!` après la portée pour une rupture.
  Exemple : `fix(verify): une archive absente n'est pas une corruption`.
- Avant de terminer : lancer `bash .devbox/check` et corriger jusqu'à ce qu'il passe.
- Aucune dépendance ajoutée sans justification dans le message de commit.
- Jamais d'artefacts de build, de binaires ni de fichiers volumineux dans git.
- Ambiguïté : choisir l'option la plus simple et réversible, l'expliquer dans
  le commit.

## Projet

Couche d'intégration Linux pour installer et lancer S.T.A.L.K.E.R. G.A.M.M.A. :
préfixe Proton (GE-Proton, umu), Mod Organizer 2 sous Proton, raccourcis bureau
et Steam, diagnostic. Le téléchargement et l'installation des mods sont
délégués au moteur `gamma-launcher`, appelé en sous-processus.

- **Stack** : Python ≥ 3.11 (le code doit tourner sur 3.11 : `ruff` et `mypy`
  ciblent 3.11), CLI `argparse`, sortie `rich`, GUI GTK4/libadwaita via le
  PyGObject **de la distribution**.
- **Arborescence** :
  - `src/stalker_gamma_linux/` : un sous-paquet par domaine (`engine`, `prefix`,
    `mo2`, `steam`, `desktop`, `integrity`, `backups`, `postmortem`,
    `environment`, `gui`) ; `cli.py` et `orchestrator.py` les assemblent.
  - `tests/` : pytest, un fichier par module (`test_<module>.py`).
  - `docs/ARCHITECTURE.md` : les décisions actées, une section par sujet. Lis
    la section qui concerne ta tâche, pas tout le fichier (il fait 1 600 lignes).
  - `tasks/Txx-*.md` : les fiches de travail ; `tasks/README.md` leur statut.
- **Vérifier** : `bash .devbox/check` = `ruff check`, `ruff format --check`,
  `mypy src` (strict), puis `pytest` sous `xvfb-run` (test de la GUI compris).
  C'est le job `test` + `gui` de `.github/workflows/ci.yml`.
- **Formater** : `ruff format .` puis `ruff check --fix .`.

### Conventions

- Commentaires, docstrings et noms de tests en français. Un commentaire dit
  **pourquoi** (la contrainte, le piège constaté), pas ce que fait la ligne.
- Chaînes affichées à l'utilisateur : en anglais, entourées de `_()`
  (`i18n.py`). Après en avoir ajouté ou changé : `make update-messages`,
  traduire dans `locale/fr/.../*.po`, puis `make compile-messages` ; le `.mo`
  est versionné.
- GUI : **aucune logique métier** dans `gui/`. Elle appelle les mêmes
  fonctions que la CLI, via `output.Reporter` et les callbacks de progression.
  Les modules purs de `gui/` (`viewmodel`, `worker`, `prefs`, `phases`,
  `space`, `summary`, `format`) n'importent pas `gi`.
- Suppression de fichiers ou de dossiers : toujours via les garde-fous de
  `paths_safety.py`, jamais un `shutil.rmtree` nu sur un chemin calculé.
- Dépendances : déclarées dans `pyproject.toml` avec une borne haute, et la
  clôture exacte figée dans `constraints.txt` (procédure en tête du fichier).
  `gamma-launcher` est épinglé par SHA de commit, les actions GitHub aussi.
- Tests : aucun accès réseau ni appel au vrai `gamma-launcher` hors du
  marqueur `network`, exclu par défaut. Les commandes système (`umu-run`,
  `wine`, `steam`…) sont simulées.

### Limites de la devbox

La devbox est un conteneur sans écran, sans GPU, sans Steam ni Proton :
aucune installation réelle de GAMMA, aucun `play`, aucun MO2 n'y tourne.
Un comportement qui ne se vérifie qu'en jeu ou à l'écran est validé par
Florian sur son poste : signale-le dans ton compte rendu au lieu de le
déclarer vérifié.

### Environnement (devbox)

Le venv du clone principal sert à tous les worktrees (`.devbox/check` le
trouve tout seul). À recréer après un changement de dépendances, en tant
qu'utilisateur `dev`, jamais en root :

```
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -c constraints.txt -e ".[dev]"
```

`--system-site-packages` pour voir le PyGObject de Debian ; pip en compile
quand même un plus récent, exigé par `PyGObject-stubs` (d'où `python3-dev`,
`libgirepository-2.0-dev` et `libcairo2-dev` côté système).

### Sécurité

- Les rapports d'audit (`audits/`) ne sont jamais versionnés : ils décrivent
  des failles avant correctif. Un message de commit de correctif décrit la
  faille une fois close, sans mode d'emploi.
- Aucun secret en dur : `gitleaks` scanne tout l'historique en CI.
