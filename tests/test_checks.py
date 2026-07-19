import subprocess
from pathlib import Path

import pytest

from stalker_gamma_linux.environment import checks, system
from stalker_gamma_linux.environment.distro import DistroFamily
from stalker_gamma_linux.environment.models import Status

FAMILY = DistroFamily.FEDORA


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_check_steam_native(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/steam" if cmd == "steam" else None)

    requirement = checks.check_steam(FAMILY)

    assert requirement.status is Status.OK
    assert "natif" in requirement.detail


def test_check_steam_flatpak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        system, "which", lambda cmd: "/usr/bin/flatpak" if cmd == "flatpak" else None
    )
    monkeypatch.setattr(system, "run", lambda cmd: _completed(returncode=0))

    requirement = checks.check_steam(FAMILY)

    assert requirement.status is Status.OK
    assert "Flatpak" in requirement.detail


def test_check_steam_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: None)

    requirement = checks.check_steam(FAMILY)

    assert requirement.status is Status.MISSING
    assert requirement.install_hint == "sudo dnf install steam"


def test_check_umu_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        system, "which", lambda cmd: "/usr/bin/umu-run" if cmd == "umu-run" else None
    )

    requirement = checks.check_umu(FAMILY)

    assert requirement.status is Status.OK


def test_check_umu_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: None)

    requirement = checks.check_umu(FAMILY)

    assert requirement.status is Status.MISSING
    assert requirement.install_hint is not None


def test_check_protontricks_recent_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/protontricks")
    monkeypatch.setattr(
        system, "run", lambda cmd: _completed(stdout="protontricks, version 1.12.0")
    )

    requirement = checks.check_protontricks(FAMILY)

    assert requirement.status is Status.OK
    assert "1.12.0" in requirement.detail


def test_check_protontricks_outdated_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/protontricks")
    monkeypatch.setattr(system, "run", lambda cmd: _completed(stdout="protontricks, version 1.9.0"))

    requirement = checks.check_protontricks(FAMILY)

    assert requirement.status is Status.OUTDATED
    assert requirement.install_hint is not None


def test_check_protontricks_missing_falls_back_to_flatpak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        system, "which", lambda cmd: "/usr/bin/flatpak" if cmd == "flatpak" else None
    )
    monkeypatch.setattr(system, "run", lambda cmd: _completed(returncode=0))

    requirement = checks.check_protontricks(FAMILY)

    assert requirement.status is Status.OK
    assert "Flatpak" in requirement.detail


def test_check_protontricks_entirely_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: None)

    requirement = checks.check_protontricks(FAMILY)

    assert requirement.status is Status.MISSING


def test_check_7z_present_as_7zz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/7zz" if cmd == "7zz" else None)

    requirement = checks.check_7z(FAMILY)

    assert requirement.status is Status.OK


def test_check_7z_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: None)

    requirement = checks.check_7z(FAMILY)

    assert requirement.status is Status.MISSING


def test_check_libunrar_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        system, "run", lambda cmd: _completed(stdout="libunrar.so.5 => /usr/lib/libunrar.so.5")
    )

    requirement = checks.check_libunrar(FAMILY)

    assert requirement.status is Status.OK


def test_check_libunrar_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        system, "run", lambda cmd: _completed(stdout="libc.so.6 => /usr/lib/libc.so.6")
    )

    requirement = checks.check_libunrar(FAMILY)

    assert requirement.status is Status.MISSING


def test_check_vulkan_tool_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: None)

    requirement = checks.check_vulkan(FAMILY)

    assert requirement.status is Status.MISSING


def test_check_vulkan_no_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/vulkaninfo")
    monkeypatch.setattr(system, "run", lambda cmd: _completed(stdout="no devices found"))

    requirement = checks.check_vulkan(FAMILY)

    assert requirement.status is Status.MISSING


def test_check_vulkan_device_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/vulkaninfo")
    monkeypatch.setattr(system, "run", lambda cmd: _completed(stdout="deviceName = RTX Fake 9000"))

    requirement = checks.check_vulkan(FAMILY)

    assert requirement.status is Status.OK


def test_check_disk_space_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "path_exists", lambda path: True)
    monkeypatch.setattr(
        system,
        "disk_usage",
        lambda path: system.DiskUsage(total=500 * checks.GB, used=0, free=200 * checks.GB),
    )

    requirement = checks.check_disk_space(Path("/games/stalker-gamma"))

    assert requirement.status is Status.OK


def test_check_disk_space_not_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "path_exists", lambda path: True)
    monkeypatch.setattr(
        system,
        "disk_usage",
        lambda path: system.DiskUsage(total=500 * checks.GB, used=0, free=10 * checks.GB),
    )

    requirement = checks.check_disk_space(Path("/games/stalker-gamma"))

    assert requirement.status is Status.MISSING
    assert requirement.install_hint is not None


def test_check_disk_space_walks_up_to_existing_ancestor(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = {Path("/games")}
    monkeypatch.setattr(system, "path_exists", lambda path: path in existing)
    probed: list[Path] = []

    def fake_disk_usage(path: Path) -> system.DiskUsage:
        probed.append(path)
        return system.DiskUsage(total=500 * checks.GB, used=0, free=200 * checks.GB)

    monkeypatch.setattr(system, "disk_usage", fake_disk_usage)

    checks.check_disk_space(Path("/games/stalker-gamma/nested"))

    assert probed == [Path("/games")]
