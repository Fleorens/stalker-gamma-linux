from pathlib import Path

import pytest

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.environment.distro import (
    Distro,
    DistroFamily,
    detect_distro,
    detect_family,
    parse_os_release,
)

FEDORA_OS_RELEASE = """
NAME="Fedora Linux"
ID=fedora
PRETTY_NAME="Fedora Linux 41 (Workstation Edition)"
"""

DEBIAN_LIKE_OS_RELEASE = """
NAME="Pop!_OS"
ID=pop
ID_LIKE="ubuntu debian"
PRETTY_NAME="Pop!_OS 24.04"
"""


def test_parse_os_release_strips_quotes_and_ignores_comments() -> None:
    content = '# comment\nID=arch\nPRETTY_NAME="Arch Linux"\n\n'
    values = parse_os_release(content)
    assert values == {"ID": "arch", "PRETTY_NAME": "Arch Linux"}


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"ID": "fedora"}, DistroFamily.FEDORA),
        ({"ID": "arch"}, DistroFamily.ARCH),
        ({"ID": "debian"}, DistroFamily.DEBIAN),
        ({"ID": "ubuntu"}, DistroFamily.DEBIAN),
        ({"ID": "steamos"}, DistroFamily.ARCH),
        ({"ID": "pop", "ID_LIKE": "ubuntu debian"}, DistroFamily.DEBIAN),
        ({"ID": "gentoo"}, DistroFamily.UNKNOWN),
        ({}, DistroFamily.UNKNOWN),
    ],
)
def test_detect_family(values: dict[str, str], expected: DistroFamily) -> None:
    assert detect_family(values) is expected


def test_detect_distro_reads_via_system_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "read_text", lambda path: FEDORA_OS_RELEASE)

    distro = detect_distro(Path("/does/not/matter"))

    assert distro == Distro(
        family=DistroFamily.FEDORA, pretty_name="Fedora Linux 41 (Workstation Edition)"
    )


def test_detect_distro_falls_back_to_id_like(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "read_text", lambda path: DEBIAN_LIKE_OS_RELEASE)

    distro = detect_distro()

    assert distro.family is DistroFamily.DEBIAN


def test_detect_distro_prefers_host_os_release_in_flatpak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # En Flatpak, /etc/os-release = runtime GNOME (« unknown ») ; le vrai est
    # sous /run/host/os-release. On doit lire celui-là.
    from stalker_gamma_linux.environment import distro as distro_module

    host_release = distro_module._FLATPAK_HOST_OS_RELEASE
    monkeypatch.setattr(system, "path_exists", lambda p: p == host_release)
    seen: list[Path] = []

    def fake_read(path: Path) -> str:
        seen.append(path)
        return FEDORA_OS_RELEASE

    monkeypatch.setattr(system, "read_text", fake_read)

    distro = detect_distro()

    assert distro.family is DistroFamily.FEDORA
    assert seen == [host_release]


def test_detect_distro_missing_os_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "read_text", lambda path: None)

    distro = detect_distro()

    assert distro.family is DistroFamily.UNKNOWN
    assert distro.pretty_name == "distribution inconnue"
