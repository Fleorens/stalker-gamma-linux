from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux import cli
from stalker_gamma_linux.backups import ALL_SETS, BackupSet
from stalker_gamma_linux.environment.mangohud import Preset
from stalker_gamma_linux.environment.performance import Settings


def test_build_parser_install_default_target() -> None:
    args = cli.build_parser().parse_args(["install"])

    assert args.command == "install"
    assert args.target is None
    assert args.shortcut is False


def test_build_parser_install_shortcut_flag() -> None:
    args = cli.build_parser().parse_args(["install", "--shortcut"])

    assert args.shortcut is True


def test_main_dispatches_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path | None, bool, bool]] = []

    def fake_run_install(
        target: Path | None,
        *,
        shortcut: bool,
        steam: bool = False,
        force: bool = False,
        only: Any = None,
    ) -> int:
        calls.append((target, shortcut, steam))
        return 0

    monkeypatch.setattr(cli, "run_install", fake_run_install)

    assert cli.main(["install", "--target", "/mnt/disk/GAMMA", "--shortcut"]) == 0
    assert calls == [(Path("/mnt/disk/GAMMA"), True, False)]


def test_main_dispatches_to_steam_shortcut(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path | None, bool, bool, bool]] = []

    def fake_run_steam_shortcut(
        target: Path | None, *, remove: bool, dry_run: bool, force: bool
    ) -> int:
        calls.append((target, remove, dry_run, force))
        return 0

    monkeypatch.setattr(cli, "run_steam_shortcut", fake_run_steam_shortcut)

    assert cli.main(["steam-shortcut", "--remove", "--dry-run"]) == 0
    assert calls == [(None, True, True, False)]


def test_main_ctrl_c_retourne_le_code_dannulation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ctrl-C est un usage documenté : jamais de traceback brute pour l'utilisateur.

    `KeyboardInterrupt` étant une `BaseException`, le `except Exception` général
    ne l'attrape pas — sans handler dédié, interrompre un `install` affichait une
    traceback au lieu du message de reprise.
    """

    def interrupted(
        target: Path | None,
        *,
        shortcut: bool,
        steam: bool = False,
        force: bool = False,
        only: Any = None,
    ) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_install", interrupted)

    assert cli.main(["install"]) == cli.CANCELLED_EXIT_CODE


def test_build_parser_update_default_target() -> None:
    args = cli.build_parser().parse_args(["update"])

    assert args.command == "update"
    assert args.target is None


def test_main_dispatches_to_update(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path | None] = []

    def fake_run_update(target: Path | None, *, force: bool, merge_modlist: bool) -> int:
        calls.append(target)
        return 0

    monkeypatch.setattr(cli, "run_update", fake_run_update)

    assert cli.main(["update", "--target", "/mnt/disk/GAMMA"]) == 0
    assert calls == [Path("/mnt/disk/GAMMA")]


def test_build_parser_accepts_global_verbose_before_subcommand() -> None:
    args = cli.build_parser().parse_args(["--verbose", "doctor"])

    assert args.verbose is True

    default_args = cli.build_parser().parse_args(["doctor"])
    assert default_args.verbose is False


def test_build_parser_doctor_default_target() -> None:
    args = cli.build_parser().parse_args(["doctor"])

    assert args.command == "doctor"
    assert args.target is None


def test_build_parser_doctor_explicit_target() -> None:
    args = cli.build_parser().parse_args(["doctor", "--target", "/tmp/game"])

    assert args.target == Path("/tmp/game")


def test_build_parser_requires_a_command() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_main_dispatches_to_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path | None] = []

    def fake_run_doctor(target: Path | None) -> int:
        calls.append(target)
        return 0

    monkeypatch.setattr(cli, "run_doctor", fake_run_doctor)

    exit_code = cli.main(["doctor", "--target", "/tmp/game"])

    assert exit_code == 0
    assert calls == [Path("/tmp/game")]


def test_main_returns_doctor_failure_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_doctor", lambda target: 1)

    assert cli.main(["doctor"]) == 1


def test_build_parser_prefix_doctor_defaults() -> None:
    args = cli.build_parser().parse_args(["prefix-doctor"])

    assert args.command == "prefix-doctor"
    assert args.target is None
    assert args.repair is False


def test_build_parser_prefix_doctor_flags() -> None:
    args = cli.build_parser().parse_args(["prefix-doctor", "--target", "/tmp/game", "--repair"])

    assert args.target == Path("/tmp/game")
    assert args.repair is True


def test_main_dispatches_to_prefix_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path | None, bool]] = []

    def fake_run_prefix_doctor(target: Path | None, *, repair: bool, force: bool) -> int:
        calls.append((target, repair))
        return 0

    monkeypatch.setattr(cli, "run_prefix_doctor", fake_run_prefix_doctor)

    exit_code = cli.main(["prefix-doctor", "--target", "/tmp/game", "--repair"])

    assert exit_code == 0
    assert calls == [(Path("/tmp/game"), True)]


def test_build_parser_verify_defaults() -> None:
    args = cli.build_parser().parse_args(["verify"])

    assert args.command == "verify"
    assert args.target is None
    assert args.repair is False


def test_build_parser_verify_flags() -> None:
    args = cli.build_parser().parse_args(["verify", "--target", "/tmp/game", "--repair"])

    assert args.target == Path("/tmp/game")
    assert args.repair is True


def test_build_parser_verify_full_est_optionnel_et_faux_par_defaut() -> None:
    """Le court-circuit taille/date est le défaut ; `--full` est le mode explicite."""
    default = cli.build_parser().parse_args(["verify"])
    full = cli.build_parser().parse_args(["verify", "--full"])

    assert default.full is False
    assert full.full is True


def test_main_dispatches_to_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path | None, bool, bool]] = []

    def fake_run_verify(target: Path | None, *, repair_damaged: bool, full_scan: bool) -> int:
        calls.append((target, repair_damaged, full_scan))
        return 0

    monkeypatch.setattr(cli, "run_verify", fake_run_verify)

    exit_code = cli.main(["verify", "--target", "/tmp/game", "--repair"])

    assert exit_code == 0
    assert calls == [(Path("/tmp/game"), True, False)]


def test_main_transmet_full_a_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []

    def fake_run_verify(target: Path | None, *, repair_damaged: bool, full_scan: bool) -> int:
        calls.append(full_scan)
        return 0

    monkeypatch.setattr(cli, "run_verify", fake_run_verify)

    assert cli.main(["verify", "--full"]) == 0
    assert calls == [True]


def test_build_parser_mo2_default_target() -> None:
    args = cli.build_parser().parse_args(["mo2"])

    assert args.command == "mo2"
    assert args.target is None


def test_main_dispatches_to_mo2(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path | None] = []

    def fake_run_mo2(target: Path | None) -> int:
        calls.append(target)
        return 0

    monkeypatch.setattr(cli, "run_mo2", fake_run_mo2)

    assert cli.main(["mo2", "--target", "/tmp/game"]) == 0
    assert calls == [Path("/tmp/game")]


def test_build_parser_play_defaults() -> None:
    args = cli.build_parser().parse_args(["play"])

    assert args.command == "play"
    assert args.target is None
    assert args.flat is False
    assert args.executable == "Anomaly (DX11)"


def test_main_dispatches_to_play_with_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_play(
        target: Path | None,
        *,
        flat_mode: bool,
        executable: str,
        performance: Settings,
    ) -> int:
        captured.update(
            target=target,
            flat_mode=flat_mode,
            executable=executable,
            performance=performance,
        )
        return 0

    monkeypatch.setattr(cli, "run_play", fake_run_play)

    exit_code = cli.main(
        [
            "play",
            "--target",
            "/tmp/g",
            "--flat",
            "--executable",
            "Anomaly (DX10)",
            "--no-gamemode",
        ]
    )

    assert exit_code == 0
    assert captured == {
        "target": Path("/tmp/g"),
        "flat_mode": True,
        "executable": "Anomaly (DX10)",
        "performance": Settings(gamemode=False),
    }


def test_main_play_enables_gamemode_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_play(target: Path | None, **kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(cli, "run_play", fake_run_play)

    assert cli.main(["play"]) == 0
    assert captured["performance"] == Settings()


def test_main_play_performance_layers_are_all_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aucune couche de rendu sans demande explicite : `play` nu n'active rien."""
    captured: dict[str, object] = {}
    monkeypatch.setattr(cli, "run_play", lambda target, **kw: captured.update(kw) or 0)

    cli.main(["play"])
    settings = captured["performance"]

    assert isinstance(settings, Settings)
    assert not settings.any_layer_requested
    assert settings.gamemode is True


def test_main_play_accepts_the_performance_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(cli, "run_play", lambda target, **kw: captured.update(kw) or 0)

    cli.main(
        [
            "play",
            "--mangohud",
            "--mangohud-preset",
            "full",
            "--gamescope",
            "--gamescope-render",
            "1280x720",
            "--gamescope-output",
            "2560x1440",
            "--fsr-sharpness",
            "5",
            "--windowed",
            "--vkbasalt",
        ]
    )
    settings = captured["performance"]

    assert isinstance(settings, Settings)
    assert settings.mangohud and settings.mangohud_preset is Preset.FULL
    assert settings.vkbasalt
    assert settings.gamescope
    options = settings.gamescope_options
    assert (str(options.render), str(options.output)) == ("1280x720", "2560x1440")
    assert options.fsr and options.sharpness == 5
    assert options.fullscreen is False


def test_main_play_clamps_an_out_of_range_sharpness(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(cli, "run_play", lambda target, **kw: captured.update(kw) or 0)

    cli.main(["play", "--gamescope", "--fsr-sharpness", "99"])
    settings = captured["performance"]

    assert isinstance(settings, Settings)
    assert settings.gamescope_options.sharpness == 20


def test_main_play_rejects_a_malformed_resolution() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["play", "--gamescope-render", "1280"])


def test_main_play_returns_run_play_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_play", lambda *a, **k: 1)

    assert cli.main(["play"]) == 1


def test_build_parser_shortcut_default_target() -> None:
    args = cli.build_parser().parse_args(["shortcut"])

    assert args.command == "shortcut"
    assert args.target is None


def test_build_parser_postmortem_defaults() -> None:
    args = cli.build_parser().parse_args(["postmortem"])

    assert args.command == "postmortem"
    assert args.target is None


def test_main_dispatches_to_postmortem(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path | None] = []

    def fake_run_postmortem(target: Path | None) -> int:
        calls.append(target)
        return 0

    monkeypatch.setattr(cli, "run_postmortem", fake_run_postmortem)

    assert cli.main(["postmortem", "--target", "/mnt/disk/GAMMA"]) == 0
    assert calls == [Path("/mnt/disk/GAMMA")]


def test_main_postmortem_propage_le_code_de_retour(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non nul quand il y a quelque chose à corriger — même convention que `doctor`."""
    monkeypatch.setattr(cli, "run_postmortem", lambda target: 1)

    assert cli.main(["postmortem"]) == 1


def test_main_dispatches_to_shortcut(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path | None] = []

    def fake_run_shortcut(target: Path | None) -> int:
        calls.append(target)
        return 0

    monkeypatch.setattr(cli, "run_shortcut", fake_run_shortcut)

    assert cli.main(["shortcut", "--target", "/tmp/game"]) == 0
    assert calls == [Path("/tmp/game")]


def test_main_shortcut_returns_run_shortcut_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_shortcut", lambda target: 1)

    assert cli.main(["shortcut"]) == 1


def test_main_reports_unexpected_exception_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(target: Path | None) -> int:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli, "run_doctor", boom)

    exit_code = cli.main(["doctor"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "Error" in out
    assert "log" in out.lower()


def test_main_forwards_only_steps_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_install(target: Path | None, **kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(cli, "run_install", fake_run_install)

    assert cli.main(["install", "--only", "prefix", "mo2"]) == 0
    assert captured["only"] == ["prefix", "mo2"]


def test_build_parser_rejects_an_unknown_only_step() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["install", "--only", "prefixe"])


def test_build_parser_uninstall_yes_defaults_to_false() -> None:
    args = cli.build_parser().parse_args(["uninstall"])

    assert args.yes is False


def test_build_parser_uninstall_yes_flag() -> None:
    args = cli.build_parser().parse_args(["uninstall", "--game-data", "--yes"])

    assert args.yes is True


def test_main_dispatches_to_uninstall_with_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_uninstall(target: Path | None, **kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(cli, "run_uninstall", fake_run_uninstall)

    assert cli.main(["uninstall", "--game-data", "--yes"]) == 0
    assert captured["assume_yes"] is True
    assert captured["game_data"] is True


class TestRefusDesChemins:
    """`--target`/`source` porteurs d'un caractère de contrôle : refus avant tout travail.

    Le refus tient à la frontière (`cli._validate_path_arguments`), donc AUCUNE
    commande n'est appelée — c'est ce que vérifient ces tests, plutôt que le seul
    code de sortie.
    """

    @pytest.mark.parametrize("payload", ["/tmp/a\nExec=/bin/sh", "/tmp/a\x00b", "/tmp/a\x7fb"])
    def test_shortcut_refuse_sans_appeler_la_commande(
        self, payload: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[Path | None] = []
        monkeypatch.setattr(cli, "run_shortcut", lambda target: calls.append(target) or 0)

        assert cli.main(["shortcut", "--target", payload]) == 1
        assert calls == []

    def test_import_refuse_aussi_sur_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`source` est un chemin utilisateur au même titre que `--target`."""
        calls: list[tuple[Path, Path | None]] = []

        def fake_run_import(source: Path, target: Path | None, *, dry_run: bool) -> int:
            calls.append((source, target))
            return 0

        monkeypatch.setattr(cli, "run_import", fake_run_import)

        assert cli.main(["import", "/tmp/a\nExec=/bin/sh"]) == 1
        assert calls == []

    def test_un_chemin_normal_passe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[Path | None] = []
        monkeypatch.setattr(cli, "run_shortcut", lambda target: calls.append(target) or 0)

        assert cli.main(["shortcut", "--target", "/tmp/game"]) == 0
        assert calls == [Path("/tmp/game")]

    def test_aucun_fichier_desktop_nest_ecrit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Critère d'acceptation 1 : sortie en erreur, et rien sur le disque.

        `XDG_DATA_HOME` redirige les chemins freedesktop sous `tmp_path` : si le
        refus arrivait trop tard, `install_shortcut` y aurait déposé le
        `.desktop` piégé (qu'il rend ensuite exécutable, chmod 0o755).
        """
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

        assert cli.main(["shortcut", "--target", "/tmp/a\nExec=/bin/sh"]) == 1
        assert not (tmp_path / "applications").exists()


def test_build_parser_backup_defaults_to_every_set() -> None:
    """« Sauvegarder » sans précision doit tout couvrir : c'est le geste avant de bricoler."""
    args = cli.build_parser().parse_args(["backup"])

    assert cli._selected_sets(args) == ALL_SETS


def test_build_parser_backup_honours_a_single_set() -> None:
    args = cli.build_parser().parse_args(["backup", "--saves"])

    assert cli._selected_sets(args) == (BackupSet.SAVES,)


def test_main_dispatches_to_backup(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Path | None, tuple[BackupSet, ...], bool]] = []

    def fake_run_backup(
        target: Path | None, *, sets: tuple[BackupSet, ...], list_only: bool
    ) -> int:
        calls.append((target, sets, list_only))
        return 0

    monkeypatch.setattr(cli, "run_backup", fake_run_backup)

    assert cli.main(["backup", "--target", "/mnt/disk/GAMMA", "--profiles", "--saves"]) == 0
    assert calls == [(Path("/mnt/disk/GAMMA"), (BackupSet.PROFILES, BackupSet.SAVES), False)]


def test_main_dispatches_to_backup_list(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bool] = []

    def fake_run_backup(
        _target: Path | None, *, sets: tuple[BackupSet, ...], list_only: bool
    ) -> int:
        seen.append(list_only)
        return 0

    monkeypatch.setattr(cli, "run_backup", fake_run_backup)

    assert cli.main(["backup", "--list"]) == 0
    assert seen == [True]


def test_main_dispatches_to_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Path | None, bool, bool]] = []

    def fake_run_restore(
        identifier: str, target: Path | None, *, dry_run: bool, force: bool
    ) -> int:
        calls.append((identifier, target, dry_run, force))
        return 0

    monkeypatch.setattr(cli, "run_restore", fake_run_restore)

    code = cli.main(
        ["restore", "profiles-20260907-142530", "--target", "/mnt/disk/GAMMA", "--dry-run"]
    )

    assert code == 0
    assert calls == [("profiles-20260907-142530", Path("/mnt/disk/GAMMA"), True, False)]


def test_main_dispatches_update_without_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bool] = []

    def fake_run_update(_target: Path | None, *, force: bool, merge_modlist: bool) -> int:
        seen.append(merge_modlist)
        return 0

    monkeypatch.setattr(cli, "run_update", fake_run_update)

    assert cli.main(["update", "--no-merge"]) == 0
    assert seen == [False]
