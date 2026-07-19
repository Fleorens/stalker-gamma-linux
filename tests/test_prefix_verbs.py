from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux.prefix import process, verbs
from stalker_gamma_linux.prefix.errors import PrefixCommandError, WinetricksVerbError
from stalker_gamma_linux.prefix.paths import PrefixPaths


def _paths(tmp_path: Path) -> PrefixPaths:
    paths = PrefixPaths.under(tmp_path)
    paths.prefix.mkdir(parents=True)
    return paths


def _seed_log(paths: PrefixPaths, *installed: str) -> None:
    paths.winetricks_log.write_text("\n".join(installed) + "\n", encoding="utf-8")


def test_installed_verbs_empty_without_log(tmp_path: Path) -> None:
    assert verbs.installed_verbs(_paths(tmp_path)) == frozenset()


def test_installed_verbs_parses_log_ignoring_blank_lines(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.winetricks_log.write_text("vcrun2022\n\n  d3dx9  \n", encoding="utf-8")

    assert verbs.installed_verbs(paths) == frozenset({"vcrun2022", "d3dx9"})


def test_missing_verbs_preserves_required_order(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _seed_log(paths, "vcrun2022", "d3dx9")

    assert verbs.missing_verbs(paths) == (
        "d3dcompiler_43",
        "d3dcompiler_47",
        "d3dx10",
        "d3dx11_43",
    )


def _fake_run_recording(calls: list[str]) -> Any:
    def fake_run_in_prefix(
        exe: Path | str,
        args: Sequence[str] = (),
        *,
        paths: PrefixPaths,
        proton_path: Path,
        env: Mapping[str, str] | None = None,
        log_label: str | None = None,
        on_progress: Any = None,
    ) -> Path:
        assert str(exe) == "winetricks"
        assert args[0] == "-q"
        verb = args[1]
        calls.append(verb)
        # winetricks acte chaque verb réussi dans winetricks.log.
        with paths.winetricks_log.open("a", encoding="utf-8") as log:
            log.write(f"{verb}\n")
        return paths.logs / f"winetricks-{verb}.log"

    return fake_run_in_prefix


def test_apply_missing_verbs_applies_only_missing_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    _seed_log(paths, "vcrun2022", "d3dx9")
    calls: list[str] = []
    monkeypatch.setattr(process, "run_in_prefix", _fake_run_recording(calls))

    applied = verbs.apply_missing_verbs(paths, tmp_path / "GE")

    assert applied == ("d3dcompiler_43", "d3dcompiler_47", "d3dx10", "d3dx11_43")
    assert calls == list(applied)
    assert verbs.missing_verbs(paths) == ()


def test_apply_missing_verbs_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(process, "run_in_prefix", _fake_run_recording(calls))

    verbs.apply_missing_verbs(paths, tmp_path / "GE")
    second = verbs.apply_missing_verbs(paths, tmp_path / "GE")

    assert len(calls) == len(verbs.REQUIRED_VERBS)
    assert second == ()


def test_apply_missing_verbs_wraps_failure_in_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    log_path = tmp_path / "logs" / "winetricks-vcrun2022.log"

    def failing_run(*args: Any, **kwargs: Any) -> Path:
        raise PrefixCommandError("umu-run winetricks -q vcrun2022", 1, log_path, "sortie d'échec")

    monkeypatch.setattr(process, "run_in_prefix", failing_run)

    with pytest.raises(WinetricksVerbError) as excinfo:
        verbs.apply_missing_verbs(paths, tmp_path / "GE")

    error = excinfo.value
    assert error.verb == "vcrun2022"
    assert error.log_path == log_path
    assert "vcrun2022" in str(error)
    assert "sortie d'échec" in str(error)
