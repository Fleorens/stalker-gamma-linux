import subprocess
from pathlib import Path

import pytest

from stalker_gamma_linux import doctor, state
from stalker_gamma_linux.environment import system


def _make_fully_equipped_system(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        system, "read_text", lambda path: 'ID=fedora\nPRETTY_NAME="Fedora Linux 41"\n'
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


def test_run_doctor_combines_all_three_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_fully_equipped_system(monkeypatch)
    state.mark_done(tmp_path, "anomaly")

    exit_code = doctor.run_doctor(tmp_path)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Environnement" in out
    assert "Préfixe Proton" in out
    assert "Installation" in out
    assert "Fedora Linux 41" in out
    assert "[ OK ]" in out
    assert "[ A FAIRE ]" in out


def test_run_doctor_fails_only_on_missing_prerequisites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(system, "read_text", lambda path: None)
    monkeypatch.setattr(system, "which", lambda cmd: None)
    monkeypatch.setattr(system, "path_exists", lambda path: False)
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

    assert doctor.run_doctor(tmp_path) == 1
