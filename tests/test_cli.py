from pathlib import Path

import pytest

from stalker_gamma_linux import cli


def test_build_parser_install_default_target() -> None:
    args = cli.build_parser().parse_args(["install"])

    assert args.command == "install"
    assert args.target is None


def test_main_dispatches_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Path | None] = []

    def fake_run_install(target: Path | None) -> int:
        calls.append(target)
        return 0

    monkeypatch.setattr(cli, "run_install", fake_run_install)

    assert cli.main(["install", "--target", "/mnt/disk/GAMMA"]) == 0
    assert calls == [Path("/mnt/disk/GAMMA")]


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

    def fake_run_prefix_doctor(target: Path | None, *, repair: bool) -> int:
        calls.append((target, repair))
        return 0

    monkeypatch.setattr(cli, "run_prefix_doctor", fake_run_prefix_doctor)

    exit_code = cli.main(["prefix-doctor", "--target", "/tmp/game", "--repair"])

    assert exit_code == 0
    assert calls == [(Path("/tmp/game"), True)]


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
    assert args.no_diagnose is False
    assert args.executable == "Anomaly (DX11)"


def test_main_dispatches_to_play_with_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_play(
        target: Path | None, *, flat_mode: bool, executable: str, diagnose: bool
    ) -> int:
        captured.update(
            target=target, flat_mode=flat_mode, executable=executable, diagnose=diagnose
        )
        return 0

    monkeypatch.setattr(cli, "run_play", fake_run_play)

    exit_code = cli.main(
        ["play", "--target", "/tmp/g", "--flat", "--executable", "Anomaly (DX10)", "--no-diagnose"]
    )

    assert exit_code == 0
    assert captured == {
        "target": Path("/tmp/g"),
        "flat_mode": True,
        "executable": "Anomaly (DX10)",
        "diagnose": False,
    }


def test_main_play_returns_run_play_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_play", lambda *a, **k: 1)

    assert cli.main(["play"]) == 1


def test_build_parser_shortcut_default_target() -> None:
    args = cli.build_parser().parse_args(["shortcut"])

    assert args.command == "shortcut"
    assert args.target is None


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
