"""Classification et suppression ciblée pour `verify --repair` (T12).

Deux garanties se jouent ici, et ce sont celles qui peuvent détruire des
données de l'utilisateur si elles cèdent :

1. rien n'est supprimé hors de `mods/` / `downloads/`, quel que soit le nom
   qui arrive de la liste amont ou d'un `meta.ini` ;
2. un mod qui contient des fichiers ajoutés par l'utilisateur n'est jamais
   réparé — le `rmtree` les emporterait avec lui.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stalker_gamma_linux.integrity import repair
from stalker_gamma_linux.integrity.errors import ModpackDefinitionMissingError, RepairFailedError
from stalker_gamma_linux.integrity.report import IntegrityReport
from stalker_gamma_linux.paths_safety import UnsafeWipeTargetError
from tests.conftest import RecordingReporter

_UPSTREAM = frozenset({"101- Mod A", "102- Mod B"})


def _install(root: Path) -> Path:
    """Squelette minimal : `gamma/mods/`, `gamma/downloads/`, définitions amont."""
    gamma = root / "gamma"
    (gamma / "mods").mkdir(parents=True)
    (gamma / "downloads").mkdir(parents=True)
    return gamma


def _mod(gamma: Path, name: str, *, archive: str | None = None) -> Path:
    mod_dir = gamma / "mods" / name
    mod_dir.mkdir(parents=True)
    (mod_dir / "gamedata").mkdir()
    (mod_dir / "gamedata" / "x.ltx").write_text("content")
    if archive is not None:
        (mod_dir / "meta.ini").write_text(
            f"[General]\ngameName=stalkeranomaly\ninstallationFile={archive}\nmodid=0\n"
        )
        (gamma / "downloads" / archive).write_bytes(b"archive")
    return mod_dir


def _definitions(gamma: Path, names: list[str]) -> Path:
    directory = gamma / ".Grok's Modpack Installer" / "G.A.M.M.A" / "modpack_data"
    directory.mkdir(parents=True)
    body = "".join(f"+{name}\n" for name in names)
    (directory / "modlist.txt").write_text(f"# This file was automatically generated\n{body}")
    return directory


class TestUpstreamModNames:
    def test_lit_la_liste_deposee_par_le_moteur(self, tmp_path: Path) -> None:
        gamma = _install(tmp_path)
        _definitions(gamma, ["101- Mod A", "102- Mod B"])

        assert repair.upstream_mod_names(gamma) == _UPSTREAM

    def test_inclut_les_mods_desactives(self, tmp_path: Path) -> None:
        """Désactivé dans MO2 ≠ absent du disque : il reste d'origine officielle."""
        gamma = _install(tmp_path)
        directory = _definitions(gamma, ["101- Mod A"])
        (directory / "modlist.txt").write_text("+101- Mod A\n-102- Mod B\n")

        assert repair.upstream_mod_names(gamma) == _UPSTREAM

    def test_compte_les_separateurs_de_mo2(self, tmp_path: Path) -> None:
        """Ce sont de vrais dossiers, créés par le moteur — pas des ajouts du joueur.

        Constaté sur une install réelle : 28 des 43 dossiers absents de la
        liste « mods » étaient des séparateurs, que `--repair` annonçait comme
        « ressemble à un mod que vous avez ajouté vous-même ».
        """
        gamma = _install(tmp_path)
        directory = _definitions(gamma, ["101- Mod A"])
        (directory / "modlist.txt").write_text("+Weapons_separator\n+101- Mod A\n")

        assert repair.upstream_mod_names(gamma) == frozenset({"101- Mod A", "Weapons_separator"})

    def test_compte_les_mods_livres_en_clair_dans_modpack_addons(self, tmp_path: Path) -> None:
        """`modlist.txt` n'est pas la liste complète des dossiers du modpack.

        Constaté sur une install réelle : `modpack_addons/` livre 388 dossiers
        que `_copy_gamma_modpack` copie tels quels dans `mods/`, sans qu'ils
        figurent dans `modlist.txt`. Les ignorer faisait refuser leur
        réparation en les prenant pour des ajouts du joueur.
        """
        gamma = _install(tmp_path)
        _definitions(gamma, ["101- Mod A"])
        addons = gamma / ".Grok's Modpack Installer" / "G.A.M.M.A" / "modpack_addons"
        (addons / "Un Addon Livré En Clair").mkdir(parents=True)
        (addons / "un-fichier-pas-un-mod.txt").write_text("ignoré")

        assert repair.upstream_mod_names(gamma) == frozenset(
            {"101- Mod A", "Un Addon Livré En Clair"}
        )

    def test_sans_modpack_addons_seule_la_liste_compte(self, tmp_path: Path) -> None:
        gamma = _install(tmp_path)
        _definitions(gamma, ["101- Mod A", "102- Mod B"])

        assert repair.upstream_mod_names(gamma) == _UPSTREAM

    def test_liste_absente_leve_une_erreur_typee(self, tmp_path: Path) -> None:
        gamma = _install(tmp_path)

        with pytest.raises(ModpackDefinitionMissingError):
            repair.upstream_mod_names(gamma)


class TestArchiveNameForMod:
    def test_lit_installation_file(self, tmp_path: Path) -> None:
        gamma = _install(tmp_path)
        mod_dir = _mod(gamma, "101- Mod A", archive="mod-a-1.2.7z")

        assert repair.archive_name_for_mod(mod_dir) == "mod-a-1.2.7z"

    def test_sans_meta_ini(self, tmp_path: Path) -> None:
        gamma = _install(tmp_path)
        mod_dir = _mod(gamma, "101- Mod A")

        assert repair.archive_name_for_mod(mod_dir) is None

    def test_meta_ini_sans_la_cle(self, tmp_path: Path) -> None:
        gamma = _install(tmp_path)
        mod_dir = _mod(gamma, "101- Mod A")
        (mod_dir / "meta.ini").write_text("[General]\nmodid=0\n")

        assert repair.archive_name_for_mod(mod_dir) is None


class TestBuildRepairPlan:
    def test_mod_amont_abime_est_reparable(self, tmp_path: Path) -> None:
        report = IntegrityReport(mods_dir=tmp_path, changed=("101- Mod A/gamedata/x.ltx",))

        plan = repair.build_repair_plan(report, _UPSTREAM)

        assert plan.repairable == ("101- Mod A",)
        assert plan.withheld == ()

    def test_fichier_disparu_rend_le_mod_reparable(self, tmp_path: Path) -> None:
        report = IntegrityReport(mods_dir=tmp_path, removed=("102- Mod B/y.ltx",))

        assert repair.build_repair_plan(report, _UPSTREAM).repairable == ("102- Mod B",)

    def test_mod_sans_source_officielle_laisse_intact(self, tmp_path: Path) -> None:
        report = IntegrityReport(mods_dir=tmp_path, changed=("999- Mon mod perso/x.ltx",))

        plan = repair.build_repair_plan(report, _UPSTREAM)

        assert plan.repairable == ()
        assert [mod.name for mod in plan.withheld] == ["999- Mon mod perso"]
        assert "not found in the local modpack definition" in plan.withheld[0].reason

    def test_mod_contenant_des_fichiers_ajoutes_laisse_intact(self, tmp_path: Path) -> None:
        """Réparer, c'est `rmtree` : ça emporterait le fichier de l'utilisateur."""
        report = IntegrityReport(
            mods_dir=tmp_path,
            changed=("101- Mod A/gamedata/x.ltx",),
            added=("101- Mod A/gamedata/mon-tweak.ltx",),
        )

        plan = repair.build_repair_plan(report, _UPSTREAM)

        assert plan.repairable == ()
        assert "would delete them" in plan.withheld[0].reason

    def test_ajouts_seuls_ne_declenchent_aucune_reparation(self, tmp_path: Path) -> None:
        report = IntegrityReport(mods_dir=tmp_path, added=("101- Mod A/mon-tweak.ltx",))

        plan = repair.build_repair_plan(report, _UPSTREAM)

        assert plan.is_empty
        assert plan.withheld == ()

    def test_fichiers_en_vrac_sous_mods_ne_sont_pas_un_mod(self, tmp_path: Path) -> None:
        report = IntegrityReport(mods_dir=tmp_path, changed=("note.txt",))

        plan = repair.build_repair_plan(report, _UPSTREAM)

        assert plan.repairable == ()
        assert "loose files" in plan.withheld[0].reason


class TestRemoveMod:
    def test_supprime_le_dossier_et_son_archive(self, tmp_path: Path) -> None:
        gamma = _install(tmp_path)
        mod_dir = _mod(gamma, "101- Mod A", archive="mod-a.7z")

        removed_dir, removed_archive = repair.remove_mod(tmp_path, "101- Mod A")

        assert removed_dir == mod_dir.resolve()
        assert removed_archive == (gamma / "downloads" / "mod-a.7z").resolve()
        assert not mod_dir.exists()
        assert not (gamma / "downloads" / "mod-a.7z").exists()

    def test_sans_archive_connue_seul_le_dossier_part(self, tmp_path: Path) -> None:
        gamma = _install(tmp_path)
        mod_dir = _mod(gamma, "101- Mod A")

        _removed_dir, removed_archive = repair.remove_mod(tmp_path, "101- Mod A")

        assert removed_archive is None
        assert not mod_dir.exists()

    def test_archive_deja_absente_nest_pas_une_erreur(self, tmp_path: Path) -> None:
        gamma = _install(tmp_path)
        _mod(gamma, "101- Mod A", archive="mod-a.7z")
        (gamma / "downloads" / "mod-a.7z").unlink()

        _removed_dir, removed_archive = repair.remove_mod(tmp_path, "101- Mod A")

        assert removed_archive is None

    def test_ne_touche_pas_aux_autres_mods(self, tmp_path: Path) -> None:
        gamma = _install(tmp_path)
        _mod(gamma, "101- Mod A", archive="mod-a.7z")
        voisin = _mod(gamma, "102- Mod B", archive="mod-b.7z")

        repair.remove_mod(tmp_path, "101- Mod A")

        assert voisin.is_dir()
        assert (gamma / "downloads" / "mod-b.7z").exists()

    @pytest.mark.parametrize("name", ["..", "../../etc", "sous/dossier", "..\\ailleurs"])
    def test_nom_qui_sechappe_de_mods_refuse(self, tmp_path: Path, name: str) -> None:
        _install(tmp_path)
        temoin = tmp_path / "precieux"
        temoin.mkdir()

        with pytest.raises(UnsafeWipeTargetError):
            repair.remove_mod(tmp_path, name)

        assert temoin.is_dir()

    def test_mod_qui_est_un_lien_symbolique_refuse(self, tmp_path: Path) -> None:
        gamma = _install(tmp_path)
        ailleurs = tmp_path / "precieux"
        ailleurs.mkdir()
        (ailleurs / "fichier").write_text("à ne pas perdre")
        (gamma / "mods" / "101- Mod A").symlink_to(ailleurs)

        with pytest.raises(UnsafeWipeTargetError):
            repair.remove_mod(tmp_path, "101- Mod A")

        assert (ailleurs / "fichier").exists()

    def test_archive_qui_sechappe_de_downloads_refusee(self, tmp_path: Path) -> None:
        """Le `meta.ini` n'est pas écrit par nous : son contenu est validé aussi."""
        gamma = _install(tmp_path)
        mod_dir = _mod(gamma, "101- Mod A")
        (mod_dir / "meta.ini").write_text("[General]\ninstallationFile=../../../etc/passwd\n")

        with pytest.raises(UnsafeWipeTargetError):
            repair.remove_mod(tmp_path, "101- Mod A")

        # Refusé **avant** toute suppression : le mod n'est pas laissé à moitié retiré.
        assert mod_dir.is_dir()

    def test_dossier_deja_disparu_nest_pas_une_erreur(self, tmp_path: Path) -> None:
        """Un mod entièrement effacé est justement un des cas qu'on répare."""
        _install(tmp_path)

        assert repair.remove_mod(tmp_path, "101- Mod A") == (None, None)

    def test_echec_de_suppression_leve_une_erreur_typee(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        gamma = _install(tmp_path)
        _mod(gamma, "101- Mod A")

        def refuse(*_args: object, **_kwargs: object) -> None:
            raise OSError("Read-only file system")

        monkeypatch.setattr(repair.shutil, "rmtree", refuse)
        with pytest.raises(RepairFailedError):
            repair.remove_mod(tmp_path, "101- Mod A")


class TestRemoveMods:
    def test_rapporte_ce_qui_a_ete_retire(
        self, tmp_path: Path, reporter: RecordingReporter
    ) -> None:
        gamma = _install(tmp_path)
        _mod(gamma, "101- Mod A", archive="mod-a.7z")
        _mod(gamma, "102- Mod B")

        removed = repair.remove_mods(tmp_path, ["101- Mod A", "102- Mod B"], reporter=reporter)

        assert removed == ("101- Mod A", "102- Mod B")
        assert "mod-a.7z" in reporter.text

    def test_liste_vide(self, tmp_path: Path, reporter: RecordingReporter) -> None:
        _install(tmp_path)

        assert repair.remove_mods(tmp_path, [], reporter=reporter) == ()


class TestFormatPlan:
    def test_annonce_les_deux_categories(self) -> None:
        plan = repair.RepairPlan(
            repairable=("101- Mod A",),
            withheld=(repair.WithheldMod("999- Perso", "no upstream source"),),
        )

        text = repair.format_plan(plan)

        assert "101- Mod A" in text
        assert "999- Perso" in text
        assert "no upstream source" in text
