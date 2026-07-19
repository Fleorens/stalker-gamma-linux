from pathlib import Path

import pytest

from stalker_gamma_linux.prefix import download, proton


def _make_build(directory: Path, name: str) -> Path:
    build = directory / name
    build.mkdir(parents=True)
    (build / "proton").write_text("#!/bin/sh\n")
    return build


def test_parse_ge_version() -> None:
    assert proton.parse_ge_version("GE-Proton10-34") == (10, 34)
    assert proton.parse_ge_version("GE-Proton9-7") == (9, 7)
    assert proton.parse_ge_version("UMU-Proton-9.0-3") is None
    assert proton.parse_ge_version("Proton 9.0") is None


def test_find_proton_builds_keeps_only_dirs_with_proton_executable(tmp_path: Path) -> None:
    _make_build(tmp_path, "GE-Proton10-34")
    (tmp_path / "pas-un-proton").mkdir()

    builds = proton.find_proton_builds([tmp_path])

    assert [build.name for build in builds] == ["GE-Proton10-34"]
    assert builds[0].version == (10, 34)


def test_find_proton_builds_skips_missing_dirs_and_dedupes(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _make_build(first, "GE-Proton10-34")
    _make_build(second, "GE-Proton10-34")
    _make_build(second, "GE-Proton9-7")

    builds = proton.find_proton_builds([tmp_path / "absent", first, second])

    names = [build.name for build in builds]
    assert names == ["GE-Proton10-34", "GE-Proton9-7"]
    assert builds[0].path == first / "GE-Proton10-34"


def test_select_proton_build_prefers_most_recent_ge(tmp_path: Path) -> None:
    _make_build(tmp_path, "GE-Proton9-7")
    _make_build(tmp_path, "GE-Proton10-34")
    _make_build(tmp_path, "UMU-Proton-9.0-3")

    selected = proton.select_proton_build(proton.find_proton_builds([tmp_path]))

    assert selected is not None
    assert selected.name == "GE-Proton10-34"


def test_select_proton_build_falls_back_to_non_ge(tmp_path: Path) -> None:
    _make_build(tmp_path, "UMU-Proton-9.0-3")

    selected = proton.select_proton_build(proton.find_proton_builds([tmp_path]))

    assert selected is not None
    assert selected.name == "UMU-Proton-9.0-3"


def test_select_proton_build_returns_none_without_builds() -> None:
    assert proton.select_proton_build([]) is None


def test_ensure_proton_returns_installed_without_downloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_build(tmp_path, "GE-Proton10-34")

    def fail_download(*args: object, **kwargs: object) -> Path:
        raise AssertionError("download_proton_ge ne doit pas être appelé")

    monkeypatch.setattr(download, "download_proton_ge", fail_download)

    build = proton.ensure_proton([tmp_path])

    assert build.name == "GE-Proton10-34"


def test_ensure_proton_downloads_into_first_search_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_download(
        release: str = download.RECOMMENDED_GE_RELEASE,
        install_dir: Path | None = None,
        *,
        on_progress: object = None,
    ) -> Path:
        captured["install_dir"] = install_dir
        assert install_dir is not None
        return _make_build(install_dir, release).parent / release

    monkeypatch.setattr(download, "download_proton_ge", fake_download)

    build = proton.ensure_proton([tmp_path])

    assert captured["install_dir"] == tmp_path
    assert build.name == download.RECOMMENDED_GE_RELEASE
    assert build.version is not None
    assert build.path == tmp_path / download.RECOMMENDED_GE_RELEASE
