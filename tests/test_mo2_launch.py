from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux.mo2 import launch
from stalker_gamma_linux.mo2.errors import Mo2NotInstalledError
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.prefix import process
from stalker_gamma_linux.prefix.paths import PrefixPaths


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, exe: Path | str, args: Any = (), *, log_label: str | None = None, **kw: Any
    ) -> Path:
        self.calls.append({"exe": str(exe), "args": list(args), "log_label": log_label})
        return Path("/logs/fake.log")


def _installed_instance(tmp_path: Path) -> tuple[Mo2Paths, PrefixPaths]:
    mo2 = Mo2Paths.under(tmp_path)
    mo2.instance.mkdir(parents=True)
    mo2.executable.write_text("", encoding="utf-8")
    return mo2, PrefixPaths.under(tmp_path)


def test_moshortcut_portable_instance_has_empty_instance_name() -> None:
    assert launch.moshortcut("Anomaly (DX11)") == "moshortcut://:Anomaly (DX11)"


def test_moshortcut_named_instance() -> None:
    assert launch.moshortcut("Anomaly (DX11)", "GAMMA") == "moshortcut://GAMMA:Anomaly (DX11)"


def test_launch_mo2_runs_executable_without_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mo2, prefix = _installed_instance(tmp_path)
    recorder = _Recorder()
    monkeypatch.setattr(process, "run_in_prefix", recorder)

    launch.launch_mo2(mo2, prefix, tmp_path / "GE")

    assert recorder.calls[0]["exe"] == str(mo2.executable)
    assert recorder.calls[0]["args"] == []
    assert recorder.calls[0]["log_label"] == "mo2"


def test_launch_game_passes_moshortcut(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mo2, prefix = _installed_instance(tmp_path)
    recorder = _Recorder()
    monkeypatch.setattr(process, "run_in_prefix", recorder)

    launch.launch_game(mo2, prefix, tmp_path / "GE")

    assert recorder.calls[0]["exe"] == str(mo2.executable)
    assert recorder.calls[0]["args"] == ["moshortcut://:Anomaly (DX11)"]
    assert recorder.calls[0]["log_label"] == "mo2-game"


def test_launch_game_custom_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mo2, prefix = _installed_instance(tmp_path)
    recorder = _Recorder()
    monkeypatch.setattr(process, "run_in_prefix", recorder)

    launch.launch_game(mo2, prefix, tmp_path / "GE", executable="Anomaly (DX10)")

    assert recorder.calls[0]["args"] == ["moshortcut://:Anomaly (DX10)"]


def test_launch_requires_installed_mo2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mo2 = Mo2Paths.under(tmp_path)  # ModOrganizer.exe absent
    prefix = PrefixPaths.under(tmp_path)
    monkeypatch.setattr(process, "run_in_prefix", _Recorder())

    with pytest.raises(Mo2NotInstalledError):
        launch.launch_game(mo2, prefix, tmp_path / "GE")
