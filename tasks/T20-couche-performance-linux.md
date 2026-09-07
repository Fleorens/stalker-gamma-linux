# T20 — Couche performance Linux : MangoHud, gamescope/FSR, vkBasalt

**Modèle recommandé : Opus 5, effort maximal** — le point dur est la visibilité des couches
Vulkan **à l'intérieur** du conteneur pressure-vessel d'umu ; ça se mesure, ça
ne se déduit pas.
**Dépendances : T04, T05.**

## Contexte

Relevé le 2026-09-07.

`grep -ril "mangohud\|gamescope\|vkbasalt\|fsr" src/` ne ramène **rien**. Or :

- le README promet vkBasalt « en équivalent » de ReShade, que nous retirons à
  chaque install et à chaque update (`remove_reshade`). On retire, on ne rend
  pas l'équivalent — la promesse n'est tenue que dans la documentation ;
- **gamescope + FSR est exactement ce qui rend GAMMA jouable** sur un Steam
  Deck ou un GPU modeste, et c'est un levier qui n'existe pas sous Windows ;
- MangoHud est l'overlay que le public Linux attend par défaut, et c'est aussi
  l'outil qui permet à un joueur de nous dire *quoi* est lent quand il ouvre
  une issue.

C'est le seul lot de cette série où l'on ne rattrape pas Windows : on passe
devant.

Le raccordement existe déjà et il est propre : `environment/gamemode.py`
enveloppe `umu-run` via `wrap()`, uniquement sur les lancements de jeu
(`launch_game`, `launch_flat`), jamais sur l'installation ni sur MO2. C'est le
même point d'entrée, la même politique, et le même « no-op silencieux quand
l'outil n'est pas installé ».

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis
`src/stalker_gamma_linux/environment/gamemode.py` en entier — docstring
comprise, elle contient le raisonnement à reproduire —,
`src/stalker_gamma_linux/mo2/launch.py`,
`src/stalker_gamma_linux/environment/checks.py` et
`src/stalker_gamma_linux/gui/windows/preferences.py`).

Objectif : un module `environment/performance.py` (ou un découpage plus fin si
ça dépasse 400 lignes) qui compose l'enveloppe de lancement, plus les réglages
correspondants dans les Préférences.

1. **Le vrai risque technique, à mesurer en premier.** Le jeu tourne dans le
   conteneur steamrt de pressure-vessel. `docs/ARCHITECTURE.md` documente déjà
   le cas de GameMode : pressure-vessel importe bien `libgamemodeauto.so.0` en
   `LD_PRELOAD`, mais **pas** le `libgamemode.so.0` qu'elle `dlopen` ensuite —
   d'où les dizaines de lignes `gamemodeauto: dlopen failed` à chaque partie.
   MangoHud et vkBasalt sont des **couches Vulkan implicites** : elles ont le
   même problème potentiel, en pire (il leur faut le manifeste JSON *et* la
   bibliothèque, dans les deux ABI). **Commence par vérifier, jeu lancé, si
   l'overlay s'affiche réellement** ; si umu ne les importe pas, dis-le dans la
   doc et documente le contournement (variables `VK_*` / `--filesystem` d'umu)
   plutôt que de livrer un interrupteur qui ne fait rien.

2. **L'ordre d'emboîtement n'est pas libre.** gamescope est un compositeur : il
   doit être **le plus à l'extérieur** (`gamescope … -- gamemoderun umu-run …`).
   MangoHud et vkBasalt passent par l'environnement (couches Vulkan), pas par un
   wrapper supplémentaire — préfère les variables au script `mangohud`, qui
   ajoute un niveau de `LD_PRELOAD` de plus dans une pile qui en compte déjà
   trop. Écris l'ordre retenu et sa justification dans `docs/ARCHITECTURE.md`.

3. **Composer, pas empiler des `if`.** `gamemode.wrap()` est une fonction pure
   `Sequence[str] -> list[str]`. Garde cette forme : chaque couche est une
   fonction de la même signature (plus un enrichissement d'environnement), et
   le lancement les compose dans l'ordre décidé. Aucune mutation de la commande
   ni de `os.environ` — on construit un nouvel environnement.

4. **Chaque couche est optionnelle et silencieuse.** Outil absent ⇒ la commande
   repart telle quelle, exactement comme GameMode aujourd'hui. Ajoute les
   `check_*` correspondants dans `environment/checks.py` avec la commande
   d'installation par distribution (le patron est déjà là, neuf fois), pour que
   `doctor` et la vue Diagnostic les affichent comme des **optionnels**, pas
   comme des prérequis manquants.

5. **Réglages exposés — peu, et utiles** :
   - MangoHud : interrupteur, plus un choix de préset (léger : fps + frametime ;
     complet : CPU/GPU/VRAM/températures). Écris notre propre fichier de
     configuration dans `~/.config/stalker-gamma-linux/`, **sans jamais
     toucher au `MangoHud.conf` global de l'utilisateur** ;
   - gamescope : interrupteur, résolution de rendu et résolution de sortie,
     FSR on/off avec son niveau de netteté, plein écran/fenêtré. Sur Steam Deck,
     propose des valeurs par défaut cohérentes avec l'écran (1280×800) — la GUI
     a déjà une détection Deck, réutilise-la ;
   - vkBasalt : interrupteur, et **un préset « ReShade-like »** fourni par nous
     (CAS + un peu de correction de couleur). C'est la réponse concrète à la
     promesse du README.

6. **Où ça s'applique.** Uniquement `launch_game` et `launch_flat`. Jamais
   `launch_mo2` (un overlay par-dessus MO2 n'a aucun sens), jamais les étapes
   d'installation. Même frontière que GameMode, pour la même raison.

7. **Tout est opt-out par défaut.** Aucun de ces trois outils ne s'active sans
   que l'utilisateur l'ait demandé : ils changent le rendu et les performances,
   et un joueur qui ouvre une issue doit pouvoir dire « rien d'activé ». Le
   défaut du projet reste « GameMode oui, le reste non ».

8. **Le journal.** Le projet a déjà décidé de ne pas filtrer le bruit d'umu et
   de wine (« masquer ce que crachent umu et wine reviendrait à masquer aussi
   les vrais problèmes »). Tiens la même ligne ici : on n'avale pas les
   avertissements des couches.

Contraintes : aucune dépendance Python nouvelle ; fonctions pures et testables
sans lancer quoi que ce soit (la composition de commande se teste en dur) ;
messages via `i18n._` ; fichiers courts et cohésifs ; pas de mutation.

## Critères d'acceptation

- Sur l'install réelle, jeu lancé : l'overlay MangoHud s'affiche **ou** la doc
  explique précisément pourquoi il ne peut pas et ce qui a été mesuré.
- gamescope + FSR activés : le jeu tourne à la résolution de rendu choisie et
  est mis à l'échelle vers la sortie ; mesure avant/après notée dans la doc.
- vkBasalt activé : effet visible, préset fourni par le paquet.
- Les trois outils absents du système : `play` se comporte exactement comme
  aujourd'hui, aucun message d'erreur.
- `doctor` liste les trois comme optionnels avec la bonne commande par distro.
- Tests de composition : ordre d'emboîtement correct pour les huit combinaisons
  d'activation, et environnement construit sans muter `os.environ`.
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
feat(performance): MangoHud, gamescope/FSR et vkBasalt en couches optionnelles
```
