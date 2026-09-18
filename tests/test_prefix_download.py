from __future__ import annotations

import hashlib
import tarfile
import urllib.error
from pathlib import Path

import pytest

from stalker_gamma_linux.prefix import download
from stalker_gamma_linux.prefix.errors import (
    ChecksumMismatchError,
    ProtonDownloadError,
    RemoteResponseTooLargeError,
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
    monkeypatch: pytest.MonkeyPatch,
    archive_bytes: bytes,
    checksum_line: str,
    *,
    asset: str = RELEASE,
) -> list[str]:
    """Sert les fichiers publiés sous le nom `asset`, et 404 pour tout autre nom.

    Une release GE n'existe que sous **une** convention de nom : répondre à
    n'importe quelle URL laisserait passer un code qui demande un asset
    inexistant — précisément le bug des releases ≥ GE-Proton11-4.
    """
    fetched_urls: list[str] = []

    def _serve(url: str) -> None:
        fetched_urls.append(url)
        if not url.rsplit("/", 1)[-1].startswith(f"{asset}."):
            raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)  # type: ignore[arg-type]

    def fake_read_remote_text(url: str) -> str:
        _serve(url)
        return checksum_line

    def fake_download_to(url: str, dest: Path, **kwargs: object) -> None:
        _serve(url)
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
    _patch_remote(monkeypatch, data, f"{digest}  {latest}.tar.gz\n", asset=latest)
    install_dir = tmp_path / "compatibilitytools.d"

    result = download.download_proton_ge(install_dir=install_dir)

    assert result == install_dir / latest
    assert (result / "proton").is_file()


def test_download_handles_the_x86_64_asset_naming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Convention depuis GE-Proton11-4 : l'archive, le .sha512sum *et* le
    # répertoire qu'elle contient portent le suffixe `-x86_64`. Le tag, non.
    release = "GE-Proton11-7"
    asset = f"{release}-x86_64"
    data, digest = _make_release_archive(tmp_path, asset)
    urls = _patch_remote(monkeypatch, data, f"{digest}  {asset}.tar.gz\n", asset=asset)
    install_dir = tmp_path / "compatibilitytools.d"

    result = download.download_proton_ge(release, install_dir)

    # Installé sous le nom du tag : notre convention ne suit pas celle de l'amont.
    assert result == install_dir / release
    assert (result / "proton").is_file()
    assert f"{asset}.tar.gz" in urls[-1]


def test_download_still_handles_the_unsuffixed_asset_naming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Une version épinglée par l'utilisateur peut être antérieure au
    # basculement (la GUI propose `GE-Proton10-8` en exemple).
    release = "GE-Proton10-8"
    data, digest = _make_release_archive(tmp_path, release)
    urls = _patch_remote(monkeypatch, data, f"{digest}  {release}.tar.gz\n", asset=release)
    install_dir = tmp_path / "compatibilitytools.d"

    result = download.download_proton_ge(release, install_dir)

    assert (result / "proton").is_file()
    # Le suffixe est sondé d'abord, et son 404 ne fait pas échouer la reprise.
    assert any(f"{release}-x86_64.sha512sum" in url for url in urls)


def test_download_reports_when_no_asset_convention_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, digest = _make_release_archive(tmp_path)
    _patch_remote(monkeypatch, data, f"{digest}  x\n", asset="GE-Proton99-9")
    install_dir = tmp_path / "compatibilitytools.d"

    with pytest.raises(ProtonDownloadError, match="No published archive found"):
        download.download_proton_ge(RELEASE, install_dir)


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


class TestReadRemoteBytesCap:
    """`read_remote_bytes` ne sert qu'à de petites métadonnées : elle doit refuser de
    bufferiser une réponse anormalement grosse plutôt que d'y engloutir la mémoire."""

    def test_reponse_sous_le_plafond_acceptee(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = b"petite reponse"
        _patch_urlopen(monkeypatch, _FakeResponse(payload, announced_length=None))

        result = download.read_remote_bytes(
            "https://example.invalid/metadata", max_bytes=len(payload)
        )

        assert result == payload

    def test_reponse_au_dessus_du_plafond_rejetee(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = b"un octet de trop"
        _patch_urlopen(monkeypatch, _FakeResponse(payload, announced_length=None))

        with pytest.raises(RemoteResponseTooLargeError) as excinfo:
            download.read_remote_bytes(
                "https://example.invalid/metadata", max_bytes=len(payload) - 1
            )

        assert excinfo.value.max_bytes == len(payload) - 1
        assert isinstance(excinfo.value, OSError)


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
