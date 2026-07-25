from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux.engine import runner
from stalker_gamma_linux.engine.errors import EngineExecutionError, VerificationError
from stalker_gamma_linux.engine.paths import InstallPaths


def _paths(tmp_path: Path) -> InstallPaths:
    return InstallPaths.under(tmp_path)


def test_install_anomaly_invokes_anomaly_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        runner, "run", lambda subcommand, args, **kw: calls.append((subcommand, args))
    )

    paths = _paths(tmp_path)
    runner.install_anomaly(paths)

    assert calls == [
        (
            "anomaly-install",
            ["--anomaly", str(paths.anomaly), "--cache-directory", str(paths.cache)],
        )
    ]
    assert paths.anomaly.is_dir()
    assert paths.cache.is_dir()


def test_install_gamma_invokes_full_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        runner, "run", lambda subcommand, args, **kw: calls.append((subcommand, args))
    )

    paths = _paths(tmp_path)
    runner.install_gamma(paths)

    # Pas de --cache-directory : sa présence fait planter la mise à jour
    # (GammaSetup fait `downloads.rmdir()` sur un lien symbolique existant,
    # NotADirectoryError). Voir install_gamma.
    assert calls == [
        (
            "full-install",
            [
                "--anomaly",
                str(paths.anomaly),
                "--gamma",
                str(paths.gamma),
            ],
        )
    ]


def test_install_gamma_redirects_tmpdir_to_install_drive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(runner, "run", lambda subcommand, args, **kw: captured.update(kw))

    paths = _paths(tmp_path)
    runner.install_gamma(paths)

    # Extraction hors du tmpfs /tmp : le TMPDIR imposé est sur le disque cible
    # (sous cache/, même FS que mods/).
    assert captured["tmpdir"] == paths.cache / "tmp"


def test_install_anomaly_redirects_tmpdir_to_install_drive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(runner, "run", lambda subcommand, args, **kw: captured.update(kw))

    paths = _paths(tmp_path)
    runner.install_anomaly(paths)

    assert captured["tmpdir"] == paths.cache / "tmp"


def test_update_gamma_is_an_alias_for_install_gamma(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(runner, "run", lambda subcommand, args, **kw: calls.append(subcommand))

    runner.update_gamma(_paths(tmp_path))

    assert calls == ["full-install"]


def test_verify_runs_check_md5_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        runner, "run", lambda subcommand, args, **kw: calls.append((subcommand, args))
    )

    paths = _paths(tmp_path)
    runner.verify(paths)

    # Pas de check-anomaly : il compare aux checksums vanilla, or GAMMA patche
    # bin/*.exe et fsgame.ltx → échec systématique post-patch. Voir verify.
    assert calls == [("check-md5", ["--gamma", str(paths.gamma)])]


def test_verify_wraps_execution_error_as_verification_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(subcommand: str, args: list[str], **kw: Any) -> None:
        raise EngineExecutionError(subcommand, 1, "Invalid file(s) detected:\nfoo.dll")

    monkeypatch.setattr(runner, "run", fake_run)

    with pytest.raises(VerificationError) as excinfo:
        runner.verify(_paths(tmp_path))

    assert excinfo.value.subcommand == "check-md5"


def test_remove_reshade_invokes_subcommand(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        runner, "run", lambda subcommand, args, **kw: calls.append((subcommand, args))
    )

    paths = _paths(tmp_path)
    runner.remove_reshade(paths)

    assert calls == [("remove-reshade", ["--anomaly", str(paths.anomaly)])]


def test_purge_shader_cache_invokes_subcommand(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        runner, "run", lambda subcommand, args, **kw: calls.append((subcommand, args))
    )

    paths = _paths(tmp_path)
    runner.purge_shader_cache(paths)

    assert calls == [("purge-shader-cache", ["--anomaly", str(paths.anomaly)])]


def test_build_flat_install_invokes_usvfs_workaround(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        runner, "run", lambda subcommand, args, **kw: calls.append((subcommand, args))
    )

    paths = _paths(tmp_path)
    final = tmp_path / "flat"
    runner.build_flat_install(paths, final)

    assert calls == [
        (
            "usvfs-workaround",
            [
                "--anomaly",
                str(paths.anomaly),
                "--gamma",
                str(paths.gamma),
                "--final",
                str(final),
            ],
        )
    ]
    assert final.is_dir()


def test_progress_callback_is_forwarded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    received: list[str] = []

    def fake_run(subcommand: str, args: list[str], *, on_progress: Any = None, **kw: Any) -> None:
        if on_progress:
            on_progress(f"{subcommand} started")

    monkeypatch.setattr(runner, "run", fake_run)

    runner.install_gamma(_paths(tmp_path), on_progress=received.append)

    assert received == ["full-install started"]
