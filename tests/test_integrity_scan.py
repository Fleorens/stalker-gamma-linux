"""Parcours et hachage de `mods/` (T12) : blocs, annulation, progression, pool.

L'horloge est injectée (`clock=`) : la cadence de progression se teste alors
sans `sleep`, et sans dépendre de la vitesse de la machine qui exécute la suite.

Le hachage étant parallèle, la suite vérifie surtout ce que le pool ne doit
**pas** changer : mêmes empreintes, même ordre, mêmes illisibles qu'un scan
séquentiel (`workers=1`), quel que soit le nombre de fils. Les cas de course
sont provoqués, jamais espérés — arborescence dont le premier fichier est aussi
le plus gros, annulation déclenchée depuis un fil de hachage.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from stalker_gamma_linux.integrity import scan
from stalker_gamma_linux.integrity.errors import IntegrityCancelledError
from stalker_gamma_linux.integrity.fingerprint import FileStat, KnownFile
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


def _reference_of(result: scan.ScanResult) -> dict[str, KnownFile]:
    """La référence qu'un scan produirait, telle que `baseline` la relira."""
    return {
        relative: KnownFile(digest=digest, stat=result.stats[relative])
        for relative, digest in result.digests.items()
    }


def _rewrite_keeping_mtime(path: Path, payload: bytes) -> None:
    """Réécrit un fichier en lui rendant sa date — la corruption que le défaut ne voit pas."""
    before = path.stat()
    path.write_bytes(payload)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))


def _mod_tree(root: Path) -> Path:
    mods = root / "mods"
    (mods / "101- Mod A" / "gamedata").mkdir(parents=True)
    (mods / "101- Mod A" / "gamedata" / "a.ltx").write_bytes(b"alpha")
    (mods / "102- Mod B").mkdir()
    (mods / "102- Mod B" / "b.dds").write_bytes(b"beta")
    return mods


class YieldingClock(FakeClock):
    """Horloge factice qui rend la main au milieu de la section critique.

    Sans elle, un test de concurrence sur `_ScanProgress` ne prouve rien :
    CPython ne préempte un fil qu'aux sauts et aux appels, si bien qu'une
    boucle courte s'exécute d'un trait et qu'aucun entrelacement ne se produit.
    Le `sleep(0)` relâche le GIL exactement entre la lecture de l'horloge et la
    mise à jour de `_last_report` — le `check-then-act` que le verrou protège.
    """

    def __call__(self) -> float:
        value = super().__call__()
        time.sleep(0)
        return value


def _wide_tree(root: Path, *, directories: int = 6, per_directory: int = 15) -> Path:
    """Arborescence assez large et assez inégale pour que l'ordre d'achèvement diverge.

    Le tout premier fichier dans l'ordre de parcours est aussi le plus gros :
    c'est le cas qui démasque une implémentation qui consommerait les tâches
    dans l'ordre d'achèvement (`as_completed`) au lieu de l'ordre de soumission.
    """
    mods = root / "mods"
    for directory in range(directories):
        current = mods / f"{100 + directory}- Mod {directory}" / "gamedata"
        current.mkdir(parents=True)
        for index in range(per_directory):
            size = 8 if (directory or index) else scan.BLOCK_SIZE * 3
            (current / f"{index:03d}.ltx").write_bytes(f"{directory}-{index}-".encode() * size)
    return mods


class CancellingReporter(RecordingReporter):
    """Reporter qui demande l'annulation dès la première ligne de progression.

    C'est la façon la plus fidèle de déclencher une annulation **en cours** de
    scan : elle part d'un fil de hachage, au milieu de la lecture, exactement
    comme le bouton « Annuler » de la GUI le ferait depuis le fil GTK.
    """

    def __init__(self, cancel_event: threading.Event) -> None:
        super().__init__()
        self._cancel_event = cancel_event

    def progress(self, message: str) -> None:
        super().progress(message)
        self._cancel_event.set()


def _surviving_hash_threads() -> list[str]:
    return [thread.name for thread in threading.enumerate() if thread.name.startswith("gamma-md5")]


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


class TestParallelHashing:
    def test_meme_resultat_et_meme_ordre_quel_que_soit_le_nombre_de_fils(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """L'invariant central du pool : le parallélisme ne se voit pas dans le résultat."""
        mods = _wide_tree(tmp_path)

        sequential = scan.scan_tree(mods, reporter=reporter, workers=1)
        parallel = scan.scan_tree(mods, reporter=reporter, workers=8)

        assert parallel.digests == sequential.digests
        # `==` sur des dict ignore l'ordre : c'est lui qu'on vérifie ici.
        assert list(parallel.digests) == list(sequential.digests)
        assert parallel.total_bytes == sequential.total_bytes
        assert parallel.file_count == sequential.file_count

    def test_empreintes_conformes_a_hashlib(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """Un pool qui mélangerait deux fichiers passerait les tests d'ordre, pas celui-ci."""
        mods = _wide_tree(tmp_path, directories=3, per_directory=4)

        result = scan.scan_tree(mods, reporter=reporter, workers=8)

        expected = {
            path.relative_to(mods).as_posix(): hashlib.md5(
                path.read_bytes(), usedforsecurity=False
            ).hexdigest()
            for path in sorted(mods.rglob("*.ltx"))
        }
        assert result.digests == expected

    def test_ordre_de_parcours_conserve(self, tmp_path: Path, reporter: RecordingReporter) -> None:
        mods = _wide_tree(tmp_path, directories=3, per_directory=5)

        result = scan.scan_tree(mods, reporter=reporter, workers=8)

        assert list(result.digests) == sorted(result.digests)

    @skip_as_root
    def test_fichier_illisible_collecte_et_non_propage(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """L'`OSError` remonte maintenant par une `Future` : elle doit rester rangée."""
        mods = _wide_tree(tmp_path, directories=2, per_directory=4)
        unreadable = mods / "100- Mod 0" / "gamedata" / "002.ltx"
        unreadable.chmod(0o000)

        try:
            result = scan.scan_tree(mods, reporter=reporter, workers=8)
        finally:
            unreadable.chmod(0o644)

        assert [entry.relative for entry in result.unreadable] == [
            "100- Mod 0/gamedata/002.ltx",
        ]
        assert "100- Mod 0/gamedata/002.ltx" not in result.digests
        assert result.file_count == 7  # les sept autres sont bien allés au bout

    @skip_as_root
    def test_illisibles_dans_le_meme_ordre_que_le_scan_sequentiel(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """Fichiers et dossiers illisibles naissent à des moments décalés : ordre stable exigé."""
        mods = _wide_tree(tmp_path, directories=3, per_directory=4)
        blocked_file = mods / "101- Mod 1" / "gamedata" / "001.ltx"
        blocked_file.chmod(0o000)
        blocked_dir = mods / "102- Mod 2" / "gamedata"
        blocked_dir.chmod(0o000)

        try:
            sequential = scan.scan_tree(mods, reporter=reporter, workers=1)
            parallel = scan.scan_tree(mods, reporter=reporter, workers=8)
        finally:
            blocked_file.chmod(0o644)
            blocked_dir.chmod(0o755)

        assert [entry.relative for entry in parallel.unreadable] == [
            "101- Mod 1/gamedata/001.ltx",
            "102- Mod 2/gamedata",
        ]
        assert parallel.unreadable == sequential.unreadable

    def test_annulation_en_cours_de_scan_leve_et_ne_laisse_aucun_fil(self, tmp_path: Path) -> None:
        """Annulation déclenchée depuis un fil de hachage, pas avant le départ."""
        mods = tmp_path / "mods"
        mods.mkdir()
        for index in range(300):
            (mods / f"{index:03d}.ltx").write_bytes(b"x")
        cancel_event = threading.Event()
        reporter = CancellingReporter(cancel_event)

        with pytest.raises(IntegrityCancelledError):
            # Horloge factice : chaque relevé de progression est « dû », donc la
            # toute première lecture de bloc déclenche l'annulation.
            scan.scan_tree(
                mods,
                reporter=reporter,
                cancel_event=cancel_event,
                clock=FakeClock(step=10.0),
                workers=4,
            )

        # Deux événements par fichier au maximum (bloc + fichier) : rester très
        # en deçà de 600 prouve que le scan s'est arrêté au lieu d'aller au bout.
        assert len(reporter.of_kind("progress")) < 200
        assert _surviving_hash_threads() == []

    def test_aucun_fil_ne_survit_a_un_scan_normal(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        scan.scan_tree(_wide_tree(tmp_path, directories=2, per_directory=3), reporter=reporter)

        assert _surviving_hash_threads() == []

    def test_nombre_de_fils_invalide_refuse_tout_de_suite(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        with pytest.raises(ValueError, match="workers"):
            scan.scan_tree(_mod_tree(tmp_path), reporter=reporter, workers=0)


class TestWorkerDefaults:
    def test_un_seul_fil_sur_disque_mecanique(self, monkeypatch, tmp_path: Path) -> None:
        """Quatre têtes de lecture concurrentes sur des plateaux : plus lent, pas plus rapide."""
        monkeypatch.setattr(scan.storage, "is_rotational", lambda _path: True)

        assert scan._default_workers(tmp_path) == 1

    def test_plusieurs_fils_sur_memoire_flash(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(scan.storage, "is_rotational", lambda _path: False)

        assert scan._default_workers(tmp_path) == min(scan.MAX_HASH_WORKERS, os.cpu_count() or 1)

    def test_support_indetermine_traite_comme_flash(self, monkeypatch, tmp_path: Path) -> None:
        """btrfs multi-disques, NFS, conteneur sans `/proc` : le doute ne bride pas le scan."""
        monkeypatch.setattr(scan.storage, "is_rotational", lambda _path: None)

        assert scan._default_workers(tmp_path) > 1 or (os.cpu_count() or 1) == 1

    def test_le_defaut_est_bien_celui_que_scan_tree_applique(
        self, monkeypatch, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        monkeypatch.setattr(scan.storage, "is_rotational", lambda _path: True)
        requested: list[int] = []
        real_executor = scan.ThreadPoolExecutor

        def spy(*, max_workers: int, thread_name_prefix: str) -> ThreadPoolExecutor:
            requested.append(max_workers)
            return real_executor(max_workers=max_workers, thread_name_prefix=thread_name_prefix)

        monkeypatch.setattr(scan, "ThreadPoolExecutor", spy)

        scan.scan_tree(_mod_tree(tmp_path), reporter=reporter)

        assert requested == [1]


class TestScanProgressConcurrency:
    def test_cadence_et_compteurs_exacts_sous_concurrence(
        self, reporter: RecordingReporter
    ) -> None:
        """Huit fils, une seconde par lecture d'horloge, un rapport dû toutes les 1,5 s.

        Le résultat attendu est *exact*, pas approximatif : une ligne toutes les
        deux lectures, et pas un octet perdu. Sans verrou, deux fils lisent la
        même heure et franchissent ensemble le test de cadence — le compte tombe
        alors autour de 1 650 au lieu de 2 000, et il varie d'une exécution à
        l'autre.
        """
        threads_count, per_thread = 8, 500
        readings = threads_count * per_thread
        progress = scan._ScanProgress(reporter, clock=YieldingClock(step=1.0))

        def hammer() -> None:
            for _index in range(per_thread):
                progress.add_bytes(3)

        threads = [threading.Thread(target=hammer) for _ in range(threads_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(reporter.of_kind("progress")) == readings // 2
        assert progress.total_bytes == readings * 3


class TestShortCircuit:
    """Ne pas relire ce qui n'a pas bougé — et le repli sûr partout ailleurs.

    Le compromis est écrit noir sur blanc dans `fingerprint` : tout ce qui passe
    par une écriture ordinaire déplace la taille ou la date, donc est relu ; une
    réécriture qui remet la date à la main ne l'est pas. Les deux sont testés
    ici, le second parce qu'une garantie qu'on n'a pas doit être visible dans la
    suite plutôt que découverte par un utilisateur.
    """

    def test_fichier_inchange_nest_pas_rehache(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        mods = _mod_tree(tmp_path)
        first = scan.scan_tree(mods, reporter=reporter)

        second = scan.scan_tree(mods, reference=_reference_of(first), reporter=reporter)

        assert set(second.reused) == set(first.digests)
        # Pas un octet lu : c'est exactement ce que le court-circuit achète.
        assert second.total_bytes == 0
        assert second.digests == first.digests

    def test_taille_modifiee_est_rehachee_et_detectee(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        mods = _mod_tree(tmp_path)
        first = scan.scan_tree(mods, reporter=reporter)
        touched = mods / "101- Mod A" / "gamedata" / "a.ltx"
        touched.write_bytes(b"alpha corrompu, plus long")

        second = scan.scan_tree(mods, reference=_reference_of(first), reporter=reporter)

        assert second.reused == ("102- Mod B/b.dds",)
        assert (
            second.digests["101- Mod A/gamedata/a.ltx"]
            != first.digests["101- Mod A/gamedata/a.ltx"]
        )
        assert (
            second.digests["101- Mod A/gamedata/a.ltx"]
            == hashlib.md5(b"alpha corrompu, plus long", usedforsecurity=False).hexdigest()
        )

    def test_mtime_modifiee_seule_suffit_a_faire_rehacher(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """Même contenu, même taille : la date seule doit suffire à déclencher la relecture."""
        mods = _mod_tree(tmp_path)
        first = scan.scan_tree(mods, reporter=reporter)
        touched = mods / "102- Mod B" / "b.dds"
        before = touched.stat()
        os.utime(touched, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))

        second = scan.scan_tree(mods, reference=_reference_of(first), reporter=reporter)

        assert second.reused == ("101- Mod A/gamedata/a.ltx",)
        assert second.total_bytes == len(b"beta")
        # Relu, et identique : la date change, le verdict ne bouge pas.
        assert second.digests == first.digests

    def test_taille_identique_mais_contenu_different_est_detecte(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """Le cas courant d'une corruption : l'écriture a déplacé la date, donc on relit."""
        mods = _mod_tree(tmp_path)
        first = scan.scan_tree(mods, reporter=reporter)
        (mods / "102- Mod B" / "b.dds").write_bytes(b"BETA")

        second = scan.scan_tree(mods, reference=_reference_of(first), reporter=reporter)

        assert "102- Mod B/b.dds" not in second.reused
        assert second.digests["102- Mod B/b.dds"] != first.digests["102- Mod B/b.dds"]

    def test_corruption_qui_preserve_taille_et_date_passe_au_travers(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """La contrepartie assumée, et la porte de sortie : rescanner sans référence."""
        mods = _mod_tree(tmp_path)
        first = scan.scan_tree(mods, reporter=reporter)
        _rewrite_keeping_mtime(mods / "102- Mod B" / "b.dds", b"BETA")

        court_circuite = scan.scan_tree(mods, reference=_reference_of(first), reporter=reporter)
        complet = scan.scan_tree(mods, reporter=reporter)

        assert court_circuite.digests["102- Mod B/b.dds"] == first.digests["102- Mod B/b.dds"]
        assert complet.digests["102- Mod B/b.dds"] != first.digests["102- Mod B/b.dds"]

    def test_sans_reference_tout_est_rehache(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        mods = _mod_tree(tmp_path)
        scan.scan_tree(mods, reporter=reporter)

        second = scan.scan_tree(mods, reference=None, reporter=reporter)

        assert second.reused == ()
        assert second.total_bytes == len(b"alpha") + len(b"beta")

    def test_reference_sans_taille_ni_date_fait_tout_rehacher(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """Une référence d'ancien format ne produit aucune entrée : repli sûr, tout est relu."""
        mods = _mod_tree(tmp_path)

        result = scan.scan_tree(mods, reference={}, reporter=reporter)

        assert result.reused == ()
        assert result.total_bytes == len(b"alpha") + len(b"beta")

    def test_une_reference_partielle_ne_court_circuite_que_ce_quelle_couvre(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        mods = _mod_tree(tmp_path)
        first = scan.scan_tree(mods, reporter=reporter)
        partial = {"102- Mod B/b.dds": _reference_of(first)["102- Mod B/b.dds"]}

        second = scan.scan_tree(mods, reference=partial, reporter=reporter)

        assert second.reused == ("102- Mod B/b.dds",)
        assert second.total_bytes == len(b"alpha")

    def test_les_stats_couvrent_aussi_les_fichiers_non_relus(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """Sinon la référence suivante perdrait sa colonne pour tout ce qui n'a pas bougé."""
        mods = _mod_tree(tmp_path)
        first = scan.scan_tree(mods, reporter=reporter)

        second = scan.scan_tree(mods, reference=_reference_of(first), reporter=reporter)

        assert second.stats == first.stats
        assert set(second.stats) == set(second.digests)
        assert second.stats["102- Mod B/b.dds"] == FileStat(
            size=len(b"beta"), mtime_ns=(mods / "102- Mod B" / "b.dds").stat().st_mtime_ns
        )

    def test_un_fichier_reference_mais_illisible_reste_illisible(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """Le court-circuit ne doit pas ressusciter un fichier disparu depuis la référence."""
        mods = _mod_tree(tmp_path)
        first = scan.scan_tree(mods, reporter=reporter)
        (mods / "102- Mod B" / "b.dds").unlink()

        second = scan.scan_tree(mods, reference=_reference_of(first), reporter=reporter)

        assert "102- Mod B/b.dds" not in second.digests
        assert second.reused == ("101- Mod A/gamedata/a.ltx",)

    def test_le_pool_ne_change_rien_au_court_circuit(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        """Même invariant que le reste du module : le nombre de fils ne change pas le résultat."""
        mods = _wide_tree(tmp_path, directories=3, per_directory=4)
        reference = _reference_of(scan.scan_tree(mods, reporter=reporter, workers=1))

        sequential = scan.scan_tree(mods, reference=reference, reporter=reporter, workers=1)
        parallel = scan.scan_tree(mods, reference=reference, reporter=reporter, workers=8)

        assert sequential.reused == parallel.reused
        assert sequential.digests == parallel.digests
        assert parallel.total_bytes == 0
