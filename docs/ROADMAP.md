# Roadmap

Découpage en tâches exécutables : voir [../tasks/](../tasks/).

## Phase 0 — Fondations ✅ (ce commit)
- Repo, licence GPL-3.0, architecture, découpage des tâches.

## Phase 1 — MVP : installation en une commande
- **T01** Spec : installation manuelle reproduite et documentée (la référence).
- **T02** Squelette Python + détection environnement/prérequis.
- **T03** Wrapper du moteur gamma-launcher (install/update/check-md5).
- **T04** Gestion du préfixe Proton (Proton-GE, umu, verbs winetricks).
- **T05** MO2 sous Proton : lancement fiable + configuration auto de l'instance.
- **T07** CLI orchestrateur : `install`, `update`, `play`, `doctor`.

Livrable : `stalker-gamma-linux install` → GAMMA jouable via MO2 sous Proton.

## Phase 2 — Intégration bureau
- **T06** Intégration Steam : entrée non-Steam, launch options, artwork.
- **T08** GUI GTK4/libadwaita : Installer / Mettre à jour / Jouer / logs.

## Phase 3 — Distribution
- **T09** Packaging : Flatpak (cible Steam Deck), AppImage, AUR.
- **T10** CI : test d'installation conteneurisé à chaque release amont de GAMMA,
  lint, release automatisée.

## Hors scope (assumé)
- Portage natif du moteur X-Ray Monolith (sans Proton) : projet d'une autre
  échelle, Proton est la réponse pour les années à venir.
- Rehosting de mods ou du jeu.

## Risques suivis
- Fragilité MO2/USVFS selon versions Proton → matrice de compatibilité (T05).
- Rate-limit / changements de miroirs ModDB → géré en amont (gamma-launcher).
- Cadence de mise à jour de GAMMA → CI de non-régression (T10).
