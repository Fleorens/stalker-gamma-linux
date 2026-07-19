# T08 — GUI GTK4/libadwaita

**Modèle recommandé : Sonnet 5** (repasser en Fable 5 si problèmes d'async
GTK retors).
**Dépendances : T07.**

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md` et `src/`).

Objectif : GUI GTK4 + libadwaita (PyGObject) au-dessus de la même API que la
CLI — aucune logique métier dans la GUI.

- Fenêtre principale : état de l'installation (pas installé / installé /
  mise à jour disponible), gros bouton contextuel (Installer / Mettre à
  jour / Jouer), bouton secondaire « Ouvrir MO2 ».
- Vue progression pendant install/update : étape courante, barre de
  progression, log repliable en direct ; annulation propre.
- Vue « Diagnostic » = `doctor` rendu graphiquement, avec les commandes de
  remède copiables.
- Préférences : chemin d'installation, version Proton-GE, opt-in Steam.
- Les opérations longues tournent hors du main loop GTK (thread/async) avec
  remontée de progression via les callbacks existants du module `engine`.
- Adaptif écran Steam Deck (1280×800, utilisable à la manette/tactile).
- Entry point `stalker-gamma-linux-gui` + fichier `.desktop` + icône.

Critères d'acceptation : la GUI fait install → jouer sans toucher un
terminal ; l'UI ne gèle jamais pendant un téléchargement ; `ruff`/`mypy`
passent ; la CLI reste utilisable indépendamment.
