"""Helpers de formatage purs de la GUI (`gui.format`)."""

from __future__ import annotations

import pytest

from stalker_gamma_linux.gui.format import format_duration, format_gib, parse_step_index


class TestParseStepIndex:
    def test_nominal(self) -> None:
        assert parse_step_index("3/7") == (3, 7)

    def test_premiere_et_derniere(self) -> None:
        assert parse_step_index("1/6") == (1, 6)
        assert parse_step_index("6/6") == (6, 6)

    @pytest.mark.parametrize(
        "index",
        ["", "3", "3/", "/7", "a/7", "3/b", "0/7", "8/7", "3/7/9", "-1/7", "3 / 7"],
    )
    def test_illisible_ou_hors_bornes(self, index: str) -> None:
        assert parse_step_index(index) is None


class TestFormatGib:
    def test_grand_volume_sans_decimale(self) -> None:
        assert format_gib(245 * 1024**3) == "245 Gio"

    def test_petit_volume_avec_virgule(self) -> None:
        assert format_gib(int(1.5 * 1024**3)) == "1,5 Gio"

    def test_zero(self) -> None:
        assert format_gib(0) == "0,0 Gio"


class TestFormatDuration:
    def test_secondes(self) -> None:
        assert format_duration(42) == "42 s"

    def test_minutes(self) -> None:
        assert format_duration(4 * 60 + 5) == "4 min 05"

    def test_heures(self) -> None:
        assert format_duration(3600 + 2 * 60) == "1 h 02 min"

    def test_negatif_borne_a_zero(self) -> None:
        assert format_duration(-3.2) == "0 s"
