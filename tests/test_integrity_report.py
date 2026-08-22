"""Diff référence ↔ disque et attribution des écarts à leur mod (T12).

Logique pure : aucun fichier n'est touché ici, on compare deux dictionnaires.
La distinction qui compte est `is_damaged` (modifié/disparu) vs
`has_user_files` (ajouté) — c'est elle qui décide plus tard de ce que
`--repair` a le droit de supprimer.
"""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.integrity import report as report_module
from stalker_gamma_linux.integrity.scan import UnreadableFile

_MD5_A = "0123456789abcdef0123456789abcdef"
_MD5_B = "fedcba9876543210fedcba9876543210"

MODS = Path("/install/gamma/mods")


class TestCompare:
    def test_identique(self) -> None:
        digests = {"mod/a.ltx": _MD5_A}

        assert report_module.compare(digests, dict(digests)) == ((), (), ())

    def test_fichier_modifie(self) -> None:
        changed, added, removed = report_module.compare(
            {"mod/a.ltx": _MD5_A}, {"mod/a.ltx": _MD5_B}
        )

        assert (changed, added, removed) == (("mod/a.ltx",), (), ())

    def test_fichier_ajoute(self) -> None:
        changed, added, removed = report_module.compare(
            {"mod/a.ltx": _MD5_A}, {"mod/a.ltx": _MD5_A, "mod/tweak.ltx": _MD5_B}
        )

        assert (changed, added, removed) == ((), ("mod/tweak.ltx",), ())

    def test_fichier_disparu(self) -> None:
        changed, added, removed = report_module.compare({"mod/a.ltx": _MD5_A}, {})

        assert (changed, added, removed) == ((), (), ("mod/a.ltx",))

    def test_les_quatre_categories_a_la_fois(self) -> None:
        baseline = {"mod/a.ltx": _MD5_A, "mod/b.ltx": _MD5_A, "mod/c.ltx": _MD5_A}
        observed = {"mod/a.ltx": _MD5_B, "mod/c.ltx": _MD5_A, "mod/neuf.ltx": _MD5_B}

        changed, added, removed = report_module.compare(baseline, observed)

        assert changed == ("mod/a.ltx",)
        assert added == ("mod/neuf.ltx",)
        assert removed == ("mod/b.ltx",)

    def test_resultats_tries(self) -> None:
        changed, _added, _removed = report_module.compare(
            {"z.ltx": _MD5_A, "a.ltx": _MD5_A}, {"z.ltx": _MD5_B, "a.ltx": _MD5_B}
        )

        assert changed == ("a.ltx", "z.ltx")


class TestModOf:
    def test_premier_segment(self) -> None:
        assert report_module.mod_of("312- Gunslinger - Teivazcz/gamedata/a.dds") == (
            "312- Gunslinger - Teivazcz"
        )

    def test_fichier_a_la_racine_nappartient_a_aucun_mod(self) -> None:
        assert report_module.mod_of("note.txt") == report_module.ROOT_MOD


class TestGroupByMod:
    def test_attribue_chaque_ecart_a_son_mod(self) -> None:
        report = report_module.IntegrityReport(
            mods_dir=MODS,
            changed=("101- A/gamedata/x.ltx", "102- B/y.ltx"),
            added=("101- A/mon-tweak.ltx",),
            removed=("102- B/z.ltx",),
        )

        findings = {finding.name: finding for finding in report_module.group_by_mod(report)}

        assert findings["101- A"].changed == ("101- A/gamedata/x.ltx",)
        assert findings["101- A"].added == ("101- A/mon-tweak.ltx",)
        assert findings["102- B"].removed == ("102- B/z.ltx",)

    def test_un_mod_avec_seulement_des_ajouts_nest_pas_abime(self) -> None:
        report = report_module.IntegrityReport(mods_dir=MODS, added=("101- A/mon-tweak.ltx",))

        (finding,) = report_module.group_by_mod(report)

        assert finding.has_user_files
        assert not finding.is_damaged
        assert report_module.damaged_mods(report) == ()

    def test_damaged_mods_ne_garde_que_les_abimes(self) -> None:
        report = report_module.IntegrityReport(
            mods_dir=MODS, changed=("101- A/x.ltx",), added=("102- B/mon-tweak.ltx",)
        )

        assert [finding.name for finding in report_module.damaged_mods(report)] == ["101- A"]


class TestIntegrityReport:
    def test_intact_malgre_des_ajouts_de_lutilisateur(self) -> None:
        report = report_module.IntegrityReport(mods_dir=MODS, added=("101- A/tweak.ltx",))

        assert report.is_intact
        assert not report.is_clean

    def test_un_fichier_illisible_compte_comme_une_avarie(self) -> None:
        report = report_module.IntegrityReport(
            mods_dir=MODS, unreadable=(UnreadableFile("101- A/x.ltx", "Permission denied"),)
        )

        assert not report.is_intact


class TestFormatReport:
    def test_install_intacte(self) -> None:
        text = report_module.format_report(
            report_module.IntegrityReport(mods_dir=MODS, scanned_files=3, scanned_bytes=1024)
        )

        assert "Unchanged" in text

    def test_les_ajouts_sont_annonces_comme_laisses_tranquilles(self) -> None:
        text = report_module.format_report(
            report_module.IntegrityReport(mods_dir=MODS, added=("101- A/tweak.ltx",))
        )

        assert "left alone" in text
        assert "101- A/tweak.ltx" in text

    def test_les_mods_touches_sont_nommes(self) -> None:
        text = report_module.format_report(
            report_module.IntegrityReport(mods_dir=MODS, changed=("101- A/gamedata/x.ltx",))
        )

        assert "101- A" in text

    def test_longue_liste_resumee(self) -> None:
        paths = tuple(f"101- A/{index}.ltx" for index in range(50))
        text = report_module.format_report(
            report_module.IntegrityReport(mods_dir=MODS, changed=paths)
        )

        assert "and 40 more" in text
        assert "101- A/49.ltx" not in text

    def test_lignes_de_reference_illisibles_signalees(self) -> None:
        text = report_module.format_report(
            report_module.IntegrityReport(
                mods_dir=MODS, removed=("a.ltx",), unparsed_baseline_lines=("n'importe quoi",)
            )
        )

        assert "unreadable line(s) in the reference" in text
