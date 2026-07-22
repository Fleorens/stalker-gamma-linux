from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux import engine, orchestrator, state
from stalker_gamma_linux.engine.errors import EngineExecutionError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.mo2 import instance
from stalker_gamma_linux.prefix import provision
from stalker_gamma_linux.prefix.proton import ProtonBuild


def _patch_engine(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    for name in ("install_anomaly", "install_gamma", "remove_reshade", "purge_shader_cache"):
        monkeypatch.setattr(
            engine,
            name,
            (lambda label: (lambda *a, **k: events.append(label)))(name),
        )


def _patch_prefix_and_mo2(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    fake_build = ProtonBuild(name="GE-Proton10-1", path=Path("/opt/GE"), version=(10, 1))

    def fake_ensure_prefix(*a: Any, **k: Any) -> ProtonBuild:
        events.append("ensure_prefix")
        return fake_build

    monkeypatch.setattr(provision, "ensure_prefix", fake_ensure_prefix)
    monkeypatch.setattr(orchestrator, "resolve_anomaly", lambda mo2, install: install.anomaly)
    monkeypatch.setattr(
        instance,
        "configure_instance",
        lambda *a, **k: events.append("configure_instance"),
    )


def _patch_all(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    _patch_engine(monkeypatch, events)
    _patch_prefix_and_mo2(monkeypatch, events)


def test_run_install_runs_full_pipeline_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)

    code = orchestrator.run_install(tmp_path)

    assert code == 0
    assert events == [
        "install_anomaly",
        "install_gamma",
        "remove_reshade",
        "purge_shader_cache",
        "ensure_prefix",
        "configure_instance",
    ]


def test_run_install_passes_install_paths_under_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    events: list[str] = []

    def fake_anomaly(paths: InstallPaths, **kw: Any) -> None:
        captured["paths"] = paths

    _patch_all(monkeypatch, events)
    monkeypatch.setattr(engine, "install_anomaly", fake_anomaly)

    orchestrator.run_install(tmp_path)

    assert captured["paths"] == InstallPaths.under(tmp_path)


def test_run_install_returns_one_on_engine_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    def boom(*a: Any, **k: Any) -> None:
        raise EngineExecutionError("full-install", 1, "ModDB download link not found")

    _patch_all(monkeypatch, events)
    monkeypatch.setattr(engine, "install_anomaly", lambda *a, **k: None)
    monkeypatch.setattr(engine, "install_gamma", boom)

    assert orchestrator.run_install(tmp_path) == 1


def test_run_install_persists_progress_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    def boom(*a: Any, **k: Any) -> None:
        raise EngineExecutionError("full-install", 1, "boom")

    _patch_all(monkeypatch, events)
    monkeypatch.setattr(engine, "install_anomaly", lambda *a, **k: None)
    monkeypatch.setattr(engine, "install_gamma", boom)

    orchestrator.run_install(tmp_path)

    result = state.load_state(tmp_path)
    assert result.is_done("anomaly")
    assert not result.is_done("gamma")


def test_run_install_skips_steps_already_marked_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)
    state.mark_done(tmp_path, "anomaly")
    state.mark_done(tmp_path, "gamma")
    state.mark_done(tmp_path, "reshade")

    code = orchestrator.run_install(tmp_path)

    assert code == 0
    assert events == ["ensure_prefix", "configure_instance"]


def test_run_install_creates_shortcut_only_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_all(monkeypatch, events)
    monkeypatch.setattr(
        orchestrator, "install_shortcut", lambda target: events.append("install_shortcut")
    )

    orchestrator.run_install(tmp_path, shortcut=False)
    assert "install_shortcut" not in events
    assert not state.load_state(tmp_path).is_done("shortcut")

    orchestrator.run_install(tmp_path, shortcut=True)
    assert "install_shortcut" in events
    assert state.load_state(tmp_path).is_done("shortcut")


def test_run_update_runs_pipeline_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    for name in ("update_gamma", "remove_reshade", "purge_shader_cache", "verify"):
        monkeypatch.setattr(
            engine,
            name,
            (lambda label: (lambda *a, **k: events.append(label)))(name),
        )

    code = orchestrator.run_update(tmp_path)

    assert code == 0
    assert events == ["update_gamma", "remove_reshade", "purge_shader_cache", "verify"]
    assert state.load_state(tmp_path).is_done("gamma")


def test_run_update_returns_one_on_engine_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise EngineExecutionError("check-md5", 1, "fichier corrompu")

    monkeypatch.setattr(engine, "update_gamma", lambda *a, **k: None)
    monkeypatch.setattr(engine, "remove_reshade", lambda *a, **k: None)
    monkeypatch.setattr(engine, "purge_shader_cache", lambda *a, **k: None)
    monkeypatch.setattr(engine, "verify", boom)

    assert orchestrator.run_update(tmp_path) == 1
