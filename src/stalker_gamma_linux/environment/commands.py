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
from stalker_gamma_linux.i18n import _

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
_UMU_ZIPAPP_HINT = _("stalker-gamma-linux install-umu   # automatic, no sudo (official zipapp)")


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
        # ⚠ Ces noms périment. Vérifiés le 2026-08-16 dans les dépôts réels
        # (conteneurs fedora:44, archlinux:latest, debian:13) — le job
        # `package-names` de la CI le revérifie à chaque push, parce que
        # « paquet renommé en amont » est invisible d'ici et casse le seul
        # remède qu'on donne à l'utilisateur.
        #
        # p7zip est mort chez Fedora et Arch, remplacé par `7zip` (upstream
        # 7-Zip officiel) : `dnf install p7zip p7zip-plugins` et
        # `pacman -S p7zip` échouaient tous les deux sur « no match ».
        # Debian/Ubuntu gardent `p7zip-full`, toujours présent en 13/24.04.
        packages={
            DistroFamily.FEDORA: ("7zip",),
            DistroFamily.ARCH: ("7zip",),
            DistroFamily.DEBIAN: ("p7zip-full",),
        },
    ),
    "libunrar": InstallCommand(
        # Le paquet doit fournir la bibliothèque .so (chargée en ctypes par
        # gamma-launcher), pas le binaire CLI `unrar` — les deux sont des
        # paquets distincts partout (bug réel constaté en VM le 2026-07-25 :
        # `dnf install unrar` laissait le diagnostic « absent »).
        # Noms revérifiés le 2026-08-16 dans les dépôts réels :
        # - Fedora : `libunrar` (RPM Fusion nonfree) — confirmé, c'est bien lui
        #   qui fournit /lib64/libunrar.so sur la machine de dev ;
        # - Arch : `libunrar` dans extra (l'AUR n'est plus requis) ;
        # - Debian/Ubuntu : `libunrar5`. La valeur précédente (`libunrar5t64`,
        #   posée en supposant la transition time64) **n'existe pas sur
        #   Debian 13** — la commande y échouait. Ubuntu 24.04 fournit les deux
        #   noms, donc `libunrar5` est le seul qui marche partout.
        packages={
            DistroFamily.FEDORA: ("libunrar",),
            DistroFamily.DEBIAN: ("libunrar5",),
            DistroFamily.ARCH: ("libunrar",),
        },
        note=_(
            "Fedora: RPM Fusion nonfree repo required — enable it first if "
            "needed: sudo dnf install https://mirrors.rpmfusion.org/nonfree/"
            "fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm · "
            "Debian/Ubuntu: non-free/multiverse component required"
        ),
    ),
    "vulkan": InstallCommand(
        packages={
            DistroFamily.FEDORA: ("vulkan-tools", "mesa-vulkan-drivers"),
            DistroFamily.ARCH: ("vulkan-tools", "vulkan-icd-loader"),
            DistroFamily.DEBIAN: ("vulkan-tools", "mesa-vulkan-drivers"),
        },
    ),
    "gamemode": InstallCommand(
        # Arch : `lib32-gamemode` fournit la `libgamemodeauto.so.0` 32 bits que
        # préchargent les processus wine 32 bits — sans elle, l'éditeur de liens
        # se contente d'un avertissement (le jeu tourne, GameMode reste actif via
        # le processus parent 64 bits). Fedora et Debian empaquettent les deux
        # architectures dans le même nom (`gamemode` / multiarch), rien à ajouter.
        packages={
            DistroFamily.FEDORA: ("gamemode",),
            DistroFamily.ARCH: ("gamemode", "lib32-gamemode"),
            DistroFamily.DEBIAN: ("gamemode",),
        },
    ),
    "mangohud": InstallCommand(
        # Arch : `lib32-mangohud` (multilib) fournit la couche 32 bits, comme
        # `lib32-gamemode` plus haut. Fedora et Debian empaquettent la variante
        # 32 bits sous le même nom mais une autre architecture — d'où la note
        # plutôt qu'un second nom de paquet, qui exigerait
        # `dpkg --add-architecture i386` pour être seulement *interrogeable*.
        packages={
            DistroFamily.FEDORA: ("mangohud",),
            DistroFamily.ARCH: ("mangohud", "lib32-mangohud"),
            DistroFamily.DEBIAN: ("mangohud",),
        },
        note=_(
            "the Vulkan layer must match the ABI of the process that renders: "
            "add the 32-bit variant if the overlay stays invisible "
            "(Fedora: mangohud.i686 · Debian/Ubuntu: mangohud:i386 after "
            "`sudo dpkg --add-architecture i386`)"
        ),
    ),
    "gamescope": InstallCommand(
        packages={
            DistroFamily.FEDORA: ("gamescope",),
            DistroFamily.ARCH: ("gamescope",),
            DistroFamily.DEBIAN: ("gamescope",),
        },
    ),
    "vkbasalt": InstallCommand(
        # ⚠ Fedora empaquette sous le nom amont, avec sa majuscule : `vkBasalt`,
        # pas `vkbasalt`. Arch ne l'empaquette **pas** officiellement (ni extra
        # ni multilib) — seulement l'AUR, d'où le remède manuel : annoncer
        # `pacman -S vkbasalt` enverrait l'utilisateur sur un « target not found ».
        packages={
            DistroFamily.FEDORA: ("vkBasalt",),
            DistroFamily.DEBIAN: ("vkbasalt",),
        },
        manual={
            DistroFamily.ARCH: _("yay -S vkbasalt lib32-vkbasalt   # AUR (no official package)")
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
