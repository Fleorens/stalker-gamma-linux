import subprocess
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from stalker_gamma_linux.engine import process
from stalker_gamma_linux.engine.errors import EngineExecutionError, EngineNotFoundError
from stalker_gamma_linux.environment import system


class _FakeProcess:
    def __init__(self, lines: list[str], returncode: int) -> None:
        self.stdout: Iterator[str] = iter(f"{line}\n" for line in lines)
        self._returncode = returncode

    def wait(self) -> int:
        return self._returncode


def _fake_popen(lines: list[str], returncode: int) -> Callable[..., _FakeProcess]:
    def factory(*args: Any, **kwargs: Any) -> _FakeProcess:
        return _FakeProcess(lines, returncode)

    return factory


def test_run_raises_when_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: None)

    with pytest.raises(EngineNotFoundError):
        process.run("anomaly-install", ["--anomaly", "/tmp/x"])


def test_run_streams_lines_to_progress_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/gamma-launcher")
    monkeypatch.setattr(subprocess, "Popen", _fake_popen(["[+] step one", "[+] step two"], 0))

    seen: list[str] = []
    process.run("full-install", ["--anomaly", "/tmp/a"], on_progress=seen.append)

    assert seen == ["[+] step one", "[+] step two"]


def test_run_succeeds_without_progress_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/gamma-launcher")
    monkeypatch.setattr(subprocess, "Popen", _fake_popen(["[+] step"], 0))

    process.run("full-install", [])


def test_run_raises_execution_error_with_output_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/gamma-launcher")
    monkeypatch.setattr(
        subprocess, "Popen", _fake_popen(["oops", "ModDB download link not found"], 1)
    )

    with pytest.raises(EngineExecutionError) as excinfo:
        process.run("full-install", [])

    error = excinfo.value
    assert error.subcommand == "full-install"
    assert error.returncode == 1
    assert "ModDB download link not found" in error.output_tail
    assert "issue #167" in str(error)


def test_run_disables_gamma_launcher_persistent_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/gamma-launcher")
    captured_env: dict[str, str] = {}

    def factory(*args: Any, **kwargs: Any) -> _FakeProcess:
        captured_env.update(kwargs["env"])
        return _FakeProcess([], 0)

    monkeypatch.setattr(subprocess, "Popen", factory)

    process.run("check-md5", ["--gamma", "/tmp/g"])

    assert captured_env["GAMMA_LAUNCHER_NO_CONFIG"] == "1"


def test_run_decodes_output_tolerantly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/gamma-launcher")
    captured: dict[str, Any] = {}

    def factory(*args: Any, **kwargs: Any) -> _FakeProcess:
        captured["errors"] = kwargs.get("errors")
        return _FakeProcess([], 0)

    monkeypatch.setattr(subprocess, "Popen", factory)

    process.run("check-md5", ["--gamma", "/tmp/g"])

    # Un octet non-UTF-8 dans la sortie ne doit jamais crasher le lecteur.
    assert captured["errors"] == "replace"
