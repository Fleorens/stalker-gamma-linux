"""Détection d'un préfixe partagé occupé (MO2 ou le jeu en train de tourner dedans).

Un MO2 vivant est le seul signal fiable pour répondre à une question qu'aucune
commande ne se pose aujourd'hui : le préfixe Wine est-il en cours d'utilisation ?
Rien n'empêchait `prefix-doctor --repair`, `update` ou `install --only prefix` de
travailler dessus pendant que MO2 ou le jeu tournent dedans — le résultat est une
corruption silencieuse, diagnostiquée plus tard comme un bug Proton.

Trois signaux, du plus fiable au moins :

1. un `wineserver` vivant dont l'environnement (`/proc/<pid>/environ`) pointe sur
   notre préfixe — le seul qui couvre « MO2 fermé mais le jeu tourne encore » ;
2. `pgrep -f 'ModOrganizer\\.exe'` — le point échappé compte : sans lui, un chemin
   d'install contenant simplement le mot « ModOrganizer » (ex. `--target` pointant
   vers un tel dossier) matcherait notre propre ligne de commande ;
3. les exécutables du jeu (`AnomalyDX11*.exe`, `Anomaly*.exe`).

Dégradation systématique vers « pas occupé », jamais vers un blocage : `pgrep`
absent, `/proc` illisible ou un process qui disparaît en cours de lecture ne
doivent jamais empêcher l'utilisateur d'agir sur l'indisponibilité d'un outil de
diagnostic — voir `system.run`, qui porte déjà le timeout sur `pgrep`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.prefix.errors import PrefixBusyError
from stalker_gamma_linux.prefix.paths import PrefixPaths

_PROC = Path("/proc")
_WINESERVER_COMM = "wineserver"

# Le point échappé compte : voir le docstring du module.
_MO2_PATTERN = r"ModOrganizer\.exe"
_GAME_PATTERNS = (r"AnomalyDX11[^/\\]*\.exe", r"Anomaly[^/\\]*\.exe")


@dataclass(frozen=True, slots=True)
class ProcessHold:
    """Ce qui tient le préfixe partagé : à qui le dire, et quoi fermer pour le libérer."""

    pid: int
    name: str
    what_to_close: str


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        # Fichier disparu (process terminé entre le listing et la lecture),
        # accès refusé (process d'un autre utilisateur) : dans les deux cas on
        # ne peut pas conclure sur CE process, pas la peine de faire échouer
        # toute la détection pour autant.
        return None


def _wineserver_holder(paths: PrefixPaths) -> ProcessHold | None:
    try:
        entries = list(_PROC.iterdir())
    except OSError:
        return None

    target = str(paths.prefix)
    for entry in entries:
        if not entry.name.isdigit():
            continue
        comm = _read_bytes(entry / "comm")
        if comm is None or comm.decode("utf-8", "replace").strip() != _WINESERVER_COMM:
            continue
        environ = _read_bytes(entry / "environ")
        if environ is None:
            continue
        for raw_entry in environ.split(b"\0"):
            text = raw_entry.decode("utf-8", "replace")
            prefix_value = text.removeprefix("WINEPREFIX=")
            if prefix_value == text:
                continue
            if prefix_value == target:
                return ProcessHold(
                    pid=int(entry.name),
                    name=_("a Wine process using this prefix"),
                    what_to_close=_("Mod Organizer 2 and/or the game"),
                )
            break
    return None


def _pgrep(pattern: str) -> list[int]:
    if system.which("pgrep") is None:
        return []
    result = system.run(["pgrep", "-f", pattern])
    pids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def _first_pid(pattern: str) -> int | None:
    pids = _pgrep(pattern)
    return pids[0] if pids else None


def prefix_in_use(paths: PrefixPaths) -> ProcessHold | None:
    """Ce qui tient le préfixe partagé, ou `None` s'il est libre.

    Voir le docstring du module pour l'ordre des trois signaux et la logique de
    dégradation.
    """
    hold = _wineserver_holder(paths)
    if hold is not None:
        return hold

    pid = _first_pid(_MO2_PATTERN)
    if pid is not None:
        return ProcessHold(pid=pid, name=_("Mod Organizer 2"), what_to_close=_("it"))

    for pattern in _GAME_PATTERNS:
        pid = _first_pid(pattern)
        if pid is not None:
            return ProcessHold(pid=pid, name=_("the game (Anomaly)"), what_to_close=_("it"))

    return None


def require_free(paths: PrefixPaths, *, action: str, force: bool = False) -> None:
    """Lève `PrefixBusyError` si le préfixe est occupé. `force=True` passe outre.

    Brancher avant toute opération destructrice sur le préfixe partagé
    (`prefix-doctor --repair`, `update`, `install --only prefix`,
    `uninstall --game-data`). `action` est inséré dans le message d'erreur
    (ex. « repairing the prefix »).
    """
    if force:
        return
    hold = prefix_in_use(paths)
    if hold is not None:
        raise PrefixBusyError(hold.pid, hold.name, hold.what_to_close, action=action)
