from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path

import pytest

from stalker_gamma_linux.prefix import download
from stalker_gamma_linux.prefix.errors import (
    ChecksumMismatchError,
    ProtonDownloadError,
    TruncatedDownloadError,
)

RELEASE = "GE-Proton10-34"


def _make_release_archive(tmp_path: Path, release: str = RELEASE) -> tuple[bytes, str]:
    source = tmp_path / "upstream" / release
    source.mkdir(parents=True)
    (source / "proton").write_text("#!/bin/sh\n")
    archive = tmp_path / "upstream" / f"{release}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source, arcname=release)
    data = archive.read_bytes()
    return data, hashlib.sha512(data).hexdigest()


def _patch_remote(
    monkeypatch: pytest.MonkeyPatch, archive_bytes: bytes, checksum_line: str
) -> list[str]:
    fetched_urls: list[str] = []

    def fake_read_remote_text(url: str) -> str:
        fetched_urls.append(url)
        return checksum_line

    def fake_download_to(url: str, dest: Path, **kwargs: object) -> None:
        fetched_urls.append(url)
        dest.write_bytes(archive_bytes)

    monkeypatch.setattr(download, "read_remote_text", fake_read_remote_text)
    monkeypatch.setattr(download, "download_to", fake_download_to)
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

    monkeypatch.setattr(download, "read_remote_text", fail_fetch)
    monkeypatch.setattr(download, "download_to", fail_fetch)

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

    monkeypatch.setattr(download, "read_remote_text", fail_fetch)

    with pytest.raises(ProtonDownloadError) as excinfo:
        download.download_proton_ge(RELEASE, tmp_path / "compatibilitytools.d")

    assert "réseau injoignable" in str(excinfo.value)


def test_resolve_latest_ge_release_parses_github_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(download, "read_remote_text", lambda url: '{"tag_name": "GE-Proton12-3"}')

    assert download.resolve_latest_ge_release() == "GE-Proton12-3"


def test_resolve_latest_ge_release_falls_back_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_fetch(url: str) -> str:
        raise OSError("rate limit")

    monkeypatch.setattr(download, "read_remote_text", fail_fetch)
    seen: list[str] = []

    release = download.resolve_latest_ge_release(on_progress=seen.append)

    assert release == download.FALLBACK_GE_RELEASE
    assert any("falling back" in line for line in seen)


def test_resolve_latest_ge_release_falls_back_on_unexpected_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(download, "read_remote_text", lambda url: '{"tag_name": "v1.0"}')

    assert download.resolve_latest_ge_release() == download.FALLBACK_GE_RELEASE


def test_download_defaults_to_latest_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    latest = "GE-Proton12-3"
    monkeypatch.setattr(download, "resolve_latest_ge_release", lambda **kwargs: latest)
    data, digest = _make_release_archive(tmp_path, latest)
    _patch_remote(monkeypatch, data, f"{digest}  {latest}.tar.gz\n")
    install_dir = tmp_path / "compatibilitytools.d"

    result = download.download_proton_ge(install_dir=install_dir)

    assert result == install_dir / latest
    assert (result / "proton").is_file()


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


class _FakeResponse:
    """Réponse HTTP minimale : `Content-Length` annoncé vs octets réellement servis."""

    def __init__(self, payload: bytes, announced_length: str | None) -> None:
        self._payload = payload
        self._offset = 0
        self.headers = {} if announced_length is None else {"Content-Length": announced_length}

    def read(self, size: int) -> bytes:
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _patch_urlopen(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse) -> None:
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda url, timeout=None: response)


class TestDownloadToTruncation:
    """Une connexion coupée termine la boucle de lecture sans lever : il faut le détecter."""

    def test_transfert_tronque_rejete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_urlopen(monkeypatch, _FakeResponse(b"moitie", announced_length="9999"))
        dest = tmp_path / "archive.tar"

        with pytest.raises(TruncatedDownloadError) as excinfo:
            download.download_to("https://example.invalid/archive.tar", dest)

        assert excinfo.value.expected == 9999
        assert excinfo.value.received == len(b"moitie")

    def test_transfert_complet_accepte(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = b"contenu complet"
        _patch_urlopen(monkeypatch, _FakeResponse(payload, announced_length=str(len(payload))))
        dest = tmp_path / "archive.tar"

        download.download_to("https://example.invalid/archive.tar", dest)

        assert dest.read_bytes() == payload

    def test_sans_content_length_on_ne_peut_rien_conclure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = b"reponse en chunked"
        _patch_urlopen(monkeypatch, _FakeResponse(payload, announced_length=None))
        dest = tmp_path / "archive.tar"

        download.download_to("https://example.invalid/archive.tar", dest)

        assert dest.read_bytes() == payload


class TestChecksumValidation:
    """La somme de référence doit être un vrai digest, sinon on accuse la mauvaise pièce."""

    @pytest.mark.parametrize(
        ("contenu", "cas"),
        [
            ("z" * 128, "128 caractères non hexadécimaux"),
            ("<html>page d'erreur</html>", "page HTML au lieu du fichier"),
            ("", "réponse vide"),
            ("a" * 127, "digest trop court"),
        ],
    )
    def test_somme_illisible_designe_le_fichier_de_reference(
        self, contenu: str, cas: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(download, "read_remote_text", lambda url: contenu)

        with pytest.raises(ProtonDownloadError, match="checksum file"):
            download._remote_checksum(RELEASE)

    def test_digest_valide_accepte_et_normalise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        digest = "AB" * 64  # majuscules : sha512sum les accepte, hexdigest() les sort en minuscules
        monkeypatch.setattr(
            download, "read_remote_text", lambda url: f"{digest}  {RELEASE}.tar.gz\n"
        )

        assert download._remote_checksum(RELEASE) == digest.lower()
