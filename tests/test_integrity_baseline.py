"""Format de l'empreinte de référence `gamma-md5.txt` (T12).

Le point sensible est le **parsing** : un découpage par offsets fixes
(`line[:32]`) marche sur nos propres fichiers et casse sur tout le reste. Les
cas ci-dessous couvrent donc les variantes de format qu'on peut réellement
croiser, plus la garantie d'atomicité de l'écriture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from stalker_gamma_linux.integrity import baseline
from stalker_gamma_linux.integrity.errors import BaselineReadError, BaselineWriteError

_MD5_A = "0123456789abcdef0123456789abcdef"
_MD5_B = "fedcba9876543210fedcba9876543210"


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


class TestFormatBaseline:
    def test_trie_par_chemin(self) -> None:
        text = baseline.format_baseline({"z.ltx": _MD5_A, "a.ltx": _MD5_B})

        assert text == f"{_MD5_B}  a.ltx\n{_MD5_A}  z.ltx\n"

    def test_aller_retour(self) -> None:
        digests = {"mod/a b.ltx": _MD5_A, "autre/c.dds": _MD5_B}

        assert baseline.parse_baseline(baseline.format_baseline(digests)).digests == digests

    def test_vide(self) -> None:
        assert baseline.format_baseline({}) == ""


class TestReadWriteBaseline:
    def test_absente_au_premier_passage(self, tmp_path: Path) -> None:
        assert baseline.read_baseline(tmp_path) is None

    def test_ecriture_puis_relecture(self, tmp_path: Path) -> None:
        written = baseline.write_baseline(tmp_path, {"a.ltx": _MD5_A})

        assert written == tmp_path / baseline.BASELINE_FILENAME
        parsed = baseline.read_baseline(tmp_path)
        assert parsed is not None
        assert parsed.digests == {"a.ltx": _MD5_A}

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
