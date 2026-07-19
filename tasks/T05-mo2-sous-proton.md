# T05 — MO2 sous Proton (mode principal)

**Modèle recommandé : Fable 5** — c'est la tâche la plus difficile du projet
(USVFS sous Wine, comportements non documentés).
**Dépendances : T03, T04.**

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md`, `docs/INSTALL-MANUAL.md`).

Objectif : Mod Organizer 2 fonctionne dans le préfixe partagé et lance le jeu
avec USVFS actif — **la flexibilité des mods (activer/désactiver/ajouter) est
la raison d'être de ce mode**, décision utilisateur actée.

1. Recherche d'abord l'état de l'art 2025-2026 : quelles combinaisons
   MO2 × Proton(-GE) fonctionnent avec USVFS (issues GitHub MO2 et
   gamma-launcher, ProtonDB, Reddit). Consigne le résultat dans
   `docs/MO2-PROTON-COMPAT.md` (matrice : version MO2 / version Proton /
   statut / source).
2. Module `mo2/` :
   - Configuration automatique de l'instance MO2 livrée par GAMMA : chemin
     Anomaly (en chemin Windows vu du préfixe, ex. `Z:\...`), profil
     `G.A.M.M.A` sélectionné, exécutable `Anomaly (DX11)` par défaut —
     c'est l'étape que gamma-launcher ne sait pas faire, on l'automatise en
     éditant les `.ini` de MO2.
   - `launch_mo2()` : démarre `ModOrganizer.exe` via `run_in_prefix` (T04).
   - `launch_game()` : lance le jeu **à travers MO2** (`ModOrganizer.exe
     "moshortcut://..."` ou équivalent) pour que USVFS monte les mods.
3. Diagnostic : si le jeu démarre sans mods (symptôme USVFS mort), le
   détecter (ex. absence d'un fichier sentinelle d'un mod dans le VFS au
   lancement) et l'expliquer à l'utilisateur avec les remèdes de la matrice.
4. Le mode flat (`usvfs-workaround` de gamma-launcher) reste un **fallback**
   accessible par flag explicite, avec avertissement de perte de flexibilité.

Critères d'acceptation : sur machine réelle, MO2 s'ouvre, liste les mods
GAMMA, et lance Anomaly DX11 avec les mods actifs ; ajout/désactivation d'un
mod dans MO2 se reflète en jeu ; la matrice de compat existe et est sourcée ;
`ruff`/`mypy`/`pytest` passent.
