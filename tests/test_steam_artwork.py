"""Artwork : uniquement des assets du paquet, et un retrait qui n'écrase rien."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.steam import artwork

APPID = 3379557880


def test_les_cinq_noms_attendus_par_steam() -> None:
    names = artwork.filenames(APPID)

    assert names == (
        f"{APPID}p.png",
        f"{APPID}.png",
        f"{APPID}_hero.png",
        f"{APPID}_logo.png",
        f"{APPID}_icon.png",
    )


def test_les_fichiers_viennent_du_paquet(tmp_path: Path) -> None:
    """Aucun téléchargement : les capsules sont livrées avec le paquet."""
    written = artwork.write(tmp_path / "grid", APPID)

    assert len(written) == 5
    for path in written:
        assert path.is_file()
        assert path.stat().st_size > 0
    # PNG : les huit octets de signature.
    assert written[0].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_reecrire_est_idempotent(tmp_path: Path) -> None:
    grid = tmp_path / "grid"

    first = artwork.write(grid, APPID)
    second = artwork.write(grid, APPID)

    assert first == second
    assert sorted(path.name for path in grid.iterdir()) == sorted(artwork.filenames(APPID))


def test_le_retrait_supprime_ce_quon_a_ecrit(tmp_path: Path) -> None:
    grid = tmp_path / "grid"
    artwork.write(grid, APPID)

    removed, kept = artwork.remove(grid, APPID)

    assert len(removed) == 5
    assert kept == ()
    assert list(grid.iterdir()) == []


def test_le_retrait_epargne_ce_qui_nest_plus_le_notre(tmp_path: Path) -> None:
    grid = tmp_path / "grid"
    artwork.write(grid, APPID)
    (grid / f"{APPID}_hero.png").write_bytes(b"ma banniere")

    removed, kept = artwork.remove(grid, APPID)

    assert len(removed) == 4
    assert [path.name for path in kept] == [f"{APPID}_hero.png"]


def test_le_retrait_dun_dossier_vide_ne_leve_pas(tmp_path: Path) -> None:
    removed, kept = artwork.remove(tmp_path / "grid", APPID)

    assert removed == () and kept == ()


def test_un_lien_symbolique_en_travers_est_laisse_en_place(tmp_path: Path) -> None:
    """`paths_safety` : supprimer à travers emporterait une cible sans rapport."""
    grid = tmp_path / "grid"
    grid.mkdir()
    victim = tmp_path / "ailleurs.png"
    victim.write_bytes(b"innocent")
    (grid / f"{APPID}p.png").symlink_to(victim)

    _removed, kept = artwork.remove(grid, APPID)

    assert victim.read_bytes() == b"innocent"
    assert [path.name for path in kept] == [f"{APPID}p.png"]
