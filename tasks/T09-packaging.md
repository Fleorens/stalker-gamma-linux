# T09 — Packaging : Flatpak, AppImage, AUR

**Modèle recommandé : Sonnet 5.**
**Dépendances : T07 (T08 pour le Flatpak GUI).**

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md` et `src/`).

Objectif : trois canaux de distribution couvrant toutes les distributions
Linux (le Steam Deck est un cas supporté parmi d'autres, pas la cible
principale).

1. **Flatpak** (canal principal) : manifest sous `packaging/flatpak/`,
   runtime GNOME récent, permissions minimales mais suffisantes (réseau,
   accès au dossier d'installation choisi, lancement de Steam/umu — attention
   au bac à sable : documenter précisément pourquoi chaque permission).
   Vérifier que le scénario Steam Deck (SteamOS immuable, tout en user)
   fonctionne. Préparer le dossier de soumission Flathub sans soumettre.
2. **AppImage** : build reproductible sous `packaging/appimage/` embarquant
   Python + le paquet (python-appimage ou équivalent), CI-able.
3. **AUR** : `PKGBUILD` pour `stalker-gamma-linux` (release) sous
   `packaging/aur/`, dépendances système correctes (7z, libunrar, umu…).
4. Un `make package-<canal>` (ou scripts) pour builder chaque canal en local.
5. `docs/PACKAGING.md` : comment builder, tester et publier chaque canal.

Critères d'acceptation : chaque artefact se builde localement et `doctor`
fonctionne depuis chacun ; le Flatpak tourne sur une session SteamOS-like
sans sudo ; rien dans les paquets ne contient de données du jeu.
