"""Détection et sélection des builds Proton-GE installés (Steam, umu)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from stalker_gamma_linux.prefix import download
from stalker_gamma_linux.prefix.download import ProgressCallback

_GE_NAME_RE = re.compile(r"^GE-Proton(\d+)-(\d+)$")

# Proton Experimental de Steam : alternative acceptée quand aucun GE n'est
# installé (décision utilisateur 2026-07-19). Vit dans steamapps/common, pas
# dans compatibilitytools.d.
PROTON_EXPERIMENTAL = "Proton - Experimental"


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


def default_steam_common_dirs() -> tuple[Path, ...]:
    """Emplacements `steamapps/common` connus, où vit « Proton - Experimental »."""
    home = Path.home()
    return (
        home / ".local" / "share" / "Steam" / "steamapps" / "common",
        home / ".steam" / "root" / "steamapps" / "common",
        home / ".steam" / "steam" / "steamapps" / "common",
        home / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam"
        / "steamapps" / "common",
    )


def find_proton_builds(
    search_dirs: Sequence[Path] | None = None,
    steam_common_dirs: Sequence[Path] | None = None,
) -> tuple[ProtonBuild, ...]:
    """Recense les builds Proton installés (répertoires contenant un exécutable `proton`).

    Un même nom présent dans plusieurs répertoires n'est retenu qu'une fois
    (première occurrence, dans l'ordre de `search_dirs`). S'y ajoute le
    « Proton - Experimental » de Steam s'il est présent dans un
    `steamapps/common`. Fournir `search_dirs` sans `steam_common_dirs`
    restreint la recherche à ces seuls répertoires (déterminisme des tests) ;
    tout à None = emplacements par défaut de la machine.
    """
    dirs = search_dirs if search_dirs is not None else default_search_dirs()
    if steam_common_dirs is not None:
        commons: Sequence[Path] = steam_common_dirs
    elif search_dirs is None:
        commons = default_steam_common_dirs()
    else:
        commons = ()

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
    for directory in commons:
        entry = directory / PROTON_EXPERIMENTAL
        if PROTON_EXPERIMENTAL not in builds and (entry / "proton").is_file():
            builds[PROTON_EXPERIMENTAL] = ProtonBuild(
                name=PROTON_EXPERIMENTAL, path=entry, version=None
            )
    return tuple(builds.values())


def select_proton_build(builds: Sequence[ProtonBuild]) -> ProtonBuild | None:
    """Choisit le build à utiliser, par ordre de préférence (décision utilisateur) :
    le GE versionné le plus récent, sinon Proton Experimental, sinon le premier autre."""
    versioned = [build for build in builds if build.version is not None]
    if versioned:
        return max(versioned, key=lambda build: build.version or (0, 0))
    for build in builds:
        if build.name == PROTON_EXPERIMENTAL:
            return build
    return builds[0] if builds else None


def ensure_proton(
    search_dirs: Sequence[Path] | None = None,
    *,
    on_progress: ProgressCallback | None = None,
) -> ProtonBuild:
    """Retourne un build Proton utilisable, en téléchargeant la dernière release
    GE publiée si aucun n'est installé (ni GE, ni Proton Experimental). Idempotent."""
    selected = select_proton_build(find_proton_builds(search_dirs))
    if selected is not None:
        return selected
    # Télécharger dans le premier répertoire de recherche : la relance suivante
    # doit retrouver ce qu'on vient d'installer.
    install_dir = search_dirs[0] if search_dirs else None
    path = download.download_proton_ge(install_dir=install_dir, on_progress=on_progress)
    return ProtonBuild(name=path.name, path=path, version=parse_ge_version(path.name))
