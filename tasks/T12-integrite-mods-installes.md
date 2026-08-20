# T12 — Intégrité MD5 des mods installés + réparation ciblée

**Modèle recommandé : Fable 5** — beaucoup de décisions de conception subtiles
(quand rebaseliner, quoi ne jamais réparer), et un scan de 150 Gio à ne pas
rater.
**Dépendances : T03, T07.**

## Contexte

Relevé le 2026-08-17.

Aujourd'hui nous vérifions les **archives** via le `check-md5` du moteur
(`engine/runner.py`). Ça couvre « le téléchargement était-il correct ». Ça ne
couvre pas « l'install sur le disque est-elle encore intacte » : un fichier de
mod corrompu, écrasé par un autre outil, ou tronqué par un disque plein après
l'installation est aujourd'hui indétectable. C'est le premier symptôme que
remonte un joueur (« le jeu crashe depuis hier »), et on n'a rien à lui dire.

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md`, `src/stalker_gamma_linux/engine/runner.py` et
`src/stalker_gamma_linux/state.py`).

Objectif : module `integrity.py` qui vérifie le contenu installé sous
`<install>/gamma/mods` contre une empreinte de référence, et sait réparer
les mods abîmés sans toucher au reste.

1. **Baseline.** Fichier `<install>/gamma-md5.txt`, une ligne par fichier :
   `<md5><séparateur><chemin relatif>`, trié. Parser avec un `split` après le
   hash — **pas** par offsets fixes (`line[32:34]`), qui cassent au premier
   format inattendu.

2. **Premier passage** : création de la baseline, **aucun diff**, et le dire
   explicitement à l'utilisateur (« référence enregistrée — relance la
   vérification pour détecter les changements »). Ne jamais laisser croire
   qu'une vérification a eu lieu.

3. **Passages suivants** : re-hacher tout et classer en `changed` / `added` /
   `removed` / `unreadable`.

4. **Annulation → jamais de réécriture de baseline.** Tu as déjà `cancel_event`
   partout (`engine/process.py`, `prefix/process.py`) : réutilise-le. Un scan
   interrompu ne doit jamais figer une install potentiellement cassée comme
   nouvelle référence.

5. **Rebaseline explicite après réparation.** Sinon les mods réparés
   ressortent comme `changed` au passage suivant. C'est une opération distincte
   et intentionnelle, pas un effet de bord du scan.

6. **Classification pour la réparation** :
   - un mod est réparable si son dossier correspond à une entrée de la liste
     modpack amont ;
   - les fichiers **`added` ne sont jamais réparés** — ce sont les ajouts et
     réglages de l'utilisateur. Les signaler, les laisser tranquilles ;
   - les mods sans source officielle (extras du joueur) : signalés, intacts.

7. **Réparation** : suppression du dossier de mod + de son archive en cache,
   puis relance du moteur sur ce sous-ensemble uniquement. **Avant tout
   `rmtree`/`unlink`, refuser tout nom qui s'échappe de `mods/`** : vérifier que
   le dossier visé est un enfant *direct* de `mods/`, avec les mêmes garanties
   que T11 (et à factoriser avec, si `paths_safety.py` existe déjà).

8. **Progression.** Un scan de 150 Gio prend plusieurs minutes. Cadence les
   rapports de progression **au temps écoulé**, pas au nombre de fichiers :
   un `index % N == 0` donne une interface figée pendant de longues secondes
   dès que les fichiers sont gros.
   Passe par `output.Reporter` comme le reste, pour que CLI et GUI partagent.

9. **Surface** : commande `stalker-gamma-linux verify [--repair]`, plus un
   bouton dans la vue Diagnostic de la GUI. Aucune logique métier dans la GUI —
   même règle que T08.

Contraintes : lecture par blocs (ne jamais charger un fichier de mod en
mémoire) ; un fichier illisible n'interrompt pas le scan, il est rapporté ;
erreurs typées avec contexte ; sortie `rich` cohérente avec `doctor`.

## Critères d'acceptation

- Sur une install réelle : premier passage crée la référence, second passage
  rapporte « inchangé », modification manuelle d'un fichier de mod → détectée
  et attribuée au bon mod.
- Un scan annulé à mi-parcours laisse la baseline précédente intacte.
- `--repair` ne supprime que les dossiers de mods concernés, jamais un fichier
  ajouté par l'utilisateur.
- Tests avec une arborescence temporaire : création de baseline, diff sur les
  quatre catégories, annulation, rebaseline, refus d'un nom de mod contenant
  `..` ou un séparateur de chemin.
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
feat(integrity): vérification MD5 des mods installés et réparation ciblée
```
