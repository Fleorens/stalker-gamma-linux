import subprocess
from pathlib import Path

import pytest

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.environment.distro import Distro, DistroFamily
from stalker_gamma_linux.environment.models import EnvironmentReport, Requirement, Status
from stalker_gamma_linux.environment.report import build_report, format_report


def _make_fully_equipped_system(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        system,
        "read_text",
        lambda path: 'ID=fedora\nPRETTY_NAME="Fedora Linux 41"\n',
    )
    monkeypatch.setattr(system, "which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr(system, "path_exists", lambda path: True)
    monkeypatch.setattr(
        system,
        "disk_usage",
        lambda path: system.DiskUsage(total=500 * 2**30, used=0, free=200 * 2**30),
    )
    monkeypatch.setattr(
        system,
        "run",
        lambda cmd: subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="protontricks, version 1.12.0\nlibunrar.so.5\ndeviceName = Fake GPU",
            stderr="",
        ),
    )


def test_build_report_all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _make_fully_equipped_system(monkeypatch)

    report = build_report(target=Path("/games/stalker-gamma"))

    assert report.is_ready
    assert report.distro.pretty_name == "Fedora Linux 41"
    assert len(report.requirements) == 7


def test_build_report_missing_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "read_text", lambda path: None)
    monkeypatch.setattr(system, "which", lambda cmd: None)
    monkeypatch.setattr(system, "path_exists", lambda path: True)
    monkeypatch.setattr(
        system,
        "disk_usage",
        lambda path: system.DiskUsage(total=10 * 2**30, used=0, free=1 * 2**30),
    )
    monkeypatch.setattr(
        system,
        "run",
        lambda cmd: subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr=""),
    )

    report = build_report(target=Path("/games/stalker-gamma"))

    assert not report.is_ready


def test_format_report_lists_each_requirement(monkeypatch: pytest.MonkeyPatch) -> None:
    _make_fully_equipped_system(monkeypatch)

    report = build_report(target=Path("/games/stalker-gamma"))
    text = format_report(report)

    assert "Fedora Linux 41" in text
    assert "Steam" in text
    assert "GPU Vulkan" in text
    assert "Tous les prérequis sont satisfaits." in text


def test_format_report_shows_one_consolidated_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "read_text", lambda path: "ID=fedora\n")
    monkeypatch.setattr(system, "which", lambda cmd: None)
    monkeypatch.setattr(system, "path_exists", lambda path: True)
    monkeypatch.setattr(system, "detect_virtualization", lambda: None)
    monkeypatch.setattr(
        system,
        "disk_usage",
        lambda path: system.DiskUsage(total=500 * 2**30, used=0, free=200 * 2**30),
    )
    monkeypatch.setattr(
        system,
        "run",
        lambda cmd: subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr=""),
    )

    text = format_report(build_report(target=Path("/games/stalker-gamma")))

    # Un seul bloc groupé, pas une ligne « → » éparpillée par prérequis.
    assert "Pour tout installer d'un coup :" in text
    assert text.count("sudo dnf install") == 1
    assert "sudo dnf install steam protontricks p7zip p7zip-plugins unrar" in text
    assert "→" not in text
    # umu-launcher n'a pas de paquet : étape à part, via le zipapp (jamais pipx).
    assert "umu-launcher : " in text
    assert "pipx" not in text


def test_is_ready_ignores_unavailable_requirements() -> None:
    report = EnvironmentReport(
        distro=Distro(family=DistroFamily.FEDORA, pretty_name="Fedora"),
        requirements=(
            Requirement("Steam", Status.OK, "présent"),
            Requirement("GPU Vulkan", Status.UNAVAILABLE, "normal en VM"),
        ),
    )

    assert report.is_ready
