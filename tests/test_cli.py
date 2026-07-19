from pathlib import Path

import pytest

from stalker_gamma_linux import cli


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
