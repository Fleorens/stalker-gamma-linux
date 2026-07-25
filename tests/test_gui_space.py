"""Évaluation d'espace disque pour la cible d'installation (`gui.space`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from stalker_gamma_linux.gui import space

_GIB = 1024**3


class TestVerdictFor:
    def test_insuffisant_sous_le_minimum(self) -> None:
        assert space.verdict_for(space.MINIMUM_FREE_BYTES - 1) is space.SpaceVerdict.INSUFFICIENT

    def test_juste_entre_minimum_et_recommande(self) -> None:
        assert space.verdict_for(space.MINIMUM_FREE_BYTES) is space.SpaceVerdict.TIGHT
        assert (
            space.verdict_for(space.RECOMMENDED_FREE_BYTES - 1) is space.SpaceVerdict.TIGHT
        )

    def test_ok_au_recommande(self) -> None:
        assert space.verdict_for(space.RECOMMENDED_FREE_BYTES) is space.SpaceVerdict.OK


class TestNearestExistingParent:
    def test_cible_existante(self, tmp_path: Path) -> None:
        assert space.nearest_existing_parent(tmp_path) == tmp_path

    def test_remonte_jusqu_au_parent_existant(self, tmp_path: Path) -> None:
        target = tmp_path / "Games" / "stalker-gamma"
        assert space.nearest_existing_parent(target) == tmp_path

    def test_chemin_totalement_absent(self) -> None:
        target = Path("/nulle/part/du/tout")
        assert space.nearest_existing_parent(target) == Path("/")


class TestAssess:
    def test_rapport_nominal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_disk_usage(path: str | Path) -> tuple[int, int, int]:
            assert Path(path) == tmp_path
            usage = type("Usage", (), {"free": 300 * _GIB})
            return usage()  # type: ignore[return-value]

        monkeypatch.setattr(space.shutil, "disk_usage", fake_disk_usage)
        report = space.assess(tmp_path / "Games" / "stalker-gamma")
        assert report.verdict is space.SpaceVerdict.OK
        assert report.free_bytes == 300 * _GIB
        assert report.free_label == "300 Gio libres"

    def test_volume_illisible(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def failing_disk_usage(_path: str | Path) -> tuple[int, int, int]:
            raise OSError("volume déconnecté")

        monkeypatch.setattr(space.shutil, "disk_usage", failing_disk_usage)
        report = space.assess(tmp_path)
        assert report.verdict is space.SpaceVerdict.UNKNOWN
        assert report.free_bytes is None
        assert report.free_label == "espace libre inconnu"
