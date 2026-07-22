"""Traduction des chemins Linux en chemins Windows vus depuis le préfixe Wine.

Wine expose la racine du système de fichiers Linux (`/`) via le lecteur `Z:`.
MO2 tourne comme une application Windows dans le préfixe : le `gamePath` qu'on
écrit dans son `.ini`, comme les arguments qu'on lui passe, doivent être des
chemins Windows (`Z:\\home\\...`), pas des chemins Linux.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

# Lettre de lecteur sous laquelle Wine monte la racine Linux `/`.
WINE_ROOT_DRIVE = "Z:"


def to_windows_path(linux_path: Path | str) -> str:
    r"""Convertit un chemin Linux **absolu** en chemin Windows vu du préfixe.

    `/home/x/Games/anomaly` → `Z:\home\x\Games\anomaly`. Le chemin doit être
    absolu (les chemins relatifs n'ont pas de sens une fois traversée la
    frontière Linux→Windows) : sinon `ValueError`. Le chemin est normalisé
    (`..`, `.`, `//` réduits) sans toucher au disque — on ne résout pas les
    liens symboliques, pour ne pas dépendre de l'existence de la cible.
    """
    posix = PurePosixPath(linux_path)
    if not posix.is_absolute():
        raise ValueError(f"chemin Linux absolu attendu, reçu : {linux_path!r}")
    # PurePosixPath réduit déjà `.` et `//` ; on résout `..` textuellement.
    parts: list[str] = []
    for part in posix.parts[1:]:  # [0] == "/"
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return WINE_ROOT_DRIVE + "\\" + "\\".join(parts)
