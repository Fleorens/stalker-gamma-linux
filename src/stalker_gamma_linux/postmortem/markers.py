"""Marqueurs du journal du moteur X-Ray — relevés, jamais devinés.

Trois sources, toutes vérifiables, aucune chaîne inventée :

1. **Deux journaux réels complets** d'installs GAMMA de cette machine
   (`anomaly/appdata/logs/xray_steamuser.log`, X-Ray Monolith 1.5.3,
   `'xrCore' build 9959`) :
   - une session **quittée normalement** (13/08/2026, 104 329 lignes) ;
   - une session **plantée** (26/08/2026, 75 973 lignes), journal interrompu net.
2. Les **chaînes de format du moteur lui-même**, extraites de
   `anomaly/bin/AnomalyDX11.exe` (`strings`) : elles disent littéralement ce que
   `xrDebugNew.cpp` peut écrire (`%sFATAL ERROR%s%s`, `%sExpression    : %s%s`,
   `stack trace:%s%s`, `Out of memory. Memory request: %lld K`,
   `* [x-ray]: OOM requesting %lld bytes`).
3. Les lignes d'erreur applicatives d'Anomaly, comptées sur ces deux journaux.

## Le piège, mesuré : `[error]` et `stack trace` ne sont PAS des marqueurs de crash

Sur la session **quittée normalement**, une recherche naïve insensible à la
casse trouve **65 occurrences de `[error]`** et **27 de `stack trace`**. Ce ne
sont pas des crashes : ce sont les erreurs *applicatives* que GAMMA produit en
continu et dont le moteur se relève —

    ! [ERROR] --- Failed to load script mags_patches
    ~ STACK TRACEBACK:

Classer cette session en « crash » serait un faux positif sur *chaque* partie.
Ce qui distingue le bloc fatal du moteur, c'est qu'il est **en début de ligne** :
`xrDebugNew.cpp` écrit `FATAL ERROR` seul sur sa ligne, puis ses champs préfixés
`[error]`, puis `stack trace:` — tandis qu'Anomaly préfixe toujours les siennes
d'un `! ` ou d'un `~ `. Les motifs ci-dessous sont donc **ancrés en début de
ligne** ; l'insensibilité à la casse redevient alors sans danger (mesuré : 0
occurrence sur la session propre, 1 sur la session plantée).

## Fin de session

- Fin propre : `[xrLogger] InternalCloseLog called, terminating thread` — dernière
  ligne de la session propre, absente de la session plantée (chaîne présente
  telle quelle dans le binaire).
- Crash : `stack trace:` en début de ligne, suivi du dump `SymInit:` /
  `at address 0x…` (relevé en fin de la session plantée), et/ou le bloc
  `FATAL ERROR` du moteur.
- Manque de mémoire : `Out of memory. Memory request: <n> K` (gestionnaire
  `out_of_memory_handler` du moteur) ou `* [x-ray]: OOM requesting <n> bytes`.
  **Aucun des deux journaux réels ne contient ce cas** : le motif vient des
  chaînes de format du binaire, pas d'une observation — c'est dit ici plutôt que
  de laisser croire qu'il a été vu tourner.
"""

from __future__ import annotations

import re

# Début de session : `Game started: 26.08.2026 21:01:50.007` (une seule fois par
# journal — X-Ray repart d'un fichier vide à chaque lancement).
SESSION_START_RE = re.compile(r"^Game started:\s*(?P<stamp>.+?)\s*$", re.MULTILINE)

# Identité du moteur, utile dans un rapport d'issue : `'xrCore' build 9959, May 15 2026`.
ENGINE_BUILD_RE = re.compile(r"^'xrCore' build (?P<build>\d+)", re.MULTILINE)

# Fin propre : le logger a été fermé par le moteur, donc le processus est allé
# jusqu'au bout de son arrêt.
CLEAN_EXIT_RE = re.compile(r"^\[xrLogger\] InternalCloseLog", re.MULTILINE | re.IGNORECASE)

# Crash du moteur. Ancrés en début de ligne : voir l'avertissement du module.
STACK_TRACE_RE = re.compile(r"^stack trace:", re.MULTILINE | re.IGNORECASE)
FATAL_ERROR_RE = re.compile(r"^[ \t]*FATAL ERROR[ \t]*$", re.MULTILINE | re.IGNORECASE)
# Champs du bloc fatal (`%sExpression    : %s%s` & co, préfixe `[error]`).
ERROR_FIELD_RE = re.compile(
    r"^\[error\](?P<field>\w[\w ]*?)\s*:\s*(?P<value>.*)$", re.MULTILINE | re.IGNORECASE
)

# Arrêt par manque de mémoire (chaînes de format du binaire — cas non observé).
OUT_OF_MEMORY_RE = re.compile(
    r"^(?:\* \[x-ray\]: OOM requesting|Out of memory\. Memory request:)",
    re.MULTILINE | re.IGNORECASE,
)

# Dump post-crash de `xrDebugNew.cpp` : confirme qu'on lit bien la fin d'un
# processus mort, et donne l'adresse fautive à recopier dans une issue.
CRASH_DUMP_RE = re.compile(
    r"^(?:SymInit: Symbol-SearchPath:|OS-Version:|at address 0x[0-9A-Fa-f]+)",
    re.MULTILINE,
)

# --- Références de fichiers exploitables pour l'attribution ------------------
#
# Chaque motif correspond à une forme de ligne **relevée dans les journaux
# réels** ; rien n'est extrapolé.

# `! error in stalker [sim_default_csky_2], profile [dick_…] with visual
# [actors\stalker_nebo\stalker_nebo3_exohead]` — 1158 occurrences sur la session
# plantée, dont les dernières lignes avant le `stack trace:`. Le chemin est un
# *visual* : pas d'extension, à chercher sous `meshes/` en `.ogf`.
VISUAL_REF_RE = re.compile(r"with visual \[(?P<path>[^\]]+)\]", re.IGNORECASE)

# Chemin complet cité par le moteur ou par une erreur Lua : `…\gamedata\scripts\
# foo.script`, `gamedata/configs/misc/bar.ltx`.
# Bornes de l'extension : de 2 (`.db`) à 6 caractères — `.script`, la plus
# longue que le moteur cite, en fait 6. Une borne à 4 ratait précisément
# celle-là, c'est-à-dire le seul type de fichier qu'une trace Lua nomme.
GAMEDATA_REF_RE = re.compile(
    r"gamedata[\\/](?P<path>[\w\-. \\/]+?\.[A-Za-z0-9]{2,6})\b", re.IGNORECASE
)

# Script nommé nu, tel que le donne la trace Lua :
# `... mosin_carbine_reload_script.script (line: 178) in function 'on_game_start'`.
SCRIPT_REF_RE = re.compile(r"(?P<path>[\w\-]+\.script)\b", re.IGNORECASE)

# Extensions que le moteur cite mais qui n'appartiennent à aucun mod : ses
# propres sources (`..\xrServerEntities\script_engine.cpp`) et ses binaires. Les
# retenir produirait un « suspect » qui n'existe pas.
NON_MOD_EXTENSIONS = frozenset({".cpp", ".h", ".hpp", ".exe", ".dll", ".pdb"})

# Où vit chaque type d'asset sous `gamedata/`, tel que l'arborescence d'un mod
# GAMMA le montre (`gamedata/{configs,meshes,scripts,sounds,textures,anims}`).
EXTENSION_ROOTS: dict[str, tuple[str, ...]] = {
    ".script": ("scripts",),
    ".ltx": ("configs",),
    ".xml": ("configs",),
    ".ogf": ("meshes",),
    ".omf": ("meshes",),
    ".dds": ("textures",),
    ".thm": ("textures",),
    ".ogg": ("sounds",),
    ".wav": ("sounds",),
    ".anm": ("anims",),
    ".ppe": ("anims",),
    ".seq": ("anims",),
}

# Extension d'un « visual » cité sans extension par le moteur.
VISUAL_EXTENSION = ".ogf"
VISUAL_ROOT = "meshes"
