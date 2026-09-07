# Roadmap

Découpage en tâches exécutables : voir [../tasks/](../tasks/).

## Phase 0 — Fondations ✅ (ce commit)
- Repo, licence GPL-3.0, architecture, découpage des tâches.

## Phase 1 — MVP : installation en une commande
- **T01** Spec : installation manuelle reproduite et documentée (la référence).
- **T02** Squelette Python + détection environnement/prérequis.
- **T03** Wrapper du moteur gamma-launcher (install/update/check-md5).
- **T04** Gestion du préfixe Proton (Proton-GE, umu, verbs winetricks).
- **T05** ✅ **validé en réel (2026-07-22, GE-Proton11-1)** MO2 sous Proton :
  configuration auto de l'instance (`gamePath`/profil), lancement du jeu via
  `moshortcut://` (USVFS, 577 mods servis), diagnostic USVFS, fallback flat
  explicite, matrice de compatibilité (`docs/MO2-PROTON-COMPAT.md`).
  Commandes `mo2` et `play`.
- **T07** ✅ CLI orchestrateur complète : `install` (pipeline résumable —
  anomaly → GAMMA → retrait ReShade → préfixe → instance MO2 → raccourci
  optionnel), `update` (modpack + re-vérification MD5), `doctor` (environnement
  + préfixe + état d'installation), `play`/`mo2` (T05), `shortcut` (T06),
  `--verbose` + logs tournants + sortie `rich`, `install.sh` curl-able.

Livrable MVP atteint : `stalker-gamma-linux install` → GAMMA jouable via MO2
sous Proton, reprise après interruption, mise à jour incrémentale.

## Phase 2 — Intégration bureau
- **T06** Raccourci bureau : entrée `.desktop` + icône (ajout à Steam en
  jeu non-Steam laissé à l'utilisateur, via le bouton natif de Steam).
- **T08** ✅ GUI GTK4/libadwaita, testée en réel (2026-07-23) : fenêtre
  principale (statut, bouton contextuel Installer/Jouer, Ouvrir MO2), vue
  progression (étape, barre, journal repliable, annulation propre), vue
  Diagnostic (rendu graphique de `doctor`, commandes de remède copiables),
  Préférences (chemin, version Proton-GE, raccourci Steam). Opérations
  longues hors fil GTK (`gui.worker.BackgroundTask`) ; aucune logique
  métier dans la GUI — même `orchestrator`/`mo2.session` que la CLI, via
  `output.Reporter` (nouveau) et les callbacks `on_progress`/`cancel_event`
  déjà en place. Entrée `stalker-gamma-linux-gui` + `.desktop` + icône.

## Phase 3 — Distribution
- **T09** Packaging Flatpak (canal principal, sandboxé, Steam Deck inclus) et
  AppImage (CLI portable) implémenté (2026-07-23, AUR retiré du périmètre).
  **Retiré du projet le 2026-07-26** : le dogfooding (voir T08) a montré que
  le sandbox se battait en permanence contre la nature Wine/Proton de
  l'outil (outils hôte invisibles, libunrar, stack 32-bit) alors que l'
  install native (`install.sh`) utilise directement ce que l'utilisateur a
  déjà. Seul le canal natif reste.
- **T10** ✅ CI : `ci.yml` (lint/types/tests matrice 3.11-3.13 + build),
  `upstream-watch.yml` (cron quotidien, sous-ensemble non-graphique du
  pipeline en conteneur, issue automatique), `release.yml` (tag `v*` →
  vérifications puis GitHub Release, sans artefact de packaging depuis le
  retrait de T09). Voir `docs/CI.md`.

## Phase 4 — Durcissement (ouverte le 2026-08-17)

Issue d'une revue d'état de l'art menée le 2026-08-17 sur les autres outils de
l'écosystème Linux/GAMMA. Sur dix pistes retenues, quatre étaient déjà
couvertes chez nous ; six deviennent des tâches.

- **T11** 🔴 Garde-fous de chemin sur `uninstall --game-data`. `build_plan()`
  ajoute `--target` à la liste des suppressions **sans validation**, et
  `apply_plan()` fait `rmtree` dessus sans confirmation interactive : une faute
  de frappe (`--target ~`) suffit. À corriger avant tout le reste.
- **T12** ✅ Intégrité MD5 des **mods installés** + réparation ciblée
  (`integrity/`, commande `verify [--repair]` + bouton dans la vue Diagnostic).
  Nous ne vérifiions que les archives (`check-md5` du moteur), pas le contenu
  sur le disque : un fichier de mod corrompu après l'installation était
  indétectable. Référence `gamma-md5.txt`, diff en quatre catégories,
  réparation des seuls mods amont abîmés, ajouts de l'utilisateur jamais
  touchés — y compris le dossier de mod qui en contient. Voir
  docs/ARCHITECTURE.md « Intégrité des mods installés ».
- **T13** ✅ Verrou « préfixe occupé » (commit `9b8e44a`).
  `prefix.session.require_free` est branché sur les quatre opérations
  destructrices — `install --only prefix` (`orchestrator.py`), `update`,
  `prefix-doctor --repair` et `uninstall --game-data` — avec `--force` partout.
  Détection par `wineserver` du préfixe, puis MO2, puis le jeu.
- **T14** 🟡 Diagnostic du log de lancement : `mo2/diagnostics.py` couvre
  l'USVFS mais pas les échecs qui surviennent en amont (`concrt140.dll`,
  `version mismatch` d'un préfixe construit par un autre Proton).
- **T15** ✅ **validé en réel (2026-08-22, install de test complète, umu 1.4.1
  + GE-Proton11-3)** `play` détaché du terminal : qualifié (seul le
  lancement direct en ligne de commande était concerné, ni le `.desktop`
  direct ni la GUI), confirmé par simulation SIGHUP (`forkpty`), corrigé
  (`prefix.process.run_detached` — `start_new_session=True` **et**
  `stdin=DEVNULL`, voir `docs/MO2-PROTON-COMPAT.md`). Le premier essai
  (`start_new_session` seul) échouait encore en réel : la sandbox interne
  d'umu-run (`srt-bwrap`) reprenait le stdin hérité comme son propre terminal
  de contrôle et se faisait tuer avec toute la chaîne en dessous — `stdin`
  devait être coupé aussi. Rejoué avec le correctif complet : toute la chaîne
  jusqu'à `AnomalyDX11.exe` survit à la fermeture du terminal.
- **T16** 🔵 Épinglage `WINESERVER` sous umu — investigation à mener, patch
  seulement si un découplage est mesuré.

Déjà couvert, donc écarté de la revue : contournement du rate-limit de l'API
GitHub (`updates.py` le documente ; `prefix/umu.py` et `prefix/download.py` ont
leurs replis `FALLBACK_*`), distinction compat-data / `pfx`
(`prefix/paths.py`), préservation des clés inconnues de `ModOrganizer.ini`
(`mo2/ini.py`), packaging AppImage (hors périmètre depuis T09).

## Phase 5 — Adoption (ouverte le 2026-09-07)

Issue d'une revue comparative avec le **launcher Windows officiel**. Le constat
qui oriente toute la phase : le launcher officiel a *trois boutons* (*First
Install Initialization*, *Install / Update GAMMA*, *Play*). Nous avons déjà en
plus la reprise après interruption, `verify --repair`, `doctor`,
`prefix-doctor`, `import`, le verrou de préfixe et le rapport d'issue anonymisé.
**Il n'y a pas de parité à rattraper.** Ces six tâches visent donc deux choses :
ce que seul Linux permet, et les modes d'échec qui font abandonner. Découpage :
[../tasks/](../tasks/).

- **T17** 🔴 Sauvegarde/restauration + **fusion de la modlist**. Plainte n°1 de
  GAMMA toutes plateformes : le wiki officiel écrit que chaque « Install /
  Update GAMMA » réinitialise modlist, réglages et réglages de mods. Nous en
  faisons déjà la moitié (`orchestrator.backup_mo2_profiles` sauvegarde
  `profiles/` avant chaque update) mais **aucune commande ne restaure**, les
  sauvegardes de partie ne sont pas couvertes, et `<root>/backups/` n'est jamais
  purgé. Objectif : passer de « réversible » à « ça ne se perd plus ».
- **T18** 🟠 Post-mortem de session. `mo2/diagnostics.py` sait diagnostiquer,
  mais depuis T15 `run_play` ne l'appelle plus (le jeu tourne encore ⇒ faux
  négatif) et **aucune commande ne le rappelle après coup** : le diagnostic est
  écrit et mort. Manque aussi la lecture du log X-Ray lui-même, seul endroit où
  un crash s'attribue à un mod — via `integrity.report.mod_of`, déjà écrit.
- **T19** 🟠 Steam / mode Gaming en un clic (`shortcuts.vdf`). **Revient sur le
  hors-scope de T06** : le « gain limité aux joueurs Deck » est devenu le public
  qui grossit, et en mode Gaming l'utilisateur *ne peut pas* suivre notre
  consigne (« Ajouter un jeu non-Steam » exige le mode Bureau).
- **T20** 🟠 MangoHud, gamescope/FSR, vkBasalt. Aucune trace dans le code, alors
  que le README promet vkBasalt en équivalent du ReShade que nous retirons.
  Seul lot où l'on passe devant Windows au lieu de l'égaler. Point dur à
  mesurer avant de coder : la visibilité des couches Vulkan **dans** le
  conteneur pressure-vessel (cf. le cas `libgamemode.so` déjà documenté).
- **T21** 🟡 Cache de shaders hors préfixe. `install --only prefix` est notre
  remède officiel au « prefix has an invalid version » — et il fait
  silencieusement perdre des heures de compilation. Les caches DXVK/pilote
  doivent vivre sous `<root>/cache/`, comme `TMPDIR` déjà.
- **T22** 🟠 Résilience ModDB. Issue amont **ouverte** (#282, captchas
  Cloudflare), plus #286/#284/#283. `engine.runner.verify` sait déjà classer ces
  marqueurs en avertissement ; le raisonnement n'a jamais été porté sur le
  chemin du téléchargement, où il bloque. Périmètre explicite : **aucun
  contournement de protection** — on diagnostique, on indique le dépôt manuel
  (`<gamma>/downloads`), on reprend.

**Le frein principal n'est pas fonctionnel.** À la même revue : 5 étoiles, 0
issue, 0 fork. Trois leviers, hors fiches ci-dessus — un paquet **AUR** puis
**COPR** (les raisons du retrait de T09, le sandbox contre Wine/Proton, ne
s'appliquent pas à un paquet natif) ; une présence dans les **guides Linux du
wiki GAMMA** et son Discord ; l'**i18n au-delà de en/fr** (ru/uk/pl/de).

## Hors scope (assumé)
- Portage natif du moteur X-Ray Monolith (sans Proton) : projet d'une autre
  échelle, Proton est la réponse pour les années à venir.
- Rehosting de mods ou du jeu.

## Risques suivis
- Fragilité MO2/USVFS selon versions Proton → matrice de compatibilité livrée
  (`docs/MO2-PROTON-COMPAT.md`) + diagnostic auto + fallback flat (T05).
- Rate-limit / changements de miroirs ModDB → géré en amont (gamma-launcher).
- Cadence de mise à jour de GAMMA → CI de non-régression (T10).
