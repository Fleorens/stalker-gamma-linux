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
│  - Install natif (install.sh, pas de sandbox)│
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
5. **Fallback flat (`flat.py` + `merge.py`)** — accessible uniquement par flag
   explicite (`play --flat`). Fusionne Anomaly + les mods **par liens durs**,
   puis lance `AnomalyLauncher.exe` du dossier fusionné. **Perte de la
   flexibilité des mods** — d'où le flag et l'avertissement
   (docs/INSTALL-MANUAL.md annexe A).

   *Seule divergence assumée vis-à-vis du moteur amont*, et elle est mesurée :
   `gamma-launcher usvfs-workaround` fait des `copytree` (vérifié dans son code
   v3.1, `commands/usvfs.py`), donc le fallback coûtait une seconde
   installation complète — ~100 Gio. Un lien dur donne le même arbre pour
   quelques inodes. On ne réimplémente que la fusion : la résolution ModDB, le
   parsing des directives et la vérification MD5 restent chez gamma-launcher.
   Le correctif a vocation à remonter en amont (option `--link`).

   Deux règles que `merge.py` applique et qui n'ont rien d'évident :
   l'ordre d'application suit `modlist.txt` **de bas en haut** (priorité
   croissante vers le haut chez MO2, donc le mod prioritaire écrase en
   dernier), et tout ce qui vit sous `appdata/` est **copié, jamais lié** —
   le jeu y réécrit ses réglages et ses sauvegardes, et un lien dur les
   ferait remonter dans l'installation MO2 d'origine.

`session.py` orchestre les commandes `mo2` et `play` : préfixe prêt (T04) →
instance configurée → lancement → diagnostic.

### GameMode : enveloppe du lancement, pas de l'installation

`environment/gamemode.py` enveloppe la commande dans `gamemoderun` quand Feral
GameMode est installé. Trois choix qui méritent d'être écrits :

- **Où** : uniquement les lancements de *jeu* (`launch_game`, `launch_flat`),
  jamais `launch_mo2` ni les étapes d'installation — épingler le gouverneur CPU
  en `performance` pendant un téléchargement de 146 Gio n'a aucun intérêt.
- **Quoi envelopper** : `umu-run`, pas l'exécutable du jeu. `gamemoderun` pose
  `libgamemodeauto.so.0` dans `LD_PRELOAD`, qui se propage à toute la
  descendance (runtime umu → wine → MO2 → le jeu) ; c'est exactement le
  mécanisme de l'option Steam `gamemoderun %command%`. Inutile d'aller chercher
  le processus du jeu au fond de la pile.
- **Le piège du groupe `gamemode`** : Fedora et Arch livrent une règle polkit
  qui réserve `cpugovctl`/`gpuclockctl` aux membres du groupe `gamemode`
  (l'action est en `allow_active: no`). Hors du groupe, le mode s'active et
  `gamemoded -s` répond « active », mais chaque changement de gouverneur échoue
  en `pkexec … Not authorized` dans le journal — rien de visible côté joueur, la
  moitié du bénéfice en moins. `gamemode.group_status()` le détecte et `doctor`
  affiche le `usermod` correspondant. L'appartenance se lit dans la base système
  (`grp`/`pwd`) et **pas** dans les gids du processus : c'est ce que fait le
  `subject.isInGroup()` de polkit. Mesuré le 2026-08-13 sur la machine de dev —
  après `usermod -aG`, le gouverneur est passé en `performance` (16/16 CPU,
  `gamemoded -t` intégralement au vert) sans reconnexion, alors que le daemon
  comme le shell appelant dataient d'avant l'ajout au groupe.

Rien n'est bloquant : sans GameMode, la commande part telle quelle ; sans le
groupe, le jeu se lance quand même avec les priorités I/O.

**Bruit attendu dans le journal de lancement.** À chaque partie, la sortie
contient des dizaines de lignes :

```
gamemodeauto: dlopen failed - libgamemode.so: cannot open shared object file
```

C'est cosmétique, et identique sous Steam avec `gamemoderun %command%`.
pressure-vessel importe bien la bibliothèque préchargée dans le conteneur
steamrt (`--ld-preload=/run/host/lib64/libgamemodeauto.so.0:abi=x86_64…`, plus
son équivalent i386), mais **pas** le `libgamemode.so.0` qu'elle `dlopen` à
l'exécution : ce n'est pas une entrée `LD_PRELOAD`, et l'éditeur de liens du
conteneur ne cherche pas dans le `/usr` de l'hôte. Chaque processus interne
râle donc puis s'abstient de s'enregistrer. Sans conséquence : c'est le
processus `umu-run` côté hôte qui détient l'enregistrement pour toute la durée
de la session. Vérifié le 2026-08-13, jeu lancé : `gamemode is active` et
16/16 CPU en `performance`. Même remarque pour les
`ERROR: Skipping ioprio on client […]` du journal de `gamemoded` — message
amont bavard, pas un échec.

On ne filtre pas ces lignes de notre sortie : masquer ce que crachent umu et
wine reviendrait à masquer aussi les vrais problèmes le jour où il y en aura.

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

### Modules purs (`viewmodel`, `worker`, `prefs`, `phases`, `space`, `summary`, `format`) : testables sans `gi`

`gui/__init__.py` est vide de tout import : ces modules ne dépendent
jamais de PyGObject et sont testés par `pytest` comme n'importe quel autre
module du projet (`tests/test_gui_*.py`), y compris sur une machine sans
GTK4/libadwaita. Seuls `gui/app.py`, `gui/theme.py` et `gui/windows/*.py`
importent `gi`.

Le rendu « launcher » (refonte post-T08) repose sur quatre modules purs
supplémentaires, chacun avec sa suite de tests :

- **`phases.py`** : timeline immuable des étapes d'install/update. Chaque
  événement `Reporter` (`step`/`skip` indexés « n/total », `progress`,
  `error`, `success`) produit une **nouvelle** `Timeline` ; la vue
  progression ne fait que la redessiner (états fait / déjà fait / en cours
  avec détail moteur / échec) et en tirer une **fraction réelle** — plus de
  barre en pulsation pendant une installation.
- **`space.py`** : espace libre sur le volume de la cible
  (`shutil.disk_usage` sur le premier ancêtre existant), verdict
  OK / juste / insuffisant / inconnu. Le dialog de pré-installation bloque
  sous `MINIMUM_FREE_BYTES` (160 Gio) et avertit sous
  `RECOMMENDED_FREE_BYTES` (250 Gio, recommandation amont). Ces deux seuils
  viennent de `sizing.py` (voir « Dimensionnement disque » ci-dessous) — pas
  de constante locale.
- **`summary.py`** : compresse l'`EnvironmentReport` (7 prérequis) en une
  puce « Système prêt / N prérequis manquants » pour l'accueil — la collecte
  tourne dans un thread au démarrage et à chaque retour de tâche.
- **`format.py`** : parsing d'index « n/total », tailles (`Gio`), durées.

L'identité visuelle vit dans `gui/theme.py` (palette « Zone », feuille de
style unique — aucune vue ne fait de CSS inline) ; l'artwork de fond est
généré de façon déterministe par `scripts/generate_background.py`
(numpy + Pillow, seed fixe, jamais importés par le paquet) et embarqué en
`assets/background.jpg`.

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
  Le drainage est intégral (sortir un événement de la queue ne coûte rien),
  mais le **rendu** est plafonné à `_POLL_EVENT_BUDGET` événements par tick :
  gamma-launcher sort par rafales de centaines de lignes, et les rendre toutes
  dans un seul tour de boucle figeait la fenêtre (138 ms mesurés sur une rafale
  de 5000 lignes, 24 ms avec le budget) — or « Annuler » est le seul contrôle
  de cet écran. Le retard est repris aux ticks suivants ; une fin de tâche vue
  derrière une rafale est traitée dans le tick même où elle arrive, sans
  attendre l'affichage du retard. La console est bornée à `_LOG_MAX_LINES`
  (le tampon atteignait sinon des centaines de milliers de lignes sur une
  install complète) : la troncature ne concerne **que** l'affichage, le journal
  complet restant écrit sur disque par `QueueReporter`.
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
menu applications — installé par `install.sh` ; il n'est **pas**
auto-installé par `pip install`, à la différence du raccourci dynamique de
T06 (`stalker-gamma-linux shortcut`, qui pointe vers `play`, pas vers la
GUI).

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

## Intégrité des mods installés (T12)

`engine.verify` (`check-md5` du moteur) répond à « le téléchargement était-il
correct » : il compare les **archives** de `gamma/downloads` aux sommes
publiées. Il ne dit rien de ce qui est réellement posé sur le disque. Le
paquet `integrity/` couvre l'autre moitié — « l'install est-elle encore
intacte » — c'est-à-dire le premier symptôme que remonte un joueur (« le jeu
crashe depuis hier », après qu'un autre outil a écrasé un fichier ou qu'un
disque plein en a tronqué un). Commande `verify [--repair]`, plus deux boutons
dans la vue Diagnostic de la GUI ; `integrity.run_verify` est le seul point
d'entrée, partagé mot pour mot par les deux (`Reporter` + `cancel_event`).

Sept décisions qui ne se lisent pas dans le code :

1. **La référence est un fichier texte à côté de l'install**
   (`<install>/gamma-md5.txt`, format `md5sum`), pas un état sous
   `~/.config`. Elle décrit *cette* installation : elle doit la suivre si elle
   est déplacée ou sauvegardée, et rester lisible à la main. Le parsing
   découpe **après le hash** au lieu de trancher à l'offset 32 : un fichier
   produit par `md5sum -b` (préfixe `*`) ou retabulé continue d'être relu, et
   toute ligne qui ne se relit pas est rapportée à l'utilisateur — jamais
   avalée, parce qu'elle produit de faux « supprimé ».
2. **Premier passage = enregistrement, pas vérification.** Sans référence
   antérieure il n'y a rien à comparer ; annoncer « aucun écart » ferait
   croire à une vérification. On enregistre, on le dit, et la reprise de
   référence après réparation est une **étape à part entière** (un second scan
   complet, annoncé comme tel) — sans elle, les mods qu'on vient de remettre
   en état ressortiraient « modifiés » au passage suivant.
3. **Un scan annulé ne peut pas atteindre l'écriture de la référence.** Ce
   n'est pas une convention d'appel : `scan.scan_tree` **lève**
   `IntegrityCancelledError` au lieu de retourner un résultat partiel. Une
   install potentiellement cassée ne peut donc pas être figée comme nouvelle
   référence par un Ctrl-C ou un bouton Annuler.
4. **« Venir du modpack » ne se lit pas dans un seul fichier.** C'est le
   piège que seule une install réelle a révélé : `full-install` peuple
   `mods/` depuis **trois** sources, et `modlist.txt` n'en est qu'une.
   - `modlist.txt`, séparateurs compris — `mo2/modlist.py` les écarte à
     raison pour qui compte des mods, mais gamma-launcher en crée de vrais
     dossiers avec un `meta.ini` (`SeparatorInstaller.install`) : 28 sur
     l'install de test ;
   - `modpack_addons/` — 388 dossiers livrés en clair, copiés tels quels par
     `_copy_gamma_modpack`, **absents de `modlist.txt`** ;
   - les ressources Git (`gamma_large_files_v2`,
     `teivaz_anomaly_gunslinger`), dont les dossiers ne sont connus qu'après
     clonage.

   On réunit les deux premières, qui se lisent hors ligne. La troisième reste
   hors de portée sans plomberie Git : ses mods tombent dans « source
   inconnue » et sont signalés puis **laissés intacts** — le bon échec, le
   doute devant toujours empêcher une suppression. Sur l'install de test, le
   nombre de dossiers non reconnus est passé de 43 à 5, dont 3 relèvent de ce
   dernier cas ; le message ne prétend donc plus que le joueur les a ajoutés.

   Corollaire mesuré : comme la réparation délègue à `full-install`, qui
   ré-extrait **tous** les mods par-dessus l'existant, elle ne se limite pas
   au mod visé — 478 fichiers d'autres mods ont changé, et 43 sont apparus,
   sur une install réelle. Rien n'a disparu, et les fichiers ajoutés par le
   joueur ont été préservés (`copytree(dirs_exist_ok=True)` recouvre, ne
   supprime pas). Effet secondaire utile : les mods écartés de la réparation
   voient quand même leurs fichiers abîmés restaurés en place. La commande le
   dit maintenant explicitement plutôt que de laisser croire à une opération
   strictement chirurgicale.
5. **Les fichiers `added` ne sont jamais réparés — et le dossier qui les
   contient non plus.** Réparer, c'est `rmtree` sur le dossier du mod : un
   `.ltx` retouché ou un patch déposé dedans partirait avec. Épargner le
   fichier au moment du diff ne suffit donc pas, il faut épargner son dossier.
   Un mod abîmé qui contient des ajouts est signalé avec sa raison et laissé
   intact, comme les mods sans source amont (extras du joueur). La liste qui
   fait autorité est le `modlist.txt` de `modpack_data/` déposé par
   gamma-launcher, entrées désactivées comprises — désactivé dans MO2 ne veut
   pas dire absent du disque.
6. **« Réinstaller ce sous-ensemble » n'existe pas côté moteur.**
   gamma-launcher v3.1 n'a aucune option pour n'installer qu'un mod
   (`FullInstall._install_mods` parcourt toute la liste). Ce qu'on contrôle,
   c'est le sous-ensemble **retéléchargé** : en retirant le dossier du mod
   *et* son archive, seuls ces mods-là repartent du réseau, le reste étant
   réutilisé depuis le cache (`use_cached=True`). La correspondance dossier →
   archive se lit dans le `meta.ini` que le moteur écrit à l'installation
   (`installationFile=`) : c'est la seule disponible **hors ligne**, le nom de
   fichier réel d'un téléchargement ModDB n'étant connu qu'en interrogeant la
   page ModDB.
7. **Un fichier dont la taille et la date n'ont pas bougé n'est pas relu — et
   on le dit.** La référence porte désormais une colonne `taille,mtime_ns`
   (`<md5>  <taille>,<mtime_ns>  <chemin>`), ce qui permet à `scan_tree` de
   reprendre une empreinte au lieu de rouvrir le fichier. Sans elle, deux
   `verify` d'affilée relisaient les 83 Gio à l'identique — mesuré sur banc :
   2,34 Gio passent de 0,84 s à 0,04 s, aucun octet lu, empreintes
   identiques. Ce que ça coûte, dit franchement : une corruption qui
   préserverait taille *et* date deviendrait invisible. Toutes celles que ce
   module vise passent par une écriture ordinaire — troncature sur disque
   plein, écrasement par un autre outil, extraction interrompue — et déplacent
   donc l'une ou l'autre ; ce qui reste, c'est la réécriture suivie d'un
   `os.utime` délibéré (un geste d'adversaire, et ce MD5 n'authentifie rien —
   qui peut réécrire un mod peut réécrire `gamma-md5.txt`, fichier texte non
   signé) et l'altération survenue *sous* le système de fichiers (bitrot,
   câble ou RAM défaillants). C'est pour cette dernière qu'existe
   `verify --full`, qui ignore la colonne et relit tout. Trois garde-fous
   rendent le défaut tenable : le nombre de fichiers non relus figure **dans
   le rapport**, pas en note de bas de page ; une référence d'ancien format
   n'a aucune colonne, donc fait tout rehacher (le doute fait toujours relire,
   jamais l'inverse) ; et la reprise qui ajoute la colonne à une telle
   référence n'attache taille et date qu'aux fichiers dont l'empreinte relue
   **égale** celle de la référence — en donner à un fichier abîmé le ferait
   court-circuiter au passage suivant, et l'avarie sortirait du rapport sans
   avoir été réparée.

Trois points d'implémentation qui ont une raison précise :

- **La progression est cadencée au temps écoulé, jamais à l'index.** Les
  fichiers de mods vont de quelques octets à plusieurs gigaoctets : un
  `i % 500 == 0` fige l'interface pendant de longues secondes sur les gros
  puis noie la console sur les petits. Le compteur est aussi rafraîchi *entre
  deux blocs* d'un même fichier, et c'est au même endroit que l'annulation est
  vérifiée — un `cancel_event` levé au milieu d'un fichier de 4 Gio rend la
  main tout de suite. L'horloge est injectable, ce qui rend la cadence
  testable sans `sleep`.
- **Le hachage est parallèle, le résultat ne l'est pas.** `scan_tree`
  distribue les fichiers sur un `ThreadPoolExecutor` (jamais
  `multiprocessing` : `hashlib` libère le GIL, le coût de sérialisation
  mangerait le gain). Mesuré sur 7,86 Gio et 20 735 fichiers, cache de pages
  vidé avant chaque passe : 18,6 s avant, 10,4 s après — les empreintes étant
  bit à bit identiques. Trois précautions rendent ce gain acceptable :
  - **L'ordre ne bouge pas.** Les tâches sont consommées dans l'ordre de
    *soumission* et non d'achèvement, ce qui laisse `digests` dans l'ordre de
    parcours ; `unreadable` est retrié en sortie, ses entrées naissant à la
    fois du parcours et du hachage, donc à des moments décalés.
  - **Le défaut s'adapte au support.** Quatre fils sur mémoire flash — c'est
    le coude de la courbe, doubler encore ne rend que ~8 % parce que le
    plafond n'est plus MD5 mais la part de la boucle qui garde le GIL — et
    **un seul** sur un disque à plateaux, où quatre lecteurs concurrents
    remplacent une lecture séquentielle par un va-et-vient de têtes.
    `integrity/storage.py` répond à cette question-là, et il ne peut pas se
    contenter de `st_dev` : sur btrfs ou NFS le noyau rend un numéro anonyme,
    il faut passer par `/proc/self/mountinfo` puis `queue/rotational`. Un
    support indéterminable est traité comme non mécanique.
  - **L'annulation reste immédiate.** Un `threading.Event` interne double
    celui de l'appelant, qui peut être absent : Ctrl-C compris, les fils en vol
    sortent au bloc suivant (~1 Mio) au lieu de finir un fichier de plusieurs
    Gio, et `scan_tree` ne rend jamais la main en laissant un fil derrière lui.
- **Les noms de mods sont validés avant tout `rmtree`/`unlink`**, par les
  mêmes fonctions que T11 (`paths_safety.validate_removable_child`) : ils
  viennent de la liste amont et de `meta.ini`, pas de nous. Un `..`, un
  séparateur de chemin ou un lien symbolique fait tout refuser — et le refus
  intervient **avant** la moindre suppression, pour qu'un `meta.ini` douteux
  ne laisse pas un mod à moitié retiré.

### Effet de bord corrigé au passage : `output.py` échappait le balisage `rich`

Les messages passés à `output.progress`/`warn`/… étaient rendus tels quels par
`rich.Console.print`, donc interprétés comme du balisage. Un nom de dossier de
mod comme `101- Mod A [pack]` — les crochets sont courants dans le modpack —
**disparaissait** de l'affichage, et une chaîne contenant `[/…]` levait
`MarkupError` en pleine installation. Les couleurs sont maintenant posées
autour d'un message échappé. L'échappement ne concerne que le rendu console :
le logger et le `Reporter` de la GUI reçoivent toujours le message brut.

## Sauvegarde, restauration, et fusion de la modlist (T17)

C'est la plainte n°1 de G.A.M.M.A., toutes plateformes confondues. Le wiki
officiel l'écrit lui-même : « *every time you click Install / Update GAMMA,
your modlist, settings, and mod settings will reset. This is on purpose […]
remember to make backups before clicking that button* ». Sous Windows, la
réponse tient donc en un conseil que personne n'applique.

Deux moitiés, et elles ne font pas la même chose : le paquet `backups/` rend
la perte **réversible**, la fusion de `mo2/modlist_merge.py` fait qu'elle
**n'a pas lieu**.

### Où vivent les sauvegardes de partie — constaté, pas supposé

Anomaly est portable (`fsgame.ltx` : `$game_saves$ = $app_data_root$ |
savedgames\`), mais sous MO2 l'USVFS peut rediriger ces écritures vers
`overwrite/` ou vers le profil selon la configuration de l'instance. La
question a donc été tranchée **sur l'installation de test** avant d'être codée
(`/mnt/games_samsung/Games/GAMMA`, GAMMA 920, MO2 2.5.2, relevé le
2026-09-07, parties jouées jusqu'au 26 août) :

| Constat | Mesure |
|---|---|
| `anomaly/appdata/savedgames/` | 29 fichiers, 39 Mio, horodatés à la minute de la dernière session de jeu |
| `gamma/overwrite/` | **vide** — créé le 22 août, jamais écrit |
| `profiles/G.A.M.M.A/settings.ini` | `LocalSaves=false`, et aucun `profiles/G.A.M.M.A/saves/` |
| dernier `usvfs-*.log` | **aucune** correspondance pour `savedgames` ; les seules entrées sous `appdata\` concernent `shaders_cache`, et elles mappent le chemin réel sur lui-même |

Conclusion : sur la configuration livrée par GAMMA, le jeu écrit ses
sauvegardes **en direct** dans `anomaly/appdata/savedgames`, sans passer par
`overwrite/`. Les deux autres emplacements restent atteignables par
configuration (`LocalSaves=true` range les parties par profil ; l'USVFS
dévierait vers `overwrite/` une écriture faite dans un dossier virtualisé) :
ils sont donc sauvegardés **aussi**, quand ils existent et ne sont pas vides.
Trois `is_dir()` contre le risque de rater l'emplacement réel, le choix est
vite fait. Quand deux ensembles se recouvrent (`gamma/overwrite/appdata/
savedgames` vit sous `gamma/overwrite`), le plus large gagne — sinon la
sauvegarde doublerait de taille et la restauration aurait deux vérités.

### Format, rotation, restauration

Un dossier horodaté par sauvegarde sous `<root>/backups/`, **au nommage
historique** `profiles-%Y%m%d-%H%M%S` : les sauvegardes déjà posées par
l'ancien `orchestrator.backup_mo2_profiles` restent ainsi reconnues et
restaurables (`manifest.legacy_manifest` en synthétise le manifeste à partir
de ce qu'on sait d'elles avec certitude — le dossier *est* une copie de
`profiles/`, et son nom porte la date). Le préfixe est donc un vestige
assumé : c'est le **manifeste** (`backup.toml` : date, version GAMMA,
ensembles, destinations, tailles) qui dit ce qu'il y a dedans, et c'est lui
que lit `--list`, jamais un `stat` du dossier.

Trois règles portent le reste :

1. **Rotation** — cinq sauvegardes automatiques au plus, la plus ancienne part
   au-delà. Une sauvegarde créée explicitement (`stalker-gamma-linux backup`)
   n'y entre **jamais** : c'est un point de retour, pas un cache. Toute
   suppression passe par `paths_safety.validate_removable_child` — c'est un
   `rmtree` sur un chemin dérivé de `--target`, exactement le périmètre de T11.
2. **Restauration** — `restore <id>` sauvegarde l'état courant **avant** de
   l'écraser (une restauration ratée ne doit pas être un aller simple), refuse
   de tourner si MO2 ou le jeu occupent le préfixe (`prefix.session`, T13 ;
   `--force` passe outre), et affiche son plan avec `--dry-run` comme
   `uninstall` et `import`. Chaque destination est reconstruite **à côté**
   puis échangée par deux `rename` : un échec de copie laisse le dossier du
   joueur intact, et un échec de l'échange le remet.
3. **Ce qui est mis à l'abri avant un `update`** — les profils (le motif
   d'origine : `full-install` les réécrit) **et les parties**. Le même update
   appelle `purge-shader-cache`, donc un `rmtree` amont *dans `appdata/`*, à
   côté de `savedgames/` ; quelques dizaines de Mio pour couvrir la seule
   donnée du joueur qui ne se retélécharge pas.

Vérifié sur l'installation réelle le 2026-09-07 : `backup --saves` produit une
sauvegarde de 29 fichiers/38,9 Mio, `restore` la remet en place après avoir
mis l'état courant de côté, et les 29 fichiers ressortent avec les **mêmes
MD5** qu'avant — y compris celui qui avait été retiré pour l'essai. Aucun
résidu d'échange (`.sgl-restore-tmp`/`.sgl-restore-old`) derrière.

### Fusion à trois voies de `modlist.txt`

`full-install` réécrit `profiles/G.A.M.M.A/modlist.txt` avec la liste amont
(`_install_modorganizer_profile` chez gamma-launcher). Trois choses distinctes
disparaissent : les mods **désactivés** par le joueur, l'**ordre** qu'il a
ajusté, et les mods qu'il a **ajoutés**. `mo2/modlist_merge.py` rejoue
par-dessus la nouvelle liste amont les seuls écarts qui lui sont imputables ;
`mo2/modlist_sync.py` est la couche disque, et `update --no-merge` rend le
comportement historique (écrasement amont + sauvegarde).

**Pourquoi un instantané maison, et pas le `modlist.txt` de définition du
modpack.** Le premier réflexe est d'utiliser
`gamma/.Grok's Modpack Installer/G.A.M.M.A/modpack_data/modlist.txt` comme
`base` : il est là, il est amont, il est gratuit. Comparé au profil réel de
l'installation de test — 751 entrées contre 756, écrits le même jour par le
même `full-install` — il en diffère de **27 entrées**, dont une douzaine ne
sont démontrablement *pas* des écarts du joueur :

- une sentinelle `-End` (ligne 2) que MO2 ne reprend pas ;
- un doublon : `G.A.M.M.A. Vehicles in Darkscape` y figure deux fois ;
- deux lignes à blanc terminal (`-G.A.M.M.A. FDDA Rework ` avec une espace,
  `+425- Dynamic News Manager Fixes and Tweaks - dEmergence` avec une
  tabulation), que MO2 réécrit rognées ;
- des noms qui ne correspondent pas au dossier réellement posé sous `mods/`
  (`272- Grulag's Dead Bushes - Grulag` contre `Grulag's Dead Bushes`), et
  au moins une coquille amont corrigée en passant (`DarkasleQif's` →
  `Darkasleif's`).

L'utiliser comme `base` inventerait donc une douzaine de faux « ajouts du
joueur » et autant de fausses suppressions. On enregistre **notre propre
instantané** (`<root>/backups/upstream-modlist.txt`),
pris juste après que le moteur a écrit le profil — à la fin de l'étape
`gamma` d'un `install`, et à chaque `update`. Conséquence assumée : sur une
installation qui n'a jamais vu cette version de l'outil, la première mise à
jour ne fusionne pas, elle enregistre la référence, et le dit.

**L'ordre et l'état sont deux problèmes séparés.** L'ordre est une suite de
noms, l'état (`+` activé, `-` désactivé, `*` non géré) une propriété de chaque
nom. Les mélanger produit les fusions subtilement fausses que cette tâche
existe pour éviter — un mod déplacé *et* désactivé n'est pas deux fois le même
écart.

- **L'ordre** passe par un diff3 classique sur la suite des noms : région que
  le joueur n'a pas touchée → l'amont ; région que l'amont n'a pas touchée →
  le joueur ; **région modifiée des deux côtés → l'amont**, et on le dit.
- **L'état** se décide nom par nom : si le joueur l'a changé depuis `base`,
  c'est le sien ; sinon c'est celui de l'amont, qui a pu légitimement activer
  ou désactiver un mod dans la nouvelle version. Le marqueur entier est repris,
  pas seulement « activé/désactivé » : transformer un `*` en `+` changerait le
  sens de la ligne.

Cinq règles qui n'ont rien d'évident, et que le code applique :

1. `modlist.txt` se lit **de bas en haut** (priorité croissante vers le haut).
   Raisonner « ligne N » se trompe de sens un jour sur deux : rien n'est indexé
   en absolu ici, tout est positionné par rapport à des **voisins nommés**.
2. Un mod **retiré en amont** n'est jamais ressuscité — son dossier n'existe
   plus sous `mods/`, MO2 l'afficherait en « missing ». L'ensemble des noms du
   résultat est contraint à `theirs ∪ (ours − base)`, et rien d'autre ; si le
   diff3 ne peut pas tenir cette contrainte, on retombe sur l'ordre amont, qui
   est complet par construction.
3. Un mod **ajouté par le joueur** est réinséré auprès de son voisin conservé
   le plus proche (on s'éloigne d'un cran à la fois, en regardant d'abord
   au-dessus), jamais empilé en fin de liste. Un ajout déjà replacé devient
   lui-même un ancrage : une grappe de mods ajoutés ensemble garde son ordre
   interne — le cas réel du haut de liste d'une install GAMMA.
4. Les **séparateurs** sont des entrées comme les autres — c'est ce qui fait
   qu'un mod réinséré retombe dans la bonne section — mais ne sont pas comptés
   comme des mods dans le rapport.
5. **En cas de doute, on ne fusionne pas** : liste vide, même mod deux fois,
   ligne incomprise → on garde l'amont, on conserve la sauvegarde, et on
   l'annonce. Une fusion silencieusement fausse est pire qu'une restauration
   manuelle.

Après fusion, le rapport dit ce qui a été réappliqué (« N mods
réactivés/désactivés selon tes réglages, M mods ajoutés par toi réinsérés, K
entrées retirées en amont non restaurées »). Sans ce compte rendu,
l'utilisateur ne sait pas s'il doit ouvrir MO2 pour vérifier.

**Fins de ligne.** L'instance MO2 vient de Windows : le `modlist.txt` de
l'install de test est en CRLF. `Path.read_text` applique la traduction
universelle des sauts de ligne et rendrait un texte en LF — le fichier
réécrit changerait alors d'encodage de ligne d'un bout à l'autre sans que
personne l'ait demandé. D'où `open(..., newline="")` en lecture **et** en
écriture, et une écriture toujours atomique (fichier voisin puis
`os.replace`) : une coupure en plein milieu laisse l'ancien fichier intact,
jamais un `modlist.txt` tronqué qui ferait démarrer MO2 sans aucun mod.

Validé hors ligne sur la vraie liste (756 entrées, CRLF) : les réglages du
joueur reviennent, ses ajouts retrouvent leur position, le mod retiré en amont
n'est pas ressuscité, aucun doublon, et le fichier reste intégralement en CRLF.

## Dimensionnement disque (`sizing.py`)

Le volume qu'exige une installation est une donnée **unique**, dans
`src/stalker_gamma_linux/sizing.py` : découpage (17 Gio de jeu de base +
83 Gio de modpack + 46 Gio de cache = 146 Gio, mesuré dans
docs/INSTALL-MANUAL.md §1), seuil bloquant (160 Gio, le total plus la marge
d'extraction) et recommandation amont (250 Gio).

Pourquoi un module dédié plutôt que des constantes locales : les deux
consommateurs — la ligne « Espace disque » de `doctor`
(`environment/checks.py`) et le dialog de pré-installation de la GUI
(`gui/space.py`) — avaient divergé. `checks.py` reprenait le chiffre amont
« 27 Go téléchargés / 76 Go installés », que notre propre manuel invalide
(on **conserve** le cache pour les mises à jour incrémentales), tandis que la
GUI bloquait sous 160 Gio. Résultat : à 120 Gio libres, `doctor` affichait
« [ OK ] Espace disque » pendant que la GUI refusait de lancer
l'installation. `tests/test_sizing.py` verrouille cet accord seuil par seuil.

Unité : tout est en **Gio** (2³⁰ octets), ce que renvoie `shutil.disk_usage`
et ce qu'affichent la CLI comme la GUI — `gui/format.format_gib` libellait
« GB » des valeurs qui étaient déjà des Gio.

## Packaging : Flatpak/AppImage retirés (2026-07-26)

T09 (2026-07-23) avait livré deux canaux : un **Flatpak** (GUI+CLI,
sandboxé) et une **AppImage** (CLI portable). Retirés du projet le
2026-07-26 : le dogfooding en VM et sur la machine réelle de Florian a
montré que le sandbox se battait en permanence contre la nature Wine/Proton
de l'outil (outils hôte invisibles derrière `flatpak-spawn`, libunrar à
rebundler, stack 32-bit manquante côté runtime GNOME — spam de
notifications de plantage `pressure-vessel`), alors que l'install **native**
(`install.sh`, venv `--system-site-packages`) utilise directement le
Wine/Proton/Steam/libunrar que l'utilisateur a déjà sur sa machine. Seul le
canal natif reste ; voir « Environnement de développement » ci-dessus et
`install.sh` à la racine pour le mécanisme actuel.

## CI (T10)

Trois workflows (`ci.yml`, `upstream-watch.yml`, `release.yml`), détails et
pièges rencontrés dans `docs/CI.md`. Un point structurant : `ci.yml` et
`release.yml` doivent installer des en-têtes système GTK4/libadwaita
(`libcairo2-dev`, `libgirepository-2.0-dev`, `gir1.2-gtk-4.0`,
`gir1.2-adw-1`) avant `pip install ".[dev]"`, alors même que la CLI n'a
jamais besoin de GTK — l'extra `dev` embarque `PyGObject-stubs`, qui tire
`PyGObject` en dépendance dure (pas de roue manylinux, même contrainte que
plus haut « Environnement de développement »), donc n'importe quelle
installation de l'extra `dev` sur une machine nue échoue à la compilation
sans ces en-têtes.

`upstream-watch.yml` s'appuie sur une asymétrie réelle entre les deux dépôts
amont : `Grokitach/Stalker_GAMMA` ne publie ni tags ni releases (vérifié via
l'API), suivi par sha de commit ; `Mord3rca/gamma-launcher` publie de vraies
Releases, suivi normalement. Le job d'intégration tourne dans un conteneur
`ubuntu:24.04` (pas le runner nu) parce que `read_mod_maker`/l'extraction
d'archives de gamma-launcher importent `unrar` (ctypes) au chargement, qui
exige `libunrar.so` — absent des images `python:*-slim` (Debian), présent
d'origine sur Ubuntu (`multiverse`).

## Internationalisation

Toutes les chaînes visibles par l'utilisateur (CLI, GUI, messages d'erreur des
modules métier partagés) sont en **anglais dans le code source** (`msgid`
gettext) et passent par `stalker_gamma_linux.i18n._()`. L'anglais est **la
langue par défaut**, point — volontairement pas de suivi de la locale système
(`LANG`/`LC_ALL`/`LC_MESSAGES`) : sinon un poste en `fr_FR.UTF-8` afficherait
du français sans que l'utilisateur l'ait demandé, ce qui n'est pas le
comportement voulu ici. Seule la variable GNU `LANGUAGE`, positionnée
explicitement, change la langue (ex. `LANGUAGE=fr stalker-gamma-linux doctor`) ;
`gettext.translation(..., fallback=True)` retourne le `msgid` (donc l'anglais)
tel quel dès qu'aucune langue demandée n'a de `.mo` correspondant. Résolu
**une fois** à l'import du module (modèle gettext classique : changer de
langue en cours de session nécessite un redémarrage, jamais un bug).

Traductions disponibles : `src/stalker_gamma_linux/locale/<code>/LC_MESSAGES/
stalker-gamma-linux.po` (+ `.mo` compilé, embarqué au paquet via
`package-data`). Français fourni à 100 % à la refonte i18n (2026-07-26,
226 chaînes). Outillage **Babel** (`dev` extra, pip pur — pas de dépendance
système `gettext`/`xgettext`, cohérent avec le reste du projet qui n'exige
jamais sudo) :

```sh
make extract-messages   # régénère le .pot depuis tous les `_("...")` de src/
make update-messages    # fusionne les nouveaux msgids dans chaque .po existant
make compile-messages   # .po → .mo, à refaire avant de tester une traduction
```

Ajouter une langue : `pybabel init -i src/stalker_gamma_linux/locale/
stalker-gamma-linux.pot -d src/stalker_gamma_linux/locale -l <code> -D
stalker-gamma-linux`, traduire le `.po` généré, puis `make compile-messages`.

Piège de test : les assertions de `pytest` portent sur le texte anglais
(source), qui ne doit pas dépendre de la locale de la machine qui exécute la
suite (ex. poste de développement en `fr_FR.UTF-8`). `tests/conftest.py` fixe
`LANGUAGE=en` **au niveau module** (pas dans une fixture) : `i18n.py` résout
sa traduction une seule fois, au premier import — une fixture, même
`autouse`, s'exécute après cet import et arriverait trop tard.

Hors périmètre gettext (laissé en l'état, ce ne sont pas des chaînes
traduisibles) : les identifiants internes (`STEPS`, valeurs de l'enum
`Status`, clés `INSTALL_COMMANDS`) ne sont jamais affichés directement — un
dict de mapping séparé s'en charge à chaque fois — et le CSS de `gui/theme.py`
(commentaires de code, pas du texte utilisateur).

## Références

- Moteur : https://github.com/Mord3rca/gamma-launcher
- Compatibilité MO2 × Proton × USVFS : `docs/MO2-PROTON-COMPAT.md`
- Modpack : https://github.com/Grokitach/Stalker_GAMMA (AGPL-3.0)
- API modlist : https://stalker-gamma.com/api/list
- Guide historique : https://github.com/FaithBeam/stalker-gamma-cli/wiki/Linux-Install
- Gist d'install manuelle : https://gist.github.com/v1ld/e9069af307bd90495e0b345f3a260725
