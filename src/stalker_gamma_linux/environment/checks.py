"""Vérifications individuelles composant l'EnvironmentReport."""

from __future__ import annotations

import re
from pathlib import Path

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.environment.commands import INSTALL_COMMANDS
from stalker_gamma_linux.environment.distro import DistroFamily
from stalker_gamma_linux.environment.models import Requirement, Status
from stalker_gamma_linux.i18n import _

GB = 1024**3
REQUIRED_DOWNLOAD_GB = 27
REQUIRED_INSTALL_GB = 76
REQUIRED_TOTAL_GB = REQUIRED_DOWNLOAD_GB + REQUIRED_INSTALL_GB

# ⚠ À VALIDER : seuil indicatif (support Flatpak/shortcuts non-Steam robuste).
MIN_PROTONTRICKS_VERSION = (1, 10)

_VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def _flatpak_app_installed(app_id: str) -> bool:
    # L'utilisateur peut avoir Steam/protontricks installés en Flatpak plutôt
    # qu'en paquet natif — repli de détection indépendant de notre packaging.
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
        return Requirement(name="Steam", status=Status.OK, detail=_("Native Steam detected"))
    if _flatpak_app_installed("com.valvesoftware.Steam"):
        return Requirement(name="Steam", status=Status.OK, detail=_("Steam (Flatpak) detected"))
    # Facultatif : l'installation et le jeu passent par umu (runtime autonome),
    # Proton-GE est téléchargé depuis GitHub si absent. Steam ne sert qu'au
    # confort (Steam Input, mode Gaming du Deck via « jeu non-Steam ») et comme
    # source alternative de Proton — jamais requis par le pipeline.
    return Requirement(
        name="Steam",
        status=Status.OPTIONAL,
        detail=_(
            "absent — optional: useful for Steam Input / Gaming Mode (Deck), "
            "not needed to install or play (umu handles it)"
        ),
        install_hint=INSTALL_COMMANDS["steam"].for_family(family),
        key="steam",
    )


def check_umu(family: DistroFamily) -> Requirement:
    if system.which("umu-run") is not None:
        return Requirement(name="umu-launcher", status=Status.OK, detail=_("umu-run detected"))
    return Requirement(
        name="umu-launcher",
        status=Status.MISSING,
        detail=_("umu-run not found in PATH"),
        install_hint=INSTALL_COMMANDS["umu-launcher"].for_family(family),
        key="umu-launcher",
    )


def check_protontricks(family: DistroFamily) -> Requirement:
    path = system.which("protontricks")
    if path is None:
        if _flatpak_app_installed("com.github.Matoking.protontricks"):
            return Requirement(
                name="protontricks",
                status=Status.OK,
                detail=_("protontricks (Flatpak) detected"),
            )
        # Facultatif : jamais invoqué par le pipeline (les verbs du préfixe
        # passent par umu) — seulement cité comme voie de dépannage manuelle.
        return Requirement(
            name="protontricks",
            status=Status.OPTIONAL,
            detail=_(
                "absent — optional: manual prefix troubleshooting tool, "
                "the pipeline doesn't need it (verbs are applied via umu)"
            ),
            install_hint=INSTALL_COMMANDS["protontricks"].for_family(family),
            key="protontricks",
        )

    result = system.run(["protontricks", "--version"])
    version = _parse_version(result.stdout or result.stderr)
    if version is None:
        return Requirement(
            name="protontricks", status=Status.OK, detail=_("detected (version unreadable)")
        )
    if version < MIN_PROTONTRICKS_VERSION:
        version_str = ".".join(str(part) for part in version)
        min_str = ".".join(str(part) for part in MIN_PROTONTRICKS_VERSION)
        return Requirement(
            name="protontricks",
            status=Status.OUTDATED,
            detail=_("version {version} detected, {minimum}+ required").format(
                version=version_str, minimum=min_str
            ),
            install_hint=INSTALL_COMMANDS["protontricks"].for_family(family),
            key="protontricks",
        )
    return Requirement(
        name="protontricks",
        status=Status.OK,
        detail=_("version {version} detected").format(
            version=".".join(str(part) for part in version)
        ),
    )


def check_7z(family: DistroFamily) -> Requirement:
    if system.which("7z") is not None or system.which("7zz") is not None:
        return Requirement(name="7z", status=Status.OK, detail=_("7z detected"))
    return Requirement(
        name="7z",
        status=Status.MISSING,
        detail=_("neither 7z nor 7zz found in PATH"),
        install_hint=INSTALL_COMMANDS["7z"].for_family(family),
        key="7z",
    )


def check_libunrar(family: DistroFamily) -> Requirement:
    result = system.run(["ldconfig", "-p"])
    if "libunrar" in result.stdout:
        return Requirement(name="libunrar", status=Status.OK, detail=_("libunrar detected"))
    return Requirement(
        name="libunrar",
        status=Status.MISSING,
        detail=_("libunrar absent from the ldconfig cache"),
        install_hint=INSTALL_COMMANDS["libunrar"].for_family(family),
        key="libunrar",
    )


def check_vulkan(family: DistroFamily) -> Requirement:
    tool = system.which("vulkaninfo")
    has_device = False
    if tool is not None:
        result = system.run(["vulkaninfo", "--summary"])
        has_device = result.returncode == 0 and "deviceName" in result.stdout
    if has_device:
        return Requirement(
            name=_("Vulkan GPU"), status=Status.OK, detail=_("Vulkan device detected")
        )

    # Pas de device Vulkan. En VM (sans passthrough GPU) c'est normal et non
    # actionnable — le GPU ne sert qu'à *jouer*, pas à télécharger/installer —
    # donc on ne l'affiche pas comme un manque bloquant avec un faux remède.
    virt = system.detect_virtualization()
    if virt is not None:
        return Requirement(
            name=_("Vulkan GPU"),
            status=Status.UNAVAILABLE,
            detail=_("not detected (normal in a VM: {virt}) — only needed to play").format(
                virt=virt
            ),
        )

    detail = (
        _("vulkaninfo not found in PATH")
        if tool is None
        else _("no Vulkan device detected")
    )
    return Requirement(
        name=_("Vulkan GPU"),
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
            detail=_("GTK4/libadwaita (PyGObject) unavailable: {error}").format(error=error),
            install_hint=INSTALL_COMMANDS["gtk-gui"].for_family(family),
            key="gtk-gui",
        )
    return Requirement(
        name="GTK GUI", status=Status.OK, detail=_("GTK4 + libadwaita detected (PyGObject)")
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
    detail = _(
        "{free:.1f} GB free on {path} (needs ≈ {total} GB: {download} download "
        "+ {install} install)"
    ).format(
        free=free_gb,
        path=probe_path,
        total=REQUIRED_TOTAL_GB,
        download=REQUIRED_DOWNLOAD_GB,
        install=REQUIRED_INSTALL_GB,
    )
    if free_gb >= REQUIRED_TOTAL_GB:
        return Requirement(name=_("Disk space"), status=Status.OK, detail=detail)
    return Requirement(
        name=_("Disk space"),
        status=Status.MISSING,
        detail=detail,
        install_hint=_("Free up space or choose another target (--target)"),
    )
