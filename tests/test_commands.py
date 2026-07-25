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


def test_for_family_groups_multiple_packages() -> None:
    command = INSTALL_COMMANDS["7z"]
    assert command.for_family(DistroFamily.FEDORA) == "sudo dnf install p7zip p7zip-plugins"


def test_umu_hint_uses_zipapp_not_pipx() -> None:
    # umu-launcher n'est pas sur PyPI : `pipx install umu-launcher` renvoie un 404.
    umu = INSTALL_COMMANDS["umu-launcher"]
    assert umu.for_family(DistroFamily.ARCH) == "sudo pacman -S umu-launcher"
    fedora = umu.for_family(DistroFamily.FEDORA)
    assert fedora is not None
    assert "zipapp" in fedora
    assert "pipx" not in fedora
    assert umu.for_family(DistroFamily.DEBIAN) == fedora


def test_libunrar_note_is_carried_inline() -> None:
    hint = INSTALL_COMMANDS["libunrar"].for_family(DistroFamily.FEDORA)
    assert hint is not None
    assert hint.startswith("sudo dnf install libunrar")
    assert "RPM Fusion" in hint
