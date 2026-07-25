"""Détection des outils de l'HÔTE depuis un bac à sable Flatpak (via flatpak-spawn)."""

import subprocess

import pytest

from stalker_gamma_linux.environment import checks, system
from stalker_gamma_linux.environment.distro import DistroFamily
from stalker_gamma_linux.environment.models import Status

FAMILY = DistroFamily.FEDORA


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_host_which_delegates_to_which_outside_flatpak(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_in_flatpak", lambda: False)
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/steam" if cmd == "steam" else None)

    assert system.host_which("steam") == "/usr/bin/steam"


def test_host_which_uses_flatpak_spawn_in_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_in_flatpak", lambda: True)
    calls: list[list[str]] = []

    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _completed(stdout="/usr/bin/steam\n")

    monkeypatch.setattr(system, "run", fake_run)

    assert system.host_which("steam") == "/usr/bin/steam"
    assert calls[0][:3] == ["flatpak-spawn", "--host", "sh"]


def test_host_which_none_when_host_lacks_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_in_flatpak", lambda: True)
    monkeypatch.setattr(system, "run", lambda cmd: _completed(returncode=1))

    assert system.host_which("steam") is None


def test_host_run_prefixes_flatpak_spawn_in_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_in_flatpak", lambda: True)
    seen: list[list[str]] = []

    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return _completed()

    monkeypatch.setattr(system, "run", fake_run)

    system.host_run(["vulkaninfo", "--summary"])

    assert seen[0] == ["flatpak-spawn", "--host", "vulkaninfo", "--summary"]


def test_check_steam_sees_host_steam_from_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    # Le cœur du bug : dans le Flatpak, `which steam` échoue mais le steam de
    # l'hôte existe. On doit le voir, pas déclarer « Steam introuvable ».
    monkeypatch.setattr(system, "_in_flatpak", lambda: True)

    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[-1] == "command -v steam":
            return _completed(stdout="/usr/bin/steam\n")
        return _completed(returncode=1)

    monkeypatch.setattr(system, "run", fake_run)

    requirement = checks.check_steam(FAMILY)

    assert requirement.status is Status.OK


def test_check_vulkan_sees_host_gpu_from_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "_in_flatpak", lambda: True)

    def fake_run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[-1] == "command -v vulkaninfo":
            return _completed(stdout="/usr/bin/vulkaninfo\n")
        if "vulkaninfo" in cmd:
            return _completed(stdout="deviceName = Radeon RX 7900 XT")
        return _completed(returncode=1)

    monkeypatch.setattr(system, "run", fake_run)

    requirement = checks.check_vulkan(FAMILY)

    assert requirement.status is Status.OK
