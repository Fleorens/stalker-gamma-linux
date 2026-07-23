from pathlib import Path

import pytest

from stalker_gamma_linux import state
from stalker_gamma_linux.environment.report import DEFAULT_INSTALL_TARGET
from stalker_gamma_linux.gui import viewmodel


def test_install_status_not_installed_when_core_steps_missing() -> None:
    assert viewmodel.install_status(state.InstallState()) is viewmodel.InstallStatus.NOT_INSTALLED


def test_install_status_not_installed_when_partially_done() -> None:
    partial = state.InstallState(anomaly=True, gamma=True)

    assert viewmodel.install_status(partial) is viewmodel.InstallStatus.NOT_INSTALLED


def test_install_status_installed_when_core_steps_done_regardless_of_shortcut() -> None:
    done = state.InstallState(anomaly=True, gamma=True, reshade=True, prefix=True, mo2=True)

    assert viewmodel.install_status(done) is viewmodel.InstallStatus.INSTALLED
    # `shortcut` (T06) est optionnelle : elle ne doit jamais bloquer "installé".
    also_done = state.InstallState(
        anomaly=True, gamma=True, reshade=True, prefix=True, mo2=True, shortcut=True
    )
    assert viewmodel.install_status(also_done) is viewmodel.InstallStatus.INSTALLED


def test_main_window_state_primary_action_label(tmp_path: Path) -> None:
    not_installed = viewmodel.MainWindowState(
        target=tmp_path,
        status=viewmodel.InstallStatus.NOT_INSTALLED,
        install=state.InstallState(),
    )
    installed = viewmodel.MainWindowState(
        target=tmp_path,
        status=viewmodel.InstallStatus.INSTALLED,
        install=state.InstallState(
            anomaly=True, gamma=True, reshade=True, prefix=True, mo2=True
        ),
    )

    assert not_installed.primary_action_label == "Installer"
    assert not_installed.is_installed is False
    assert installed.primary_action_label == "Jouer"
    assert installed.is_installed is True


def test_load_main_window_state_reads_persisted_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(state, "config_dir", lambda: tmp_path / "config")
    state.mark_done(tmp_path, "anomaly")
    state.mark_done(tmp_path, "gamma")

    result = viewmodel.load_main_window_state(tmp_path)

    assert result.target == tmp_path
    assert result.status is viewmodel.InstallStatus.NOT_INSTALLED
    assert result.install.is_done("anomaly")
    assert not result.install.is_done("prefix")


def test_load_main_window_state_defaults_target_when_none() -> None:
    result = viewmodel.load_main_window_state(None)

    assert result.target == DEFAULT_INSTALL_TARGET
