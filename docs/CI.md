# CI (T10)

Trois workflows GitHub Actions, chacun avec un rôle distinct :

| Workflow | Déclencheur | Rôle |
|---|---|---|
| `ci.yml` | push sur `main`, pull request | lint (`ruff`), types (`mypy --strict`), tests (`pytest`) sur Python 3.11/3.12/3.13, build du paquet |
| `upstream-watch.yml` | cron quotidien, `workflow_dispatch` | détecte une nouvelle révision de `Grokitach/Stalker_GAMMA` ou `Mord3rca/gamma-launcher` ; si oui, exécute un sous-ensemble non-graphique du pipeline dans un conteneur ; ouvre une issue si ça casse |
| `release.yml` | tag `v*` | rejoue les vérifications, construit les artefacts de packaging (T09 : AppImage + bundle Flatpak), publie une GitHub Release avec notes générées |

Aucun secret requis : tout est public (dépôt, ModDB, GitHub releases), et les
seules écritures (commit de l'état amont, création d'issue, publication de
release) utilisent le `GITHUB_TOKEN` par défaut avec des permissions
explicitement scoppées par job (`contents`/`issues` seulement là où
nécessaire — `contents: read` au niveau du workflow partout ailleurs).
`concurrency` annule les runs `ci.yml` obsolètes du même `ref` (pushes
rapides sur une PR) ; `upstream-watch`/`release` ne s'annulent pas entre eux
(un run en cours ne doit pas être tué par un second déclenchement accidentel
pendant qu'il committe ou publie).

## `ci.yml`

Piège réel rencontré en écrivant ce workflow (validé dans un conteneur
`ubuntu:24.04` avant d'être commité) : l'extra `dev` de `pyproject.toml`
inclut `PyGObject-stubs`, qui déclare une dépendance dure sur `PyGObject`
lui-même (confirmé via `pip show PyGObject-stubs` : `Requires: PyGObject,
typing_extensions`). Sans en-têtes système, `pip install ".[dev]"` échoue à
la compilation de `pycairo`/`PyGObject` (pas de roue manylinux, voir
`pyproject.toml`). D'où l'étape `apt-get install libcairo2-dev
libgirepository-2.0-dev gir1.2-gtk-4.0 gir1.2-adw-1 pkg-config` avant
l'install Python — testé pour de vrai sur les trois versions de la matrice
(3.11.15, 3.12.3, 3.13.14 via le PPA deadsnakes dans un conteneur
`ubuntu:24.04`, la même base que les runners `ubuntu-latest` GitHub-hosted) :
~10-20s de compilation par version, `ruff`/`mypy --strict`/`pytest`
(260 tests) et `python -m build` tous verts.

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
puis construit en parallèle :

- **AppImage** (`make package-appimage`, CLI seul — voir `docs/PACKAGING.md`
  pour pourquoi la GUI n'y est pas).
- **Flatpak**, sous forme de **bundle installable en un fichier**
  (`make package-flatpak-bundle`, nouvelle cible : `package-flatpak`
  existant de T09 + `flatpak build-bundle --runtime-repo=…` — un
  `.flatpak-repo` seul n'est pas distribuable tel quel, un utilisateur ne
  peut pas faire `flatpak install` dessus directement). `--runtime-repo`
  pointe vers Flathub pour que l'installateur sache où récupérer
  `org.gnome.Platform//49` (pas embarqué dans le bundle, ~10 Mo). **Testé
  pour de vrai** avant de committer, à partir du `.flatpak-repo` déjà
  construit localement pendant T09.

Publication via `gh release create --generate-notes` (notes auto-générées
par GitHub à partir des PRs/commits depuis le tag précédent) — pas de
script de changelog maison.

## Ce qui n'est pas testé en conditions CI réelles

- `release.yml` : la logique est validée pièce par pièce (AppImage et
  Flatpak buildés/testés pour de vrai pendant T09 et T10, `gh release
  create` est une commande standard) mais le workflow complet, de bout en
  bout sur un vrai tag poussé, n'a pas encore tourné sur GitHub au moment
  d'écrire ceci — se référer aux runs Actions du dépôt pour la première
  exécution réelle.
- Steam Deck / SteamOS réel pour la partie packaging : voir les gaps déjà
  documentés dans `docs/PACKAGING.md` (mêmes limites, T10 n'y change rien).
