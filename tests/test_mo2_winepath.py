from pathlib import Path

import pytest

from stalker_gamma_linux.mo2 import winepath


def test_absolute_path_maps_to_z_drive_with_backslashes() -> None:
    result = winepath.to_windows_path("/home/florian/Games/stalker-gamma/anomaly")

    assert result == r"Z:\home\florian\Games\stalker-gamma\anomaly"


def test_root_maps_to_z_backslash() -> None:
    assert winepath.to_windows_path("/") == "Z:\\"


def test_accepts_pathlib_path() -> None:
    assert winepath.to_windows_path(Path("/opt/game")) == r"Z:\opt\game"


def test_normalizes_dot_and_double_slash() -> None:
    assert winepath.to_windows_path("/home//florian/./anomaly") == r"Z:\home\florian\anomaly"


def test_resolves_parent_segments_textually() -> None:
    # `..` retire le segment précédent (`florian`), pas `home`.
    assert winepath.to_windows_path("/home/florian/../root/anomaly") == r"Z:\home\root\anomaly"


def test_relative_path_is_rejected() -> None:
    with pytest.raises(ValueError):
        winepath.to_windows_path("home/florian/anomaly")
