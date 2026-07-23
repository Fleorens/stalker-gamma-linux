# Architecture

## Principe

Trois couches. On ne réécrit que ce qui est spécifique à Linux.

```
┌─────────────────────────────────────────────┐
│  GUI (GTK4/libadwaita) — phase 3            │
├─────────────────────────────────────────────┤
│  stalker-gamma-linux (ce repo)              │
│  - CLI orchestrateur (install/update/play)  │
│  - Détection environnement & prérequis      │
│  - Gestion préfixe Proton (umu, Proton-GE,  │
│    verbs winetricks)                        │
│  - MO2 sous Proton (mode principal)         │
│  - Raccourci bureau (.desktop + icône)      │
│  - Packaging (Flatpak, AppImage)            │
├─────────────────────────────────────────────┤
│  Moteur : Mord3rca/gamma-launcher (GPL-3.0) │
│  - Résolution miroirs ModDB, téléchargement │
│  - Parsing modlist GAMMA, directives        │
│  - anomaly-install, full-install, update,   │
│    check-md5                                │
└─────────────────────────────────────────────┘
```

## Décisions actées

1. **Option B** : wrapper au-dessus de `gamma-launcher`, pas de réécriture du
   moteur. On bénéficie de la maintenance amont quand le modpack change.
2. **MO2 sous Proton est le mode principal** (décision utilisateur) : c'est ce
   qui marche aujourd'hui et c'est ce qui préserve la flexibilité des mods
   (activer/désactiver/ajouter). Le mode « flat » (`usvfs-workaround`) n'est
   qu'un fallback documenté pour les configs où MO2 ne tourne pas.
3. **Préfixe unique** : MO2 et le jeu vivent dans le *même* préfixe Proton.
   MO2 lance `AnomalyLauncher.exe`/le jeu à travers son USVFS, donc les deux
   doivent partager le prefix. Verbs requis : `vcrun2022`, `d3dcompiler_43`,
   `d3dcompiler_47`, `d3dx9`, `d3dx10`, `d3dx11_43`.
4. **Proton-GE via umu-launcher** de préférence à protontricks quand possible :
   fonctionne hors Steam, scriptable, reproductible.
5. **ReShade est retiré** (incompatible DXVK) ; vkBasalt proposé en équivalent.
6. **Python** partout (cohérence avec le moteur), packaging `pyproject.toml`.
7. **Jamais de rehosting** : le repo ne contient que du code. Tous les
   téléchargements (Anomaly, mods) se font côté client depuis ModDB/GitHub.

## Arborescence cible d'une installation

```
~/Games/stalker-gamma/            # configurable
├── prefix/                       # préfixe Proton partagé (MO2 + jeu)
├── anomaly/                      # jeu de base (archives ModDB)
├── gamma/                        # MO2 + mods + profils GAMMA
│   ├── ModOrganizer.exe
│   ├── mods/
│   └── profiles/G.A.M.M.A/
└── cache/                        # archives téléchargées (reprise/update)
```

## Intégration du moteur gamma-launcher (T03)

### Décision : subprocess, pas import direct

Le module `engine/` pilote `gamma-launcher` (tag `v3.1` étudié) en lançant le
binaire installé (`gamma-launcher <sous-commande> ...`) via `subprocess`, et
non en important `launcher` comme bibliothèque Python. Raisons, constatées en
lisant le code source de v3.1 :

1. **`CheckMD5.run()` appelle `sys.exit()` directement**
   (`launcher/commands/check.py`). Importer et appeler cette méthode en
   process tuerait le processus appelant. `CheckAnomaly.run()`, à l'inverse,
   lève un `RuntimeError` en cas d'échec, et d'autres commandes se contentent
   d'un retour silencieux. La sémantique d'échec est incohérente d'une
   commande à l'autre côté Python ; elle est en revanche **uniforme côté
   process** : code de retour 0 = succès, non nul = échec, quel que soit le
   mécanisme interne. Le subprocess normalise ça pour nous gratuitement.
2. **Aucune API de progression** : les commandes font `print()` (étapes,
   stdout) et utilisent `tqdm` (progression octet par octet des
   téléchargements, stderr par défaut). Il n'y a pas de callback/hook exposé.
   Que l'on importe ou qu'on lance en sous-processus, on doit de toute façon
   *parser une sortie texte* pour en tirer une progression — le sous-processus
   ne coûte donc rien de plus ici, et isole en prime notre process appelant
   d'un crash ou d'un `sys.exit` amont.
3. **Classes internes non documentées et instables** : `AnomalyInstall`,
   `FullInstall`, etc. attendent un `argparse.Namespace` avec des attributs
   précis (`anomaly_verify`, `cache_path`, `mo_version`, `custom_def`, …) qui
   ne sont ni un contrat public ni stables — `git diff v2.6 v3.1` montre des
   changements dans `commands/install.py` et `commands/check.py` entre ces
   deux releases. Le vrai contrat stable, documenté dans le README amont et
   utilisé par tous les guides (T01), c'est la **CLI** (`gamma-launcher
   <sous-commande> --anomaly ... --gamma ...`), pas les classes Python.
4. **Dépendances lourdes évitées** : importer `launcher` tirerait
   `cloudscraper`, `py7zr`, `GitPython`, `unrar`, `tenacity`, `tqdm`,
   `beautifulsoup4` dans le même environnement/process que
   `stalker-gamma-linux`. En sous-processus, `gamma-launcher` peut même
   tourner dans un interpréteur/venv différent — utile pour le contournement
   documenté du bug d'extraction `py7zr` sur Python 3.14 (voir
   `docs/INSTALL-MANUAL.md` §4, table des pièges).
5. **État caché à neutraliser** : `launcher.cli.main()` mémorise
   `--anomaly`/`--gamma`/`--cache-directory` dans un `config.ini` persistant
   (`platformdirs`) et les réinjecte automatiquement aux appels suivants via
   `argv.insert(2, '@config.ini')`. On désactive ce mécanisme en passant
   `GAMMA_LAUNCHER_NO_CONFIG=1` dans l'environnement du sous-processus, pour
   que nos chemins explicites soient toujours la seule source de vérité.

En clair : le sous-processus est ici le choix *robuste*, pas un pis-aller —
l'API Python interne de gamma-launcher n'est justement pas conçue pour être
appelée en bibliothèque (elle appelle `sys.exit`, elle imprime au lieu de
remonter des événements, elle n'est pas versionnée comme telle).

### Mapping sous-commandes ↔ fonctions `engine/`

| Fonction `engine/` | Sous-commande(s) gamma-launcher | Notes |
|---|---|---|
| `install_anomaly(paths)` | `anomaly-install --anomaly --cache-directory` | |
| `install_gamma(paths)` | `full-install --anomaly --gamma --cache-directory` | Idempotent en amont : réinstalle ce qui manque, met à jour sinon. |
| `update_gamma(paths)` | *identique à `install_gamma`* | **gamma-launcher v3.1 n'a pas de sous-commande `update` séparée** (contrairement à ce que supposait le prompt T03) — `full-install` vérifie déjà `revision.txt` et ne retélécharge/ré-applique que ce qui a changé. `update_gamma` est un alias documenté de `install_gamma`. |
| `verify(paths)` | `check-anomaly --anomaly` puis `check-md5 --gamma` | Les deux couvrent des fichiers différents (binaires du jeu vs archives de mods) ; on les enchaîne pour un seul appel `verify()`. |

### Cache partagé et reprise

`--cache-directory` n'est utilisé par gamma-launcher que lors du **premier**
`gamma-setup` (invoqué par `full-install` si `gamma/mods/` n'existe pas
encore) : à ce moment-là, `gamma/downloads` est remplacé par un **symlink**
vers notre `cache/` (voir `launcher/commands/install.py:GammaSetup.run`,
`downloads_dir.symlink_to(cache_dir)`). C'est pour ça que `check-md5` (qui lit
en dur `gamma/downloads`, sans option `--cache-directory`) voit bien nos
fichiers en cache. Tant qu'on repointe systématiquement `--cache-directory`
vers `cache/` et qu'on ne le supprime jamais entre deux appels, relancer
`install_gamma`/`update_gamma` après une interruption reprend sur les
archives déjà présentes et vérifiées (`use_cached=True` en amont) — aucune
logique de reprise à réimplémenter côté `stalker-gamma-linux`.

## Gestion du préfixe Proton (T04)

Le module `prefix/` crée et entretient le préfixe **unique et partagé**
(décision 3) dans `<install>/prefix/`, via **umu-launcher** (décision 4).

### Choix d'implémentation

1. **umu = voie principale, protontricks = fallback documenté.** umu est
   scriptable hors Steam et laisse choisir l'emplacement du préfixe. Le
   fallback protontricks (docs/INSTALL-MANUAL.md §6.1-6.2) exige une entrée
   Steam existante — donc un APPID, que l'utilisateur crée lui-même via
   *Ajouter un jeu non-Steam* (T06 ne l'automatise pas) — et des clics dans
   Steam : il reste manuel, il n'est pas automatisé ici. `UmuNotFoundError`
   pointe vers ce fallback.
2. **Layout du préfixe** : on passe `WINEPREFIX=<install>/prefix` à umu.
   Validé en réel (umu 1.4.1, 2026-07-19) : umu crée le préfixe **à plat**
   dans ce répertoire et y ajoute un symlink de compatibilité `pfx -> .`
   (layout compatdata Proton). `PrefixPaths.wine_root` absorbe les deux
   layouts. `GAMEID=umu-stalkergamma` fixe la clé protonfixes.
3. **Création** : sentinelle `createprefix` d'umu-run (initialise le préfixe
   sans rien lancer). Validé en réel : sentinelle officielle d'umu 1.4.1
   (chaîne vide ou `createprefix` dans `umu_run.py`) ; création du préfixe
   observée (« Upgrading prefix from None to GE-Proton11-1 »). Après
   création on vérifie `system.reg`.
4. **Idempotence des verbs** : la source de vérité est le `winetricks.log`
   que winetricks tient lui-même à la racine du préfixe (y compris posé par
   protontricks, qui délègue à winetricks). On n'applique que les verbs
   absents, **un à la fois** : échec attribuable, et chaque verb réussi est
   acté — une relance ne rejoue que le reste.
5. **Version de Proton** (décision utilisateur, 2026-07-19) : la **dernière
   release GE-Proton** par défaut. Ordre de préférence : GE le plus récent
   déjà installé (détection dans les `compatibilitytools.d` connus — Steam
   natif, `~/.steam`, Flatpak ; umu y installe aussi les siens) → **Proton
   Experimental** de Steam (`steamapps/common/Proton - Experimental`) →
   autre build présent → téléchargement de la dernière release GE publiée
   (résolue via l'API GitHub, repli épinglé `GE-Proton11-1` si l'API est
   rate-limitée) avec vérification SHA-512 contre le `.sha512sum` publié,
   extraction en répertoire temporaire puis rename — aucun résidu en cas
   d'échec. La recommandation « Proton 9/10 vanilla » des guides est
   remplacée par cette décision ; si la matrice MO2/GE (T05) révèle un
   souci, elle l'arbitrera.
6. **Toute commande externe** passe par `run_in_prefix()` : sortie capturée
   dans `<install>/logs/*.log`, code non nul ⇒ `PrefixCommandError` avec le
   chemin du journal et les dernières lignes. Décodage en
   `errors="replace"` : Wine émet des octets non-UTF-8 (crash constaté en
   réel avec un décodage strict). Les variables structurelles
   (`WINEPREFIX`, `GAMEID`, `PROTONPATH`) sont imposées en dernier :
   l'appelant (T05/T06/T07) ne peut pas casser l'invariant du préfixe
   partagé.
7. **`prefix-doctor`** vérifie umu, Proton, initialisation, verbs et DXVK
   (marqueur `DXVK` dans `d3d11.dll`/`dxgi.dll` de system32 — les builtin
   Wine ne l'ont pas) ; `--repair` rejoue le provisioning idempotent.

## MO2 sous Proton — mode principal (T05)

Le module `mo2/` fait tourner Mod Organizer 2 dans le préfixe partagé avec
**USVFS actif** : c'est la raison d'être du projet côté jeu (flexibilité des
mods). Découpage :

1. **Configuration de l'instance (`instance.py`)** — l'étape que gamma-launcher
   ne fait pas. L'instance MO2 livrée par GAMMA est construite hors Wine, donc
   son `gamePath` est invalide. On l'édite **chirurgicalement** dans
   `ModOrganizer.ini` : `gamePath` → dossier Anomaly en **chemin Windows**
   (`Z:\...`, traduit par `winepath.py`), `selected_profile` → `G.A.M.M.A`.
   On ne réécrit jamais tout le fichier (`ini.py` remplace ligne à ligne) : MO2
   y sérialise des blobs Qt (`@ByteArray(...)`, `[customExecutables]`) qu'un
   `configparser` corromprait. Sauvegarde `.bak` du fichier d'origine, idempotent.
2. **Lancement (`launch.py`)** — on ne lance jamais l'exe du jeu directement
   (l'USVFS est local au processus MO2). `launch_mo2()` ouvre l'interface ;
   `launch_game()` passe à `ModOrganizer.exe` un URI `moshortcut://:Anomaly (DX11)`
   (instance portable = partie instance vide), ce qui monte l'USVFS et lance le
   jeu à travers lui. Tout passe par `run_in_prefix` (T04).
3. **Diagnostic (`diagnostics.py`)** — symptôme n°1 : jeu lancé « vanilla »
   (USVFS mort). Après un lancement, on lit le dernier `logs/usvfs-*.log` de
   l'instance : marqueur `proxy run successful` ⇒ VFS monté ; absent ⇒ USVFS
   probablement mort. On vérifie aussi que le profil a des mods activés
   (`modlist.txt`). Les remèdes renvoient vers `docs/MO2-PROTON-COMPAT.md`.
4. **Version de Proton** : arbitrée par `docs/MO2-PROTON-COMPAT.md`. Défaut =
   dernier GE (décision T04) ; repli documenté sur Proton 9/10 *vanilla* si le
   diagnostic détecte un USVFS mort.
5. **Fallback flat (`flat.py`)** — accessible uniquement par flag explicite
   (`play --flat`). Délègue la fusion à `engine.build_flat_install`
   (`gamma-launcher usvfs-workaround`) puis lance `AnomalyLauncher.exe` du
   dossier fusionné. **Perte de la flexibilité des mods** — d'où le flag et
   l'avertissement (docs/INSTALL-MANUAL.md annexe A).

`session.py` orchestre les commandes `mo2` et `play` : préfixe prêt (T04) →
instance configurée → lancement → diagnostic.

## CLI orchestrateur (T07)

### Framework : `argparse`, pas `click`/`typer`

Les tâches T04-T06 avaient déjà posé, commande après commande, une CLI
`argparse` complète (sous-commandes, `--help` par commande, dispatch testé —
182 tests avant même T07). La retravailler en `click`/`typer` maintenant
aurait été une réécriture pure (parser + ~180 tests de dispatch) sans gain
fonctionnel : `argparse` couvre déjà tous les critères d'acceptation
(sous-commandes, aide claire, codes de retour). On la garde donc, et
`rich`/`logging` (ajoutés en T07) fournissent la progression lisible et les
logs indépendamment du parser choisi.

### `install` : pipeline résumable

`orchestrator.run_install` enchaîne désormais **six** étapes (`anomaly`,
`gamma`, `reshade`, `prefix`, `mo2`, `shortcut` — cette dernière seulement si
`--shortcut`) sur l'installation `--target` : la vérification des prérequis
(`environment.report`) n'est qu'un avertissement non bloquant en tête, les
autres délèguent au moteur (T03), au préfixe (T04) et à l'instance MO2 (T05).

Chaque étape est déjà idempotente **côté module** (voir plus haut) ; `state.py`
ajoute par-dessus un raccourci de reprise : un TOML sous
`~/.config/stalker-gamma-linux/install-state.toml`, keyé par chemin cible
absolu, marque chaque étape validée. Une relance après Ctrl-C saute les étapes
déjà faites au lieu de les rejouer (en particulier `full-install`, dont la
re-vérification MD5 sur ~90 Go n'est pas gratuite). Ce n'est **pas** la source
de vérité de santé de l'installation — si une étape est cassée manuellement
après coup, c'est `update`/`prefix-doctor --repair` qui corrige, pas une
invalidation automatique de cet état.

`run_update` (aussi dans `orchestrator.py`) est plus simple et non résumable
par design (le prompt ne le demande pas) : `update_gamma` → retrait de
ReShade/purge shaders → `verify` (check-anomaly + check-md5), à chaque appel.

### `doctor` : composition, pas fusion

La commande `doctor` (`doctor.py`, racine du paquet — distinct de
`environment.report` et de `prefix.doctor`) affiche les trois rapports
existants côte à côte (environnement, préfixe, état d'installation) sans les
fusionner. Le code de retour ne reflète que les prérequis système : le
préfixe/l'installation peuvent être légitimement incomplets sur une machine
neuve avant `install`, ce n'est pas un échec de `doctor` — `prefix-doctor`
reste l'outil de vérité pour la santé du préfixe.

### Sortie et logs

`output.py` centralise la sortie des commandes orchestrées (`install`,
`update`, `doctor`) via `rich.console.Console` (couleurs, formatage), et double
chaque message vers le logger applicatif (`logging_setup.py`). Ce dernier
configure un `RotatingFileHandler` toujours actif (DEBUG) sous
`~/.local/state/stalker-gamma-linux/`, et un handler console dont le niveau
suit le flag global `--verbose` (avant la sous-commande :
`stalker-gamma-linux --verbose install`). Les modules bas niveau (`engine/`,
`prefix/`, `mo2/`) gardent leurs `print()`/`on_progress` existants — non
retouchés, déjà lisibles et déjà testés ; seule la couche orchestrateur ajoute
`rich`. `cli.main()` attrape toute exception inattendue à la racine, la loggue
avec sa trace complète, et affiche un message actionnable (chemin du journal,
suggestion `--verbose`) plutôt qu'un traceback brut.

## GUI GTK4/libadwaita (T08)

### Aucune logique métier dans la GUI : `output.Reporter` + callbacks existants

La GUI (`src/stalker_gamma_linux/gui/`) consomme exactement les mêmes
fonctions que la CLI (`orchestrator.run_install`/`run_update`,
`mo2.session.run_mo2`/`run_play`, `doctor.build_full_report`) — rien n'est
réimplémenté. Deux petits ajouts, partagés avec la CLI et testés
indépendamment de GTK, ont rendu ça possible :

1. **`output.Reporter`** (protocole structurel) : `orchestrator.run_install`/
   `run_update` appelaient jusqu'ici `output.header`/`step`/`warn`/… en dur
   (`rich` + logger). Ils acceptent maintenant `reporter: Reporter =
   output.console_reporter` — la CLI ne change pas de comportement (le
   défaut est l'ancien `output.py`), la GUI fournit `gui.worker.QueueReporter`,
   qui pousse chaque événement sur une `queue.Queue` au lieu de l'imprimer.
2. **`cancel_event: threading.Event | None`** : ajouté à `engine.process.run`,
   `prefix.process.run_in_prefix`, et propagé à travers `engine/runner.py`,
   `prefix/provision.py`/`proton.py`/`verbs.py`/`download.py` et
   `orchestrator.run_install`/`run_update`. Un thread « watchdog » dédié
   (`_watch_cancellation`) tue le sous-process (`terminate` puis `kill`) dès
   que l'event est levé ; le sous-process lève alors `EngineCancelledError`/
   `PrefixCancelledError` au lieu du code d'erreur habituel.
   `orchestrator.CANCELLED_EXIT_CODE` (130, convention POSIX 128+SIGINT) est
   retourné dans ce cas — l'étape interrompue n'est pas marquée faite dans
   `state.py`, une relance la rejoue. Jamais passé par la CLI (`None` par
   défaut) : comportement inchangé.

`mo2.session.run_mo2`/`run_play` étaient câblés en dur sur `print()` ; ils
acceptent maintenant `on_progress: Callable[[str], None] | None` (retombant
sur `print` si absent, résolu dynamiquement pour rester monkeypatchable —
voir le piège de liaison tardive ci-dessous). `doctor.py` a été scindé :
`build_full_report()` fait la collecte (retourne un `DoctorReport` structuré,
`Requirement` par `Requirement`, avec `install_hint`) ; `run_doctor()` (CLI)
est la seule fonction du module qui imprime.

Piège rencontré : `on_progress: ProgressCallback = print` comme *valeur par
défaut* lie `print` à l'import du module — un test qui monkeypatche
`builtins.print` plus tard ne voit plus rien. Le correctif (déjà en usage
ailleurs dans le code, `engine/process.py` etc.) : `on_progress: ... | None
= None` + `progress = on_progress or print` **dans le corps** de la fonction,
résolu à chaque appel.

### `gui.viewmodel`/`gui.worker`/`gui.prefs` : testables sans `gi`

`gui/__init__.py` est vide de tout import : ces trois modules ne dépendent
jamais de PyGObject et sont testés par `pytest` comme n'importe quel autre
module du projet (`tests/test_gui_*.py`), y compris sur une machine sans
GTK4/libadwaita. Seuls `gui/app.py` et `gui/windows/*.py` importent `gi`.

- **`viewmodel.py`** : `InstallStatus` (NOT_INSTALLED/INSTALLED) ne lit que
  `state.py` (TOML local, quasi instantané) — **pas**
  `doctor.build_full_report`, qui lance plusieurs sous-process
  (`which`/`ldconfig`/`vulkaninfo`…) et rafraîchirait le statut de la
  fenêtre principale en gelant l'UI le temps de ces appels. La vue
  Diagnostic, elle, appelle `build_full_report` dans un thread dédié.
- **`worker.BackgroundTask`** : lance `func(events, cancel_event) -> int`
  dans un thread démon ; publie `ReporterEvent`/`DoneEvent`/`FailedEvent` sur
  une `queue.Queue`. Le côté GTK (`ProgressPage`) la draine via
  `GLib.timeout_add` (poll, 80 ms) — c'est le seul point de contact avec la
  boucle GTK, tout le reste de `worker.py` est du `threading`/`queue` pur.
- **`prefs.py`** : préférences GUI (chemin d'installation, version
  Proton-GE, création du raccourci) en TOML sous
  `~/.config/stalker-gamma-linux/gui-prefs.toml` (réutilise
  `state.config_dir()` — même racine XDG que `install-state.toml`, fichier
  séparé). « Version Proton-GE » a nécessité un petit ajout partagé (pas GUI
  uniquement) : `proton.ensure_proton(..., release=...)` /
  `provision.ensure_prefix(..., proton_release=...)` /
  `orchestrator.run_install(..., proton_release=...)`, vide = comportement
  par défaut inchangé (dernière release GE, décision T04).

### « Mise à jour disponible » : pas de détection, action explicite

Le prompt T08 demandait un statut « pas installé / installé / mise à jour
disponible ». Vérifié dans `gamma-launcher` (v3.1, `commands/install.py`) :
il n'existe **aucun moyen bon marché** de savoir si une mise à jour est
disponible sans lancer le téléchargement lui-même — la comparaison de
révision (`crev == g.downloader.revision`) se fait *après* avoir téléchargé
l'archive GitHub. Fabriquer une détection (ex. appeler une API externe) sans
mécanisme réel derrière aurait été de la logique métier inventée dans la
GUI, contraire au principe du prompt. Le statut est donc binaire
(`InstallStatus`), et « Mettre à jour » est exposée comme une action
explicite du menu (toujours visible, activée seulement si installé) plutôt
que comme un troisième état auto-détecté — exactement ce que fait déjà la
CLI avec ses commandes séparées `install`/`update`.

### Annulation

`ProgressPage` passe un `threading.Event` neuf par tâche à `BackgroundTask` ;
le bouton « Annuler » le lève. Propagé à `orchestrator.run_install`/
`run_update` (voir plus haut), il interrompt proprement le sous-process en
cours — jamais un `kill -9` du process GUI lui-même. `mo2.session.run_mo2`/
`run_play` n'acceptent pas `cancel_event` (portée volontairement limitée :
ce sont des lancements courts, pas des téléchargements de plusieurs Go) ; le
bouton Annuler de `ProgressPage` est donc masqué pour ces deux tâches
(`cancellable=False`).

### Adaptatif Steam Deck (1280×800)

Fenêtre par défaut 820×620 (confortable dans 1280×800, y compris en fenêtre
bordless de Gaming Mode) ; boutons principaux dimensionnés pour le tactile
(`_BUTTON_HEIGHT = 56`, recommandation HIG ≥ 44 px) ; navigation clavier/
manette gratuite via le focus GTK4 standard (`set_default_widget` + focus
initial sur le bouton contextuel, Steam Input mappe le D-Pad/A sur les
flèches/Entrée sans code spécifique) ; retour geste tactile natif via
`Adw.NavigationView`. Pas d'`Adw.Breakpoint` : 1280×800 est un paysage large,
pas un cas de collapse étroit — en ajouter un aurait été de la complexité
sans besoin réel identifié.

### Identifiant d'application

`Gio.Application` exige un id syntaxiquement à la D-Bus (au moins un point),
contrairement au `.desktop` de T06 qui reste `stalker-gamma-linux` sans
reverse-DNS (décision explicite de `desktop/paths.py`, pour rester
indépendant d'un compte GitHub précis). Même logique reconduite ici :
`org.stalkergammalinux.Gui` plutôt que `io.github.<compte>...`. Fichier
statique `data/stalker-gamma-linux-gui.desktop` (+ `data/icons/`) pour le
menu applications — packagé par T09 (Flatpak/AppImage installent chacun
ce genre de fichier différemment) ; il n'est **pas** auto-installé par
`pip install`, à la différence du raccourci dynamique de T06
(`stalker-gamma-linux shortcut`, qui pointe vers `play`, pas vers la GUI).

### Environnement de développement : `--system-site-packages`

PyGObject n'a pas de roue manylinux (extension liée à GLib/GObject-
introspection du système) ; `pip install pygobject` échoue sans
`cairo-devel`/`gobject-introspection-devel` (constaté en réel). Le venv de
dev est donc créé avec `python3 -m venv --system-site-packages .venv` pour
voir le PyGObject du système (déjà installé, GTK4 4.22 + libadwaita 1.9
validés en réel) ; `PyGObject-stubs` est ajouté à l'extra `dev` pour que
`mypy --strict` type les appels `gi.repository.*`. La CLI n'a jamais besoin
de ce groupe (`gui` en extra séparé) — `stalker-gamma-linux-gui`
(`gui/launch.py`) vérifie GTK4/libadwaita avant tout `import gi` et affiche
un message actionnable (par distribution) si absent, au lieu d'un
`ModuleNotFoundError` brut.

## Packaging (T09)

### Deux canaux, pas trois : AUR retiré du périmètre

Le prompt T09 demandait Flatpak/AppImage/AUR. Décision Florian (2026-07-23,
« AUR je m'en tape ») : retiré. Les deux canaux restants se répartissent le
travail par ce que chacun fait bien : le **Flatpak** (canal principal) porte
la GUI (bac à sable, GTK4/libadwaita fournis par le runtime GNOME) ; l'
**AppImage** porte un **CLI portable** (voir plus bas pourquoi pas la GUI).
Détails complets, permissions ligne par ligne, et ce qui est délibérément
non embarqué (libunrar) : `docs/PACKAGING.md`.

### Flatpak : bac à sable et dépendances externes non visibles

Le sandbox ne voit ni le `umu-run` ni le `7z` de l'hôte (recherche PATH
strictement interne à `/app:/usr`, `--filesystem=host` ne donne qu'une
visibilité fichier, pas d'exécution). Sans rien de plus, `gamma-launcher`
échouerait à extraire les archives et `prefix/process.py` ne trouverait
jamais umu, même sur un hôte qui les a tous les deux. D'où deux modules
supplémentaires embarqués :

- **p7zip** (module `p7zip.yml`), compilé depuis les sources
  (`p7zip-project/p7zip` v17.05, LGPL/domaine public) — fournit `7z` dans
  `/app/bin`.
- **umu-launcher** (module `umu-launcher.yml`), la release « zipapp »
  officielle (script Python autonome, dépendances gelées dedans) — même
  mécanisme que celui que Florian utilise déjà manuellement sur sa propre
  machine (voir historique T04), mais embarqué une fois pour toutes au lieu
  d'être une étape manuelle par utilisateur.

Les dépendances Python (les nôtres + celles de `gamma-launcher`) viennent
d'un module généré par `flatpak-pip-generator` (`python3-requirements.json`)
plutôt qu'écrites à la main : c'est la seule façon réaliste de figer une
douzaine de paquets (dont plusieurs extensions C : `py7zr` en tire sept)
avec les bons sha256 et sans jamais toucher le réseau pendant le build
flatpak-builder proprement dit.

Deuxième piège Python-sur-Flatpak, indépendant du premier : `sys.prefix` de
l'interpréteur du runtime est `/usr` (c'est là que vit `/usr/bin/python3`),
donc `/app/lib/python3.13/site-packages` n'est pas sur `sys.path` par
défaut alors que c'est là que `pip install --prefix=/app` installe tout —
fixé par `--env=PYTHONPATH=/app/lib/python3.13/site-packages` dans
`finish-args` (même fix que Bottles, pour la même raison).

### AppImage : CLI seul, pas la GUI

Embarquer GTK4/libadwaita proprement dans une AppImage est un projet à part
(`linuxdeploy` + son plugin GTK, typelibs, thèmes d'icônes...), d'une échelle
différente de « empaqueter un CLI Python ». Plutôt que de le faire à moitié,
le périmètre est scindé : le Flatpak porte la GUI (GTK fourni par le
runtime), l'AppImage porte un CLI totalement portable (aucune dépendance
GTK). Mêmes modules `p7zip`/`umu-run` embarqués que le Flatpak, mêmes
raisons — sauf que l'AppImage n'est *pas* dans un bac à sable (elle hérite du
`$PATH` normal de l'hôte), donc c'est ici une question de disponibilité
réelle sur la machine cible plutôt que d'isolation.

Trois pièges rencontrés côté outillage amont (`python-appimage`), documentés
en commentaire à l'endroit exact où ils mordent (`requirements.txt.in`,
`stalker-gamma-linux.desktop`, `entrypoint.sh`) :

1. Son étape d'installation des dépendances passe par un `shell=True` non
   quoté (`utils/system.py` : `' '.join(args)`) — un requirement PEP 508
   `nom @ url` (espaces autour du `@`) est coupé en plusieurs tokens et
   casse pip. Contournement : la forme `git+url` seule, sans espace.
2. Même défaut de quoting pour l'étape finale d'empaquetage : le nom de
   fichier `.AppImage` de sortie vient du `Name=` du `.desktop`, donc un nom
   « d'affichage » avec espaces/parenthèses casse l'appel à `appimagetool`.
   Contournement : `Name=` reste un identifiant simple.
3. `stalker_gamma_linux.cli` n'a pas de garde
   `if __name__ == "__main__"` (volontaire : le point d'entrée prévu est le
   script `console_scripts` généré par pip, pas `-m`) — `entrypoint.sh`
   appelle donc directement ce script généré plutôt que
   `-m stalker_gamma_linux.cli`, qui importerait le module sans jamais
   appeler `main()` et sortirait en silence avec le code 0.

## Références

- Moteur : https://github.com/Mord3rca/gamma-launcher
- Compatibilité MO2 × Proton × USVFS : `docs/MO2-PROTON-COMPAT.md`
- Modpack : https://github.com/Grokitach/Stalker_GAMMA (AGPL-3.0)
- API modlist : https://stalker-gamma.com/api/list
- Guide historique : https://github.com/FaithBeam/stalker-gamma-cli/wiki/Linux-Install
- Gist d'install manuelle : https://gist.github.com/v1ld/e9069af307bd90495e0b345f3a260725
