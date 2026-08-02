"""Dimensionnement disque (`sizing`) — et son unicité entre la CLI et la GUI.

Le vrai objet de ce fichier est le dernier test : `doctor` (CLI) et le dialog
d'installation (GUI) doivent rendre le **même** verdict sur la même machine.
Ils ont divergé (103 Gio contre 160 Gio) : à 120 Gio libres, `doctor` affichait
« [ OK ] Espace disque » pendant que la GUI bloquait le bouton d'installation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stalker_gamma_linux import sizing
from stalker_gamma_linux.environment import checks, system
from stalker_gamma_linux.environment.models import Status
from stalker_gamma_linux.gui import space


class TestBreakdown:
    def test_le_total_est_la_somme_des_postes(self) -> None:
        assert sizing.TOTAL_INSTALL_GIB == (
            sizing.ANOMALY_GIB + sizing.MODPACK_GIB + sizing.CACHE_GIB
        )

    def test_le_seuil_bloquant_couvre_l_installation_complete(self) -> None:
        """Bloquer sous le volume qu'on va effectivement écrire n'aurait aucun sens."""
        assert sizing.MINIMUM_FREE_GIB >= sizing.TOTAL_INSTALL_GIB

    def test_le_recommande_depasse_le_minimum(self) -> None:
        assert sizing.RECOMMENDED_FREE_GIB > sizing.MINIMUM_FREE_GIB


class TestSeuilPartage:
    def test_gui_et_sizing_partagent_les_memes_octets(self) -> None:
        assert space.MINIMUM_FREE_BYTES == sizing.MINIMUM_FREE_BYTES
        assert space.RECOMMENDED_FREE_BYTES == sizing.RECOMMENDED_FREE_BYTES

    @pytest.mark.parametrize(
        "free_gib",
        [
            0,
            sizing.MINIMUM_FREE_GIB - 1,
            sizing.MINIMUM_FREE_GIB,
            sizing.MINIMUM_FREE_GIB + 1,
            sizing.RECOMMENDED_FREE_GIB,
            sizing.RECOMMENDED_FREE_GIB * 2,
        ],
    )
    def test_cli_et_gui_saccordent_a_chaque_seuil(
        self, free_gib: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`doctor` ne dit jamais « OK » là où la GUI refuse de lancer, ni l'inverse."""
        free_bytes = free_gib * sizing.GIB
        monkeypatch.setattr(system, "path_exists", lambda path: True)
        monkeypatch.setattr(
            system,
            "disk_usage",
            lambda path: system.DiskUsage(total=free_bytes * 2, used=0, free=free_bytes),
        )

        cli_ok = checks.check_disk_space(Path("/games/stalker-gamma")).status is Status.OK
        gui_blocked = space.verdict_for(free_bytes) is space.SpaceVerdict.INSUFFICIENT

        assert cli_ok is not gui_blocked
