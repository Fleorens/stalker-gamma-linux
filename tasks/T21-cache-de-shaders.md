# T21 — Cache de shaders : le conserver, et le chauffer

**Modèle recommandé : Sonnet 5, effort moyen** — quelques variables d'environnement bien
placées et une mesure ; le raisonnement est court, la mesure compte.
**Dépendances : T04, T05.**

## Contexte

Relevé le 2026-09-07.

Le premier lancement de GAMMA compile des milliers de shaders. C'est le premier
« sous Linux ça marche moins bien » qu'un joueur écrit — et c'est faux : c'est
un coût unique qu'on ne lui a simplement pas expliqué, et qu'on lui fait payer
plusieurs fois.

Deux problèmes distincts, à ne pas confondre :

1. **Le cache X-Ray** (celui d'Anomaly). On le purge volontairement après un
   retrait de ReShade ou une update (`engine.runner.purge_shader_cache`, qui
   passe `--anomaly` et rien d'autre). C'est correct et documenté
   (`docs/INSTALL-MANUAL.md` §5, §9) — **ne touche pas à ce comportement**.
2. **Le cache de pipelines DXVK et le cache du pilote** (DXVK state cache,
   `MESA_SHADER_CACHE_DIR` côté Mesa, `__GL_SHADER_DISK_CACHE_PATH` côté
   NVIDIA). Celui-là, personne ne le gère chez nous : il atterrit où le pilote
   et le préfixe décident. `prefix/process.py::_prefix_environment` impose
   `WINEPREFIX`, `GAMEID` et `PROTONPATH`, et rien sur les caches.

La conséquence est concrète : `install --only prefix` **reconstruit le préfixe
à partir de zéro** — c'est le remède officiel de la matrice de compatibilité
pour un « prefix has an invalid version ». Un joueur qui suit notre conseil
perd donc, sans être prévenu, des heures de compilation de shaders. Le cache
par défaut de Mesa est en plus plafonné bien trop bas pour un modpack de cette
taille : il se fait évincer tout seul en cours de route.

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis
`src/stalker_gamma_linux/prefix/process.py` (`_prefix_environment`),
`src/stalker_gamma_linux/engine/runner.py` (`purge_shader_cache`),
`src/stalker_gamma_linux/engine/paths.py` et
`src/stalker_gamma_linux/uninstall.py`).

Objectif : que le coût de compilation des shaders soit payé une fois, pas à
chaque réparation de préfixe.

1. **Sortir les caches du préfixe.** Pose les caches DXVK et pilote sous
   `<root>/cache/shaders/` (même volume que l'install, comme `TMPDIR` en
   `engine/runner.py::_extract_tmpdir` — reprends ce raisonnement, il est déjà
   écrit). Ils survivent alors à une reconstruction de préfixe, à un changement
   de version de Proton-GE, et à `prefix-doctor --repair`.

2. **Les variables à poser** dans `_prefix_environment`, avec un commentaire
   disant *pourquoi* chacune : chemin du state cache DXVK, répertoire de cache
   Mesa **et son plafond de taille** (le défaut évince silencieusement), chemin
   et taille du cache disque NVIDIA. Ne pose une variable pilote que si le
   pilote correspondant est présent — inutile de polluer l'environnement des
   autres. `env` étant déjà un paramètre de `run_in_prefix`, l'appelant doit
   pouvoir surcharger : les variables structurelles restent imposées, celles-ci
   sont des défauts.

3. **Ne jamais les supprimer par accident.** `install --only prefix` et
   `prefix-doctor --repair` ne doivent pas y toucher. `uninstall --game-data`,
   lui, les emporte (ils sont sous `<root>`) : c'est cohérent, mais vérifie que
   c'est bien le cas et que `sizing.py` en tient compte dans l'estimation
   annoncée avant suppression.

4. **Le dire à l'utilisateur.** Après une installation réussie, une ligne :
   la première partie compilera ses shaders et sera saccadée, c'est normal,
   ça ne se reproduira pas. Un joueur prévenu n'ouvre pas d'issue — et surtout
   ne conclut pas que Proton est en cause.

5. **Chauffage optionnel, seulement si ça se mesure.** Un pré-chauffage
   (lancer une fois pour peupler le cache) n'a d'intérêt que si le gain est
   réel. **Mesure d'abord** : temps du premier lancement, du deuxième, taille
   du state cache après chacun. Si le gain ne se voit pas, n'implémente rien et
   écris la mesure dans `docs/MO2-PROTON-COMPAT.md` — une piste fermée
   proprement vaut mieux qu'une fonctionnalité décorative (c'est ce qu'a fait
   T16 pour `WINESERVER`).

6. **Ce qu'on ne fera pas, et pourquoi l'écrire.** Distribuer un state cache
   « communautaire » pré-compilé : il est spécifique au GPU, au pilote et à sa
   version, et ça reviendrait à héberger un binaire tiers — deux fois contraire
   aux règles du projet (« jamais de rehosting »). Note-le dans la doc pour que
   la question ne revienne pas.

Contraintes : aucune dépendance nouvelle ; détection de pilote par ce qui est
présent sur le système, pas par une supposition ; pas de mutation de
`os.environ` ; messages via `i18n._`.

## Critères d'acceptation

- Après un `install --only prefix`, le cache de shaders est intact et le
  deuxième lancement ne recompile pas.
- Le state cache DXVK grossit d'une session à l'autre sous `<root>/cache/shaders/`
  et non dans le préfixe.
- Mesure des deux premiers lancements consignée dans la doc, avec la décision
  sur le pré-chauffage.
- `purge_shader_cache` continue de ne toucher qu'au cache X-Ray.
- `uninstall --game-data --dry-run` annonce une taille qui inclut ces caches.
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
perf(prefix): sortir les caches de shaders du préfixe pour qu'ils y survivent
```
