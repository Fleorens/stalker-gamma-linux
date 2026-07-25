from pathlib import Path

import pytest

from stalker_gamma_linux import presence
from stalker_gamma_linux.environment import system


def _only_present(monkeypatch: pytest.MonkeyPatch, present: set[Path]) -> None:
    resolved = {str(p) for p in present}
    monkeypatch.setattr(system, "path_exists", lambda p: str(p) in resolved)


def test_installed_when_anomaly_and_mo2_present(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path("/games/gamma")
    _only_present(
        monkeypatch,
        {root / "anomaly" / "AnomalyLauncher.exe", root / "gamma" / "ModOrganizer.exe"},
    )

    assert presence.is_installed_on_disk(root)


def test_not_installed_when_mo2_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path("/games/gamma")
    _only_present(monkeypatch, {root / "anomaly" / "AnomalyLauncher.exe"})

    assert not presence.is_installed_on_disk(root)


def test_not_installed_when_anomaly_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path("/games/gamma")
    _only_present(monkeypatch, {root / "gamma" / "ModOrganizer.exe"})

    assert not presence.is_installed_on_disk(root)


def test_installed_with_nested_anomaly_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    # Layout GAMMA réel constaté : Anomaly imbriqué dans l'instance (<gamma>/anomaly),
    # pas en sibling — `resolve_anomaly` doit le retrouver.
    root = Path("/mnt/games/GAMMA/gamma")
    _only_present(
        monkeypatch,
        {
            root / "gamma" / "anomaly" / "AnomalyLauncher.exe",
            root / "gamma" / "ModOrganizer.exe",
        },
    )

    assert presence.is_installed_on_disk(root)


def test_not_installed_on_empty_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    _only_present(monkeypatch, set())

    assert not presence.is_installed_on_disk(Path("/games/gamma"))
