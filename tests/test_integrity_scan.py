"""Parcours et hachage de `mods/` (T12) : lecture par blocs, annulation, progression.

L'horloge est injectée (`clock=`) : la cadence de progression se teste alors
sans `sleep`, et sans dépendre de la vitesse de la machine qui exécute la suite.
"""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

import pytest

from stalker_gamma_linux.integrity import scan
from stalker_gamma_linux.integrity.errors import IntegrityCancelledError
from tests.conftest import RecordingReporter

# `chmod 000` n'empêche pas root de lire : les deux cas « illisible » ne veulent
# rien dire dans un conteneur de CI lancé en root.
skip_as_root = pytest.mark.skipif(
    os.geteuid() == 0, reason="root ignores the permissions these cases rely on"
)


class FakeClock:
    """Horloge monotone pilotée par le test (une seconde par appel par défaut)."""

    def __init__(self, step: float = 1.0) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


def _mod_tree(root: Path) -> Path:
    mods = root / "mods"
    (mods / "101- Mod A" / "gamedata").mkdir(parents=True)
    (mods / "101- Mod A" / "gamedata" / "a.ltx").write_bytes(b"alpha")
    (mods / "102- Mod B").mkdir()
    (mods / "102- Mod B" / "b.dds").write_bytes(b"beta")
    return mods


class TestHashFile:
    def test_correspond_au_md5_de_reference(self, tmp_path: Path) -> None:
        payload = b"x" * (scan.BLOCK_SIZE * 2 + 7)
        path = tmp_path / "big.bin"
        path.write_bytes(payload)

        digest, size = scan.hash_file(path)

        assert digest == hashlib.md5(payload, usedforsecurity=False).hexdigest()
        assert size == len(payload)

    def test_lit_par_blocs_sans_charger_le_fichier(self, tmp_path: Path) -> None:
        """Trois blocs lus pour deux blocs et demi : aucune lecture intégrale."""
        path = tmp_path / "big.bin"
        path.write_bytes(b"y" * (scan.BLOCK_SIZE * 2 + 1))
        blocks: list[int] = []

        scan.hash_file(path, on_block=blocks.append)

        assert blocks == [scan.BLOCK_SIZE, scan.BLOCK_SIZE, 1]

    def test_annulation_au_milieu_dun_gros_fichier(self, tmp_path: Path) -> None:
        path = tmp_path / "big.bin"
        path.write_bytes(b"z" * (scan.BLOCK_SIZE * 3))
        cancel_event = threading.Event()

        def cancel_after_first(_count: int) -> None:
            cancel_event.set()

        with pytest.raises(IntegrityCancelledError):
            scan.hash_file(path, cancel_event=cancel_event, on_block=cancel_after_first)


class TestScanTree:
    def test_empreintes_relatives_a_la_racine(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        mods = _mod_tree(tmp_path)

        result = scan.scan_tree(mods, reporter=reporter)

        assert set(result.digests) == {"101- Mod A/gamedata/a.ltx", "102- Mod B/b.dds"}
        assert (
            result.digests["102- Mod B/b.dds"]
            == hashlib.md5(b"beta", usedforsecurity=False).hexdigest()
        )
        assert result.total_bytes == len(b"alpha") + len(b"beta")
        assert result.file_count == 2

    def test_arborescence_vide(self, tmp_path: Path, reporter: RecordingReporter) -> None:
        mods = tmp_path / "mods"
        mods.mkdir()

        result = scan.scan_tree(mods, reporter=reporter)

        assert result.digests == {}
        assert result.unreadable == ()

    @skip_as_root
    def test_fichier_illisible_rapporte_sans_interrompre(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        mods = _mod_tree(tmp_path)
        unreadable = mods / "101- Mod A" / "gamedata" / "secret.ltx"
        unreadable.write_bytes(b"nope")
        unreadable.chmod(0o000)

        try:
            result = scan.scan_tree(mods, reporter=reporter)
        finally:
            unreadable.chmod(0o644)

        assert [entry.relative for entry in result.unreadable] == ["101- Mod A/gamedata/secret.ltx"]
        # Le scan est allé jusqu'au bout malgré lui.
        assert set(result.digests) == {"101- Mod A/gamedata/a.ltx", "102- Mod B/b.dds"}

    @skip_as_root
    def test_dossier_illisible_rapporte_au_lieu_detre_saute_en_silence(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """`os.walk` ignore un dossier illisible par défaut : c'est ce qu'on refuse."""
        mods = _mod_tree(tmp_path)
        closed = mods / "103- Mod C"
        closed.mkdir()
        (closed / "c.ltx").write_bytes(b"gamma")
        closed.chmod(0o000)

        try:
            result = scan.scan_tree(mods, reporter=reporter)
        finally:
            closed.chmod(0o755)

        assert [entry.relative for entry in result.unreadable] == ["103- Mod C"]

    def test_annulation_leve_au_lieu_de_rendre_un_resultat_partiel(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        mods = _mod_tree(tmp_path)
        cancel_event = threading.Event()
        cancel_event.set()

        with pytest.raises(IntegrityCancelledError):
            scan.scan_tree(mods, reporter=reporter, cancel_event=cancel_event)

    def test_lien_symbolique_vers_un_dossier_nest_pas_suivi(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """Sans ça, un lien vers la racine ferait boucler le parcours à l'infini."""
        mods = _mod_tree(tmp_path)
        (mods / "boucle").symlink_to(mods)

        result = scan.scan_tree(mods, reporter=reporter)

        assert set(result.digests) == {"101- Mod A/gamedata/a.ltx", "102- Mod B/b.dds"}


class TestProgressPacing:
    def test_cadence_au_temps_ecoule_pas_au_nombre_de_fichiers(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """200 petits fichiers, horloge figée : aucune ligne de progression."""
        mods = tmp_path / "mods"
        mods.mkdir()
        for index in range(200):
            (mods / f"{index}.ltx").write_bytes(b"x")

        scan.scan_tree(mods, reporter=reporter, clock=lambda: 0.0)

        assert reporter.of_kind("progress") == []

    def test_progression_emise_quand_le_temps_passe(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        mods = _mod_tree(tmp_path)

        scan.scan_tree(mods, reporter=reporter, clock=FakeClock(step=10.0))

        assert reporter.of_kind("progress")

    def test_progression_pendant_la_lecture_dun_seul_gros_fichier(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """Un fichier de plusieurs blocs doit rafraîchir l'affichage en cours de route."""
        mods = tmp_path / "mods"
        mods.mkdir()
        (mods / "enorme.dds").write_bytes(b"w" * (scan.BLOCK_SIZE * 3))

        scan.scan_tree(mods, reporter=reporter, clock=FakeClock(step=10.0))

        assert len(reporter.of_kind("progress")) >= 2
