# T11 — Garde-fous de chemin sur `uninstall --game-data`

**Modèle recommandé : Sonnet 5** — périmètre net, logique pure, beaucoup de
tests. Pas besoin d'un modèle de raisonnement.
**Dépendances : T07.**
**Priorité : haute — défaut de sûreté existant, pas une amélioration.**

## Contexte

Relevé le 2026-08-17. Aujourd'hui, dans `uninstall.py` :

- `build_plan()` ajoute `root` — c'est-à-dire `--target`, fourni par
  l'utilisateur, **sans aucune validation** — à la liste des suppressions dès
  que `game_data=True` ;
- `apply_plan()` fait `shutil.rmtree(removal.path)` dessus, dans un
  `try/except OSError: continue` qui avale l'échec ;
- `run_uninstall()` n'exige **aucune confirmation interactive** : hors
  `--dry-run`, il applique le plan directement.

Donc :

```sh
stalker-gamma-linux uninstall --game-data --target ~        # rmtree sur $HOME
stalker-gamma-linux uninstall --game-data --target /        # rmtree sur /
stalker-gamma-linux uninstall --game-data --target ~/lien   # suit le symlink
```

Le `--dry-run` et l'affichage du plan atténuent, mais ce sont des conventions
d'interface, pas des invariants. Une faute de frappe dans `--target` suffit.

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md`, et `src/stalker_gamma_linux/uninstall.py`).

Objectif : rendre structurellement impossible la suppression d'un chemin qui
n'est pas une install GAMMA, quoi que contienne `--target`.

1. **Nouveau module `paths_safety.py`** (ou une section dédiée d'`uninstall.py`
   s'il reste sous 300 lignes) exposant :

   ```python
   def is_safe_wipe_target(raw: Path, resolved: Path) -> bool: ...
   def resolve_wipe_target(raw: Path) -> Path | None: ...
   ```

   Refuser si :
   - `resolved` est une racine système : `/`, `/home`, `/root`, `/usr`,
     `/etc`, `/var`, `/opt`, `/boot`, `/bin`, `/sbin`, `/lib`, `/lib64`,
     `/srv`, `/mnt`, `/media`, `/tmp` ;
   - `resolved` est `Path.home()`, son parent, ou **un sibling** de
     `Path.home()` (`/home/quelqu-un-d-autre`) ;
   - `resolved` est le répertoire courant, ou la racine du dépôt/venv d'où l'on
     tourne ;
   - `len(resolved.parts) < 3` — une install réelle est nichée au moins deux
     niveaux sous la racine ;
   - `raw` (**avant** `resolve()`) est un symlink : `resolve()` l'a déjà suivi,
     et supprimer à travers emporterait une arborescence non liée.

2. **Exiger un marqueur d'install.** En plus des refus ci-dessus, n'accepter
   `root` que s'il contient au moins un des marqueurs attendus — `anomaly/`,
   `gamma/`, `mods/`, `prefix/`, ou le fichier d'état d'install. Les refus
   génériques ne suffisent pas : un dossier étranger niché assez profondément
   les passe tous. Le marqueur est ce qui distingue « un chemin plausible » de
   « une install GAMMA ».

3. **Résoudre une seule fois.** `resolve_wipe_target()` retourne le chemin
   résolu, et c'est **exactement ce chemin** qui est validé puis supprimé.
   Ne jamais re-résoudre entre le contrôle et le `rmtree` (TOCTOU).

4. **Échouer bruyamment.** Un chemin refusé lève une erreur typée
   (`UnsafeWipeTargetError`, dans le style des autres erreurs du projet) avec le
   chemin concerné et la raison du refus. Pas de `continue` silencieux : le
   `except OSError` d'`apply_plan()` reste pour les échecs de permissions, mais
   un refus de sûreté doit interrompre.

5. **Vérifier après coup** que le dossier a bien disparu ; sinon, lever plutôt
   que de rapporter un succès partiel.

6. **Confirmation interactive** pour `--game-data` hors `--dry-run` : afficher
   le chemin résolu et la taille estimée, exiger une saisie explicite. Ajouter
   `--yes` pour les usages scriptés (et pour `install.sh --uninstall`, qui ne
   doit pas se retrouver bloqué).

Contraintes : logique pure et testable sans toucher au disque (les fonctions de
décision ne font pas d'E/S au-delà de `resolve`/`is_symlink`/`is_dir`) ;
messages traduits via `i18n._` comme le reste ; aucune mutation d'objet.

## Critères d'acceptation

- Tests couvrant **chacun** des refus : toutes les racines protégées, `$HOME`,
  le parent de `$HOME`, un sibling de `$HOME`, un symlink pointant vers une
  install légitime, un chemin relatif, un chemin contenant `..`, une cible
  inexistante, un dossier existant mais sans marqueur, et le cas nominal.
- `uninstall --game-data --target ~` échoue avec un message clair et **ne
  supprime rien**.
- `uninstall --game-data` sur une vraie install fonctionne toujours, avec
  confirmation.
- `install.sh --uninstall` n'est pas cassé (passe `--yes`).
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
fix(uninstall): refuser de supprimer une cible hors d'une install GAMMA
```
