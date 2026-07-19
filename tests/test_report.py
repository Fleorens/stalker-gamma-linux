import subprocess
from pathlib import Path

import pytest

from stalker_gamma_linux.environment import system
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
