# T06 — Intégration Steam

**Modèle recommandé : Sonnet 5.**
**Dépendances : T04.**

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md`).

Objectif : module `steam/` qui ajoute GAMMA comme jeu non-Steam, proprement.

1. Localiser l'installation Steam (native et Flatpak) et le bon
   `userdata/<id>/config/shortcuts.vdf` ; si plusieurs comptes, choisir le
   dernier connecté (et le dire).
2. Écrire l'entrée non-Steam dans `shortcuts.vdf` (format VDF binaire —
   utiliser une lib existante type `vdf` plutôt que réimplémenter) :
   nom « S.T.A.L.K.E.R. G.A.M.M.A. », cible = notre commande de lancement
   (le jeu via MO2, T05), dossier de démarrage, et la version Proton(-GE) du
   préfixe forcée en compat tool (`config.vdf` / `CompatToolMapping`).
3. Sauvegarde du `shortcuts.vdf` avant modification ; ne jamais dupliquer
   l'entrée si elle existe (mise à jour idempotente).
4. Artwork : grille/hero/logo depuis les assets officiels GAMMA si
   redistribuables, sinon placeholder généré — pas de rehosting douteux.
5. Steam Deck : vérifier que l'entrée apparaît en mode Gaming ; documenter
   dans `docs/STEAM-DECK.md` toute spécificité (chemins SteamOS, microSD).
6. Commande CLI `steam-add` branchée sur l'entry point ; avertir que Steam
   doit être fermé pendant l'écriture du VDF.

Critères d'acceptation : l'entrée apparaît dans Steam avec la bonne compat
tool ; relancer `steam-add` ne crée pas de doublon ; tests sur fichiers VDF
de fixture ; `ruff`/`mypy`/`pytest` passent.
