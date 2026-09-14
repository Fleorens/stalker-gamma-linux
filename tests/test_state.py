import logging
from pathlib import Path

import pytest

from stalker_gamma_linux import state
from stalker_gamma_linux.logging_setup import LOGGER_NAME


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


def test_load_state_tolerates_corrupt_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert "[ TODO ]" in text
    for label in state.STEP_LABELS.values():
        assert label in text


def _failure(
    name: str = "Boomsticks and Sharpsticks", cause: str = "MOD_LINK_BROKEN"
) -> state.FailedMod:
    return state.FailedMod(
        name=name,
        cause=cause,
        detail=f"gamma-launcher full-install failed on {name}",
        recorded_at="2026-09-14T12:00:00+00:00",
        archive_name="Boomsticks_and_Sharpsticks_1.4.7z",
        expected_md5="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )


class TestFailedMods:
    """Mémoire des mods en échec (T22) — ce qui alimente `install --retry-failed`."""

    def test_load_failures_is_empty_by_default(self, tmp_path: Path) -> None:
        assert state.load_failures(tmp_path / "install") == ()

    def test_record_failure_persists_and_reloads(self, tmp_path: Path) -> None:
        target = tmp_path / "install"
        failure = _failure()

        state.record_failure(target, failure)

        assert state.load_failures(target) == (failure,)

    def test_recording_the_same_mod_again_replaces_it(self, tmp_path: Path) -> None:
        target = tmp_path / "install"
        state.record_failure(target, _failure(cause="NETWORK_UNREACHABLE"))

        state.record_failure(target, _failure(cause="MOD_LINK_BROKEN"))

        failures = state.load_failures(target)
        assert len(failures) == 1
        assert failures[0].cause == "MOD_LINK_BROKEN"

    def test_recording_does_not_disturb_step_progress(self, tmp_path: Path) -> None:
        target = tmp_path / "install"
        state.mark_done(target, "anomaly")

        state.record_failure(target, _failure())

        assert state.load_state(target).is_done("anomaly")

    def test_marking_a_step_done_does_not_disturb_recorded_failures(self, tmp_path: Path) -> None:
        target = tmp_path / "install"
        state.record_failure(target, _failure())

        state.mark_done(target, "anomaly")

        assert state.load_failures(target) == (_failure(),)

    def test_clear_failure_removes_only_the_named_mod(self, tmp_path: Path) -> None:
        target = tmp_path / "install"
        state.record_failure(target, _failure(name="Mod A"))
        state.record_failure(target, _failure(name="Mod B"))

        state.clear_failure(target, "Mod A")

        remaining = [f.name for f in state.load_failures(target)]
        assert remaining == ["Mod B"]

    def test_clear_failure_is_silent_when_the_mod_is_not_recorded(self, tmp_path: Path) -> None:
        target = tmp_path / "install"

        state.clear_failure(target, "Nothing there")  # ne lève pas

        assert state.load_failures(target) == ()

    def test_clear_all_failures_empties_the_list(self, tmp_path: Path) -> None:
        target = tmp_path / "install"
        state.record_failure(target, _failure(name="Mod A"))
        state.record_failure(target, _failure(name="Mod B"))

        state.clear_all_failures(target)

        assert state.load_failures(target) == ()

    def test_failures_are_keyed_per_target(self, tmp_path: Path) -> None:
        first = tmp_path / "install-a"
        second = tmp_path / "install-b"
        state.record_failure(first, _failure())

        assert state.load_failures(first) != ()
        assert state.load_failures(second) == ()

    def test_format_failures_is_empty_for_no_failures(self) -> None:
        assert state.format_failures(()) == ""

    def test_format_failures_lists_every_mod_and_points_to_retry_failed(self) -> None:
        text = state.format_failures((_failure(name="Mod A"), _failure(name="Mod B")))

        assert "Mod A" in text
        assert "Mod B" in text
        assert "install --retry-failed" in text


class TestCorruptStateFile:
    """Un état illisible ne doit pas disparaître en silence (re-vérification MD5 inexpliquée)."""

    def _corrupt(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        path = state.state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ceci n'est pas du TOML [[[", encoding="utf-8")
        return path

    def test_repart_dun_etat_vide(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._corrupt(monkeypatch, tmp_path)

        assert state.load_state(tmp_path / "install") == state.InstallState()

    def test_le_fichier_est_mis_en_quarantaine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = self._corrupt(monkeypatch, tmp_path)
        original = path.read_text(encoding="utf-8")

        state.load_state(tmp_path / "install")

        quarantined = path.with_suffix(f"{path.suffix}.corrupt")
        assert quarantined.read_text(encoding="utf-8") == original
        assert not path.exists()

    def test_lavertissement_est_journalise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._corrupt(monkeypatch, tmp_path)

        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            state.load_state(tmp_path / "install")

        assert any("unreadable" in record.message for record in caplog.records)

    def test_marquer_une_etape_apres_corruption_repart_proprement(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._corrupt(monkeypatch, tmp_path)
        target = tmp_path / "install"

        updated = state.mark_done(target, "anomaly")

        assert updated.is_done("anomaly")
        assert state.load_state(target).is_done("anomaly")
