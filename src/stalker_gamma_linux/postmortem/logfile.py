"""Localisation et lecture bornée du journal du moteur X-Ray.

**Emplacement : constaté, pas supposé.** Sur les deux installs GAMMA réelles de
cette machine, le moteur écrit son journal dans le dossier *Anomaly*, pas dans
l'instance MO2 :

    <anomaly>/appdata/logs/xray_steamuser.log

`steamuser` est le nom de compte Windows du préfixe Proton, d'où le glob : sur
un préfixe construit autrement, le nom change. La redirection d'écriture de
l'USVFS (tout ce qu'un processus MO2 crée atterrit dans `overwrite/`) **n'a pas
eu lieu** sur ces installs — `appdata/` est hors de l'arborescence virtualisée —
mais elle reste possible selon la configuration de l'instance, donc les deux
emplacements sont cherchés et c'est le fichier le plus récemment modifié qui
gagne (même règle que `mo2.diagnostics.latest_usvfs_log`, à ceci près qu'ici le
nom n'est pas horodaté : on trie sur la date de modification, pas sur le nom).

**Lecture bornée.** Un journal X-Ray fait couramment plusieurs mégaoctets (5,2
Mo / 104 329 lignes sur la session mesurée) et rien n'en borne la taille. On
n'en charge donc jamais l'intégralité :

- l'en-tête (`Game started:`, `'xrCore' build`) tient dans les premiers
  kilo-octets — on lit ce préfixe et on s'arrête ;
- le verdict et la trace sont à la **fin** — on se positionne à la fin du
  fichier, on relit le dernier bloc d'octets, et on ne garde que les dernières
  lignes dans un `deque` borné (même idée que le `tail` de
  `prefix.process.run_in_prefix`, mais sans relire le fichier entier pour
  arriver à sa fin).

Le décodage est **tolérant** (`errors="replace"`) : `system.read_text` échoue en
UTF-8 strict, et le moteur — comme Wine — écrit des octets qui n'en sont pas.
Un journal illisible ne doit pas produire un diagnostic muet.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# Nom du journal du moteur : `xray_<compte windows>.log` (`xray_steamuser.log`
# sous un préfixe Proton standard).
XRAY_LOG_GLOB = "xray_*.log"

# Sous-chemin du dossier de journaux, relatif au dossier qui porte `appdata/`.
_APPDATA_LOGS = ("appdata", "logs")

# Assez pour couvrir l'en-tête du moteur (CPU, système de fichiers, `Game
# started:`, version) sans lire plus loin.
_HEAD_BYTES = 8 * 1024

# Fenêtre de fin de journal relue pour le verdict. Large de deux ordres de
# grandeur par rapport au bloc de crash (une trentaine de lignes), mais bornée :
# la session plantée mesurée noie ses dernières lignes utiles sous un flot de
# lignes d'inventaire répétées.
_TAIL_BYTES = 512 * 1024
_TAIL_LINES = 600


@dataclass(frozen=True, slots=True)
class EngineLog:
    """Un journal du moteur, lu par les deux bouts et jamais en entier."""

    path: Path
    head: str
    tail: tuple[str, ...]

    @property
    def tail_text(self) -> str:
        return "\n".join(self.tail)

    @property
    def is_empty(self) -> bool:
        return not self.head.strip() and not self.tail_text.strip()


def candidate_log_dirs(anomaly: Path, overwrite: Path) -> tuple[Path, ...]:
    """Les deux endroits où le journal du moteur peut atterrir.

    `anomaly` est le dossier du jeu (voir `mo2.session.resolve_anomaly`, qui
    tolère les deux layouts) ; `overwrite` est le dossier fourre-tout de
    l'instance MO2, cible de la redirection d'écriture de l'USVFS.
    """
    return (anomaly.joinpath(*_APPDATA_LOGS), overwrite.joinpath(*_APPDATA_LOGS))


def find_engine_log(directories: Iterable[Path]) -> Path | None:
    """Journal `xray_*.log` le plus récemment modifié parmi `directories`.

    None si aucun n'existe — un journal absent est une réponse (« je ne peux pas
    conclure »), pas une erreur à faire remonter.
    """
    newest: Path | None = None
    newest_mtime = float("-inf")
    for directory in directories:
        try:
            candidates = sorted(directory.glob(XRAY_LOG_GLOB))
        except OSError:
            continue
        for candidate in candidates:
            try:
                mtime = candidate.stat().st_mtime
            except OSError:
                continue
            if mtime > newest_mtime:
                newest, newest_mtime = candidate, mtime
    return newest


def read_head(path: Path, limit: int = _HEAD_BYTES) -> str:
    """Premiers `limit` octets, décodés en tolérant les octets invalides."""
    try:
        with path.open("rb") as handle:
            return handle.read(limit).decode("utf-8", errors="replace")
    except OSError:
        return ""


def read_tail(
    path: Path, *, max_lines: int = _TAIL_LINES, max_bytes: int = _TAIL_BYTES
) -> tuple[str, ...]:
    """Les `max_lines` dernières lignes, sans lire plus de `max_bytes` octets.

    On se place à `taille - max_bytes` puis on jette la première ligne lue : elle
    est presque toujours coupée en son milieu, et une ligne tronquée n'a aucune
    valeur de preuve pour un diagnostic.
    """
    try:
        with path.open("rb") as handle:
            size = handle.seek(0, 2)
            start = max(0, size - max_bytes)
            handle.seek(start)
            raw = handle.read()
    except OSError:
        return ()

    lines = raw.decode("utf-8", errors="replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]
    return tuple(deque(lines, maxlen=max_lines))


def load_engine_log(path: Path) -> EngineLog:
    """Lit un journal du moteur par ses deux extrémités."""
    return EngineLog(path=path, head=read_head(path), tail=read_tail(path))
