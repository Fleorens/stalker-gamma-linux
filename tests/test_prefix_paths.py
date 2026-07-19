from pathlib import Path

from stalker_gamma_linux.prefix.paths import PrefixPaths


def test_under_builds_standard_layout() -> None:
    paths = PrefixPaths.under(Path("/games/stalker-gamma"))

    assert paths.prefix == Path("/games/stalker-gamma/prefix")
    assert paths.logs == Path("/games/stalker-gamma/logs")


def test_wine_root_falls_back_to_prefix_without_pfx(tmp_path: Path) -> None:
    paths = PrefixPaths.under(tmp_path)
    paths.prefix.mkdir(parents=True)

    assert paths.wine_root == paths.prefix


def test_wine_root_uses_pfx_subdirectory_when_present(tmp_path: Path) -> None:
    paths = PrefixPaths.under(tmp_path)
    (paths.prefix / "pfx").mkdir(parents=True)

    assert paths.wine_root == paths.prefix / "pfx"


def test_derived_paths_follow_wine_root(tmp_path: Path) -> None:
    paths = PrefixPaths.under(tmp_path)
    (paths.prefix / "pfx").mkdir(parents=True)

    assert paths.winetricks_log == paths.prefix / "pfx" / "winetricks.log"
    assert paths.system32 == paths.prefix / "pfx" / "drive_c" / "windows" / "system32"
    assert paths.version_file == paths.prefix / "version"


def test_ensure_directories_is_idempotent(tmp_path: Path) -> None:
    paths = PrefixPaths.under(tmp_path)

    paths.ensure_directories()
    paths.ensure_directories()

    assert paths.prefix.is_dir()
    assert paths.logs.is_dir()
