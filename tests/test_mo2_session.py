from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux import engine
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.mo2 import diagnostics, flat, instance, launch, session
from stalker_gamma_linux.mo2.diagnostics import UsvfsDiagnosis
from stalker_gamma_linux.mo2.errors import AnomalyNotFoundError
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.prefix import provision
from stalker_gamma_linux.prefix.errors import PrefixError
from stalker_gamma_linux.prefix.proton import ProtonBuild


def _with_anomaly(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "AnomalyLauncher.exe").write_text("", encoding="utf-8")
    return directory


def test_resolve_anomaly_prefers_sibling_layout(tmp_path: Path) -> None:
    mo2 = Mo2Paths.under(tmp_path)
    install = InstallPaths.under(tmp_path)
    _with_anomaly(install.anomaly)

    assert session.resolve_anomaly(mo2, install) == install.anomaly


def test_resolve_anomaly_falls_back_to_nested_gamma_layout(tmp_path: Path) -> None:
    mo2 = Mo2Paths.under(tmp_path)
    install = InstallPaths.under(tmp_path)
    nested = _with_anomaly(mo2.instance / "anomaly")  # <gamma>/anomaly

    assert session.resolve_anomaly(mo2, install) == nested


def test_resolve_anomaly_defaults_to_sibling_when_neither_exists(tmp_path: Path) -> None:
    mo2 = Mo2Paths.under(tmp_path)
    install = InstallPaths.under(tmp_path)

    assert session.resolve_anomaly(mo2, install) == install.anomaly


@pytest.fixture
def fake_build(tmp_path: Path) -> ProtonBuild:
    return ProtonBuild(name="GE-Proton10-1", path=tmp_path / "GE", version=(10, 1))


@pytest.fixture(autouse=True)
def _patch_prefix(monkeypatch: pytest.MonkeyPatch, fake_build: ProtonBuild) -> None:
    monkeypatch.setattr(provision, "ensure_prefix", lambda *a, **k: fake_build)


def _diagnosis(active: bool) -> UsvfsDiagnosis:
    return UsvfsDiagnosis(active=active, checked_log=None, enabled_mod_count=3, message="msg")


def _recorder(events: list[str], label: str, result: Any = None) -> Any:
    def record(*a: Any, **k: Any) -> Any:
        events.append(label)
        return result

    return record


def test_run_play_nominal_configures_launches_and_diagnoses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    monkeypatch.setattr(instance, "configure_instance", _recorder(events, "configure"))
    monkeypatch.setattr(launch, "launch_game", _recorder(events, "launch", Path("/l")))
    monkeypatch.setattr(diagnostics, "diagnose_usvfs", lambda *a, **k: _diagnosis(True))

    code = session.run_play(tmp_path)

    assert code == 0
    assert events == ["configure", "launch"]


def test_run_play_returns_nonzero_when_usvfs_dead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(instance, "configure_instance", lambda *a, **k: None)
    monkeypatch.setattr(launch, "launch_game", lambda *a, **k: Path("/l"))
    monkeypatch.setattr(diagnostics, "diagnose_usvfs", lambda *a, **k: _diagnosis(False))

    assert session.run_play(tmp_path) == 1


def test_run_play_forwards_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_launch(mo2: Any, prefix: Any, proton: Any, *, executable: str, **kw: Any) -> Path:
        captured["executable"] = executable
        return Path("/l")

    monkeypatch.setattr(instance, "configure_instance", lambda *a, **k: None)
    monkeypatch.setattr(launch, "launch_game", fake_launch)
    monkeypatch.setattr(diagnostics, "diagnose_usvfs", lambda *a, **k: _diagnosis(True))

    session.run_play(tmp_path, executable="Anomaly (DX10)")

    assert captured["executable"] == "Anomaly (DX10)"


def test_run_play_no_diagnose_skips_diagnosis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(instance, "configure_instance", lambda *a, **k: None)
    monkeypatch.setattr(launch, "launch_game", lambda *a, **k: Path("/l"))

    def fail_diagnose(*a: Any, **k: Any) -> UsvfsDiagnosis:
        raise AssertionError("diagnostic ne doit pas être appelé")

    monkeypatch.setattr(diagnostics, "diagnose_usvfs", fail_diagnose)

    assert session.run_play(tmp_path, diagnose=False) == 0


def test_run_play_flat_builds_and_launches_flat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    def fail_configure(*a: Any, **k: Any) -> None:
        raise AssertionError("le mode flat ne configure pas MO2")

    monkeypatch.setattr(instance, "configure_instance", fail_configure)
    monkeypatch.setattr(engine, "build_flat_install", _recorder(events, "build"))
    monkeypatch.setattr(flat, "launch_flat", _recorder(events, "launch", Path("/l")))

    code = session.run_play(tmp_path, flat_mode=True)

    assert code == 0
    assert events == ["build", "launch"]


def test_run_play_reports_prefix_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> ProtonBuild:
        raise PrefixError("boom")

    monkeypatch.setattr(provision, "ensure_prefix", boom)

    assert session.run_play(tmp_path) == 1


def test_run_mo2_configures_and_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    monkeypatch.setattr(instance, "configure_instance", _recorder(events, "configure"))
    monkeypatch.setattr(launch, "launch_mo2", _recorder(events, "launch", Path("/l")))

    code = session.run_mo2(tmp_path)

    assert code == 0
    assert events == ["configure", "launch"]


def test_run_mo2_tolerates_missing_anomaly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    def raise_anomaly(*a: Any, **k: Any) -> None:
        raise AnomalyNotFoundError(tmp_path / "anomaly")

    monkeypatch.setattr(instance, "configure_instance", raise_anomaly)
    monkeypatch.setattr(launch, "launch_mo2", _recorder(events, "launch", Path("/l")))

    # MO2 s'ouvre quand même (best-effort), pour inspecter l'instance sans jeu.
    assert session.run_mo2(tmp_path) == 0
    assert events == ["launch"]
