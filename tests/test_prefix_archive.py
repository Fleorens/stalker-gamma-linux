"""Extraction tar sûre (`prefix.archive`), y compris sans `filter=` (Python < 3.11.4).

`validate_members` est testée **directement** : c'est le chemin de repli qui ne
s'exécute que sur les Python dépourvus de `data_filter` (Debian 12 = 3.11.2), donc
jamais sur la machine de développement ni sur la CI `setup-python`. Sans ces
tests, il ne serait couvert nulle part.
"""

from __future__ import annotations

import io
import stat
import tarfile
from pathlib import Path

import pytest

from stalker_gamma_linux.prefix import archive
from stalker_gamma_linux.prefix.archive import safe_extractall, validate_members
from stalker_gamma_linux.prefix.errors import UnsafeArchiveError


def _tar_with(members: list[tarfile.TarInfo], tmp_path: Path) -> tarfile.TarFile:
    """Construit une archive contenant exactement `members` (contenu vide)."""
    archive = tmp_path / "archive.tar"
    with tarfile.open(archive, "w") as tar:
        for member in members:
            if member.isreg():
                tar.addfile(member, io.BytesIO(b""))
            else:
                tar.addfile(member)
    return tarfile.open(archive)


def _regular(name: str, mode: int = 0o644) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.REGTYPE
    info.size = 0
    info.mode = mode
    return info


def _symlink(name: str, target: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE
    info.linkname = target
    return info


class TestValidateMembers:
    def test_archive_normale_acceptee(self, tmp_path: Path) -> None:
        with _tar_with(
            [_regular("GE-Proton11-1/proton"), _regular("GE-Proton11-1/files/x")], tmp_path
        ) as tar:
            validate_members(tar, tmp_path / "dest")  # ne lève pas

    def test_lien_interne_accepte(self, tmp_path: Path) -> None:
        with _tar_with(
            [_regular("umu/umu-run"), _symlink("umu/alias", "umu-run")], tmp_path
        ) as tar:
            validate_members(tar, tmp_path / "dest")

    @pytest.mark.parametrize(
        ("member", "cas"),
        [
            (_regular("../../etc/cron.d/pwn"), "remontée hors du répertoire cible"),
            (_regular("/etc/passwd"), "chemin absolu"),
            (_regular("ok/../../../../tmp/x"), "remontée masquée par un préfixe valide"),
        ],
    )
    def test_chemin_dangereux_rejete(
        self, member: tarfile.TarInfo, cas: str, tmp_path: Path
    ) -> None:
        with _tar_with([member], tmp_path) as tar, pytest.raises(UnsafeArchiveError):
            validate_members(tar, tmp_path / "dest")

    def test_lien_sortant_rejete(self, tmp_path: Path) -> None:
        with (
            _tar_with([_symlink("umu/evil", "../../../../etc/passwd")], tmp_path) as tar,
            pytest.raises(UnsafeArchiveError, match="link"),
        ):
            validate_members(tar, tmp_path / "dest")

    def test_lien_absolu_rejete(self, tmp_path: Path) -> None:
        with (
            _tar_with([_symlink("umu/evil", "/etc/passwd")], tmp_path) as tar,
            pytest.raises(UnsafeArchiveError, match="link"),
        ):
            validate_members(tar, tmp_path / "dest")

    def test_fichier_special_rejete(self, tmp_path: Path) -> None:
        fifo = tarfile.TarInfo("umu/fifo")
        fifo.type = tarfile.FIFOTYPE
        with _tar_with([fifo], tmp_path) as tar, pytest.raises(UnsafeArchiveError, match="special"):
            validate_members(tar, tmp_path / "dest")


class TestSafeExtractall:
    """Bout en bout sur le Python courant, quelle que soit la branche empruntée."""

    def test_extrait_une_archive_saine(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "GE-Proton11-1"
        source.mkdir(parents=True)
        (source / "proton").write_text("#!/bin/sh\n")
        archive = tmp_path / "release.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(source, arcname="GE-Proton11-1")

        dest = tmp_path / "dest"
        dest.mkdir()
        with tarfile.open(archive) as tar:
            safe_extractall(tar, dest)

        assert (dest / "GE-Proton11-1" / "proton").read_text() == "#!/bin/sh\n"

    def test_refuse_une_archive_malveillante(self, tmp_path: Path) -> None:
        """Quelle que soit la version de Python, rien ne s'écrit hors de `dest`."""
        archive = tmp_path / "evil.tar"
        with tarfile.open(archive, "w") as tar:
            info = tarfile.TarInfo("../escaped.txt")
            info.size = 3
            tar.addfile(info, io.BytesIO(b"pwn"))

        dest = tmp_path / "dest"
        dest.mkdir()
        with (
            tarfile.open(archive) as tar,
            pytest.raises(Exception, match="escaped|unsafe|outside|absolute|path"),
        ):
            safe_extractall(tar, dest)

        assert not (tmp_path / "escaped.txt").exists()

    def test_neutralise_setuid_et_setgid(self, tmp_path: Path) -> None:
        """Les bits setuid/setgid sont effacés lors de l'extraction (comme data_filter)."""
        with _tar_with([_regular("setuid.sh", mode=0o4755)], tmp_path) as tar:
            dest = tmp_path / "dest"
            dest.mkdir()
            safe_extractall(tar, dest)

        extracted = dest / "setuid.sh"
        assert extracted.exists()
        # Vérifier que le bit setuid (04000) est absent.
        mode = stat.S_IMODE(extracted.stat().st_mode)
        assert not (mode & stat.S_ISUID)

    def test_repli_applique_le_masque_de_data_filter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Le repli normalise le mode exactement comme `data_filter` : `& 0o755`.

        Deux précautions, sans lesquelles ce test serait vert quoi qu'il arrive :

        - `_HAS_DATA_FILTER` est forcé à False, sinon c'est la branche stdlib qui
          s'exécute et le repli n'est jamais atteint ;
        - les modes sont relevés **au moment de l'appel** à `extractall`, pas sur
          le disque après coup. Depuis Python 3.14, `extractall()` sans `filter=`
          applique `data_filter` par défaut (PEP 706) : il rattraperait un masque
          défaillant sur la machine de dev et en CI, c'est-à-dire partout sauf
          sur la Debian 12 que ce repli existe pour servir.
        """
        monkeypatch.setattr(archive, "_HAS_DATA_FILTER", False)
        members = [
            _regular("setuid.sh", mode=0o4755),
            _regular("setgid.sh", mode=0o2755),
            _regular("sticky.sh", mode=0o1755),
            _regular("worldwrite.sh", mode=0o777),
        ]
        with _tar_with(members, tmp_path) as tar:
            dest = tmp_path / "dest"
            dest.mkdir()
            submitted: dict[str, int] = {}
            extractall = tar.extractall

            def spy(*args: object, **kwargs: object) -> None:
                submitted.update({member.name: member.mode for member in tar.getmembers()})
                extractall(*args, **kwargs)  # type: ignore[arg-type]

            monkeypatch.setattr(tar, "extractall", spy)
            safe_extractall(tar, dest)

        assert submitted == dict.fromkeys(
            ("setuid.sh", "setgid.sh", "sticky.sh", "worldwrite.sh"), 0o755
        )
