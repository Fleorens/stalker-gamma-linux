"""Vérifications individuelles composant l'EnvironmentReport."""

from __future__ import annotations

import os
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
    # host_* : depuis un Flatpak, on interroge le `flatpak` de l'hôte (le sandbox
    # n'a pas la CLI flatpak ni la vue sur les apps installées côté système).
    if system.host_which("flatpak") is None:
        return False
    result = system.host_run(["flatpak", "info", app_id])
    return result.returncode == 0


def _parse_version(text: str) -> tuple[int, ...] | None:
    match = _VERSION_RE.search(text)
    if match is None:
        return None
    return tuple(int(group) for group in match.groups() if group is not None)


def check_steam(family: DistroFamily) -> Requirement:
    if system.host_which("steam") is not None:
        return Requirement(name="Steam", status=Status.OK, detail="Steam natif détecté")
    if _flatpak_app_installed("com.valvesoftware.Steam"):
        return Requirement(name="Steam", status=Status.OK, detail="Steam (Flatpak) détecté")
    # Facultatif : l'installation et le jeu passent par umu (runtime autonome),
    # Proton-GE est téléchargé depuis GitHub si absent. Steam ne sert qu'au
    # confort (Steam Input, mode Gaming du Deck via « jeu non-Steam ») et comme
    # source alternative de Proton — jamais requis par le pipeline.
    return Requirement(
        name="Steam",
        status=Status.OPTIONAL,
        detail=(
            "absent — facultatif : utile pour Steam Input / mode Gaming (Deck), "
            "pas nécessaire pour installer ni jouer (umu s'en charge)"
        ),
        install_hint=INSTALL_COMMANDS["steam"].for_family(family),
        key="steam",
    )


def check_umu(family: DistroFamily) -> Requirement:
    if system.which("umu-run") is not None:
        return Requirement(name="umu-launcher", status=Status.OK, detail="umu-run détecté")
    return Requirement(
        name="umu-launcher",
        status=Status.MISSING,
        detail="umu-run introuvable dans le PATH",
        install_hint=INSTALL_COMMANDS["umu-launcher"].for_family(family),
        key="umu-launcher",
    )


def check_protontricks(family: DistroFamily) -> Requirement:
    path = system.host_which("protontricks")
    if path is None:
        if _flatpak_app_installed("com.github.Matoking.protontricks"):
            return Requirement(
                name="protontricks",
                status=Status.OK,
                detail="protontricks (Flatpak) détecté",
            )
        # Facultatif : jamais invoqué par le pipeline (les verbs du préfixe
        # passent par umu) — seulement cité comme voie de dépannage manuelle.
        return Requirement(
            name="protontricks",
            status=Status.OPTIONAL,
            detail=(
                "absent — facultatif : outil de dépannage manuel du préfixe, "
                "le pipeline n'en a pas besoin (verbs posés via umu)"
            ),
            install_hint=INSTALL_COMMANDS["protontricks"].for_family(family),
            key="protontricks",
        )

    result = system.host_run(["protontricks", "--version"])
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
            key="protontricks",
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
        key="7z",
    )


def check_libunrar(family: DistroFamily) -> Requirement:
    # Contrairement à steam/vulkaninfo (outils *hôte*), libunrar est chargée par
    # gamma-launcher (paquet `unrar`, ctypes) DANS le contexte d'exécution — le
    # bac à sable Flatpak, pas l'hôte. On vérifie donc localement (`system.run`,
    # pas `host_run`) : sinon on afficherait « OK » (hôte) pendant que l'engine
    # plante faute de libunrar dans le sandbox. UNRAR_LIB_PATH (posé par le
    # Flatpak vers la lib bundlée) prime sur le cache ldconfig.
    lib_path = os.environ.get("UNRAR_LIB_PATH")
    if lib_path and system.path_exists(Path(lib_path)):
        return Requirement(
            name="libunrar", status=Status.OK, detail=f"libunrar fournie ({lib_path})"
        )
    result = system.run(["ldconfig", "-p"])
    if "libunrar" in result.stdout:
        return Requirement(name="libunrar", status=Status.OK, detail="libunrar détectée")
    return Requirement(
        name="libunrar",
        status=Status.MISSING,
        detail="libunrar absente du cache ldconfig",
        install_hint=INSTALL_COMMANDS["libunrar"].for_family(family),
        key="libunrar",
    )


def check_vulkan(family: DistroFamily) -> Requirement:
    tool = system.host_which("vulkaninfo")
    has_device = False
    if tool is not None:
        result = system.host_run(["vulkaninfo", "--summary"])
        has_device = result.returncode == 0 and "deviceName" in result.stdout
    if has_device:
        return Requirement(name="GPU Vulkan", status=Status.OK, detail="device Vulkan détecté")

    # Pas de device Vulkan. En VM (sans passthrough GPU) c'est normal et non
    # actionnable — le GPU ne sert qu'à *jouer*, pas à télécharger/installer —
    # donc on ne l'affiche pas comme un manque bloquant avec un faux remède.
    virt = system.detect_virtualization()
    if virt is not None:
        return Requirement(
            name="GPU Vulkan",
            status=Status.UNAVAILABLE,
            detail=f"non détecté (normal en VM : {virt}) — requis seulement pour jouer",
        )

    detail = (
        "vulkaninfo introuvable dans le PATH"
        if tool is None
        else "aucun device Vulkan détecté"
    )
    return Requirement(
        name="GPU Vulkan",
        status=Status.MISSING,
        detail=detail,
        install_hint=INSTALL_COMMANDS["vulkan"].for_family(family),
        key="vulkan",
    )


def check_gtk_gui(family: DistroFamily) -> Requirement:
    """GTK4 + libadwaita + PyGObject, requis par `stalker-gamma-linux-gui` uniquement.

    N'est jamais ajouté à `build_report` (utilisé par `install`/`update`, qui
    n'en ont pas besoin) : c'est le pré-vol de l'entrée GUI (`gui/launch.py`)
    et une ligne informative de `doctor`, pas un prérequis bloquant de la CLI.
    Import différé de `gi` : `environment.checks` ne doit jamais imposer cette
    dépendance à la CLI.
    """
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk  # noqa: F401
    except (ImportError, ValueError) as error:
        return Requirement(
            name="GTK GUI",
            status=Status.MISSING,
            detail=f"GTK4/libadwaita (PyGObject) indisponibles : {error}",
            install_hint=INSTALL_COMMANDS["gtk-gui"].for_family(family),
            key="gtk-gui",
        )
    return Requirement(
        name="GTK GUI", status=Status.OK, detail="GTK4 + libadwaita détectés (PyGObject)"
    )


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
