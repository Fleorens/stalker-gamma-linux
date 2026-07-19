from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux.prefix import process, proton, provision
from stalker_gamma_linux.prefix.errors import PrefixError
from stalker_gamma_linux.prefix.paths import PrefixPaths
from stalker_gamma_linux.prefix.proton import ProtonBuild


def test_is_initialized_detects_flat_and_pfx_layouts(tmp_path: Path) -> None:
    paths = PrefixPaths.under(tmp_path)
    assert not provision.is_initialized(paths)

    paths.prefix.mkdir(parents=True)
    (paths.prefix / "system.reg").write_text("WINE REGISTRY\n")
    assert provision.is_initialized(paths)

    pfx_paths = PrefixPaths.under(tmp_path / "autre")
    (pfx_paths.prefix / "pfx").mkdir(parents=True)
    assert not provision.is_initialized(pfx_paths)
    (pfx_paths.prefix / "pfx" / "system.reg").write_text("WINE REGISTRY\n")
    assert provision.is_initialized(pfx_paths)


def test_create_prefix_skips_when_already_initialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = PrefixPaths.under(tmp_path)
    paths.prefix.mkdir(parents=True)
    (paths.prefix / "system.reg").write_text("WINE REGISTRY\n")

    def fail_run(*args: Any, **kwargs: Any) -> Path:
        raise AssertionError("aucune commande externe attendue sur un préfixe sain")

    monkeypatch.setattr(process, "run_in_prefix", fail_run)

    provision.create_prefix(paths, tmp_path / "GE")


def _fake_run_creating_prefix(calls: list[str]) -> Any:
    def fake_run(exe: Path | str, *args: Any, paths: PrefixPaths, **kwargs: Any) -> Path:
        calls.append(str(exe))
        pfx = paths.prefix / "pfx"
        pfx.mkdir(parents=True, exist_ok=True)
        (pfx / "system.reg").write_text("WINE REGISTRY\n")
        return paths.logs / "createprefix.log"

    return fake_run


def test_create_prefix_runs_umu_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = PrefixPaths.under(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(process, "run_in_prefix", _fake_run_creating_prefix(calls))

    provision.create_prefix(paths, tmp_path / "GE")

    assert calls == ["createprefix"]
    assert provision.is_initialized(paths)


def test_create_prefix_raises_when_prefix_still_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = PrefixPaths.under(tmp_path)
    log_path = tmp_path / "logs" / "createprefix.log"

    def fake_run(*args: Any, **kwargs: Any) -> Path:
        return log_path

    monkeypatch.setattr(process, "run_in_prefix", fake_run)

    with pytest.raises(PrefixError) as excinfo:
        provision.create_prefix(paths, tmp_path / "GE")

    assert str(log_path) in str(excinfo.value)


def _fake_run_full(calls: list[str]) -> Any:
    def fake_run(
        exe: Path | str, args: Sequence[str] = (), *, paths: PrefixPaths, **kwargs: Any
    ) -> Path:
        name = str(exe)
        if name == "createprefix":
            calls.append(name)
            pfx = paths.prefix / "pfx"
            pfx.mkdir(parents=True, exist_ok=True)
            (pfx / "system.reg").write_text("WINE REGISTRY\n")
        else:
            verb = args[1]
            calls.append(f"winetricks {verb}")
            with paths.winetricks_log.open("a", encoding="utf-8") as log:
                log.write(f"{verb}\n")
        return paths.logs / "fake.log"

    return fake_run


def test_ensure_prefix_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = PrefixPaths.under(tmp_path / "install")
    ge_build = ProtonBuild(
        name="GE-Proton10-34", path=tmp_path / "GE-Proton10-34", version=(10, 34)
    )
    monkeypatch.setattr(proton, "ensure_proton", lambda *args, **kwargs: ge_build)
    calls: list[str] = []
    monkeypatch.setattr(process, "run_in_prefix", _fake_run_full(calls))

    first_build = provision.ensure_prefix(paths)
    calls_after_first = list(calls)
    second_build = provision.ensure_prefix(paths)

    assert first_build == ge_build
    assert second_build == ge_build
    assert calls_after_first[0] == "createprefix"
    assert len(calls_after_first) == 7  # createprefix + 6 verbs
    # Deuxième exécution : préfixe sain, aucune commande externe relancée.
    assert calls == calls_after_first
