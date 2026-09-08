"""Détection d'un Steam en cours d'exécution, avant d'écrire dans `shortcuts.vdf`.

Steam charge `shortcuts.vdf` au démarrage, le garde **en mémoire**, et le
réécrit intégralement en quittant. Écrire dedans pendant qu'il tourne ne
produit aucune erreur : le fichier est bien modifié, puis silencieusement
écrasé à la fermeture de Steam. C'est le pire des échecs — celui qui ne se voit
qu'une heure plus tard, quand le raccourci a disparu.

Même schéma que `prefix.session` : deux signaux, `/proc` d'abord (précis, sans
dépendance), `pgrep` en repli, et dégradation systématique vers « pas de Steam
détecté » — un `/proc` illisible ne doit jamais empêcher l'utilisateur d'agir.

`comm` plutôt que la ligne de commande : `pgrep -f steam` matcherait notre
propre processus (`stalker-gamma-linux steam-shortcut`), et refuserait donc
toujours d'écrire. Le nom de tâche du noyau, lui, vaut exactement `steam` ou
`steamwebhelper`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.steam.errors import SteamRunningError

_PROC = Path("/proc")

# `comm` est tronqué à 15 caractères par le noyau ; les deux tiennent dedans.
# `steamwebhelper` compte parce qu'il survit parfois à la fenêtre principale :
# tant qu'il tourne, la session Steam n'est pas terminée.
_STEAM_COMMS: frozenset[str] = frozenset({"steam", "steamwebhelper"})


@dataclass(frozen=True, slots=True)
class SteamProcess:
    """Le processus Steam qui tient le fichier : à qui le dire, et quoi fermer."""

    pid: int
    name: str


def _read_comm(pid_dir: Path) -> str | None:
    try:
        return pid_dir.joinpath("comm").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        # Processus disparu entre le listing et la lecture, ou appartenant à un
        # autre utilisateur : on ne peut pas conclure sur CELUI-CI, ce n'est pas
        # une raison de faire échouer toute la détection.
        return None


def _from_proc() -> SteamProcess | None:
    try:
        entries = list(_PROC.iterdir())
    except OSError:
        return None
    for entry in entries:
        if not entry.name.isdigit():
            continue
        comm = _read_comm(entry)
        if comm in _STEAM_COMMS:
            return SteamProcess(pid=int(entry.name), name=str(comm))
    return None


def _from_pgrep() -> SteamProcess | None:
    if system.which("pgrep") is None:
        return None
    for comm in sorted(_STEAM_COMMS):
        # `-x` : correspondance exacte sur le NOM du processus, jamais sur la
        # ligne de commande — voir le docstring du module.
        result = system.run(["pgrep", "-x", comm])
        for line in result.stdout.splitlines():
            if line.strip().isdigit():
                return SteamProcess(pid=int(line.strip()), name=comm)
    return None


def steam_process() -> SteamProcess | None:
    """Le Steam qui tourne, ou `None` si on n'en détecte aucun."""
    return _from_proc() or _from_pgrep()


def require_closed(*, force: bool = False) -> None:
    """Lève `SteamRunningError` si Steam tourne. `force=True` passe outre.

    À appeler avant **toute** écriture dans `shortcuts.vdf` ou dans `grid/` —
    ajout comme retrait : dans les deux sens, Steam réécrirait par-dessus.
    """
    if force:
        return
    process = steam_process()
    if process is not None:
        raise SteamRunningError(process.pid, process.name)
