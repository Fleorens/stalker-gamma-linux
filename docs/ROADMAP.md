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
- **T12** 🟠 Intégrité MD5 des **mods installés** + réparation ciblée. Nous
  vérifions les archives (`check-md5` du moteur), pas le contenu sur le disque :
  un fichier de mod corrompu après l'installation est aujourd'hui indétectable.
  Baseline, diff, réparation des seuls mods officiels abîmés, ajouts de
  l'utilisateur jamais touchés.
- **T13** 🟠 Verrou « préfixe occupé ». Rien n'empêche `prefix-doctor --repair`,
  `update` ou `install --only prefix` de travailler sur un préfixe pendant que
  MO2 ou le jeu tournent dedans.
- **T14** 🟡 Diagnostic du log de lancement : `mo2/diagnostics.py` couvre
  l'USVFS mais pas les échecs qui surviennent en amont (`concrt140.dll`,
  `version mismatch` d'un préfixe construit par un autre Proton).
- **T15** 🟡 `play` détaché du terminal — à qualifier avant de coder.
- **T16** 🔵 Épinglage `WINESERVER` sous umu — investigation à mener, patch
  seulement si un découplage est mesuré.

Déjà couvert, donc écarté de la revue : contournement du rate-limit de l'API
GitHub (`updates.py` le documente ; `prefix/umu.py` et `prefix/download.py` ont
leurs replis `FALLBACK_*`), distinction compat-data / `pfx`
(`prefix/paths.py`), préservation des clés inconnues de `ModOrganizer.ini`
(`mo2/ini.py`), packaging AppImage (hors périmètre depuis T09).

## Hors scope (assumé)
- Portage natif du moteur X-Ray Monolith (sans Proton) : projet d'une autre
  échelle, Proton est la réponse pour les années à venir.
- Rehosting de mods ou du jeu.

## Risques suivis
- Fragilité MO2/USVFS selon versions Proton → matrice de compatibilité livrée
  (`docs/MO2-PROTON-COMPAT.md`) + diagnostic auto + fallback flat (T05).
- Rate-limit / changements de miroirs ModDB → géré en amont (gamma-launcher).
- Cadence de mise à jour de GAMMA → CI de non-régression (T10).
