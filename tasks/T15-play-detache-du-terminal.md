# T15 — `play` détaché du terminal appelant

**Modèle recommandé : Sonnet 5.**
**Dépendances : T05.**
**⚠ À qualifier avant de coder — c'est peut-être un non-problème.**

## Contexte

Relevé le 2026-08-17.

`prefix/process.py` lance en `Popen` bloquant, pompe `stdout` ligne à ligne
dans le fichier de log, puis `process.wait()`. C'est le bon comportement pour
l'installation — on veut la progression et l'annulation. Pour `play`, ça
signifie que fermer le terminal envoie un SIGHUP au jeu.

La forme attendue si le problème est confirmé : `start_new_session=True`,
sortie redirigée vers un log rotatif, et descripteur refermé côté parent dès
le retour de `Popen` (l'enfant a hérité du sien — sinon un fd fuit à chaque
lancement).

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis
`src/stalker_gamma_linux/prefix/process.py`,
`src/stalker_gamma_linux/mo2/launch.py` et
`src/stalker_gamma_linux/desktop/entry.py`).

**Étape 1 — qualifier.** Avant toute modification, déterminer si le problème
existe réellement :

- l'entrée `.desktop` « Play GAMMA (direct) » lance sans terminal → non
  concernée ;
- la GUI lance via `gui/worker.py` → vérifier si la fermeture de la fenêtre
  tue le jeu ;
- reste le `stalker-gamma-linux play` en ligne de commande : tester en réel
  (lancer, fermer le terminal, vérifier si le jeu survit).

Si le jeu survit dans tous les cas, **s'arrêter là** : documenter la conclusion
dans `docs/MO2-PROTON-COMPAT.md` et clore la tâche sans changement de code.

**Étape 2 — si le problème est confirmé.** Ajouter un mode détaché à
`prefix.process.run()` (ou une fonction sœur `run_detached()`) :

1. `start_new_session=True` pour que le processus survive au SIGHUP du
   terminal.
2. Sortie redirigée directement dans le fichier de log (pas de pompage ligne à
   ligne : il n'y a plus personne pour lire), et **descripteur refermé côté
   parent immédiatement après `Popen`**.
3. Rotation du log de lancement au-delà d'une taille raisonnable — le fichier
   devient append-only entre les sessions.
4. Retourner le chemin du log pour que `play` puisse l'afficher, et pour que
   T14 puisse le diagnostiquer après coup.
5. **Ne pas toucher au chemin d'installation** : `engine`/`prefix` gardent le
   mode bloquant avec progression et `cancel_event`. Deux modes explicites,
   pas un mode devinant lequel il est.

Contraintes : ne pas dupliquer la construction d'environnement
(`_prefix_environment` reste la source unique) ; tests avec `Popen` mocké
vérifiant `start_new_session=True` et la fermeture du descripteur.

## Critères d'acceptation

- Conclusion de l'étape 1 écrite quelque part, quelle qu'elle soit.
- Si modification : `play` lancé depuis un terminal, terminal fermé → le jeu
  continue ; le log de lancement contient la sortie ; le chemin du log est
  annoncé.
- Le pipeline d'installation garde sa progression et son annulation propre
  (tests existants inchangés).
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
fix(play): détacher le jeu du terminal appelant
```

ou, si l'étape 1 conclut à un non-problème :

```
docs(mo2): le jeu survit déjà à la fermeture du terminal — mesuré
```
