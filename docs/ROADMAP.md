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
- **T08** GUI GTK4/libadwaita : Installer / Mettre à jour / Jouer / logs.

## Phase 3 — Distribution
- **T09** Packaging : Flatpak, AppImage, AUR — toutes distributions, Steam
  Deck inclus.
- **T10** CI : test d'installation conteneurisé à chaque release amont de GAMMA,
  lint, release automatisée.

## Hors scope (assumé)
- Portage natif du moteur X-Ray Monolith (sans Proton) : projet d'une autre
  échelle, Proton est la réponse pour les années à venir.
- Rehosting de mods ou du jeu.

## Risques suivis
- Fragilité MO2/USVFS selon versions Proton → matrice de compatibilité livrée
  (`docs/MO2-PROTON-COMPAT.md`) + diagnostic auto + fallback flat (T05).
- Rate-limit / changements de miroirs ModDB → géré en amont (gamma-launcher).
- Cadence de mise à jour de GAMMA → CI de non-régression (T10).
