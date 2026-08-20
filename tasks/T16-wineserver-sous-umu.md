# T16 — Épinglage `WINESERVER` sous umu (investigation)

**Modèle recommandé : Fable 5** — territoire Wine/Proton non documenté, à
mesurer avant de conclure.
**Dépendances : T04, T05.**
**⚠ Tâche d'investigation. Ne rien coder avant d'avoir mesuré.**

## Contexte

Relevé le 2026-08-17.

Hypothèse à vérifier : quand MO2 lance des processus enfants à travers l'USVFS,
un `wineserver` système ou plus ancien peut être sélectionné à la place de
celui du Proton du préfixe. Un client et un serveur Wine dépareillés produisent
exactement le `version mismatch` que T14 apprend à reconnaître. La parade
connue, sur un lancement Proton Steam direct (`proton run`), est d'imposer
`WINESERVER=<proton>/files/bin/wineserver`.

**Mais ce n'est pas notre chemin.** Nous passons par `umu-run`, qui gère son
propre runtime et pose probablement déjà un `WINESERVER` cohérent. La question
est ouverte, et poser un `WINESERVER` à la main par-dessus umu peut casser plus
que ça ne répare.

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis
`src/stalker_gamma_linux/prefix/process.py`, en particulier
`_prefix_environment`, et `docs/MO2-PROTON-COMPAT.md`).

**Étape 1 — mesurer.** Sur une machine réelle avec une install fonctionnelle :

1. Lancer MO2 via `stalker-gamma-linux mo2`.
2. Relever `WINESERVER` (et `WINELOADER`, `PROTONPATH`) dans
   `/proc/<pid>/environ` du processus MO2.
3. Lancer le jeu depuis MO2, relever les mêmes variables sur le **processus
   enfant** (`AnomalyDX11*.exe`) — c'est là que le découplage se produirait.
4. Vérifier si un `wineserver` système (`/usr/bin/wineserver`) est présent sur
   la machine de test, et si oui s'il est jamais sélectionné.
5. Refaire avec au moins deux versions de Proton-GE différentes, dont une plus
   ancienne que celle du préfixe — c'est le cas qui déclenche le découplage.

**Étape 2 — conclure.**

- Si umu pose déjà un `WINESERVER` cohérent sur toute la chaîne : écrire la
  conclusion et la méthode de mesure dans `docs/MO2-PROTON-COMPAT.md`, clore la
  tâche **sans changement de code**. La valeur est dans la question tranchée,
  pas dans le patch.
- Si un découplage est observé : imposer `WINESERVER` dans
  `_prefix_environment`, dérivé du `PROTONPATH` effectif, avec un commentaire
  qui explique le cas reproduit (pas une justification théorique).

Contraintes : ne rien changer avant d'avoir la mesure ; les variables
structurelles (`WINEPREFIX`, `GAMEID`, `PROTONPATH`) restent imposées par
`_prefix_environment` comme aujourd'hui ; si patch il y a, test vérifiant que
la variable est bien dérivée du Proton sélectionné et non codée en dur.

## Critères d'acceptation

- Une conclusion écrite dans `docs/MO2-PROTON-COMPAT.md`, avec les valeurs
  relevées et les versions de Proton testées — que le résultat soit positif ou
  négatif.
- Si patch : deux lancements successifs avec des Proton différents ne
  produisent pas de `version mismatch`.
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
docs(mo2): trancher la question WINESERVER sous umu
```

ou, si un découplage est confirmé :

```
fix(prefix): épingler WINESERVER sur le Proton du préfixe
```
