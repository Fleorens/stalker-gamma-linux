# T14 — Diagnostic du log de lancement : runtime et préfixe

**Modèle recommandé : Sonnet 5** — extension d'un module existant, marqueurs
connus.
**Dépendances : T05.**

## Contexte

Relevé le 2026-08-17.

`mo2/diagnostics.py` couvre déjà bien l'USVFS (`_VFS_MAPPING_MARKER`,
`_INITHOOKS_OK_RE`, message de repli explicite). Mais il ne reconnaît **pas**
les deux échecs qui surviennent *en amont* de l'USVFS, c'est-à-dire ceux que
l'utilisateur rencontre en premier :

- `concrt140.dll` → les runtimes VC++ manquent dans le préfixe. On les installe
  en T04, mais un préfixe bricolé ou partiellement réparé entre-temps produit
  une erreur Wine illisible.
- `wine client error:0: version mismatch`, `wrong wineserver`,
  `prefix has an invalid version`, `your wine binary was not upgraded correctly`
  → le préfixe a été construit par une autre version de Proton.

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis
`src/stalker_gamma_linux/mo2/diagnostics.py`,
`src/stalker_gamma_linux/prefix/process.py` et `docs/MO2-PROTON-COMPAT.md`).

Objectif : reconnaître dans le log de lancement les échecs de runtime et de
préfixe, et donner le remède exact plutôt que la trace Wine.

1. Étendre `mo2/diagnostics.py` avec une table
   `marqueur → (diagnostic, remède)`. Chaque entrée mappe sur une commande
   concrète du projet : `prefix-doctor --repair`, `install --only prefix`, ou
   la ligne d'installation des verbs.

2. Couvrir au minimum : `concrt140.dll` (et les autres DLL VC++ qui
   apparaissent en pratique : `msvcp140`, `vcruntime140`), le mismatch de
   version wineserver, et le préfixe créé par une autre version de Proton.

3. Brancher sur le log déjà capturé par `prefix/process.py` — le `tail` en
   `deque` est déjà en place, il n'y a rien à instrumenter de plus.

4. Ordonner les diagnostics : un échec de runtime survient avant l'USVFS, donc
   il doit être rapporté **à la place** du message USVFS générique, pas en plus.
   Un utilisateur à qui on annonce deux problèmes n'en corrige aucun.

5. Ajouter ce qui est trouvé à `docs/MO2-PROTON-COMPAT.md` : ces symptômes
   appartiennent à la matrice de compatibilité.

Contraintes : recherche insensible à la casse sur le log ; ne jamais afficher
plus d'un diagnostic principal ; messages traduits via `i18n._` ; tests sur des
extraits de logs réels (pas des chaînes inventées — s'il y en a sous
`~/.local/state/stalker-gamma-linux/`, s'en servir).

## Critères d'acceptation

- Un log contenant `concrt140.dll` produit « les runtimes VC++ manquent dans le
  préfixe » + la commande de remède, et **pas** le message USVFS.
- Un log contenant `version mismatch` produit le diagnostic « préfixe construit
  par une autre version de Proton ».
- Un log sain ne déclenche aucun faux positif.
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
feat(diagnostics): reconnaître les échecs runtime/préfixe dans le log de lancement
```
