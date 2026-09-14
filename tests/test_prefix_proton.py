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


def test_parse_ge_version_accepts_x86_64_suffix() -> None:
    """Nom historique/manuel encore répandu (ex. ProtonUp-Qt) — issue GitHub,
    Fedora 44, 0.6.0 : rejeté avant, ce qui laissait sélectionner Proton
    Experimental à sa place."""
    assert proton.parse_ge_version("GE-Proton11-6-x86_64") == (11, 6)


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


def _make_experimental(tmp_path: Path) -> Path:
    common = tmp_path / "steamapps" / "common"
    _make_build(common, proton.PROTON_EXPERIMENTAL)
    return common


def test_find_proton_builds_detects_steam_experimental(tmp_path: Path) -> None:
    common = _make_experimental(tmp_path)

    builds = proton.find_proton_builds([tmp_path / "compat"], [common])

    assert [build.name for build in builds] == [proton.PROTON_EXPERIMENTAL]
    assert builds[0].version is None


def test_select_proton_build_prefers_ge_over_experimental(tmp_path: Path) -> None:
    compat = tmp_path / "compat"
    _make_build(compat, "GE-Proton10-34")
    common = _make_experimental(tmp_path)

    selected = proton.select_proton_build(proton.find_proton_builds([compat], [common]))

    assert selected is not None
    assert selected.name == "GE-Proton10-34"


def test_select_proton_build_prefers_ge_with_x86_64_suffix_over_experimental(
    tmp_path: Path,
) -> None:
    compat = tmp_path / "compat"
    _make_build(compat, "GE-Proton11-6-x86_64")
    common = _make_experimental(tmp_path)

    selected = proton.select_proton_build(proton.find_proton_builds([compat], [common]))

    assert selected is not None
    assert selected.name == "GE-Proton11-6-x86_64"
    assert selected.version == (11, 6)


def test_select_proton_build_prefers_experimental_over_other_non_ge(tmp_path: Path) -> None:
    compat = tmp_path / "compat"
    _make_build(compat, "UMU-Proton-9.0-3")
    common = _make_experimental(tmp_path)

    selected = proton.select_proton_build(proton.find_proton_builds([compat], [common]))

    assert selected is not None
    assert selected.name == proton.PROTON_EXPERIMENTAL


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
        release: str | None = None,
        install_dir: Path | None = None,
        *,
        on_progress: object = None,
        cancel_event: object = None,
    ) -> Path:
        captured["install_dir"] = install_dir
        assert install_dir is not None
        # release=None = dernière release publiée ; le repli suffit pour le test.
        return _make_build(install_dir, release or download.FALLBACK_GE_RELEASE)

    monkeypatch.setattr(download, "download_proton_ge", fake_download)

    build = proton.ensure_proton([tmp_path])

    assert captured["install_dir"] == tmp_path
    assert build.name == download.FALLBACK_GE_RELEASE
    assert build.version is not None
    assert build.path == tmp_path / download.FALLBACK_GE_RELEASE


def test_ensure_proton_downloads_ge_even_if_experimental_is_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bug rapporté (issue GitHub, Fedora 44, 0.6.0) : sans GE installé,
    `select_proton_build` retient Proton Experimental — mais il n'a pas
    `protonfixes`, qu'umu-run exige pour créer le préfixe/poser les verbs.
    `ensure_proton` doit donc télécharger un GE plutôt que renvoyer
    Experimental tel quel.

    `search_dirs=None` (comme en usage réel, via la CLI) : c'est le seul cas où
    `find_proton_builds` regarde aussi `steam_common_dirs`, là où vit
    Experimental (voir sa docstring)."""
    compat = tmp_path / "compat"
    common = tmp_path / "steamapps" / "common"
    _make_build(common, proton.PROTON_EXPERIMENTAL)
    monkeypatch.setattr(proton, "default_search_dirs", lambda: (compat,))
    monkeypatch.setattr(proton, "default_steam_common_dirs", lambda: (common,))

    def fake_download(
        release: str | None = None,
        install_dir: Path | None = None,
        *,
        on_progress: object = None,
        cancel_event: object = None,
    ) -> Path:
        # ensure_proton() sans search_dirs (comme la CLI) passe install_dir=None ;
        # seul le vrai `download_proton_ge` sait retomber sur le Steam par défaut.
        assert install_dir is None
        return _make_build(compat, release or download.FALLBACK_GE_RELEASE)

    monkeypatch.setattr(download, "download_proton_ge", fake_download)

    build = proton.ensure_proton()

    assert build.name == download.FALLBACK_GE_RELEASE
    assert build.version is not None
