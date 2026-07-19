from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.environment.models import Status
from stalker_gamma_linux.prefix import doctor, provision
from stalker_gamma_linux.prefix.errors import UmuNotFoundError
from stalker_gamma_linux.prefix.paths import PrefixPaths
from stalker_gamma_linux.prefix.verbs import REQUIRED_VERBS


def _make_healthy_prefix(root: Path) -> PrefixPaths:
    paths = PrefixPaths.under(root)
    pfx = paths.prefix / "pfx"
    system32 = pfx / "drive_c" / "windows" / "system32"
    system32.mkdir(parents=True)
    (pfx / "system.reg").write_text("WINE REGISTRY\n")
    (pfx / "winetricks.log").write_text("\n".join(REQUIRED_VERBS) + "\n")
    (system32 / "d3d11.dll").write_bytes(b"\x00\x01DXVK\x00")
    (paths.prefix / "version").write_text("GE-Proton10-34\n")
    return paths


def _make_proton_dir(root: Path) -> Path:
    compat = root / "compatibilitytools.d"
    build = compat / "GE-Proton10-34"
    build.mkdir(parents=True)
    (build / "proton").write_text("#!/bin/sh\n")
    return compat


def _statuses(report: doctor.PrefixReport) -> dict[str, Status]:
    return {requirement.name: requirement.status for requirement in report.requirements}


def test_report_all_missing_on_empty_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: None)
    paths = PrefixPaths.under(tmp_path / "install")

    report = doctor.build_prefix_report(paths, [tmp_path / "vide"])

    assert not report.is_healthy
    assert set(_statuses(report).values()) == {Status.MISSING}


def test_report_healthy_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/umu-run")
    paths = _make_healthy_prefix(tmp_path / "install")
    compat = _make_proton_dir(tmp_path)

    report = doctor.build_prefix_report(paths, [compat])

    assert report.is_healthy
    assert set(_statuses(report).values()) == {Status.OK}


def test_report_flags_missing_verbs_and_native_dxvk_dll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/umu-run")
    paths = _make_healthy_prefix(tmp_path / "install")
    paths.winetricks_log.write_text("vcrun2022\n")
    (paths.system32 / "d3d11.dll").write_bytes(b"builtin wine, sans marqueur")
    compat = _make_proton_dir(tmp_path)

    report = doctor.build_prefix_report(paths, [compat])

    statuses = _statuses(report)
    assert statuses["Verbs winetricks"] is Status.MISSING
    assert statuses["DXVK"] is Status.MISSING
    assert statuses["Préfixe"] is Status.OK


def test_format_prefix_report_shows_status_and_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: None)
    paths = PrefixPaths.under(tmp_path / "install")

    output = doctor.format_prefix_report(doctor.build_prefix_report(paths, []))

    assert "[MANQUANT]" in output
    assert "--repair" in output
    assert "réparation" in output.lower()


def test_run_prefix_doctor_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/umu-run")
    root = tmp_path / "install"
    _make_healthy_prefix(root)
    compat = _make_proton_dir(tmp_path)

    assert doctor.run_prefix_doctor(root, search_dirs=[compat]) == 0
    assert doctor.run_prefix_doctor(tmp_path / "vide", search_dirs=[compat]) == 1
    assert "Le préfixe est sain." in capsys.readouterr().out


def test_run_prefix_doctor_repair_invokes_provisioning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/umu-run")
    root = tmp_path / "install"
    compat = _make_proton_dir(tmp_path)
    repairs: list[PrefixPaths] = []

    def fake_ensure_prefix(paths: PrefixPaths, **kwargs: Any) -> None:
        repairs.append(paths)
        _make_healthy_prefix(root)

    monkeypatch.setattr(provision, "ensure_prefix", fake_ensure_prefix)

    exit_code = doctor.run_prefix_doctor(root, repair=True, search_dirs=[compat])

    assert exit_code == 0
    assert len(repairs) == 1
    assert "Le préfixe est sain." in capsys.readouterr().out


def test_run_prefix_doctor_repair_reports_typed_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: None)

    def failing_ensure_prefix(paths: PrefixPaths, **kwargs: Any) -> None:
        raise UmuNotFoundError

    monkeypatch.setattr(provision, "ensure_prefix", failing_ensure_prefix)

    exit_code = doctor.run_prefix_doctor(tmp_path / "install", repair=True, search_dirs=[])

    assert exit_code == 1
    assert "Réparation échouée" in capsys.readouterr().out
