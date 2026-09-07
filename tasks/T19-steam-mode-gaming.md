# T19 — Steam et mode Gaming en un clic (`shortcuts.vdf`)

**Modèle recommandé : Opus 5, effort élevé** — format binaire non spécifié, calcul d'AppID à
vérifier contre du réel, et une écriture concurrente avec Steam.
**Dépendances : T06, T11.**

## Contexte

Relevé le 2026-09-07. **Cette tâche revient sur une décision de T06** : il faut
donc commencer par relire ce que T06 a écarté, et pourquoi.

T06 avait jugé le rapport effort/valeur mauvais : format binaire non documenté,
comptes multiples, Steam à fermer pour écrire, « gain essentiellement limité aux
joueurs manette / Steam Deck en mode Gaming ». Aujourd'hui
`desktop/session.py` renvoie donc l'utilisateur vers *Steam → Ajouter un jeu →
Ajouter un jeu non-Steam → Parcourir*.

Deux choses ont changé.

- **Ce « gain limité » est devenu le public qui grossit.** Steam Deck, Bazzite,
  SteamOS : ce sont précisément les machines où l'on installe GAMMA sans jamais
  ouvrir de terminal. Et **en mode Gaming, l'utilisateur ne peut pas suivre
  notre consigne** : « Ajouter un jeu non-Steam » exige de repasser en mode
  Bureau. On envoie donc notre public le plus captif faire une manipulation
  qu'il ne peut pas faire là où il est.
- **L'argument technique restant est plus faible qu'il n'y paraît.** T06 opposait
  le `.desktop` (« chemin fixe, on écrase ») au `shortcuts.vdf` (« logique de
  déduplication complexe »). La déduplication est mécanique et testable : on
  reconnaît notre entrée, on la met à jour, on n'en ajoute pas une seconde.

Le reste des réserves de T06 tient toujours et devient le cahier des charges
ci-dessous, pas une raison de renoncer.

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `tasks/T06-integration-steam.md`,
`src/stalker_gamma_linux/desktop/` en entier, `src/stalker_gamma_linux/paths_safety.py`,
et `src/stalker_gamma_linux/environment/checks.py` pour `check_steam`).

Objectif : ajouter GAMMA à la bibliothèque Steam sans que l'utilisateur touche
à Steam, artwork compris, de façon idempotente et réversible.

1. **Trouver les installations et les comptes.** Steam natif
   (`~/.steam/steam`, `~/.local/share/Steam`) **et** Steam Flatpak
   (`~/.var/app/com.valvesoftware.Steam/…`) : les deux existent sur Bazzite et
   sur des postes Fedora. Les raccourcis vivent par compte sous
   `userdata/<id>/config/shortcuts.vdf`. Plusieurs comptes ⇒ on n'en devine pas
   un : ou bien on écrit pour tous, ou bien on demande. Tranche et écris
   pourquoi. Zéro compte trouvé ⇒ message actionnable, pas une exception.

2. **Steam ouvert = on n'écrit pas.** Steam garde `shortcuts.vdf` en mémoire et
   le réécrit en quittant : écrire pendant qu'il tourne perd silencieusement le
   travail. Détecte-le (le pattern de `prefix/session.py` est là pour ça),
   refuse avec un message qui dit quoi fermer, et accepte `--force`.

3. **Sauvegarder avant d'écrire.** `shortcuts.vdf` est un fichier de
   l'utilisateur qui contient *ses autres* raccourcis. Copie `.bak` horodatée
   avant toute écriture, écriture atomique (fichier temporaire puis `replace`),
   et jamais de réécriture partielle. Même exigence qu'en T11 : rien de
   destructeur sans filet.

4. **Le format.** VDF binaire : séquence de champs typés (`0x00` map, `0x01`
   chaîne, `0x02` entier 32 bits, `0x08` fin de bloc). **Ne code pas de
   mémoire** : lis un vrai `shortcuts.vdf` de la machine, vérifie ton parseur
   en round-trip (lire → réécrire → comparer octet à octet un fichier non
   modifié), et seulement ensuite ajoute une entrée. Un round-trip qui ne rend
   pas le fichier identique est un bug bloquant, pas un détail.

5. **Préserver l'inconnu.** Même règle que `mo2/ini.py` pour `ModOrganizer.ini` :
   les clés qu'on ne comprend pas (celles que Steam a ajoutées, celles des
   autres raccourcis) doivent ressortir intactes. On ajoute et on met à jour
   une entrée, on ne normalise pas le fichier des autres.

6. **AppID : à vérifier, pas à supposer.** L'identifiant utilisé pour nommer
   les fichiers d'artwork se dérive de l'exécutable et du nom du raccourci, et
   les formules qui circulent sur le web ne s'accordent pas toutes (signé/non
   signé, décalage de 32 bits). Calcule, puis **vérifie contre un raccourci
   non-Steam réel de la machine** dont tu connais déjà le nom de fichier de
   grille. Si ça ne tombe pas juste, ne devine pas : ajoute le raccourci sans
   artwork plutôt qu'avec un artwork qui n'apparaîtra jamais.

7. **Artwork : seulement le nôtre.** Pose les images dans
   `userdata/<id>/config/grid/`. Utilise exclusivement les assets du paquet
   (`assets/logo.png`, `assets/icon.png`) et la génération procédurale de
   `scripts/generate_background.py`, aux formats attendus (grille verticale,
   horizontale, héros, logo). **Aucun téléchargement d'artwork tiers** —
   SteamGridDB comprise : la règle « jamais de rehosting, jamais d'asset tiers »
   du projet vaut ici comme ailleurs.

8. **`LaunchOptions` : attention au double emballage.** `play` enveloppe déjà
   le lancement dans `gamemoderun` (`environment/gamemode.py`). Ne remets pas
   `gamemoderun %command%` dans les options Steam : tu te retrouverais avec deux
   niveaux. Le raccourci doit pointer sur notre commande de lancement, avec un
   chemin absolu vers l'exécutable du venv — même contrainte qu'au point 1 de
   T06.

9. **Réversibilité.** `--remove` retire notre entrée (et seulement la nôtre) et
   les fichiers d'artwork qu'on a posés. Branche-le sur `uninstall`, qui doit
   nettoyer ce qu'il a créé. `--dry-run` sur les deux sens, comme `import`.

10. **Surface.** `stalker-gamma-linux steam-shortcut [--remove] [--dry-run]
    [--force]`, un interrupteur dans les Préférences de la GUI, et une case dans
    le dialogue d'installation. Attention : `prefs.create_steam_shortcut`
    **existe déjà** et désigne autre chose (une entrée `.desktop`
    supplémentaire, décochée par défaut depuis le doublon d'icônes constaté en
    VM le 2026-07-26). Ne réutilise pas ce drapeau tel quel — clarifie les deux
    notions, quitte à renommer, et mets `gui/prefs.py` à jour en conséquence.

11. **Documenter.** Mets à jour `tasks/T06-integration-steam.md` (une note « revu
    par T19 », pas une réécriture de l'historique), `docs/ARCHITECTURE.md`, et
    la section Steam Deck du README.

Contraintes : aucune dépendance nouvelle (le format se lit avec `struct`) ;
validation des chemins par `paths_safety` avant toute écriture ; erreurs typées ;
messages via `i18n._` ; tests avec des `shortcuts.vdf` fabriqués **et** un
fichier réel anonymisé versionné dans `tests/`.

## Critères d'acceptation

- Round-trip octet à octet sur un `shortcuts.vdf` réel non modifié.
- Après la commande, Steam fermé puis rouvert : GAMMA apparaît dans la
  bibliothèque, avec son artwork, et se lance.
- Relancer la commande ne crée pas de doublon ; elle met l'entrée à jour.
- Les autres raccourcis non-Steam de l'utilisateur sont intacts (comparaison
  champ à champ avant/après).
- Steam ouvert → refus explicite ; `--force` passe.
- `--remove` laisse le fichier tel qu'avant l'ajout.
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
feat(steam): ajout et retrait du raccourci Steam avec artwork
```
