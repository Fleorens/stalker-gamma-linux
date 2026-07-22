from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux import engine, orchestrator
from stalker_gamma_linux.engine.errors import EngineExecutionError
from stalker_gamma_linux.engine.paths import InstallPaths


def _patch_engine(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    for name in ("install_anomaly", "install_gamma", "remove_reshade", "purge_shader_cache"):
        monkeypatch.setattr(
            engine,
            name,
            (lambda label: (lambda *a, **k: events.append(label)))(name),
        )


def test_run_install_runs_pipeline_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    _patch_engine(monkeypatch, events)

    code = orchestrator.run_install(tmp_path)

    assert code == 0
    assert events == ["install_anomaly", "install_gamma", "remove_reshade", "purge_shader_cache"]


def test_run_install_passes_install_paths_under_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_anomaly(paths: InstallPaths, **kw: Any) -> None:
        captured["paths"] = paths

    monkeypatch.setattr(engine, "install_anomaly", fake_anomaly)
    for name in ("install_gamma", "remove_reshade", "purge_shader_cache"):
        monkeypatch.setattr(engine, name, lambda *a, **k: None)

    orchestrator.run_install(tmp_path)

    assert captured["paths"] == InstallPaths.under(tmp_path)


def test_run_install_returns_one_on_engine_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise EngineExecutionError("full-install", 1, "ModDB download link not found")

    monkeypatch.setattr(engine, "install_anomaly", lambda *a, **k: None)
    monkeypatch.setattr(engine, "install_gamma", boom)

    assert orchestrator.run_install(tmp_path) == 1
