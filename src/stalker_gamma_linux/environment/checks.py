"""Vérifications individuelles composant l'EnvironmentReport."""

from __future__ import annotations

import re
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.environment.commands import INSTALL_COMMANDS
from stalker_gamma_linux.environment.distro import DistroFamily
from stalker_gamma_linux.environment.models import Requirement, Status

GB = 1024**3
REQUIRED_DOWNLOAD_GB = 27
REQUIRED_INSTALL_GB = 76
REQUIRED_TOTAL_GB = REQUIRED_DOWNLOAD_GB + REQUIRED_INSTALL_GB

# ⚠ À VALIDER : seuil indicatif (support Flatpak/shortcuts non-Steam robuste).
MIN_PROTONTRICKS_VERSION = (1, 10)

_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def _flatpak_app_installed(app_id: str) -> bool:
    if system.which("flatpak") is None:
        return False
    result = system.run(["flatpak", "info", app_id])
    return result.returncode == 0


def _parse_version(text: str) -> tuple[int, ...] | None:
    match = _VERSION_RE.search(text)
    if match is None:
        return None
    return tuple(int(group) for group in match.groups() if group is not None)


def check_steam(family: DistroFamily) -> Requirement:
    if system.which("steam") is not None:
        return Requirement(name="Steam", status=Status.OK, detail="Steam natif détecté")
    if _flatpak_app_installed("com.valvesoftware.Steam"):
        return Requirement(name="Steam", status=Status.OK, detail="Steam (Flatpak) détecté")
    return Requirement(
        name="Steam",
        status=Status.MISSING,
        detail="Steam introuvable (ni natif, ni Flatpak)",
        install_hint=INSTALL_COMMANDS["steam"].for_family(family),
    )


def check_umu(family: DistroFamily) -> Requirement:
    if system.which("umu-run") is not None:
        return Requirement(name="umu-launcher", status=Status.OK, detail="umu-run détecté")
    return Requirement(
        name="umu-launcher",
        status=Status.MISSING,
        detail="umu-run introuvable dans le PATH",
        install_hint=INSTALL_COMMANDS["umu-launcher"].for_family(family),
    )


def check_protontricks(family: DistroFamily) -> Requirement:
    path = system.which("protontricks")
    if path is None:
        if _flatpak_app_installed("com.github.Matoking.protontricks"):
            return Requirement(
                name="protontricks",
                status=Status.OK,
                detail="protontricks (Flatpak) détecté",
            )
        return Requirement(
            name="protontricks",
            status=Status.MISSING,
            detail="protontricks introuvable (ni natif, ni Flatpak)",
            install_hint=INSTALL_COMMANDS["protontricks"].for_family(family),
        )

    result = system.run(["protontricks", "--version"])
    version = _parse_version(result.stdout or result.stderr)
    if version is None:
        return Requirement(
            name="protontricks", status=Status.OK, detail="détecté (version illisible)"
        )
    if version < MIN_PROTONTRICKS_VERSION:
        version_str = ".".join(str(part) for part in version)
        min_str = ".".join(str(part) for part in MIN_PROTONTRICKS_VERSION)
        return Requirement(
            name="protontricks",
            status=Status.OUTDATED,
            detail=f"version {version_str} détectée, {min_str}+ requise",
            install_hint=INSTALL_COMMANDS["protontricks"].for_family(family),
        )
    return Requirement(
        name="protontricks",
        status=Status.OK,
        detail=f"version {'.'.join(str(part) for part in version)} détectée",
    )


def check_7z(family: DistroFamily) -> Requirement:
    if system.which("7z") is not None or system.which("7zz") is not None:
        return Requirement(name="7z", status=Status.OK, detail="7z détecté")
    return Requirement(
        name="7z",
        status=Status.MISSING,
        detail="ni 7z ni 7zz trouvés dans le PATH",
        install_hint=INSTALL_COMMANDS["7z"].for_family(family),
    )


def check_libunrar(family: DistroFamily) -> Requirement:
    result = system.run(["ldconfig", "-p"])
    if "libunrar" in result.stdout:
        return Requirement(name="libunrar", status=Status.OK, detail="libunrar détectée")
    return Requirement(
        name="libunrar",
        status=Status.MISSING,
        detail="libunrar absente du cache ldconfig",
        install_hint=INSTALL_COMMANDS["libunrar"].for_family(family),
    )


def check_vulkan(family: DistroFamily) -> Requirement:
    if system.which("vulkaninfo") is None:
        return Requirement(
            name="GPU Vulkan",
            status=Status.MISSING,
            detail="vulkaninfo introuvable dans le PATH",
            install_hint=INSTALL_COMMANDS["vulkan"].for_family(family),
        )
    result = system.run(["vulkaninfo", "--summary"])
    if result.returncode != 0 or "deviceName" not in result.stdout:
        return Requirement(
            name="GPU Vulkan",
            status=Status.MISSING,
            detail="aucun device Vulkan détecté",
            install_hint=INSTALL_COMMANDS["vulkan"].for_family(family),
        )
    return Requirement(name="GPU Vulkan", status=Status.OK, detail="device Vulkan détecté")


def _nearest_existing_ancestor(path: Path) -> Path:
    current = path
    while not system.path_exists(current):
        parent = current.parent
        if parent == current:
            return current
        current = parent
    return current


def check_disk_space(target: Path) -> Requirement:
    probe_path = _nearest_existing_ancestor(target)
    usage = system.disk_usage(probe_path)
    free_gb = usage.free / GB
    detail = (
        f"{free_gb:.1f} Go libres sur {probe_path} "
        f"(requis ≈ {REQUIRED_TOTAL_GB} Go : {REQUIRED_DOWNLOAD_GB} téléchargement "
        f"+ {REQUIRED_INSTALL_GB} installation)"
    )
    if free_gb >= REQUIRED_TOTAL_GB:
        return Requirement(name="Espace disque", status=Status.OK, detail=detail)
    return Requirement(
        name="Espace disque",
        status=Status.MISSING,
        detail=detail,
        install_hint="Libérer de l'espace ou choisir une autre cible (--target)",
    )
