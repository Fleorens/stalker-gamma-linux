# T18 — Post-mortem de session : attribuer un crash au mod fautif

**Modèle recommandé : Opus 5, effort élevé** — l'attribution d'une trace X-Ray à un mod
demande de lire de vrais logs de crash et d'en tirer des règles, pas d'inventer
des marqueurs.
**Dépendances : T05, T12, T14.**

## Contexte

Relevé le 2026-09-07. Termine la moitié laissée ouverte par T14.

`mo2/diagnostics.py` sait déjà lire un log de lancement
(`launch_failure_diagnosis`, `diagnose_launch_log`, `diagnose_usvfs`). Mais
depuis T15, **`run_play` ne les appelle plus** : le jeu tourne encore quand
`play` rend la main, donc les lire à ce moment-là est un faux négatif
systématique. `docs/MO2-PROTON-COMPAT.md` le note explicitement — ces fonctions
« restent utilisables après coup, une fois le jeu fermé (T14 […] pas encore
câblé en commande dédiée) ».

Résultat : **le diagnostic est écrit et mort.** `play` se contente d'annoncer
le chemin du journal. L'utilisateur dont le jeu vient de planter n'a aucune
commande à taper.

Et il manque la moitié qui compte vraiment. Aujourd'hui on ne regarde que la
sortie de `umu-run` (`logs/mo2-game.log`, nom fixe depuis T15, avec rotation à
un backup). On ne lit **jamais le log du moteur X-Ray lui-même**, qui est le
seul endroit où un crash de GAMMA se laisse attribuer à un mod précis. C'est
pourtant l'attente n°1 après un plantage — et le launcher Windows ne le fait
pas non plus.

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis
`src/stalker_gamma_linux/mo2/diagnostics.py`,
`src/stalker_gamma_linux/mo2/launch.py` (le `log_label="mo2-game"`),
`src/stalker_gamma_linux/prefix/process.py` (`run_detached` et
`_rotate_detached_log`), et `src/stalker_gamma_linux/integrity/report.py`
(`mod_of`, `group_by_mod`)).

Objectif : une commande de post-mortem qui, après la fermeture du jeu, dit ce
qui s'est passé — et quand c'est possible, **quel mod** en est responsable.

1. **Localiser le log X-Ray : à établir sur l'install réelle, pas à supposer.**
   Anomaly écrit son journal sous `appdata/logs/`, mais sous MO2 l'USVFS peut
   rediriger cette écriture vers `overwrite/`. Va le chercher sur l'install de
   test, note l'emplacement observé dans `docs/MO2-PROTON-COMPAT.md`, et
   implémente une recherche qui couvre les deux cas plutôt qu'un chemin
   codé en dur. Prends le plus récent, comme `latest_usvfs_log` le fait déjà
   pour l'USVFS.

2. **Reconnaître les fins de session.** Trois issues à distinguer, parce
   qu'elles n'appellent pas les mêmes conseils : sortie propre, crash du moteur
   (`[error]`, `FATAL ERROR`, `stack trace`), et arrêt par manque de mémoire.
   Ne classe pas en « crash » une session que le joueur a simplement quittée.

3. **Attribuer au mod.** Quand la trace nomme un fichier (script `.script`,
   `.ltx`, texture, modèle), remonte au mod qui le fournit. **N'écris pas une
   deuxième attribution** : `integrity.report.mod_of` fait déjà correspondre un
   chemin relatif sous `mods/` à son mod, et `group_by_mod` regroupe. Réutilise,
   quitte à extraire la partie commune. Si le fichier n'appartient à aucun mod
   (base Anomaly, ou fichier ajouté à la main), dis-le — c'est une information,
   pas un échec.

4. **Un seul diagnostic principal.** La règle posée en T14 tient ici aussi : si
   le lancement a échoué en amont (runtime VC++, préfixe d'un autre Proton),
   c'est ce message-là qu'on affiche, pas le post-mortem X-Ray. Ordonne :
   échec de lancement > crash moteur > USVFS mort > session normale.

5. **Ne jamais affirmer plus que ce qu'on lit.** Un mod nommé dans une trace
   est un **suspect**, pas un coupable : la formulation doit le dire. Un log
   absent, tronqué par la rotation, ou illisible donne « je ne peux pas
   conclure » et le chemin du fichier — jamais une hypothèse inventée.

6. **Surface.** `stalker-gamma-linux postmortem [--target …]` (si un autre nom
   te paraît meilleur pour un joueur, argumente-le dans `docs/ARCHITECTURE.md`
   et tranche), et dans la GUI un bouton **« Le jeu a planté ? »** visible sur
   l'écran principal après un retour de `play` — c'est le moment exact où
   l'utilisateur le cherche, pas trois menus plus loin.

7. **Brancher sur le rapport d'issue.** `report_bundle.py` produit déjà un
   rapport anonymisé ; ajoute-lui le verdict du post-mortem et l'extrait de
   trace retenu. Même anonymisation des chemins que l'existant — un log X-Ray
   contient le nom du compte utilisateur.

Contraintes : recherche insensible à la casse ; lecture par la fin (`deque`,
comme le `tail` déjà en place dans `prefix/process.py`) — un log X-Ray de
plusieurs dizaines de Mo ne se charge pas en mémoire ; messages via `i18n._` ;
**tests sur de vrais extraits de logs**, pris sous
`~/.local/state/stalker-gamma-linux/` ou sur l'install de test — pas de
chaînes inventées, c'est la règle déjà posée en T14.

## Critères d'acceptation

- Après un crash provoqué sur l'install réelle, `postmortem` nomme le mod
  suspect (ou dit explicitement qu'il ne peut pas conclure).
- Après une partie quittée normalement, la commande ne crie pas au crash.
- Un log de lancement contenant `concrt140.dll` produit le diagnostic T14 et
  **pas** le post-mortem X-Ray.
- Log absent ou vidé par la rotation → message actionnable, aucun faux positif.
- Le rapport `doctor --report` inclut le verdict, chemins anonymisés.
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
feat(diagnostics): post-mortem de session et attribution d'un crash au mod
```
