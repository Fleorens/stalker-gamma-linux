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
│  - Packaging (Flatpak/AppImage/AUR)         │
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

## Références

- Moteur : https://github.com/Mord3rca/gamma-launcher
- Compatibilité MO2 × Proton × USVFS : `docs/MO2-PROTON-COMPAT.md`
- Modpack : https://github.com/Grokitach/Stalker_GAMMA (AGPL-3.0)
- API modlist : https://stalker-gamma.com/api/list
- Guide historique : https://github.com/FaithBeam/stalker-gamma-cli/wiki/Linux-Install
- Gist d'install manuelle : https://gist.github.com/v1ld/e9069af307bd90495e0b345f3a260725
