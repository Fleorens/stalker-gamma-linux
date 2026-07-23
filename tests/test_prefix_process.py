import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.prefix import process
from stalker_gamma_linux.prefix.errors import (
    PrefixCancelledError,
    PrefixCommandError,
    UmuNotFoundError,
)
from stalker_gamma_linux.prefix.paths import PrefixPaths


class _FakeProcess:
    def __init__(self, lines: list[str], returncode: int) -> None:
        self.stdout: Iterator[str] = iter(f"{line}\n" for line in lines)
        self._returncode = returncode

    def poll(self) -> int | None:
        return self._returncode

    def wait(self, timeout: float | None = None) -> int:
        return self._returncode


class _CancellableFakeProcess:
    """Process fake dont `poll`/`terminate`/`kill` sont pilotables (tests d'annulation)."""

    def __init__(self) -> None:
        self.stdout: Iterator[str] = iter(())
        self._terminated = threading.Event()
        self.terminate_called = False

    def poll(self) -> int | None:
        return -15 if self._terminated.is_set() else None

    def terminate(self) -> None:
        self.terminate_called = True
        self._terminated.set()

    def kill(self) -> None:
        self._terminated.set()

    def wait(self, timeout: float | None = None) -> int:
        if not self._terminated.wait(timeout=timeout):
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout or 0)
        return -15


def _patch_popen(
    monkeypatch: pytest.MonkeyPatch, lines: list[str], returncode: int
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def factory(command: list[str], **kwargs: Any) -> _FakeProcess:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        captured["errors"] = kwargs.get("errors")
        return _FakeProcess(lines, returncode)

    monkeypatch.setattr(subprocess, "Popen", factory)
    return captured


def test_run_in_prefix_raises_when_umu_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: None)

    with pytest.raises(UmuNotFoundError) as excinfo:
        process.run_in_prefix(
            "createprefix", paths=PrefixPaths.under(tmp_path), proton_path=tmp_path / "GE"
        )

    assert "protontricks" in str(excinfo.value)


def test_run_in_prefix_builds_command_and_structural_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/umu-run")
    captured = _patch_popen(monkeypatch, [], 0)
    paths = PrefixPaths.under(tmp_path)
    proton_path = tmp_path / "GE-Proton10-34"

    process.run_in_prefix(
        "winetricks",
        ["-q", "vcrun2022"],
        paths=paths,
        proton_path=proton_path,
        env={"WINEPREFIX": "/ailleurs", "DXVK_HUD": "1"},
    )

    assert captured["command"] == ["/usr/bin/umu-run", "winetricks", "-q", "vcrun2022"]
    # Wine émet parfois des octets non-UTF-8 : le décodage doit être tolérant.
    assert captured["errors"] == "replace"
    # Les variables structurelles gagnent toujours sur celles de l'appelant.
    assert captured["env"]["WINEPREFIX"] == str(paths.prefix)
    assert captured["env"]["GAMEID"] == process.UMU_GAME_ID
    assert captured["env"]["PROTONPATH"] == str(proton_path)
    assert captured["env"]["DXVK_HUD"] == "1"


def test_run_in_prefix_writes_output_to_log_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/umu-run")
    _patch_popen(monkeypatch, ["étape un", "étape deux"], 0)
    paths = PrefixPaths.under(tmp_path)
    seen: list[str] = []

    log_path = process.run_in_prefix(
        tmp_path / "ModOrganizer.exe",
        paths=paths,
        proton_path=tmp_path / "GE",
        on_progress=seen.append,
    )

    assert log_path.parent == paths.logs
    assert log_path.name.startswith("modorganizer-")
    content = log_path.read_text(encoding="utf-8")
    assert content.startswith("$ /usr/bin/umu-run ")
    assert "étape un\nétape deux\n" in content
    assert seen == ["étape un", "étape deux"]


def test_run_in_prefix_raises_typed_error_with_log_attached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/umu-run")
    _patch_popen(monkeypatch, ["boum"], 3)
    paths = PrefixPaths.under(tmp_path)

    with pytest.raises(PrefixCommandError) as excinfo:
        process.run_in_prefix("createprefix", paths=paths, proton_path=tmp_path / "GE")

    error = excinfo.value
    assert error.returncode == 3
    assert error.log_path.is_file()
    assert "boum" in error.output_tail
    assert str(error.log_path) in str(error)


def test_run_in_prefix_cancels_cleanly_when_cancel_event_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/umu-run")
    fake_process = _CancellableFakeProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: fake_process)
    cancel_event = threading.Event()
    cancel_event.set()

    with pytest.raises(PrefixCancelledError):
        process.run_in_prefix(
            "createprefix",
            paths=PrefixPaths.under(tmp_path),
            proton_path=tmp_path / "GE",
            cancel_event=cancel_event,
        )

    assert fake_process.terminate_called
