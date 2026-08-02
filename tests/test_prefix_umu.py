"""Installation automatique du zipapp umu-launcher (`prefix.umu`)."""

from __future__ import annotations

import io
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

from stalker_gamma_linux.prefix import umu
from stalker_gamma_linux.prefix.errors import UmuDownloadError

RELEASE = "1.4.4"


def _valid_zipapp_bytes() -> bytes:
    """Un vrai zipapp minimal : `#!` suivi d'une archive ZIP contenant `__main__.py`.

    C'est exactement ce que publie l'amont, et ce que `_require_valid_zipapp`
    vérifie — un payload bidon (`b"PK..."`) passait avant que ce contrôle
    existe, mais ne décrivait pas le format réel.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("__main__.py", "print('umu')\n")
    return b"#!/usr/bin/env python3\n" + buffer.getvalue()


def _make_zipapp_tar(tmp_path: Path, *, member: str = "umu/umu-run") -> bytes:
    source = tmp_path / "upstream" / "umu"
    source.mkdir(parents=True)
    payload = tmp_path / "upstream" / Path(member).name
    payload.write_bytes(_valid_zipapp_bytes())
    archive = tmp_path / "upstream" / "zipapp.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(payload, arcname=member)
    return archive.read_bytes()


def _patch_download(monkeypatch: pytest.MonkeyPatch, archive_bytes: bytes) -> list[str]:
    urls: list[str] = []

    def fake_download_to(url: str, dest: Path, **kwargs: object) -> None:
        urls.append(url)
        dest.write_bytes(archive_bytes)

    monkeypatch.setattr(umu, "download_to", fake_download_to)
    return urls


class TestInstallUmu:
    def test_pose_umu_run_executable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        urls = _patch_download(monkeypatch, _make_zipapp_tar(tmp_path))
        install_dir = tmp_path / "bin"

        result = umu.install_umu(RELEASE, install_dir)

        assert result == install_dir / "umu-run"
        assert result.read_bytes().startswith(b"#!")
        assert os.access(result, os.X_OK)
        assert urls == [
            f"https://github.com/Open-Wine-Components/umu-launcher/releases/download/"
            f"{RELEASE}/umu-launcher-{RELEASE}-zipapp.tar"
        ]

    def test_ecrase_une_version_precedente(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_download(monkeypatch, _make_zipapp_tar(tmp_path))
        install_dir = tmp_path / "bin"
        install_dir.mkdir()
        (install_dir / "umu-run").write_bytes(b"ancienne version")

        result = umu.install_umu(RELEASE, install_dir)

        assert result.read_bytes().startswith(b"#!")

    def test_archive_sans_umu_run_leve(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_download(monkeypatch, _make_zipapp_tar(tmp_path, member="umu/autre-chose"))

        with pytest.raises(UmuDownloadError, match="umu/umu-run"):
            umu.install_umu(RELEASE, tmp_path / "bin")

    def test_archive_corrompue_leve(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_download(monkeypatch, b"pas un tar du tout")

        with pytest.raises(UmuDownloadError, match="Corrupted"):
            umu.install_umu(RELEASE, tmp_path / "bin")

    def test_echec_reseau_leve(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def fail(url: str, dest: Path, **kwargs: object) -> None:
            raise OSError("réseau injoignable")

        monkeypatch.setattr(umu, "download_to", fail)

        with pytest.raises(UmuDownloadError, match="Could not download"):
            umu.install_umu(RELEASE, tmp_path / "bin")


class TestResolveLatestRelease:
    def test_tag_valide(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(umu, "read_remote_text", lambda url: '{"tag_name": "1.5.0"}')

        assert umu.resolve_latest_release() == "1.5.0"

    def test_api_injoignable_replie_sur_la_release_epinglee(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(url: str) -> str:
            raise OSError("rate limit")

        monkeypatch.setattr(umu, "read_remote_text", fail)
        messages: list[str] = []

        result = umu.resolve_latest_release(on_progress=messages.append)

        assert result == umu.FALLBACK_UMU_RELEASE
        assert any("falling back" in message for message in messages)

    def test_tag_inattendu_replie_aussi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(umu, "read_remote_text", lambda url: '{"tag_name": "v-nightly-broken"}')

        assert umu.resolve_latest_release() == umu.FALLBACK_UMU_RELEASE


class TestRunInstallUmu:
    def test_succes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from stalker_gamma_linux.environment import system

        monkeypatch.setattr(umu, "install_umu", lambda **kw: tmp_path / "umu-run")
        monkeypatch.setattr(system, "which", lambda cmd: "/home/x/.local/bin/umu-run")

        assert umu.run_install_umu() == 0

    def test_echec_retourne_un(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(**kw: object) -> Path:
            raise UmuDownloadError("réseau")

        monkeypatch.setattr(umu, "install_umu", boom)

        assert umu.run_install_umu() == 1

    def test_path_sans_local_bin_avertit_mais_reussit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from stalker_gamma_linux.environment import system

        monkeypatch.setattr(umu, "install_umu", lambda **kw: tmp_path / "umu-run")
        monkeypatch.setattr(system, "which", lambda cmd: None)

        assert umu.run_install_umu() == 0


class TestZipappValidation:
    """Sans somme de contrôle amont, la validité du zipapp est le seul garde-fou de contenu."""

    def _tar_with_member(self, tmp_path: Path, payload: bytes) -> bytes:
        tmp_path.mkdir(parents=True, exist_ok=True)
        member = tmp_path / "umu-run"
        member.write_bytes(payload)
        archive = tmp_path / "umu-zipapp.tar"
        with tarfile.open(archive, "w") as tar:
            tar.add(member, arcname="umu/umu-run")
        return archive.read_bytes()

    def test_zipapp_valide_accepte(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        data = self._tar_with_member(tmp_path / "src", _valid_zipapp_bytes())
        _patch_download(monkeypatch, data)

        target = umu.install_umu("1.4.4", tmp_path / "bin")

        assert target.is_file()
        assert target.stat().st_mode & 0o111  # exécutable

    def test_zip_corrompu_rejete(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Un zipapp tronqué garde son shebang mais perd son répertoire central."""
        truncated = _valid_zipapp_bytes()[:30]
        _patch_download(monkeypatch, self._tar_with_member(tmp_path / "src", truncated))

        with pytest.raises(UmuDownloadError, match="Corrupted|unreadable"):
            umu.install_umu("1.4.4", tmp_path / "bin")

    def test_sans_shebang_rejete(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("__main__.py", "x\n")
        _patch_download(monkeypatch, self._tar_with_member(tmp_path / "src", buffer.getvalue()))

        with pytest.raises(UmuDownloadError, match="zipapp"):
            umu.install_umu("1.4.4", tmp_path / "bin")

    def test_sans_point_dentree_rejete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("autre.py", "x\n")
        payload = b"#!/usr/bin/env python3\n" + buffer.getvalue()
        _patch_download(monkeypatch, self._tar_with_member(tmp_path / "src", payload))

        with pytest.raises(UmuDownloadError, match="__main__"):
            umu.install_umu("1.4.4", tmp_path / "bin")
