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


def test_install_gamma_preserves_user_config_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        runner, "run", lambda subcommand, args, **kw: calls.append((subcommand, args))
    )

    paths = _paths(tmp_path)
    user_ltx = paths.anomaly / "appdata" / "user.ltx"
    user_ltx.parent.mkdir(parents=True, exist_ok=True)
    user_ltx.write_text("[key]\nvalue\n")

    runner.install_gamma(paths)

    # Un user.ltx existe → --preserve-user-config, sinon _patch_anomaly reset
    # les réglages joueur.
    assert "--preserve-user-config" in calls[0][1]


def test_install_gamma_omits_preserve_flag_on_fresh_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        runner, "run", lambda subcommand, args, **kw: calls.append((subcommand, args))
    )

    # Pas de user.ltx (install fraîche) : passer le drapeau ferait planter
    # gamma-launcher (restauration d'un .bak inexistant).
    runner.install_gamma(_paths(tmp_path))

    assert "--preserve-user-config" not in calls[0][1]


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


def test_verify_runs_check_md5_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


def _run_emitting(lines: list[str], *, exit_error: bool) -> Any:
    """Simule `run` : rejoue `lines` sur on_progress puis échoue si demandé."""

    def fake_run(subcommand: str, args: list[str], **kw: Any) -> None:
        on_progress = kw.get("on_progress")
        for line in lines:
            if on_progress is not None:
                on_progress(line)
        if exit_error:
            raise EngineExecutionError(subcommand, 1, "\n".join(lines[-3:]))

    return fake_run


class TestVerifyClassification:
    """check-md5 sort en 1 dès qu'une entrée est « invérifiable en ligne »

    (page ModDB modifiée/throttlée), même quand toutes les archives locales
    ont passé le hash — cas réel du 2026-07-25. Ce n'est pas un échec de
    mise à jour ; seule une vraie corruption locale doit lever.
    """

    def test_moddb_seulement_devient_avertissement(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        lines = [
            "Calculating hash of Soundscape_Overhaul_3.0.zip: 100%",
            "Could not find Filename in https://www.moddb.com/mods/x/addons/barbwire",
            "Skipping Fluid_relations_1.0.7z since ModDB info do not match download url",
        ]
        monkeypatch.setattr(runner, "run", _run_emitting(lines, exit_error=True))

        unverifiable = runner.verify(_paths(tmp_path))

        assert unverifiable == (
            "Could not find Filename in https://www.moddb.com/mods/x/addons/barbwire",
            "Skipping Fluid_relations_1.0.7z since ModDB info do not match download url",
        )

    def test_les_doublons_du_bloc_final_sont_dedupliques(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # check-md5 réimprime toutes ses erreurs en bloc à la fin du run.
        line = "Could not find Filename in https://www.moddb.com/mods/x/addons/laser"
        monkeypatch.setattr(runner, "run", _run_emitting([line, line], exit_error=True))

        assert runner.verify(_paths(tmp_path)) == (line,)

    def test_corruption_locale_leve_meme_avec_du_moddb(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        lines = [
            "Could not find Filename in https://www.moddb.com/mods/x/addons/laser",
            "Hash verification failed for GAMMA_RC3.7z",
        ]
        monkeypatch.setattr(runner, "run", _run_emitting(lines, exit_error=True))

        with pytest.raises(VerificationError):
            runner.verify(_paths(tmp_path))

    def test_echec_sans_marqueur_connu_leve(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            runner, "run", _run_emitting(["Traceback (most recent call last):"], exit_error=True)
        )

        with pytest.raises(VerificationError):
            runner.verify(_paths(tmp_path))

    def test_succes_sans_erreur_retourne_vide(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(runner, "run", _run_emitting(["tout va bien"], exit_error=False))

        assert runner.verify(_paths(tmp_path)) == ()

    def test_on_progress_recoit_tout_le_flux(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        lines = ["a", "Could not find Filename in url", "b"]
        monkeypatch.setattr(runner, "run", _run_emitting(lines, exit_error=True))
        seen: list[str] = []

        runner.verify(_paths(tmp_path), on_progress=seen.append)

        assert seen == lines


def test_remove_reshade_invokes_subcommand(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
