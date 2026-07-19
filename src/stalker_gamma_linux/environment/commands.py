"""Suggestions de commandes d'installation, par distribution et par outil."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from stalker_gamma_linux.environment.distro import DistroFamily


@dataclass(frozen=True, slots=True)
class InstallCommand:
    by_family: Mapping[DistroFamily, str] = field(default_factory=dict)
    flatpak: str | None = None

    def for_family(self, family: DistroFamily) -> str | None:
        command = self.by_family.get(family)
        if command is not None:
            return command
        return self.flatpak


INSTALL_COMMANDS: Mapping[str, InstallCommand] = {
    "steam": InstallCommand(
        by_family={
            DistroFamily.FEDORA: "sudo dnf install steam",
            DistroFamily.ARCH: "sudo pacman -S steam",
            DistroFamily.DEBIAN: "sudo apt install steam",
        },
        flatpak="flatpak install flathub com.valvesoftware.Steam",
    ),
    "umu-launcher": InstallCommand(
        by_family={
            DistroFamily.ARCH: "sudo pacman -S umu-launcher",
            DistroFamily.FEDORA: "pipx install umu-launcher",
            DistroFamily.DEBIAN: "pipx install umu-launcher",
        },
    ),
    "protontricks": InstallCommand(
        by_family={
            DistroFamily.FEDORA: "sudo dnf install protontricks",
            DistroFamily.ARCH: "sudo pacman -S protontricks",
            DistroFamily.DEBIAN: "sudo apt install protontricks",
        },
        flatpak="flatpak install flathub com.github.Matoking.protontricks",
    ),
    "7z": InstallCommand(
        by_family={
            DistroFamily.FEDORA: "sudo dnf install p7zip p7zip-plugins",
            DistroFamily.ARCH: "sudo pacman -S p7zip",
            DistroFamily.DEBIAN: "sudo apt install p7zip-full",
        },
    ),
    "libunrar": InstallCommand(
        by_family={
            DistroFamily.FEDORA: "sudo dnf install unrar  # RPM Fusion",
            DistroFamily.ARCH: "yay -S libunrar  # AUR",
            DistroFamily.DEBIAN: "sudo apt install libunrar5",
        },
    ),
    "vulkan": InstallCommand(
        by_family={
            DistroFamily.FEDORA: "sudo dnf install vulkan-tools mesa-vulkan-drivers",
            DistroFamily.ARCH: "sudo pacman -S vulkan-tools vulkan-icd-loader",
            DistroFamily.DEBIAN: "sudo apt install vulkan-tools mesa-vulkan-drivers",
        },
    ),
}
