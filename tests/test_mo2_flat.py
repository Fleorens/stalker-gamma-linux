from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux.mo2 import flat
from stalker_gamma_linux.mo2.errors import Mo2InstanceError
from stalker_gamma_linux.prefix import process
from stalker_gamma_linux.prefix.paths import PrefixPaths


def test_flat_dir_is_under_root() -> None:
    assert flat.flat_dir(Path("/games/sg")) == Path("/games/sg/flat")


def test_launch_flat_runs_launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    final = tmp_path / "flat"
    final.mkdir()
    (final / "AnomalyLauncher.exe").write_text("", encoding="utf-8")
    prefix = PrefixPaths.under(tmp_path)

    calls: list[dict[str, Any]] = []

    def fake_run(exe: Path | str, *a: Any, log_label: str | None = None, **kw: Any) -> Path:
        calls.append({"exe": str(exe), "log_label": log_label})
        return Path("/logs/flat.log")

    monkeypatch.setattr(process, "run_in_prefix", fake_run)

    flat.launch_flat(final, prefix, tmp_path / "GE")

    assert calls[0]["exe"] == str(final / "AnomalyLauncher.exe")
    assert calls[0]["log_label"] == "flat-game"


def test_launch_flat_missing_install_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(process, "run_in_prefix", lambda *a, **k: Path("/x"))

    with pytest.raises(Mo2InstanceError):
        flat.launch_flat(tmp_path / "flat", PrefixPaths.under(tmp_path), tmp_path / "GE")
