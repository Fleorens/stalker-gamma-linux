"""Remèdes d'installation par prérequis : paquets système + méthodes hors-paquet.

Les remèdes sont décrits en données structurées (nom(s) de paquet par famille de
distribution) plutôt qu'en commandes déjà assemblées : ça permet à
`environment.plan` de **fusionner** les prérequis manquants en une seule commande
`sudo dnf install a b c` à copier-coller, au lieu d'éparpiller une ligne par outil.
`for_family` reconstruit la commande d'un seul prérequis (rétro-compatible).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from stalker_gamma_linux.environment.distro import DistroFamily

# Préfixe d'installation du gestionnaire de paquets natif, par famille.
PACKAGE_MANAGER: Mapping[DistroFamily, str] = {
    DistroFamily.FEDORA: "sudo dnf install",
    DistroFamily.ARCH: "sudo pacman -S",
    DistroFamily.DEBIAN: "sudo apt install",
}
FLATPAK_INSTALL = "flatpak install flathub"

# umu-launcher n'a PAS de paquet PyPI (`pipx install` 404) ni de paquet dans
# les dépôts Fedora/Debian — seul Arch l'empaquette. On l'installe donc
# NOUS-MÊMES (zipapp officiel ~420 Kio → ~/.local/bin, sans sudo) :
# `prefix.umu.install_umu`, exposé en CLI `install-umu` et en un clic dans la
# GUI. Ce hint est la commande de repli copiable, pas une procédure manuelle.
_UMU_ZIPAPP_HINT = "stalker-gamma-linux install-umu   # automatique, sans sudo (zipapp officiel)"


@dataclass(frozen=True, slots=True)
class InstallCommand:
    # Paquet(s) natif(s) par famille : regroupables en une seule commande.
    packages: Mapping[DistroFamily, tuple[str, ...]] = field(default_factory=dict)
    # Méthode hors gestionnaire de paquets (ex. zipapp umu), par famille.
    manual: Mapping[DistroFamily, str] = field(default_factory=dict)
    # Application Flatpak de repli quand aucun paquet natif n'est connu.
    flatpak_app: str | None = None
    # Mise en garde attachée aux paquets (ex. dépôt tiers requis).
    note: str | None = None

    def for_family(self, family: DistroFamily) -> str | None:
        """Commande d'installation d'un seul prérequis : paquet > manuel > flatpak."""
        packages = self.packages.get(family)
        if packages:
            command = f"{PACKAGE_MANAGER[family]} {' '.join(packages)}"
            return f"{command}  # {self.note}" if self.note else command
        manual = self.manual.get(family)
        if manual is not None:
            return manual
        if self.flatpak_app is not None:
            return f"{FLATPAK_INSTALL} {self.flatpak_app}"
        return None


INSTALL_COMMANDS: Mapping[str, InstallCommand] = {
    "steam": InstallCommand(
        packages={
            DistroFamily.FEDORA: ("steam",),
            DistroFamily.ARCH: ("steam",),
            DistroFamily.DEBIAN: ("steam",),
        },
        flatpak_app="com.valvesoftware.Steam",
    ),
    "umu-launcher": InstallCommand(
        packages={DistroFamily.ARCH: ("umu-launcher",)},
        manual={
            DistroFamily.FEDORA: _UMU_ZIPAPP_HINT,
            DistroFamily.DEBIAN: _UMU_ZIPAPP_HINT,
        },
    ),
    "protontricks": InstallCommand(
        packages={
            DistroFamily.FEDORA: ("protontricks",),
            DistroFamily.ARCH: ("protontricks",),
            DistroFamily.DEBIAN: ("protontricks",),
        },
        flatpak_app="com.github.Matoking.protontricks",
    ),
    "7z": InstallCommand(
        packages={
            DistroFamily.FEDORA: ("p7zip", "p7zip-plugins"),
            DistroFamily.ARCH: ("p7zip",),
            DistroFamily.DEBIAN: ("p7zip-full",),
        },
    ),
    "libunrar": InstallCommand(
        # Fedora : le paquet est `libunrar` (la bibliothèque .so chargée en
        # ctypes par gamma-launcher) — PAS `unrar`, qui ne contient que le
        # binaire CLI et laisse le diagnostic « absent » (bug réel constaté en
        # VM le 2026-07-25). Sur Arch, libunrar n'est que dans l'AUR (pas dans
        # les dépôts pacman) : étape manuelle `yay` plutôt qu'un faux `pacman -S`.
        packages={
            DistroFamily.FEDORA: ("libunrar",),
            DistroFamily.DEBIAN: ("libunrar5",),
        },
        manual={DistroFamily.ARCH: "yay -S libunrar  # AUR"},
        note=(
            "Fedora : dépôt RPM Fusion nonfree requis — l'activer d'abord si "
            "besoin : sudo dnf install https://mirrors.rpmfusion.org/nonfree/"
            "fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm"
        ),
    ),
    "vulkan": InstallCommand(
        packages={
            DistroFamily.FEDORA: ("vulkan-tools", "mesa-vulkan-drivers"),
            DistroFamily.ARCH: ("vulkan-tools", "vulkan-icd-loader"),
            DistroFamily.DEBIAN: ("vulkan-tools", "mesa-vulkan-drivers"),
        },
    ),
    "gtk-gui": InstallCommand(
        packages={
            DistroFamily.FEDORA: ("gtk4", "libadwaita", "python3-gobject"),
            DistroFamily.ARCH: ("gtk4", "libadwaita", "python-gobject"),
            DistroFamily.DEBIAN: ("gir1.2-gtk-4.0", "gir1.2-adw-1", "python3-gi"),
        },
    ),
}
