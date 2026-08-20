# T13 — Verrou « MO2 / préfixe occupé »

**Modèle recommandé : Sonnet 5** — détection de processus et branchement sur des
commandes existantes. Cadré.
**Dépendances : T04, T05.**

## Contexte

Relevé le 2026-08-17.

Un MO2 vivant est le signal le plus fiable pour répondre à une question que
nous ne savons pas poser aujourd'hui : **le préfixe Wine est-il en cours
d'utilisation ?** (MO2 reste en vie tant qu'il fait tourner le jeu.)

Aucun `pgrep` ni équivalent dans le dépôt aujourd'hui. Rien n'empêche
`prefix-doctor --repair`, `update` ou `install --only prefix` de travailler sur
un préfixe pendant que MO2 ou le jeu tournent dedans. Le résultat est une
corruption silencieuse, diagnostiquée plus tard comme un bug Proton.

## Prompt

Tu travailles dans le repo `stalker-gamma-linux` (lis `README.md`,
`src/stalker_gamma_linux/prefix/` et `src/stalker_gamma_linux/mo2/`).

Objectif : savoir si le préfixe partagé est occupé, et refuser les opérations
destructrices tant qu'il l'est.

1. **Helper `prefix/session.py`** (nouveau) exposant
   `prefix_in_use(paths: PrefixPaths) -> ProcessHold | None`, où `ProcessHold`
   décrit ce qui tient le préfixe (pid, nom, ce qu'il faut fermer).

2. **Trois signaux**, du plus fiable au moins :
   - un `wineserver` vivant dont l'environnement pointe sur notre préfixe :
     lire `WINEPREFIX` dans `/proc/<pid>/environ`. C'est le seul signal qui
     couvre le cas « MO2 fermé mais le jeu tourne encore » ;
   - `pgrep -f 'ModOrganizer\.exe'` — **le point échappé compte** : `-f
     ModOrganizer` matcherait notre propre ligne de commande si le chemin
     d'install contient ce mot ;
   - les exécutables du jeu (`AnomalyDX11*.exe`, `Anomaly*.exe`).

3. **Dégradation propre** : `shutil.which("pgrep")` absent, `/proc` illisible,
   timeout → retourner « pas occupé ». Ne jamais bloquer l'utilisateur sur
   l'indisponibilité d'un outil de diagnostic.

4. **Brancher le garde** sur : `prefix-doctor --repair`, `update`,
   `install --only prefix`, et `uninstall --game-data` (cf. T11).

5. **Message actionnable**, jamais un refus sec :
   « Mod Organizer 2 tourne encore (pid 12345) — ferme-le avant de réparer le
   préfixe. » Avec `--force` pour passer outre en connaissance de cause.

6. Exposer l'information dans `doctor` : une ligne « préfixe : libre / occupé
   par … ». C'est aussi une réponse utile en soi.

Contraintes : aucun appel bloquant sans timeout ; lecture de `/proc` tolérante
aux disparitions de processus en cours de route (`ProcessLookupError`,
`PermissionError`) ; tests avec `subprocess` et `/proc` mockés, comme le reste
du projet.

## Critères d'acceptation

- MO2 lancé → `prefix-doctor --repair` refuse avec le pid et le nom du
  processus ; `--force` passe.
- MO2 fermé mais jeu encore lancé → détecté aussi (via `wineserver`).
- `pgrep` absent du système → aucune commande n'est bloquée.
- Un chemin d'install contenant « ModOrganizer » ne provoque pas
  d'auto-détection.
- `ruff` / `mypy --strict` / `pytest` verts.

## Commit

```
fix(prefix): refuser les opérations destructrices sur un préfixe occupé
```
