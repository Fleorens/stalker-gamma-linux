# T06 — Raccourci bureau

**Modèle recommandé : Sonnet 5.**
**Dépendances : T04, T05.**

## Contexte

On a évalué l'écriture directe dans `shortcuts.vdf` (format binaire non
documenté officiellement, comptes multiples, fermeture de Steam requise pour
écrire dessus) et jugé le rapport effort/valeur mauvais pour un gain
essentiellement limité aux joueurs manette / Steam Deck en mode Gaming.
Steam propose déjà nativement *Ajouter un jeu → Ajouter un jeu non-Steam* :
il suffit de pointer ce bouton vers notre commande de lancement, et Steam
gère lui-même l'artwork, le choix du compat tool et la persistance —
aucune manipulation VDF de notre côté n'apporte de valeur supplémentaire.

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md` et le code existant dans `src/`).

Objectif : module `desktop/` qui installe une entrée de lancement standard
freedesktop (`.desktop`), avec icône, pour que GAMMA apparaisse dans le menu
applications de n'importe quel environnement de bureau Linux.

1. Générer un fichier `.desktop` conforme à la
   [spec freedesktop](https://specifications.freedesktop.org/desktop-entry-spec/latest/) :
   `Name=S.T.A.L.K.E.R. G.A.M.M.A.`, `Exec=` notre commande de lancement
   (le jeu via MO2, T05 — chemin absolu vers l'exécutable du venv/paquet
   installé, pas juste `stalker-gamma-linux` qui suppose un PATH activé),
   `Icon=`, `Categories=Game;`, `Terminal=false`.
2. Icône fournie avec le paquet (`src/stalker_gamma_linux/assets/icon.png`,
   embarquée via `package-data`/`importlib.resources` — pas de
   téléchargement ni de rehosting d'assets tiers), installée dans
   `~/.local/share/icons/hicolor/256x256/apps/`.
3. Écriture du `.desktop` dans `~/.local/share/applications/`. Mise à jour
   idempotente : chemin de fichier fixe (nom dérivé de l'app id, ex.
   `com.github.<user>.stalker-gamma-linux.desktop`), on écrase simplement au
   lieu de dupliquer — pas de logique de déduplication complexe nécessaire
   contrairement à un `shortcuts.vdf`.
4. Appeler `update-desktop-database` et `gtk-update-icon-cache` sur les
   répertoires utilisateur s'ils sont disponibles sur le PATH (sinon no-op
   silencieux, ce n'est qu'un rafraîchissement de cache).
5. Commande CLI `shortcut` branchée sur l'entry point (`install --shortcut`
   optionnel en plus, cf. T07).
6. Documenter dans le README (section existante ou nouvelle) : une fois le
   raccourci créé, l'utilisateur qui veut l'ajouter à Steam (pour Steam
   Input / mode Gaming sur Deck) le fait lui-même via *Ajouter un jeu
   non-Steam* en pointant sur la même commande — Steam gère alors artwork et
   compat tool nativement, aucun outillage requis de notre part.

Hors scope (explicitement abandonné) : écriture/parsing de `shortcuts.vdf`,
détection multi-comptes Steam, `CompatToolMapping` dans `config.vdf`,
`docs/STEAM-DECK.md` dédié.

Critères d'acceptation : après `shortcut`, l'entrée apparaît dans le menu
applications (testable en vérifiant le contenu du fichier généré — pas
besoin d'un vrai environnement de bureau en CI) ; relancer `shortcut`
n'écrit qu'un seul fichier, contenu remis à jour ; tests sur le rendu du
`.desktop` (chemins avec espaces, échappement `Exec=` correct) ; icône
présente dans le paquet installé ; `ruff`/`mypy`/`pytest` passent.
