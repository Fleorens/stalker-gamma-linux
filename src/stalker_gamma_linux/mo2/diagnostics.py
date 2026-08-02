"""Diagnostic « USVFS mort » : le jeu a-t-il démarré avec les mods, ou en vanilla ?

Le symptôme n°1 du mode MO2 sous Proton est un jeu qui se lance **sans contenu
GAMMA** parce que le VFS n'a pas été monté (version de Proton incompatible, ou
jeu lancé hors MO2). On le détecte sur des signaux réels, inspectables côté
Linux :

1. Le dernier `logs/usvfs-*.log` de l'instance montre-t-il que le VFS a été
   injecté dans le processus du jeu et sert des fichiers ? Marqueurs relevés sur
   un vrai run modé qui fonctionne (usvfs 0.5.6.1, GE-Proton11-1, Wine 10) :
   `inithooks in process <pid> successful` (hooks posés dans un process cible) et
   `mapping file in vfs:` (le VFS sert effectivement des fichiers au jeu).
2. Le profil `G.A.M.M.A` a-t-il bien des mods activés (`modlist.txt`) ? Sinon,
   MO2 n'a rien à monter — c'est un problème de configuration, pas d'USVFS.

Le diagnostic est **indicatif** : les logs usvfs varient selon les versions, donc
`play` réussit toujours si le jeu s'est lancé — on affiche seulement un
avertissement si les marqueurs de VFS vivant manquent. Les remèdes renvoient vers
`docs/MO2-PROTON-COMPAT.md`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.i18n import _
from stalker_gamma_linux.mo2.instance import GAMMA_PROFILE
from stalker_gamma_linux.mo2.modlist import enabled_mods, read_modlist
from stalker_gamma_linux.mo2.paths import Mo2Paths

_USVFS_LOG_GLOB = "usvfs-*.log"

# Signaux d'un VFS vivant, tirés d'un vrai log usvfs qui fonctionne : les hooks
# ont été posés dans un process cible (le jeu), et/ou des fichiers sont
# effectivement servis par le VFS. Le marqueur historique « proxy run successful »
# des forums ne correspond PAS à usvfs 0.5.6.1 (faux négatif constaté en réel).
_INITHOOKS_OK_RE = re.compile(r"inithooks in process \d+ successful")
_VFS_MAPPING_MARKER = "mapping file in vfs:"

_COMPAT_DOC = "docs/MO2-PROTON-COMPAT.md"


@dataclass(frozen=True, slots=True)
class UsvfsDiagnosis:
    """Verdict du diagnostic post-lancement."""

    active: bool
    checked_log: Path | None
    enabled_mod_count: int
    message: str


def latest_usvfs_log(mo2: Mo2Paths) -> Path | None:
    """Journal USVFS le plus récent de l'instance, ou None s'il n'y en a aucun.

    Le nom horodaté (`usvfs-AAAA-MM-JJ_HH-MM-SS.log`, zéro-padé) rend l'ordre
    lexicographique équivalent à l'ordre chronologique.
    """
    logs_dir = mo2.logs
    if not logs_dir.is_dir():
        return None
    candidates = sorted(logs_dir.glob(_USVFS_LOG_GLOB))
    return candidates[-1] if candidates else None


def usvfs_active_in(log_text: str) -> bool:
    """Vrai si le journal indique un VFS vivant : hooks posés dans un process
    cible (`inithooks in process N successful`) ou fichiers servis par le VFS
    (`mapping file in vfs:`)."""
    return bool(_INITHOOKS_OK_RE.search(log_text)) or _VFS_MAPPING_MARKER in log_text


def _no_log_message(enabled: int) -> str:
    return _(
        "No USVFS log ({glob}) found: can't confirm the VFS mounted.\n"
        "→ Launch the game **via MO2** (the `play` command, not the executable "
        "directly) at least once. G.A.M.M.A profile: {enabled} mods enabled."
    ).format(glob=_USVFS_LOG_GLOB, enabled=enabled)


def _dead_no_mods_message() -> str:
    return _(
        "⚠ No mod enabled in the G.A.M.M.A profile (modlist.txt): MO2 has nothing to "
        "mount, the game will necessarily start vanilla.\n"
        "→ Reconfigure the instance (gamePath + profile), then check that the "
        "modpack install is complete (full-install / check-md5)."
    )


def _dead_message(log: Path, enabled: int) -> str:
    return _(
        "⚠ USVFS may be inactive: no live-VFS marker (target process hooks / "
        "mappings) found in {log}.\n"
        "If the game does show GAMMA content, ignore this warning (usvfs logs "
        "vary across versions). Otherwise, the game may have started vanilla "
        "despite {enabled} enabled mods — remedies (see {doc}):\n"
        "  1. Make sure you're launching via MO2 (moshortcut), not the exe directly.\n"
        "  2. Switch to Steam's *vanilla* Proton 9.0 or 10.0 (most reliable).\n"
        "  3. Try GE-Proton9-20.\n"
        "  4. Last resort: flat mode without MO2 (`play --flat`), at the cost of "
        "mod flexibility."
    ).format(log=log, enabled=enabled, doc=_COMPAT_DOC)


def _active_message(log: Path, enabled: int) -> str:
    return _(
        "USVFS active: the VFS was injected into the game and serves the mods "
        "({enabled} mods enabled in the G.A.M.M.A profile)."
    ).format(enabled=enabled)


def diagnose_usvfs(mo2: Mo2Paths, *, profile: str = GAMMA_PROFILE) -> UsvfsDiagnosis:
    """Diagnostique l'état de l'USVFS après un lancement du jeu via MO2."""
    enabled = len(enabled_mods(read_modlist(mo2.profile(profile))))
    log = latest_usvfs_log(mo2)

    if log is None:
        return UsvfsDiagnosis(
            active=False,
            checked_log=None,
            enabled_mod_count=enabled,
            message=_no_log_message(enabled),
        )

    text = system.read_text(log) or ""
    if usvfs_active_in(text):
        return UsvfsDiagnosis(
            active=True,
            checked_log=log,
            enabled_mod_count=enabled,
            message=_active_message(log, enabled),
        )

    message = _dead_no_mods_message() if enabled == 0 else _dead_message(log, enabled)
    return UsvfsDiagnosis(active=False, checked_log=log, enabled_mod_count=enabled, message=message)
