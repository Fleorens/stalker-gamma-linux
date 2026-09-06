"""Commande `verify [--repair]` de bout en bout (T12), sur une arborescence temporaire.

Le seul élément simulé est le moteur (`engine.install_gamma`) : tout le reste —
scan réel, écriture réelle de la référence, suppressions réelles — travaille sur
de vrais fichiers sous `tmp_path`. C'est ce qui donne du sens aux quatre
scénarios du prompt : premier passage, second passage, modification manuelle
détectée et attribuée, annulation sans réécriture de la référence.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from stalker_gamma_linux.engine.errors import EngineExecutionError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.exit_codes import CANCELLED_EXIT_CODE
from stalker_gamma_linux.integrity import baseline, session
from stalker_gamma_linux.integrity import repair as repair_module
from stalker_gamma_linux.mo2.paths import Mo2Paths
from tests.conftest import RecordingReporter

UPSTREAM_MODS = ["101- Mod A", "102- Mod B"]


@pytest.fixture
def install(tmp_path: Path) -> Path:
    """Install GAMMA minimale mais réaliste : deux mods amont, leurs archives, la liste."""
    gamma = tmp_path / "gamma"
    mods = gamma / "mods"
    downloads = gamma / "downloads"
    downloads.mkdir(parents=True)

    for index, name in enumerate(UPSTREAM_MODS):
        mod_dir = mods / name / "gamedata" / "configs"
        mod_dir.mkdir(parents=True)
        (mod_dir / "item.ltx").write_text(f"[item_{index}]\ncost = {index}\n")
        archive = f"{name}.7z"
        (mods / name / "meta.ini").write_text(f"[General]\ninstallationFile={archive}\n")
        (downloads / archive).write_bytes(b"archive payload")

    definitions = gamma / ".Grok's Modpack Installer" / "G.A.M.M.A" / "modpack_data"
    definitions.mkdir(parents=True)
    (definitions / "modlist.txt").write_text("".join(f"+{name}\n" for name in UPSTREAM_MODS))
    return tmp_path


@pytest.fixture
def engine_calls(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Remplace `full-install` par un mock qui repose les mods retirés."""
    calls: list[Path] = []

    def fake_install_gamma(paths: InstallPaths, **_kwargs: object) -> None:
        root = paths.gamma.parent
        calls.append(root)
        mods = Mo2Paths.under(root).mods
        for name in UPSTREAM_MODS:
            configs = mods / name / "gamedata" / "configs"
            if configs.is_dir():
                continue
            configs.mkdir(parents=True)
            index = UPSTREAM_MODS.index(name)
            (configs / "item.ltx").write_text(f"[item_{index}]\ncost = {index}\n")
            (mods / name / "meta.ini").write_text(f"[General]\ninstallationFile={name}.7z\n")

    monkeypatch.setattr(repair_module.engine, "install_gamma", fake_install_gamma)
    return calls


def _modify(install: Path, mod: str) -> Path:
    """Simule une corruption : un fichier de mod réécrit hors de MO2."""
    path = Mo2Paths.under(install).mods / mod / "gamedata" / "configs" / "item.ltx"
    path.write_text("corrompu\n")
    return path


def _modify_keeping_size_and_date(install: Path, mod: str) -> Path:
    """La corruption que le mode par défaut ne peut pas voir : même taille, même date.

    Il faut la fabriquer à la main (`os.utime`) — aucune écriture ordinaire ne
    produit ça, ce qui est précisément l'argument du court-circuit.
    """
    path = Mo2Paths.under(install).mods / mod / "gamedata" / "configs" / "item.ltx"
    before = path.stat()
    path.write_bytes(b"x" * before.st_size)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    return path


def _downgrade_reference(install: Path) -> None:
    """Réécrit la référence sans taille ni date — celle qu'une version antérieure laissait."""
    parsed = baseline.read_baseline(install)
    assert parsed is not None
    baseline.write_baseline(install, parsed.digests)


class TestFirstPass:
    def test_cree_la_reference_sans_annoncer_de_verification(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        code = session.run_verify(install, reporter=reporter)

        assert code == 0
        assert baseline.baseline_path(install).is_file()
        message = "\n".join(reporter.of_kind("success"))
        assert "Reference recorded" in message
        assert "No comparison was made" in message
        assert "Run the check again" in message

    def test_la_reference_couvre_tous_les_fichiers_de_mods(self, install: Path) -> None:
        session.run_verify(install, reporter=RecordingReporter())

        parsed = baseline.read_baseline(install)
        assert parsed is not None
        assert set(parsed.digests) == {
            "101- Mod A/gamedata/configs/item.ltx",
            "101- Mod A/meta.ini",
            "102- Mod B/gamedata/configs/item.ltx",
            "102- Mod B/meta.ini",
        }

    def test_sans_dossier_de_mods(self, tmp_path: Path, reporter: RecordingReporter) -> None:
        code = session.run_verify(tmp_path, reporter=reporter)

        assert code == 1
        assert "No mods directory" in "\n".join(reporter.of_kind("error"))


class TestSecondPass:
    def test_install_inchangee(self, install: Path, reporter: RecordingReporter) -> None:
        session.run_verify(install, reporter=RecordingReporter())

        code = session.run_verify(install, reporter=reporter)

        assert code == 0
        assert "Unchanged" in reporter.text

    def test_modification_manuelle_detectee_et_attribuee_au_bon_mod(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        _modify(install, "101- Mod A")

        code = session.run_verify(install, reporter=reporter)

        assert code == 1
        assert "101- Mod A/gamedata/configs/item.ltx" in reporter.text
        assert "101- Mod A" in reporter.text
        assert "102- Mod B" not in reporter.text

    def test_fichier_ajoute_signale_sans_compter_comme_avarie(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        (Mo2Paths.under(install).mods / "101- Mod A" / "mon-tweak.ltx").write_text("à moi")

        code = session.run_verify(install, reporter=reporter)

        assert code == 0  # rien d'abîmé : un ajout n'est pas une avarie
        assert "mon-tweak.ltx" in reporter.text
        assert "left alone" in reporter.text
        # Le verdict le dit, au lieu de laisser l'utilisateur interpréter la liste.
        assert "Nothing damaged" in "\n".join(reporter.of_kind("success"))

    def test_conseille_repair_sans_le_faire(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        corrupted = _modify(install, "101- Mod A")

        session.run_verify(install, reporter=reporter)

        assert "verify --repair" in "\n".join(reporter.of_kind("warn"))
        assert corrupted.read_text() == "corrompu\n"


class TestCancellation:
    def test_scan_annule_laisse_la_reference_precedente_intacte(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        before = baseline.baseline_path(install).read_text()
        _modify(install, "101- Mod A")
        cancel_event = threading.Event()
        cancel_event.set()

        code = session.run_verify(install, reporter=reporter, cancel_event=cancel_event)

        assert code == CANCELLED_EXIT_CODE
        assert baseline.baseline_path(install).read_text() == before

    def test_premier_passage_annule_necrit_aucune_reference(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        cancel_event = threading.Event()
        cancel_event.set()

        code = session.run_verify(install, reporter=reporter, cancel_event=cancel_event)

        assert code == CANCELLED_EXIT_CODE
        assert not baseline.baseline_path(install).exists()


class TestRepair:
    def test_repare_le_mod_abime_et_reprend_la_reference(
        self, install: Path, engine_calls: list[Path], reporter: RecordingReporter
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        before = baseline.read_baseline(install)
        assert before is not None
        _modify(install, "101- Mod A")

        code = session.run_verify(install, repair_damaged=True, reporter=reporter)

        assert code == 0
        assert engine_calls == [install]
        # Réparé : le contenu d'origine est revenu, et la référence a été reprise.
        # Ce sont les **empreintes** qui doivent être revenues à l'identique, pas
        # le fichier de référence octet pour octet : la date de modification des
        # fichiers réinstallés a changé, et la référence la porte désormais.
        after = baseline.read_baseline(install)
        assert after is not None
        assert after.digests == before.digests
        assert set(after.known) == set(after.digests)

    def test_apres_reparation_le_passage_suivant_est_propre(
        self, install: Path, engine_calls: list[Path]
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        _modify(install, "101- Mod A")
        session.run_verify(install, repair_damaged=True, reporter=RecordingReporter())

        reporter = RecordingReporter()
        assert session.run_verify(install, reporter=reporter) == 0
        assert "Unchanged" in reporter.text

    def test_supprime_larchive_du_mod_concerne_seulement(
        self, install: Path, engine_calls: list[Path]
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        _modify(install, "101- Mod A")
        downloads = install / "gamma" / "downloads"

        session.run_verify(install, repair_damaged=True, reporter=RecordingReporter())

        assert not (downloads / "101- Mod A.7z").exists()
        assert (downloads / "102- Mod B.7z").exists()

    def test_ne_supprime_jamais_un_fichier_ajoute_par_lutilisateur(
        self, install: Path, engine_calls: list[Path], reporter: RecordingReporter
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        mine = Mo2Paths.under(install).mods / "101- Mod A" / "gamedata" / "mon-patch.ltx"
        mine.write_text("mon patch")
        _modify(install, "101- Mod A")

        code = session.run_verify(install, repair_damaged=True, reporter=reporter)

        assert code == 1  # rien de réparable sans détruire ce fichier
        assert mine.read_text() == "mon patch"
        assert engine_calls == []
        assert "would delete them" in reporter.text

    def test_mod_hors_liste_amont_signale_et_intact(
        self, install: Path, engine_calls: list[Path], reporter: RecordingReporter
    ) -> None:
        extra = Mo2Paths.under(install).mods / "999- Mon mod perso"
        extra.mkdir()
        (extra / "a.ltx").write_text("v1")
        session.run_verify(install, reporter=RecordingReporter())
        (extra / "a.ltx").write_text("v2")

        code = session.run_verify(install, repair_damaged=True, reporter=reporter)

        assert code == 1
        assert (extra / "a.ltx").read_text() == "v2"
        assert engine_calls == []
        assert "not found in the local modpack definition" in reporter.text

    def test_liste_amont_absente_refuse_de_reparer(
        self, install: Path, engine_calls: list[Path], reporter: RecordingReporter
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        _modify(install, "101- Mod A")
        (install / "gamma" / ".Grok's Modpack Installer").rename(install / "gamma" / "parti")

        code = session.run_verify(install, repair_damaged=True, reporter=reporter)

        assert code == 1
        assert "No local modpack definition" in "\n".join(reporter.of_kind("error"))
        assert engine_calls == []

    def test_echec_du_moteur_remonte_sans_reprendre_la_reference(
        self, install: Path, reporter: RecordingReporter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        before = baseline.baseline_path(install).read_text()
        _modify(install, "101- Mod A")

        def boom(*_args: object, **_kwargs: object) -> None:
            raise EngineExecutionError("full-install", 1, "boom")

        monkeypatch.setattr(repair_module.engine, "install_gamma", boom)
        code = session.run_verify(install, repair_damaged=True, reporter=reporter)

        assert code == 1
        assert baseline.baseline_path(install).read_text() == before


class TestPhaseLabels:
    def test_un_seul_temps_sans_reparation(self) -> None:
        assert len(session.verify_phase_labels()) == 1

    def test_quatre_temps_avec_reparation(self) -> None:
        assert len(session.verify_phase_labels(repair_damaged=True)) == 4


class TestShortCircuit:
    """Le court-circuit taille/date de bout en bout : ce qu'il évite, ce qu'il coûte."""

    def test_la_reference_ecrite_porte_taille_et_date(self, install: Path) -> None:
        session.run_verify(install, reporter=RecordingReporter())

        parsed = baseline.read_baseline(install)
        assert parsed is not None
        assert set(parsed.known) == set(parsed.digests)

    def test_second_passage_ne_relit_pas_ce_qui_na_pas_bouge(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())

        code = session.run_verify(install, reporter=reporter)

        assert code == 0
        # Le raccourci est dit dans le rapport, pas seulement dans la doc.
        assert "were not reread" in reporter.text
        assert "verify --full" in reporter.text

    def test_modification_reelle_toujours_detectee(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        """Une écriture ordinaire déplace la date : le court-circuit ne la couvre jamais."""
        session.run_verify(install, reporter=RecordingReporter())
        _modify(install, "101- Mod A")

        code = session.run_verify(install, reporter=reporter)

        assert code == 1
        assert "101- Mod A/gamedata/configs/item.ltx" in reporter.text

    def test_corruption_preservant_taille_et_date_echappe_au_defaut(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        """La contrepartie, écrite noir sur blanc : ce mode-là ne la voit pas."""
        session.run_verify(install, reporter=RecordingReporter())
        _modify_keeping_size_and_date(install, "101- Mod A")

        code = session.run_verify(install, reporter=reporter)

        assert code == 0
        assert "Unchanged" in reporter.text

    def test_full_voit_ce_que_le_defaut_laisse_passer(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        _modify_keeping_size_and_date(install, "101- Mod A")

        code = session.run_verify(install, full_scan=True, reporter=reporter)

        assert code == 1
        assert "101- Mod A/gamedata/configs/item.ltx" in reporter.text
        # Et le mode est annoncé avant le scan, pas déduit du résultat.
        assert "Full scan" in reporter.text

    def test_full_rehache_meme_ce_qui_na_pas_bouge(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())

        code = session.run_verify(install, full_scan=True, reporter=reporter)

        assert code == 0
        assert "were not reread" not in reporter.text


class TestOldReference:
    """Référence d'avant la colonne taille/date : repli sûr, puis reprise prudente."""

    def test_tout_est_rehache_et_lutilisateur_sait_pourquoi(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        _downgrade_reference(install)
        _modify_keeping_size_and_date(install, "101- Mod A")

        code = session.run_verify(install, reporter=reporter)

        # Rien à court-circuiter : la corruption la plus discrète est vue.
        assert code == 1
        assert "The reference predates size/date recording" in reporter.text

    def test_la_reference_est_reprise_pour_le_passage_suivant(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        """Sans cette reprise, une ancienne référence ferait tout rehacher à chaque fois."""
        session.run_verify(install, reporter=RecordingReporter())
        _downgrade_reference(install)

        session.run_verify(install, reporter=RecordingReporter())
        code = session.run_verify(install, reporter=reporter)

        assert code == 0
        assert "were not reread" in reporter.text

    def test_la_reprise_nattache_jamais_taille_et_date_a_un_fichier_abime(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        """L'invariant qui rend la reprise sûre : sinon l'avarie sortirait du rapport.

        Le fichier abîmé conserve taille et date d'origine. Lui attacher les
        siennes le ferait court-circuiter au passage suivant, avec l'empreinte
        de la référence — l'avarie disparaîtrait sans avoir été réparée.
        """
        session.run_verify(install, reporter=RecordingReporter())
        _downgrade_reference(install)
        _modify_keeping_size_and_date(install, "101- Mod A")
        session.run_verify(install, reporter=RecordingReporter())

        code = session.run_verify(install, reporter=reporter)

        assert code == 1
        assert "101- Mod A/gamedata/configs/item.ltx" in reporter.text

    def test_la_reprise_ne_fait_pas_entrer_les_ajouts_dans_la_reference(
        self, install: Path, reporter: RecordingReporter
    ) -> None:
        """Un fichier de l'utilisateur reste « ajouté » : la reprise ne change que la forme."""
        session.run_verify(install, reporter=RecordingReporter())
        _downgrade_reference(install)
        (Mo2Paths.under(install).mods / "101- Mod A" / "mon-tweak.ltx").write_text("à moi")
        session.run_verify(install, reporter=RecordingReporter())

        code = session.run_verify(install, reporter=reporter)

        assert code == 0
        assert "mon-tweak.ltx" in reporter.text
        assert "left alone" in reporter.text

    def test_les_empreintes_ne_bougent_pas_pendant_la_reprise(self, install: Path) -> None:
        session.run_verify(install, reporter=RecordingReporter())
        original = baseline.read_baseline(install)
        assert original is not None
        _downgrade_reference(install)

        session.run_verify(install, reporter=RecordingReporter())

        reprise = baseline.read_baseline(install)
        assert reprise is not None
        assert reprise.digests == original.digests
        assert set(reprise.known) == set(original.digests)
