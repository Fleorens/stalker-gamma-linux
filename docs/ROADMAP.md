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
- **T06** Raccourci bureau : entrée `.desktop` + icône (l'ajout à Steam était
  alors laissé à l'utilisateur, via le bouton natif — décision rouverte et
  tranchée dans l'autre sens par T19).
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
- **T14** ✅ Diagnostic du log de lancement : `mo2/diagnostics.py` couvre
  l'USVFS **et** les échecs qui surviennent en amont (`concrt140.dll`,
  `version mismatch` d'un préfixe construit par un autre Proton). Recâblé après
  coup par T18, qui ferme aussi les deux faux positifs restants (journal
  append-only, avertissement de préfixe non fatal).
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

- **T17** ✅ **validé en réel (2026-09-07, install de test, GAMMA 920)**
  Sauvegarde/restauration + **fusion de la modlist**. Plainte n°1 de GAMMA
  toutes plateformes : le wiki officiel écrit que chaque « Install / Update
  GAMMA » réinitialise modlist, réglages et réglages de mods. Livré : paquet
  `backups/` (profils, **sauvegardes de partie**, `overwrite/`), commandes
  `backup [--list]` / `restore <id> [--dry-run]` + boutons dans la vue
  Diagnostic, manifeste TOML, rotation à 5 automatiques qui épargne toujours
  les sauvegardes explicites, et `paths_safety` devant chaque `rmtree` ;
  `orchestrator.backup_mo2_profiles` a été **déplacé** là, pas dupliqué. La
  moitié qui compte : une **fusion à trois voies** de `modlist.txt` à chaque
  update (`mo2/modlist_merge.py`), qui rejoue les désactivations, l'ordre et
  les ajouts du joueur par-dessus la liste amont — et s'abstient en le disant
  plutôt que de deviner. `update --no-merge` garde l'ancien comportement.
  Emplacement réel des parties **constaté avant d'être codé** (voir
  docs/ARCHITECTURE.md « Sauvegarde, restauration, et fusion de la modlist »).
  Objectif atteint : on passe de « réversible » à « ça ne se perd plus ».
- **T18** ✅ **validé sur deux journaux X-Ray réels (2026-09-07)** Post-mortem
  de session : commande `postmortem` + bouton « Le jeu a planté ? » dans la GUI,
  qui relisent, une fois le jeu fermé, le journal de lancement, le journal du
  moteur X-Ray et celui de l'USVFS pour rendre **un** diagnostic — et nommer les
  mods à regarder en premier quand la trace désigne un fichier
  (`integrity.report.mod_of`, réutilisé, pas dupliqué). Vérifié sur une vraie
  partie plantée (le mod suspect est correctement nommé) et sur une vraie partie
  quittée normalement (aucun cri au crash). Le résultat s'ajoute au rapport
  `doctor --report`, anonymisé comme le reste. Le constat qui a orienté tout le
  travail : sur une session parfaitement saine, chercher `[error]` ou
  `stack trace` donne 65 et 27 faux positifs — seuls les motifs **ancrés en début
  de ligne** discriminent (voir docs/MO2-PROTON-COMPAT.md). Deux faux positifs
  préexistants corrigés au passage : le journal de lancement est append-only
  (seule la dernière session compte) et l'avertissement de préfixe non fatal
  mesuré en T16 ne masque plus un crash réel.
- **T19** ✅ Steam / mode Gaming en un clic : `steam-shortcut` écrit l'entrée
  **et** son artwork dans `shortcuts.vdf`, sans que l'utilisateur touche à
  Steam. **Revient sur le hors-scope de T06** : le « gain limité aux joueurs
  Deck » est devenu le public qui grossit, et en mode Gaming l'utilisateur *ne
  peut pas* suivre notre consigne (« Ajouter un jeu non-Steam » exige le mode
  Bureau). Les réserves de T06 sont devenues le cahier des charges : codec VDF
  écrit contre un vrai fichier et validé en **round-trip octet à octet**
  (fixture réelle anonymisée dans `tests/`), sauvegarde `.bak` horodatée +
  écriture atomique, refus d'écrire pendant que Steam tourne, préservation
  champ à champ des raccourcis des autres, `--remove` qui rend le fichier tel
  qu'avant. Vérifié de bout en bout sur la vraie install Steam de la machine le
  2026-09-08 (ajout, non-duplication, retrait à l'octet près).
- **T20** ✅ **livré et vérifié en jeu (2026-09-08)** — deux couches sur trois
  conservées. MangoHud et vkBasalt sont composés autour du lancement par
  `environment/performance.py` : `gamemoderun` au contact d'`umu-run`, les deux
  couches Vulkan par variables d'environnement (leur manifeste déclare
  `enable_environment`, donc aucun script d'enveloppe). Les deux sont **éteints
  par défaut** et apparaissent dans `doctor` comme facultatifs, avec la commande
  de leur distribution (vkBasalt : AUR sur Arch, il n'y a pas de paquet
  officiel). vkBasalt est livré avec **notre** préset « ReShade-like » (CAS +
  LUT générée) : la promesse du README est enfin tenue côté code. Le point dur —
  la visibilité des couches Vulkan **dans** le conteneur pressure-vessel — avait
  été instruit par lecture des sources faute de GPU dans l'environnement du
  lot ; il a été **relevé sur la machine de dev**, puis **confirmé en jeu** :
  `libMangoHud.so` et `libvkbasalt.so` sont tous deux chargés dans
  `AnomalyDX11.exe` (ELF 64 bits) depuis `/run/host/usr/lib64/`, et vkBasalt
  journalise avoir lu notre préset sans une erreur. Le repli `VK_ADD_LAYER_PATH`
  n'est **pas** nécessaire. **Un bug trouvé et corrigé au passage** : `doctor`
  affichait `[ OK ] vkBasalt` sur la foi du seul manifeste, alors qu'avec la
  seule bibliothèque 32 bits la couche ne se charge pas dans un jeu 64 bits, en
  silence total — `vulkan.layer_abi_support()` lit désormais la classe ELF.
  ⚠ **gamescope/FSR a été retiré** le même jour : imbriqué sous KWin, il meurt
  sur une erreur de protocole Wayland (`xdg_surface` erreur 3) et son *reaper*
  emporte la partie. Ce n'était ni notre composition ni nos options (rejouées à
  l'identique, elles fonctionnent) mais une classe de bug connue en amont, qui
  ne se pose pas sur Steam Deck — où gamescope *est* la session. Faute de Deck
  pour vérifier le cas nominal, on ne livre pas un interrupteur qui tue la
  partie sur la seule machine testable. Conditions d'un retour : docs/ARCHITECTURE.md.
  ⚠ **Dette connue** : l'amont de vkBasalt est mort (dernier commit oct. 2023,
  80 issues ouvertes). On le garde parce qu'il est le seul empaqueté et qu'il
  fonctionne ; le successeur à surveiller est vkShade, à basculer quand il
  quittera la pre-alpha **et** entrera dans les dépôts.
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

- **Refonte de l'interface** ✅ **livrée (2026-09-07)** L'habillage de la GUI
  reprend la grammaire d'un launcher de jeu : artwork de la Zone redessiné en
  plans (antenne Duga, cheminée de la centrale, pylônes, brume rasante,
  anomalie) et étalonné, barre de titre porteuse de l'état système, « pont »
  bas structuré (identité, chiffres, actions), tuiles de statut — espace libre,
  mods déployés, version —, jauge d'espace disque au dialog d'installation,
  timeline de progression jalonnée sur un rail. Côté fondations : la feuille de
  style devient un vrai fichier CSS (`gui/theme/style.css`, palette en
  `@define-color`, validée par un test), l'artwork n'est plus décodé qu'une
  fois pour toute l'application, les sept branchements de tâches longues sortent
  de `main_window.py` (`gui/jobs.py`, testables sans fenêtre), et
  `scripts/capture_screenshots.py` régénère la documentation hors écran, sur une
  install de démonstration. Deux défauts corrigés au passage : la console de
  progression pouvait s'afficher vide alors que son tampon était plein (vue
  défilée sous son contenu quand le journal tenait dans la fenêtre), et la
  feuille de style produisait un avertissement GTK par redessin en redéfinissant
  la géométrie des barres de défilement d'Adwaita.

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
