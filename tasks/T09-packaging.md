# T09 — Packaging : Flatpak, AppImage

**Modèle recommandé : Sonnet 5.**
**Dépendances : T07 (T08 pour le Flatpak GUI).**

## Contexte

Le prompt initial demandait trois canaux (Flatpak/AppImage/AUR). Décision
Florian (2026-07-23, « AUR je m'en tape ») : AUR retiré du périmètre — pas
de machine Arch disponible pour le tester réellement, et le Flatpak couvre
déjà les utilisateurs Arch/Steam Deck. Les deux canaux restants se
répartissent le travail par ce que chacun fait bien : Flatpak porte la GUI
(bac à sable, GTK4/libadwaita fournis par le runtime GNOME), AppImage porte
un CLI portable (embarquer GTK proprement dans une AppImage est un projet à
part — voir `docs/ARCHITECTURE.md`, section Packaging).

## Prompt (tel qu'exécuté)

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md` et `src/`).

Objectif : deux canaux de distribution couvrant toutes les distributions
Linux (le Steam Deck est un cas supporté parmi d'autres, pas la cible
principale).

1. **Flatpak** (canal principal) : manifest sous `packaging/flatpak/`,
   runtime GNOME récent, permissions minimales mais suffisantes (réseau,
   accès au dossier d'installation choisi, lancement d'umu — attention au
   bac à sable : documenter précisément pourquoi chaque permission).
   Vérifier que le scénario Steam Deck (SteamOS immuable, tout en user)
   fonctionne. Préparer le dossier de soumission Flathub sans soumettre.
2. **AppImage** : build reproductible sous `packaging/appimage/` embarquant
   Python + le paquet (python-appimage ou équivalent), CI-able.
3. Un `make package-<canal>` (ou scripts) pour builder chaque canal en local.
4. `docs/PACKAGING.md` : comment builder, tester et publier chaque canal.

Critères d'acceptation : chaque artefact se builde localement et `doctor`
fonctionne depuis chacun ; le Flatpak tourne sur une session SteamOS-like
sans sudo ; rien dans les paquets ne contient de données du jeu.

## Statut

✅ Terminé et validé en réel le 2026-07-23 (build + `doctor` + rendu GUI pour
le Flatpak, build + `doctor` pour l'AppImage). Détails complets — modules,
permissions ligne par ligne, pièges rencontrés côté outillage amont, ce qui
est délibérément non embarqué (libunrar) — dans `docs/PACKAGING.md` et
`docs/ARCHITECTURE.md` (section Packaging).
