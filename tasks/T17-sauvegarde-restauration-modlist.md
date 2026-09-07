# T17 — Sauvegarde / restauration, et fusion de la modlist à l'update

**Modèle recommandé : Opus 5, effort maximal** — la fusion à trois voies est la partie
délicate (quoi ressusciter, quoi ne surtout pas ressusciter), et on touche aux
données que l'utilisateur ne peut pas retélécharger.
**Dépendances : T07, T12.**

## Contexte

Relevé le 2026-09-07.

C'est la plainte n°1 de G.A.M.M.A., toutes plateformes confondues. Le wiki
officiel l'écrit lui-même : « *every time you click Install / Update GAMMA,
your modlist, settings, and mod settings will reset. This is on purpose […]
remember to make backups before clicking that button* ». Sur Windows, la
réponse tient donc en un conseil que personne n'applique.

Chez nous, la moitié du chemin est déjà faite :
`orchestrator.backup_mo2_profiles()` copie `<gamma>/profiles/` avant chaque
`update`, avec le constat mesuré en réel (757 lignes personnalisées contre 752
en amont, dont un patch de traduction ajouté par le joueur). Mais :

- **il n'existe aucune commande pour restaurer** (`grep -r restore src/` ne
  ramène que des occurrences sans rapport) : le filet existe et n'est
  utilisable qu'à coups de `cp -r` à la main ;
- **les sauvegardes de partie ne sont pas couvertes** — seulement `profiles/` ;
- **`<root>/backups/` grossit indéfiniment** : une copie complète par update,
  jamais purgée ;
- **la modlist reste écrasée** : on rend la perte réversible, on ne l'évite pas.

L'objectif de cette tâche est de passer de « réversible » à « ça ne se perd
plus ». C'est ce qui fait qu'un joueur préfère notre outil au launcher
officiel, pas juste qu'il s'en contente sous Linux.

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`docs/ARCHITECTURE.md`, `src/stalker_gamma_linux/orchestrator.py` —
particulièrement `backup_mo2_profiles`, `src/stalker_gamma_linux/mo2/paths.py`,
`src/stalker_gamma_linux/mo2/merge.py` et `src/stalker_gamma_linux/paths_safety.py`).

Objectif : un module `backups/` qui sait sauvegarder, lister et **restaurer**
ce que l'utilisateur ne peut pas retélécharger, et une fusion de `modlist.txt`
qui survit à une mise à jour amont.

### Partie 1 — sauvegarde et restauration

1. **Périmètre.** Trois ensembles, indépendamment sélectionnables :
   `profiles/` (modlist, ordre de chargement, réglages MCM), les **sauvegardes
   de partie**, et `overwrite/` de l'instance MO2. Reprends le contenu de
   `backup_mo2_profiles()` comme premier cas et **déplace-le** dans le nouveau
   module — pas de deuxième implémentation en parallèle.

2. **Où vivent les sauvegardes de partie : à établir, pas à supposer.** Anomaly
   est portable et écrit sous `appdata/savedgames`, mais sous MO2 l'USVFS peut
   rediriger ces écritures vers `overwrite/` ou vers le profil selon la
   configuration de l'instance. `mo2/merge.py` documente déjà le cas symétrique
   pour le mode flat (« tout ce qui vit sous `appdata/` est copié, jamais lié »).
   **Constate le comportement réel sur l'install de test avant de coder le
   chemin**, et écris ce que tu as observé dans `docs/ARCHITECTURE.md`. Si les
   deux emplacements peuvent être peuplés, sauvegarde les deux.

3. **Format.** Un dossier horodaté par sauvegarde sous `<root>/backups/`
   (garde le nommage existant `profiles-%Y%m%d-%H%M%S` pour ne pas rendre
   orphelines les sauvegardes déjà sur les disques des utilisateurs), plus un
   petit manifeste TOML : date, version GAMMA connue, ensembles inclus, taille.
   C'est le manifeste que lit `--list`, pas un `stat` du dossier.

4. **Rotation.** Plafond par défaut (5 sauvegardes automatiques), purge de la
   plus ancienne au-delà. Une sauvegarde créée explicitement par l'utilisateur
   n'entre **jamais** dans la rotation : marque-la dans le manifeste. Avant
   toute suppression, passe par `paths_safety` — c'est un `rmtree` sur un
   chemin dérivé de `--target`, exactement le périmètre de T11.

5. **Restauration.** `restore <id>` remet en place, après avoir **sauvegardé
   l'état courant d'abord** (une restauration ratée ne doit pas être un
   aller simple). Refuse de tourner si le préfixe est occupé —
   `prefix.session.require_free` est déjà là pour ça, avec son `--force`.
   `--dry-run` liste ce qui serait écrit, comme `uninstall` et `import`.

6. **Surface.** `stalker-gamma-linux backup [--saves] [--profiles]
   [--overwrite]`, `backup --list`, `restore <id> [--dry-run]`, plus les
   boutons correspondants dans la vue Diagnostic de la GUI. Aucune logique
   métier dans la GUI (règle T08) ; tout passe par `output.Reporter`.

### Partie 2 — fusion de la modlist

7. **Le problème exact.** `full-install` réécrit
   `profiles/G.A.M.M.A/modlist.txt` avec la liste amont
   (`_install_modorganizer_profile` chez gamma-launcher). On perd trois choses
   distinctes : les mods **désactivés** par le joueur, l'**ordre** qu'il a
   ajusté, et les mods qu'il a **ajoutés** lui-même.

8. **Fusion à trois voies.** Conserve à chaque update un instantané de la
   modlist amont (`base`). À l'update suivant : `base` = amont précédent,
   `ours` = le fichier du joueur, `theirs` = le nouvel amont. Applique
   par-dessus `theirs` les seuls écarts imputables au joueur.

9. **Les règles qui ne sont pas évidentes, et qu'il faut respecter** :
   - l'ordre de `modlist.txt` va **du bas vers le haut** en priorité croissante
     (déjà documenté dans `mo2/merge.py`) : une fusion qui raisonne « ligne N »
     se trompe de sens un jour sur deux ;
   - un mod **retiré en amont** ne doit jamais être ressuscité par la fusion :
     son dossier n'existe plus sur le disque, MO2 l'afficherait en « missing » ;
   - un mod **ajouté par le joueur** doit être réinséré à sa position relative
     (son voisin conservé le plus proche), pas empilé en fin de liste ;
   - les séparateurs sont des entrées de la liste comme les autres : ne les
     traite pas à part, mais ne les compte pas comme des mods dans le rapport ;
   - **en cas de doute, on ne fusionne pas** : on garde l'amont, on conserve la
     sauvegarde, et on le dit clairement. Une fusion silencieusement fausse est
     pire qu'une restauration manuelle.

10. **Rapport.** Après fusion, dis ce qui a été réappliqué : « N mods
    réactivés/désactivés selon tes réglages, M mods ajoutés par toi
    réinsérés, K entrées retirées en amont non restaurées ». Sans ce compte
    rendu, l'utilisateur ne sait pas s'il doit ouvrir MO2 pour vérifier.

11. **Opt-out.** `update --no-merge` garde le comportement actuel (écrasement
    amont + sauvegarde). La fusion est un défaut, pas une obligation.

Contraintes : jamais de mutation en place d'un fichier de l'utilisateur (écrire
à côté puis remplacer atomiquement) ; lecture/écriture en UTF-8 avec
préservation des fins de ligne d'origine (l'instance vient de Windows) ; erreurs
typées avec contexte ; messages via `i18n._` ; fichiers courts et cohésifs.

## Critères d'acceptation

- Sur l'install réelle : `backup --saves` produit une sauvegarde restaurable,
  `restore` la remet en place, et une partie chargée après restauration
  fonctionne.
- Une modlist personnalisée (mod désactivé + mod ajouté + ordre modifié)
  survit à un `update` complet, et le rapport annonce les bons comptes.
- Un mod supprimé en amont n'est pas ressuscité.
- La rotation supprime bien la plus ancienne sauvegarde automatique et
  **jamais** une sauvegarde explicite.
- `restore` refuse de tourner avec MO2 ouvert, et passe avec `--force`.
- Tests sur arborescence temporaire pour la fusion : les six cas du point 9,
  plus une modlist vide, plus un fichier aux fins de ligne CRLF.
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
feat(backups): sauvegarde/restauration et fusion de la modlist à la mise à jour
```
