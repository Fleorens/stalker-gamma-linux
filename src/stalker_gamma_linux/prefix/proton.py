"""Détection et sélection des builds Proton-GE installés (Steam, umu)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.prefix import download
from stalker_gamma_linux.prefix.download import ProgressCallback

_GE_NAME_RE = re.compile(r"^GE-Proton(\d+)-(\d+)$")


@dataclass(frozen=True, slots=True)
class ProtonBuild:
    name: str
    path: Path
    version: tuple[int, int] | None  # None = build non GE (ex. UMU-Proton, forks)


def parse_ge_version(name: str) -> tuple[int, int] | None:
    match = _GE_NAME_RE.match(name)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)))


def default_search_dirs() -> tuple[Path, ...]:
    """Emplacements `compatibilitytools.d` connus : Steam natif, Flatpak — et umu,
    qui installe ses builds dans celui du Steam par défaut (première entrée)."""
    home = Path.home()
    return (
        home / ".local" / "share" / "Steam" / "compatibilitytools.d",
        home / ".steam" / "root" / "compatibilitytools.d",
        home / ".steam" / "steam" / "compatibilitytools.d",
        home / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
        / "compatibilitytools.d",
    )


def find_proton_builds(search_dirs: Sequence[Path] | None = None) -> tuple[ProtonBuild, ...]:
    """Recense les builds Proton installés (répertoires contenant un exécutable `proton`).

    Un même nom présent dans plusieurs répertoires n'est retenu qu'une fois
    (première occurrence, dans l'ordre de `search_dirs`).
    """
    dirs = search_dirs if search_dirs is not None else default_search_dirs()
    builds: dict[str, ProtonBuild] = {}
    for directory in dirs:
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if entry.name in builds or not (entry / "proton").is_file():
                continue
            builds[entry.name] = ProtonBuild(
                name=entry.name, path=entry, version=parse_ge_version(entry.name)
            )
    return tuple(builds.values())


def select_proton_build(builds: Sequence[ProtonBuild]) -> ProtonBuild | None:
    """Choisit le build à utiliser : le GE versionné le plus récent, sinon le premier autre."""
    versioned = [build for build in builds if build.version is not None]
    if versioned:
        return max(versioned, key=lambda build: build.version or (0, 0))
    return builds[0] if builds else None


def ensure_proton(
    search_dirs: Sequence[Path] | None = None,
    *,
    on_progress: ProgressCallback | None = None,
) -> ProtonBuild:
    """Retourne un build Proton utilisable, en téléchargeant la release GE
    recommandée si aucun n'est installé. Idempotent."""
    selected = select_proton_build(find_proton_builds(search_dirs))
    if selected is not None:
        return selected
    # Télécharger dans le premier répertoire de recherche : la relance suivante
    # doit retrouver ce qu'on vient d'installer.
    install_dir = search_dirs[0] if search_dirs else None
    path = download.download_proton_ge(install_dir=install_dir, on_progress=on_progress)
    return ProtonBuild(name=path.name, path=path, version=parse_ge_version(path.name))
