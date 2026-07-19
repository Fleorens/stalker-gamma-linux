from pathlib import Path

from stalker_gamma_linux.engine.paths import InstallPaths


def test_under_builds_standard_tree() -> None:
    paths = InstallPaths.under(Path("/games/stalker-gamma"))

    assert paths.anomaly == Path("/games/stalker-gamma/anomaly")
    assert paths.gamma == Path("/games/stalker-gamma/gamma")
    assert paths.cache == Path("/games/stalker-gamma/cache")


def test_ensure_directories_creates_missing_dirs(tmp_path: Path) -> None:
    paths = InstallPaths.under(tmp_path / "stalker-gamma")

    paths.ensure_directories()

    assert paths.anomaly.is_dir()
    assert paths.gamma.is_dir()
    assert paths.cache.is_dir()


def test_ensure_directories_is_idempotent_and_non_destructive(tmp_path: Path) -> None:
    paths = InstallPaths.under(tmp_path / "stalker-gamma")
    paths.ensure_directories()
    marker = paths.cache / "already-downloaded.7z"
    marker.write_text("cached")

    paths.ensure_directories()

    assert marker.read_text() == "cached"
