# CI (T10)

Trois workflows GitHub Actions, chacun avec un rôle distinct :

| Workflow | Déclencheur | Rôle |
|---|---|---|
| `ci.yml` | push sur `main`, pull request | sept jobs indépendants (voir plus bas) : lint/types/tests sur une matrice Python, fumée GUI sous Xvfb, `install.sh` réel sur quatre distributions, build du paquet, scan de secrets, audit de dépendances, vérification des noms de paquets annoncés |
| `upstream-watch.yml` | cron quotidien, `workflow_dispatch` | détecte une nouvelle révision de `Grokitach/Stalker_GAMMA` ou `Mord3rca/gamma-launcher` ; si oui, exécute un sous-ensemble non-graphique du pipeline dans un conteneur ; ouvre une issue si ça casse |
| `release.yml` | tag `v*` | rejoue les vérifications, publie une GitHub Release (notes générées) — plus d'artefact de packaging depuis le retrait de Flatpak/AppImage (2026-07-26) |

Aucun secret requis : tout est public (dépôt, ModDB, GitHub releases), et les
seules écritures (commit de l'état amont, création d'issue, publication de
release) utilisent le `GITHUB_TOKEN` par défaut avec des permissions
explicitement scoppées par job (`contents`/`issues` seulement là où
nécessaire — `contents: read` au niveau du workflow partout ailleurs).
`concurrency` annule les runs `ci.yml` obsolètes du même `ref` (pushes
rapides sur une PR) ; `upstream-watch`/`release` ne s'annulent pas entre eux
(un run en cours ne doit pas être tué par un second déclenchement accidentel
pendant qu'il committe ou publie).

Les actions tierces sont épinglées par SHA de commit (pas par tag mobile,
CWE-1357/CWE-494) ; `.github/dependabot.yml` ouvre chaque semaine les PR de
bump vers le SHA à jour pour que ces épingles ne pourrissent pas sur place.

## `ci.yml`

Sept jobs, tous indépendants sauf `build` (qui attend `test`) :

### `test` — lint + types + tests

Piège réel rencontré en écrivant ce job (validé dans un conteneur
`ubuntu:24.04` avant d'être commité) : l'extra `dev` de `pyproject.toml`
inclut `PyGObject-stubs`, qui déclare une dépendance dure sur `PyGObject`
lui-même (confirmé via `pip show PyGObject-stubs` : `Requires: PyGObject,
typing_extensions`). Sans en-têtes système, `pip install ".[dev]"` échoue à
la compilation de `pycairo`/`PyGObject` (pas de roue manylinux, voir
`pyproject.toml`). D'où l'étape `apt-get install libcairo2-dev
libgirepository-2.0-dev gir1.2-gtk-4.0 gir1.2-adw-1 pkg-config` avant
l'install Python : `ruff`, `ruff format --check`, `mypy src` puis `pytest -q`.

Matrice **Python 3.11, 3.12, 3.13 et 3.14** : la 3.14 a été ajoutée car c'est
ce que livrent Fedora 44 et Arch aujourd'hui — donc ce que fait tourner une
grande partie des utilisateurs et la machine de dev. Son absence signifiait
que « CI verte » et « ça marche chez moi » ne parlaient pas de la même chose.

### `gui` — fumée GTK4 sous Xvfb

`install.sh` finit par lancer la GUI et l'entrée de menu aussi, mais ses
~1360 lignes de widgets n'étaient jamais importées en CI : le job `test`
n'installe PyGObject que pour les stubs `mypy`, et `install-script` tourne
délibérément sans GTK. Ce job construit chaque écran pour de vrai, dans un
venv `--system-site-packages` (PyGObject vient du paquet distro, pas d'une
roue manylinux — comme sur la machine d'un utilisateur), sous serveur X
virtuel (`xvfb-run`), via `tests/test_gui_smoke.py`.

### `install-script` — l'installeur réel sur quatre distributions

`install.sh` est le point d'entrée de 100 % des utilisateurs (`curl | bash`)
et n'était exécuté nulle part d'autre que sur la Fedora du mainteneur, alors
que le README promet « any Linux distribution ». Ce job le lance pour de vrai
dans des conteneurs Debian 12, Ubuntu 24.04, Fedora et Arch, et vérifie : le
remède GTK affiché est celui de la bonne distribution (GTK n'est
volontairement pas installé — le script doit s'arrêter proprement en
recommandant la commande adaptée), le venv/raccourcis/entrée de bureau sont
en place, la CLI installée démarre, et relancer le script est idempotent.

### `build` — construction du paquet

`python -m build` (sdist + wheel), dépend de `test`. Artefact conservé
14 jours.

### `secrets` — gitleaks

Les règles du projet interdisent tout secret en dur ; ce job le vérifie au
lieu de s'appuyer sur la seule revue humaine. `gitleaks` scanne **l'historique
complet** (`fetch-depth: 0`), pas seulement l'arbre de travail — une clé
committée puis retirée reste exploitable tant qu'elle est dans les objets
git. Binaire épinglé par version et vérifié par somme SHA-256 (pas l'action
officielle, qui exige une clé de licence pour un dépôt d'organisation).

### `deps` — pip-audit (non bloquant)

`constraints.txt` fige la clôture transitive, mais figer n'est pas auditer :
une version épinglée ne bouge pas quand un avis de sécurité tombe dessus.
Ce job installe la clôture épinglée (Python 3.11, la plus large : `py7zr` n'y
tire `backports.zstd` que sous 3.14) et interroge `pip-audit` sur
l'environnement réellement installé. `continue-on-error: true` pour
l'instant — à rendre bloquant quand plusieurs semaines seront vertes d'affilée
et qu'une porte de sortie écrite existera pour les alertes non corrigeables en
amont.

### `package-names` — les paquets annoncés existent-ils vraiment ?

Les noms de paquets pourrissent en silence (constaté le 2026-08-16 : `p7zip`
avait disparu de Fedora/Arch au profit de `7zip`, et `libunrar5t64` n'existe
pas sur Debian 13). Ce job interroge chaque distribution (Debian 12, Ubuntu
24.04, Fedora, Arch, dépôts non-free/multilib activés comme le fait le remède
affiché à l'utilisateur) pour vérifier que les noms extraits de
`environment/commands.py` existent réellement chez elle. N'installe rien.

## `upstream-watch.yml`

### Suivi d'état

`Grokitach/Stalker_GAMMA` ne publie **ni tags ni GitHub Releases** (vérifié
via l'API : listes vides des deux côtés) — le seul signal de nouveauté est
le dernier commit de sa branche par défaut (`main`). `Mord3rca/gamma-launcher`
publie de vraies Releases (`v3.1` au moment d'écrire ceci, la même version
épinglée dans `pyproject.toml`). D'où deux mécanismes différents dans
`scripts/check_upstream_state.py` :

- `stalker_gamma` : `GET /repos/Grokitach/Stalker_GAMMA/commits/main` → sha.
- `gamma_launcher` : `GET /repos/Mord3rca/gamma-launcher/releases/latest` →
  tag, puis `GET .../tags` pour résoudre le sha du commit correspondant.

L'état connu est committé dans `.github/upstream-state.json` (préseedé avec
les révisions réellement validées pendant le développement de T10 :
`ab0f743a…` / `v3.1` @ `ade656e0…`) — **seulement avancé si le job
d'intégration qui suit a réussi** (job `report`, branche succès). Une
régression amont laisse donc l'état inchangé : le run du lendemain la
redétecte et re-signale (commente l'issue existante au lieu d'en recréer une
— label `upstream-regression`), au lieu de la marquer silencieusement comme
« vue ».

### Job d'intégration : pourquoi un conteneur, et pourquoi si peu

`scripts/upstream_smoke_test.py` exécute, sur un sous-ensemble minimal :

1. `doctor` (informatif seulement — un conteneur CI n'a ni Steam ni GPU,
   c'est attendu, jamais bloquant ici).
2. Récupération de `modlist.txt` + `modpack_maker_list.txt` via
   `raw.githubusercontent.com` (quelques dizaines de Ko) — **pas** le clone
   de `Grokitach/Stalker_GAMMA`, dont l'archive complète pèse **674 Mo**
   (constaté en testant : bien trop pour un check quotidien).
3. Parsing via `launcher.mods.read_mod_maker` — le vrai parseur de
   gamma-launcher, pour détecter une régression du format amont.
4. Téléchargement + installation « à blanc » (répertoire temporaire) de 2
   mods ModDB (`--mod-count`), jamais les ~700 du modpack complet : c'est le
   chemin le plus fragile (mirroring ModDB + Cloudflare via `cloudscraper`),
   donc celui qui vaut la peine d'être vérifié, mais aussi celui où il faut
   le moins solliciter ModDB (rate-limits). Un `actions/cache` garde les
   archives téléchargées entre runs, clé sur le sha de `Stalker_GAMMA` : une
   même révision retestée (ex. `workflow_dispatch --force` répété) ne
   retape jamais ModDB.

Deux entrées sont explicitement exclues de la sélection (`skip_names`/
`skip_titles` dans le script) : ce sont des placeholders ModDB connus
(archive vide/invalide) que `FullInstall._install_mods()` lui-même saute
toujours en amont (`gamma-launcher/launcher/commands/install.py`) — les
inclure sans discernement aurait fait échouer le smoke test sur un problème
déjà connu et géré, pas sur une vraie régression (rencontré pour de vrai en
testant : `FDDA Redone Fixes`, une archive de 147 octets, casse
l'installation FOMOD avec `AttributeError` avant l'exclusion).

Le job tourne dans `container: image: ubuntu:24.04` (pas juste le runner
nu) : `read_mod_maker`/l'extraction d'archives importent `unrar` (ctypes) au
chargement du module, qui cherche `libunrar.so` — absent d'une image de base
et absent de `python:3.x-slim` (Debian, testé : `libunrar5` n'existe dans
aucun composant activé par défaut). `ubuntu:24.04` a `multiverse` activé
d'origine et y fournit `libunrar5t64` — **testé pour de vrai** (`ldconfig -p`
trouve `libunrar.so.5`, `import unrar.unrarlib` réussit) avant d'écrire le
workflow. Dépendances système minimales : `python3 python3-venv python3-pip
libunrar5 p7zip-full git curl ca-certificates` — pas de PyGObject/GTK ici,
`doctor` ne touche jamais ce chemin (`check_gtk_gui` n'est pas dans
`build_report`, voir `environment/checks.py`).

Testé pour de vrai avant de committer (mêmes commandes que le workflow, dans
un conteneur `ubuntu:24.04` avec accès réseau réel) : les deux mods se
téléchargent depuis les vrais miroirs ModDB (Cloudflare inclus), s'extraient
(zip + 7z), et `read_mod_maker` parse 486 entrées de la vraie révision
amont — voir l'historique du projet pour la sortie complète.

### Testable manuellement

`workflow_dispatch` avec `force: true` lance le job d'intégration même sans
changement détecté (`changed` devient `true` inconditionnellement) — utile
pour vérifier la chaîne complète, y compris l'ouverture d'issue en cas
d'échec réel, sans attendre une vraie release amont.

## `release.yml`

Un tag `v*` : rejoue lint/types/tests (les tags ne passent pas forcément
par une PR déjà vérifiée par `ci.yml`, qui ne se déclenche que sur `main`),
puis publie la GitHub Release via `gh release create --generate-notes`
(notes auto-générées par GitHub à partir des PRs/commits depuis le tag
précédent) — pas de script de changelog maison, pas d'artefact à construire
(le seul canal de distribution est `install.sh`, qui clone le repo).

**Historique (T10, 2026-07-23)** : ce workflow construisait aussi un
AppImage et un bundle Flatpak et les attachait à la release
(`stalker-gamma-linux-x86_64.AppImage`, `org.stalkergammalinux.Gui.flatpak`
— tag `v0.1.0`, https://github.com/Fleorens/stalker-gamma-linux/releases/tag/v0.1.0).
Ces deux jobs (`build-appimage`, `build-flatpak`) ont été retirés le
2026-07-26 avec le reste du packaging Flatpak/AppImage (voir
`docs/ARCHITECTURE.md` « Packaging : Flatpak/AppImage retirés »).

## Ce qui n'est pas testé en conditions CI réelles

- Steam Deck / SteamOS réel : aucun accès à une vraie machine SteamOS.
  Les trois workflows (`ci.yml`, `upstream-watch.yml` via
  `workflow_dispatch --force`, `release.yml` sur un vrai tag) ont, eux,
  tous tourné avec succès sur GitHub pendant le développement de T10.
