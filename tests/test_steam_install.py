"""Écriture réelle : sauvegarde, atomicité, artwork, `--dry-run`, réversibilité."""

from __future__ import annotations

from pathlib import Path

import pytest

from stalker_gamma_linux.steam import artwork, entry, install, paths, running, vdf
from stalker_gamma_linux.steam.errors import SteamRunningError, VdfFormatError
from stalker_gamma_linux.steam.install import Action

REAL_FILE = Path(__file__).parent / "data" / "shortcuts-real.vdf"
TARGET = Path("/games/gamma")


@pytest.fixture
def account(tmp_path: Path) -> paths.SteamAccount:
    root = tmp_path / ".local" / "share" / "Steam"
    (root / "userdata" / "111" / "config").mkdir(parents=True)
    return paths.SteamAccount(
        install=paths.SteamInstall(root=root, flatpak=False), account_id="111"
    )


@pytest.fixture(autouse=True)
def _steam_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(running, "steam_process", lambda: None)


def _seed_real_file(account: paths.SteamAccount) -> bytes:
    data = REAL_FILE.read_bytes()
    account.shortcuts_file.write_bytes(data)
    return data


def test_ajout_sur_un_compte_neuf_ecrit_entree_et_artwork(account: paths.SteamAccount) -> None:
    result = install.add_to_account(account, TARGET)

    assert result.action is Action.CREATED
    assert account.shortcuts_file.is_file()
    assert len(result.artwork_written) == 5
    assert all(path.is_file() for path in result.artwork_written)
    # Pas de sauvegarde : il n'y avait aucun fichier à sauver.
    assert result.backup is None


def test_licone_de_lentree_pointe_sur_lartwork_pose(account: paths.SteamAccount) -> None:
    result = install.add_to_account(account, TARGET)

    document = vdf.parse(account.shortcuts_file.read_bytes())
    ours = entry.find_ours(document)
    assert ours is not None
    assert result.appid is not None
    expected = artwork.icon_file(account.grid_dir, result.appid)
    assert entry.string_field(ours, "icon") == str(expected)
    assert expected.is_file()


def test_une_sauvegarde_horodatee_precede_toute_ecriture(account: paths.SteamAccount) -> None:
    """`shortcuts.vdf` contient les AUTRES raccourcis : rien de destructeur sans filet."""
    original = _seed_real_file(account)

    result = install.add_to_account(account, TARGET)

    assert result.backup is not None
    assert result.backup.read_bytes() == original
    assert result.backup.name.startswith("shortcuts.vdf.")
    assert result.backup.name.endswith(".bak")


def test_relancer_ne_cree_pas_de_doublon(account: paths.SteamAccount) -> None:
    _seed_real_file(account)

    first = install.add_to_account(account, TARGET)
    second = install.add_to_account(account, TARGET)

    assert first.action is Action.CREATED
    assert second.action is Action.UPDATED
    assert first.appid == second.appid
    document = vdf.parse(account.shortcuts_file.read_bytes())
    assert len(entry.entries(document)) == 2


def test_le_retrait_rend_le_fichier_tel_quavant(account: paths.SteamAccount) -> None:
    original = _seed_real_file(account)
    install.add_to_account(account, TARGET)

    result = install.remove_from_account(account)

    assert result.action is Action.REMOVED
    assert account.shortcuts_file.read_bytes() == original
    assert len(result.artwork_removed) == 5
    assert not any(path.exists() for path in result.artwork_removed)


def test_le_retrait_epargne_un_artwork_remplace_par_lutilisateur(
    account: paths.SteamAccount,
) -> None:
    result = install.add_to_account(account, TARGET)
    assert result.appid is not None
    custom = account.grid_dir / f"{result.appid}p.png"
    custom.write_bytes(b"ma propre capsule")

    removed = install.remove_from_account(account)

    assert custom.read_bytes() == b"ma propre capsule"
    assert custom in removed.artwork_kept


def test_le_retrait_sur_un_compte_sans_notre_entree_ne_touche_a_rien(
    account: paths.SteamAccount,
) -> None:
    original = _seed_real_file(account)

    result = install.remove_from_account(account)

    assert result.action is Action.ABSENT
    assert account.shortcuts_file.read_bytes() == original
    assert not list(account.config_dir.glob("*.bak"))


def test_dry_run_necrit_rien(account: paths.SteamAccount) -> None:
    _seed_real_file(account)
    before = account.shortcuts_file.read_bytes()

    result = install.add_to_account(account, TARGET, dry_run=True)

    assert result.action is Action.CREATED
    assert account.shortcuts_file.read_bytes() == before
    assert not account.grid_dir.exists()
    # Les chemins annoncés sont ceux qui SERAIENT écrits.
    assert len(result.artwork_written) == 5


def test_dry_run_du_retrait_necrit_rien(account: paths.SteamAccount) -> None:
    install.add_to_account(account, TARGET)
    before = account.shortcuts_file.read_bytes()

    result = install.remove_from_account(account, dry_run=True)

    assert result.action is Action.REMOVED
    assert account.shortcuts_file.read_bytes() == before
    assert all(path.is_file() for path in result.artwork_removed)


def test_steam_ouvert_bloque_lecriture(
    account: paths.SteamAccount, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        running, "steam_process", lambda: running.SteamProcess(pid=42, name="steam")
    )

    with pytest.raises(SteamRunningError):
        install.add_shortcut(TARGET, accounts=(account,))

    assert not account.shortcuts_file.exists()


def test_force_ecrit_malgre_steam_ouvert(
    account: paths.SteamAccount, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        running, "steam_process", lambda: running.SteamProcess(pid=42, name="steam")
    )

    results = install.add_shortcut(TARGET, accounts=(account,), force=True)

    assert results[0].action is Action.CREATED
    assert account.shortcuts_file.is_file()


def test_dry_run_ne_demande_pas_que_steam_soit_ferme(
    account: paths.SteamAccount, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lecture seule : refuser un `--dry-run` parce que Steam tourne n'apporte rien."""
    monkeypatch.setattr(
        running, "steam_process", lambda: running.SteamProcess(pid=42, name="steam")
    )

    results = install.add_shortcut(TARGET, accounts=(account,), dry_run=True)

    assert results[0].action is Action.CREATED


def test_tous_les_comptes_sont_servis(tmp_path: Path) -> None:
    """On n'essaie pas de deviner « le bon » compte : en mode Gaming, on ne peut
    pas demander (cf. steam/install.py)."""
    root = tmp_path / ".local" / "share" / "Steam"
    for account_id in ("111", "222"):
        (root / "userdata" / account_id / "config").mkdir(parents=True)
    accounts = paths.discover_accounts(tmp_path)

    results = install.add_shortcut(TARGET, accounts=accounts)

    assert len(results) == 2
    assert all(result.account.shortcuts_file.is_file() for result in results)


def test_un_fichier_trop_gros_est_refuse_avant_lecture(account: paths.SteamAccount) -> None:
    account.shortcuts_file.write_bytes(b"\0" * (paths.MAX_SHORTCUTS_BYTES + 1))

    with pytest.raises(VdfFormatError):
        install.read_document(account.shortcuts_file)


def test_un_fichier_absent_donne_un_document_vide(account: paths.SteamAccount) -> None:
    document = install.read_document(account.shortcuts_file)

    assert document.nodes == ()
    # Terminateur de document : un fichier qu'on crée doit se terminer comme
    # ceux que Steam écrit (le fichier réel porte ce `0x08` final).
    assert document.trailer == bytes([vdf.TYPE_END])


def test_un_fichier_neuf_se_termine_comme_ceux_de_steam(account: paths.SteamAccount) -> None:
    install.add_to_account(account, TARGET)

    written = account.shortcuts_file.read_bytes()

    assert written.endswith(bytes([vdf.TYPE_END, vdf.TYPE_END, vdf.TYPE_END]))


def test_lecriture_ne_laisse_pas_de_fichier_temporaire(account: paths.SteamAccount) -> None:
    install.add_to_account(account, TARGET)

    assert [path.name for path in account.config_dir.glob("*.tmp")] == []


def test_le_retrait_nexige_pas_la_fermeture_de_steam_sil_ny_a_rien_a_retirer(
    account: paths.SteamAccount, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`uninstall` passe ici à chaque fois : un refus gratuit serait un faux problème."""
    _seed_real_file(account)
    monkeypatch.setattr(
        running, "steam_process", lambda: running.SteamProcess(pid=42, name="steam")
    )

    results = install.remove_shortcut(accounts=(account,))

    assert results[0].action is Action.ABSENT


def test_le_retrait_exige_la_fermeture_de_steam_sil_y_a_quelque_chose_a_retirer(
    account: paths.SteamAccount, monkeypatch: pytest.MonkeyPatch
) -> None:
    install.add_to_account(account, TARGET)
    monkeypatch.setattr(
        running, "steam_process", lambda: running.SteamProcess(pid=42, name="steam")
    )

    with pytest.raises(SteamRunningError):
        install.remove_shortcut(accounts=(account,))
