from pathlib import Path

import pytest

from stalker_gamma_linux import state


def test_load_state_defaults_to_nothing_done(tmp_path: Path) -> None:
    result = state.load_state(tmp_path / "install")

    assert result == state.InstallState()
    for step in state.STEPS:
        assert not result.is_done(step)


def test_mark_done_persists_and_reloads(tmp_path: Path) -> None:
    target = tmp_path / "install"

    updated = state.mark_done(target, "anomaly")

    assert updated.is_done("anomaly")
    assert not updated.is_done("gamma")
    assert state.load_state(target).is_done("anomaly")


def test_mark_done_is_cumulative(tmp_path: Path) -> None:
    target = tmp_path / "install"

    state.mark_done(target, "anomaly")
    state.mark_done(target, "gamma")
    result = state.load_state(target)

    assert result.is_done("anomaly")
    assert result.is_done("gamma")
    assert not result.is_done("prefix")


def test_state_is_keyed_per_target(tmp_path: Path) -> None:
    first = tmp_path / "install-a"
    second = tmp_path / "install-b"

    state.mark_done(first, "anomaly")

    assert state.load_state(first).is_done("anomaly")
    assert not state.load_state(second).is_done("anomaly")


def test_mark_done_rejects_unknown_step(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not-a-step"):
        state.mark_done(tmp_path / "install", "not-a-step")


def test_load_state_tolerates_corrupt_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    state.state_file().parent.mkdir(parents=True, exist_ok=True)
    state.state_file().write_text("not valid toml [[[", encoding="utf-8")

    result = state.load_state(tmp_path / "install")

    assert result == state.InstallState()


def test_format_state_lists_every_step(tmp_path: Path) -> None:
    target = tmp_path / "install"
    state.mark_done(target, "anomaly")

    text = state.format_state(state.load_state(target), target)

    assert str(target) in text
    assert "[ OK ]" in text
    assert "[ A FAIRE ]" in text
    for label in state.STEP_LABELS.values():
        assert label in text
