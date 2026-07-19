from stalker_gamma_linux.environment.commands import INSTALL_COMMANDS
from stalker_gamma_linux.environment.distro import DistroFamily


def test_for_family_returns_distro_specific_command() -> None:
    command = INSTALL_COMMANDS["steam"]
    assert command.for_family(DistroFamily.FEDORA) == "sudo dnf install steam"
    assert command.for_family(DistroFamily.ARCH) == "sudo pacman -S steam"
    assert command.for_family(DistroFamily.DEBIAN) == "sudo apt install steam"


def test_for_family_falls_back_to_flatpak_when_unknown() -> None:
    command = INSTALL_COMMANDS["steam"]
    expected = "flatpak install flathub com.valvesoftware.Steam"
    assert command.for_family(DistroFamily.UNKNOWN) == expected


def test_for_family_returns_none_when_no_command_available() -> None:
    command = INSTALL_COMMANDS["7z"]
    assert command.for_family(DistroFamily.UNKNOWN) is None
