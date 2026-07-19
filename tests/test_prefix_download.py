import hashlib
import tarfile
from pathlib import Path

import pytest

from stalker_gamma_linux.prefix import download
from stalker_gamma_linux.prefix.errors import ChecksumMismatchError, ProtonDownloadError

RELEASE = "GE-Proton10-34"


def _make_release_archive(tmp_path: Path) -> tuple[bytes, str]:
    source = tmp_path / "upstream" / RELEASE
    source.mkdir(parents=True)
    (source / "proton").write_text("#!/bin/sh\n")
    archive = tmp_path / "upstream" / f"{RELEASE}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source, arcname=RELEASE)
    data = archive.read_bytes()
    return data, hashlib.sha512(data).hexdigest()


def _patch_remote(
    monkeypatch: pytest.MonkeyPatch, archive_bytes: bytes, checksum_line: str
) -> list[str]:
    fetched_urls: list[str] = []

    def fake_read_remote_text(url: str) -> str:
        fetched_urls.append(url)
        return checksum_line

    def fake_download_to(url: str, dest: Path) -> None:
        fetched_urls.append(url)
        dest.write_bytes(archive_bytes)

    monkeypatch.setattr(download, "_read_remote_text", fake_read_remote_text)
    monkeypatch.setattr(download, "_download_to", fake_download_to)
    return fetched_urls


def test_download_extracts_verified_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, digest = _make_release_archive(tmp_path)
    _patch_remote(monkeypatch, data, f"{digest}  {RELEASE}.tar.gz\n")
    install_dir = tmp_path / "compatibilitytools.d"

    result = download.download_proton_ge(RELEASE, install_dir)

    assert result == install_dir / RELEASE
    assert (result / "proton").is_file()


def test_download_is_idempotent_when_build_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_dir = tmp_path / "compatibilitytools.d"
    existing = install_dir / RELEASE
    existing.mkdir(parents=True)
    (existing / "proton").write_text("#!/bin/sh\n")

    def fail_fetch(*args: object) -> None:
        raise AssertionError("aucun accès réseau attendu quand le build est déjà présent")

    monkeypatch.setattr(download, "_read_remote_text", fail_fetch)
    monkeypatch.setattr(download, "_download_to", fail_fetch)

    assert download.download_proton_ge(RELEASE, install_dir) == existing


def test_download_replaces_broken_partial_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, digest = _make_release_archive(tmp_path)
    _patch_remote(monkeypatch, data, f"{digest}  {RELEASE}.tar.gz\n")
    install_dir = tmp_path / "compatibilitytools.d"
    broken = install_dir / RELEASE
    broken.mkdir(parents=True)
    (broken / "reste-extraction-interrompue").write_text("")

    result = download.download_proton_ge(RELEASE, install_dir)

    assert (result / "proton").is_file()
    assert not (result / "reste-extraction-interrompue").exists()


def test_download_rejects_checksum_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, _ = _make_release_archive(tmp_path)
    wrong = "0" * 128
    _patch_remote(monkeypatch, data, f"{wrong}  {RELEASE}.tar.gz\n")
    install_dir = tmp_path / "compatibilitytools.d"

    with pytest.raises(ChecksumMismatchError) as excinfo:
        download.download_proton_ge(RELEASE, install_dir)

    assert excinfo.value.release == RELEASE
    assert not (install_dir / RELEASE).exists()


def test_download_rejects_unreadable_checksum_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, _ = _make_release_archive(tmp_path)
    _patch_remote(monkeypatch, data, "<html>Not Found</html>")

    with pytest.raises(ProtonDownloadError):
        download.download_proton_ge(RELEASE, tmp_path / "compatibilitytools.d")


def test_download_wraps_network_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_fetch(url: str) -> str:
        raise OSError("réseau injoignable")

    monkeypatch.setattr(download, "_read_remote_text", fail_fetch)

    with pytest.raises(ProtonDownloadError) as excinfo:
        download.download_proton_ge(RELEASE, tmp_path / "compatibilitytools.d")

    assert "réseau injoignable" in str(excinfo.value)


def test_download_rejects_archive_without_proton_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "upstream" / RELEASE
    source.mkdir(parents=True)
    (source / "notes.txt").write_text("vide")
    archive = tmp_path / "upstream" / f"{RELEASE}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source, arcname=RELEASE)
    data = archive.read_bytes()
    digest = hashlib.sha512(data).hexdigest()
    _patch_remote(monkeypatch, data, f"{digest}  {RELEASE}.tar.gz\n")
    install_dir = tmp_path / "compatibilitytools.d"

    with pytest.raises(ProtonDownloadError):
        download.download_proton_ge(RELEASE, install_dir)

    assert not (install_dir / RELEASE).exists()
