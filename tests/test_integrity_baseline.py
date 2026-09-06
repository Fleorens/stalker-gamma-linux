"""Format de l'empreinte de référence `gamma-md5.txt` (T12).

Le point sensible est le **parsing** : un découpage par offsets fixes
(`line[:32]`) marche sur nos propres fichiers et casse sur tout le reste. Les
cas ci-dessous couvrent donc les variantes de format qu'on peut réellement
croiser, plus la garantie d'atomicité de l'écriture.

Depuis l'ajout de la colonne taille/mtime, la rétrocompatibilité **en lecture**
est le second point sensible : une référence écrite avant cette colonne, ou par
`md5sum`, doit continuer d'être relue à l'identique, et ne produire aucune
entrée court-circuitable (`known` vide) — c'est le repli sûr, celui qui fait
tout rehacher plutôt que de faire confiance à ce qu'on n'a pas.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stalker_gamma_linux.integrity import baseline
from stalker_gamma_linux.integrity.errors import BaselineReadError, BaselineWriteError
from stalker_gamma_linux.integrity.fingerprint import FileStat, KnownFile

_MD5_A = "0123456789abcdef0123456789abcdef"
_MD5_B = "fedcba9876543210fedcba9876543210"
_STAT_A = FileStat(size=4096, mtime_ns=1_724_313_600_123_456_789)
_STAT_B = FileStat(size=12, mtime_ns=-86_400_000_000_000)


class TestParseBaseline:
    def test_format_canonique(self) -> None:
        parsed = baseline.parse_baseline(f"{_MD5_A}  mod/gamedata/file.ltx\n")

        assert parsed.digests == {"mod/gamedata/file.ltx": _MD5_A}
        assert parsed.skipped == ()

    def test_separateur_simple_espace(self) -> None:
        parsed = baseline.parse_baseline(f"{_MD5_A} mod/file.ltx\n")

        assert parsed.digests == {"mod/file.ltx": _MD5_A}

    def test_separateur_tabulation(self) -> None:
        parsed = baseline.parse_baseline(f"{_MD5_A}\tmod/file.ltx\n")

        assert parsed.digests == {"mod/file.ltx": _MD5_A}

    def test_mode_binaire_de_md5sum(self) -> None:
        """`md5sum -b` préfixe le chemin d'un `*` : il fait partie du format."""
        parsed = baseline.parse_baseline(f"{_MD5_A}  *mod/file.ltx\n")

        assert parsed.digests == {"mod/file.ltx": _MD5_A}

    def test_chemin_avec_espaces(self) -> None:
        name = "312- Gunslinger Guns - Teivazcz/gamedata/a b.dds"
        parsed = baseline.parse_baseline(f"{_MD5_A}  {name}\n")

        assert parsed.digests == {name: _MD5_A}

    def test_chemin_commencant_par_une_espace_preserve(self) -> None:
        """Le séparateur canonique est essayé en premier, justement pour ça."""
        parsed = baseline.parse_baseline(f"{_MD5_A}   espace-devant.ltx\n")

        assert parsed.digests == {" espace-devant.ltx": _MD5_A}

    def test_hash_majuscules_normalise(self) -> None:
        parsed = baseline.parse_baseline(f"{_MD5_A.upper()}  mod/file.ltx\n")

        assert parsed.digests == {"mod/file.ltx": _MD5_A}

    def test_lignes_vides_ignorees_sans_bruit(self) -> None:
        parsed = baseline.parse_baseline(f"\n{_MD5_A}  a.ltx\n\n")

        assert parsed.digests == {"a.ltx": _MD5_A}
        assert parsed.skipped == ()

    @pytest.mark.parametrize(
        "line",
        [
            "pas du tout un hash  a.ltx",
            "0123  a.ltx",  # trop court
            f"{_MD5_A}",  # pas de chemin
            f"{_MD5_A}  ",  # chemin vide
        ],
    )
    def test_ligne_inattendue_rapportee_pas_avalee(self, line: str) -> None:
        parsed = baseline.parse_baseline(f"{line}\n{_MD5_B}  bon.ltx\n")

        assert parsed.digests == {"bon.ltx": _MD5_B}
        assert parsed.skipped == (line,)

    def test_fins_de_ligne_windows(self) -> None:
        parsed = baseline.parse_baseline(f"{_MD5_A}  a.ltx\r\n")

        assert parsed.digests == {"a.ltx": _MD5_A}


class TestParseStatColumn:
    """La colonne `taille,mtime_ns` : lue quand elle est là, jamais exigée."""

    def test_colonne_lue_et_rangee_dans_known(self) -> None:
        parsed = baseline.parse_baseline(
            f"{_MD5_A}  {_STAT_A.size},{_STAT_A.mtime_ns}  mod/file.ltx\n"
        )

        assert parsed.digests == {"mod/file.ltx": _MD5_A}
        assert parsed.known == {"mod/file.ltx": KnownFile(digest=_MD5_A, stat=_STAT_A)}
        assert parsed.predates_stats is False

    def test_mtime_negatif_accepte(self) -> None:
        """Une archive de mods peut porter une date d'avant 1970 : l'extraction la restitue."""
        parsed = baseline.parse_baseline(
            f"{_MD5_A}  {_STAT_B.size},{_STAT_B.mtime_ns}  mod/vieux.ltx\n"
        )

        assert parsed.known == {"mod/vieux.ltx": KnownFile(digest=_MD5_A, stat=_STAT_B)}

    def test_ancienne_reference_relue_sans_court_circuit_possible(self) -> None:
        """Le repli sûr : pas de colonne, donc rien à court-circuiter — tout sera rehaché."""
        parsed = baseline.parse_baseline(f"{_MD5_A}  mod/file.ltx\n{_MD5_B}  autre.dds\n")

        assert parsed.digests == {"mod/file.ltx": _MD5_A, "autre.dds": _MD5_B}
        assert parsed.known == {}
        assert parsed.predates_stats is True

    def test_reference_mixte_ne_court_circuite_que_ce_quelle_documente(self) -> None:
        parsed = baseline.parse_baseline(f"{_MD5_A}  12,34  neuf.ltx\n{_MD5_B}  ancien.ltx\n")

        assert set(parsed.digests) == {"neuf.ltx", "ancien.ltx"}
        assert set(parsed.known) == {"neuf.ltx"}
        assert parsed.predates_stats is False

    @pytest.mark.parametrize(
        "remainder",
        [
            "mod/a  b.ltx",  # deux espaces *dans* le chemin
            "12,  a.ltx",  # colonne incomplète
            "12,ab  a.ltx",  # mtime non numérique
            "-12,34  a.ltx",  # taille négative
            "12.5,34  a.ltx",  # taille non entière
        ],
    )
    def test_ce_qui_nest_pas_exactement_la_colonne_reste_le_chemin(self, remainder: str) -> None:
        """Au moindre doute le chemin est rendu entier : mieux vaut rehacher que se tromper."""
        parsed = baseline.parse_baseline(f"{_MD5_A}  {remainder}\n")

        assert parsed.digests == {remainder: _MD5_A}
        assert parsed.known == {}
        assert parsed.skipped == ()

    def test_colonne_absurdement_longue_ne_fait_pas_lever(self) -> None:
        """`int()` refuse au-delà de 4 300 chiffres : la promesse est de rapporter, pas de lever."""
        enorme = "9" * 5000
        parsed = baseline.parse_baseline(f"{_MD5_A}  {enorme},{enorme}  a.ltx\n")

        assert parsed.known == {}
        assert parsed.digests == {f"{enorme},{enorme}  a.ltx": _MD5_A}

    def test_mode_binaire_et_colonne_ensemble(self) -> None:
        parsed = baseline.parse_baseline(f"{_MD5_A}  12,34  *mod/file.ltx\n")

        assert parsed.digests == {"mod/file.ltx": _MD5_A}
        assert set(parsed.known) == {"mod/file.ltx"}

    def test_reference_vide_nest_pas_une_ancienne_reference(self) -> None:
        assert baseline.parse_baseline("").predates_stats is False


class TestFormatBaseline:
    def test_trie_par_chemin(self) -> None:
        text = baseline.format_baseline({"z.ltx": _MD5_A, "a.ltx": _MD5_B})

        assert text == f"{_MD5_B}  a.ltx\n{_MD5_A}  z.ltx\n"

    def test_aller_retour(self) -> None:
        digests = {"mod/a b.ltx": _MD5_A, "autre/c.dds": _MD5_B}

        assert baseline.parse_baseline(baseline.format_baseline(digests)).digests == digests

    def test_vide(self) -> None:
        assert baseline.format_baseline({}) == ""

    def test_ecrit_la_colonne_quand_le_stat_est_connu(self) -> None:
        text = baseline.format_baseline({"a.ltx": _MD5_A}, {"a.ltx": _STAT_A})

        assert text == f"{_MD5_A}  {_STAT_A.size},{_STAT_A.mtime_ns}  a.ltx\n"

    def test_un_chemin_sans_stat_retombe_sur_la_ligne_dorigine(self) -> None:
        """Écriture indépendante de la provenance : des hashs seuls restent écrivables."""
        text = baseline.format_baseline({"a.ltx": _MD5_A, "b.ltx": _MD5_B}, {"a.ltx": _STAT_A})

        assert text == f"{_MD5_A}  {_STAT_A.size},{_STAT_A.mtime_ns}  a.ltx\n{_MD5_B}  b.ltx\n"

    def test_aller_retour_avec_colonne_et_chemins_a_espaces(self) -> None:
        digests = {"312- Mod  Name/a b.ltx": _MD5_A, " espace-devant.dds": _MD5_B}
        stats = {"312- Mod  Name/a b.ltx": _STAT_A, " espace-devant.dds": _STAT_B}

        parsed = baseline.parse_baseline(baseline.format_baseline(digests, stats))

        assert parsed.digests == digests
        assert parsed.known == {
            relative: KnownFile(digest=digests[relative], stat=stat)
            for relative, stat in stats.items()
        }


class TestReadWriteBaseline:
    def test_absente_au_premier_passage(self, tmp_path: Path) -> None:
        assert baseline.read_baseline(tmp_path) is None

    def test_ecriture_puis_relecture(self, tmp_path: Path) -> None:
        written = baseline.write_baseline(tmp_path, {"a.ltx": _MD5_A})

        assert written == tmp_path / baseline.BASELINE_FILENAME
        parsed = baseline.read_baseline(tmp_path)
        assert parsed is not None
        assert parsed.digests == {"a.ltx": _MD5_A}

    def test_ecriture_puis_relecture_avec_les_stats(self, tmp_path: Path) -> None:
        baseline.write_baseline(tmp_path, {"a.ltx": _MD5_A}, {"a.ltx": _STAT_A})

        parsed = baseline.read_baseline(tmp_path)
        assert parsed is not None
        assert parsed.known == {"a.ltx": KnownFile(digest=_MD5_A, stat=_STAT_A)}

    def test_echec_decriture_avec_stats_laisse_la_reference_precedente(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L'atomicité ne dépend pas du format écrit : même garantie avec la colonne."""
        baseline.write_baseline(tmp_path, {"a.ltx": _MD5_A}, {"a.ltx": _STAT_A})

        def refuse(*_args: object, **_kwargs: object) -> None:
            raise OSError("No space left on device")

        monkeypatch.setattr(Path, "write_text", refuse)
        with pytest.raises(BaselineWriteError):
            baseline.write_baseline(tmp_path, {"b.ltx": _MD5_B}, {"b.ltx": _STAT_B})

        monkeypatch.undo()
        parsed = baseline.read_baseline(tmp_path)
        assert parsed is not None
        assert parsed.known == {"a.ltx": KnownFile(digest=_MD5_A, stat=_STAT_A)}
        assert [path.name for path in tmp_path.iterdir()] == [baseline.BASELINE_FILENAME]

    def test_pas_de_fichier_temporaire_laisse_derriere(self, tmp_path: Path) -> None:
        baseline.write_baseline(tmp_path, {"a.ltx": _MD5_A})

        assert [path.name for path in tmp_path.iterdir()] == [baseline.BASELINE_FILENAME]

    def test_echec_decriture_laisse_la_reference_precedente(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline.write_baseline(tmp_path, {"a.ltx": _MD5_A})

        def refuse(*_args: object, **_kwargs: object) -> None:
            raise OSError("No space left on device")

        monkeypatch.setattr(Path, "write_text", refuse)
        with pytest.raises(BaselineWriteError):
            baseline.write_baseline(tmp_path, {"b.ltx": _MD5_B})

        monkeypatch.undo()
        parsed = baseline.read_baseline(tmp_path)
        assert parsed is not None
        assert parsed.digests == {"a.ltx": _MD5_A}

    def test_reference_illisible_leve_une_erreur_typee(self, tmp_path: Path) -> None:
        # Un répertoire à la place du fichier : `read_text` lève une OSError.
        (tmp_path / baseline.BASELINE_FILENAME).mkdir()

        with pytest.raises(BaselineReadError):
            baseline.read_baseline(tmp_path)
