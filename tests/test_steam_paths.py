"""Découverte des installations Steam et des comptes locaux."""

from __future__ import annotations

from pathlib import Path

from stalker_gamma_linux.steam import paths


def _account(home: Path, *root: str, account_id: str) -> Path:
    directory = home.joinpath(*root, "userdata", account_id, "config")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_steam_natif_et_flatpak_sont_trouves_tous_les_deux(tmp_path: Path) -> None:
    """Les deux coexistent couramment (Bazzite, Fedora) : aucune n'a la priorité."""
    _account(tmp_path, ".local", "share", "Steam", account_id="111")
    _account(
        tmp_path,
        ".var",
        "app",
        "com.valvesoftware.Steam",
        ".local",
        "share",
        "Steam",
        account_id="222",
    )

    accounts = paths.discover_accounts(tmp_path)

    assert {account.account_id for account in accounts} == {"111", "222"}
    assert {account.install.flatpak for account in accounts} == {False, True}


def test_les_racines_qui_pointent_au_meme_endroit_ne_comptent_quune_fois(
    tmp_path: Path,
) -> None:
    """`~/.steam/steam` est un lien vers `~/.local/share/Steam` : écrire deux fois
    dans le même fichier écraserait la sauvegarde qu'on vient de prendre."""
    real = tmp_path / ".local" / "share" / "Steam"
    _account(tmp_path, ".local", "share", "Steam", account_id="111")
    (tmp_path / ".steam").mkdir()
    (tmp_path / ".steam" / "steam").symlink_to(real)

    installs = paths.discover_installs(tmp_path)

    assert len(installs) == 1
    assert installs[0].root == real.resolve()


def test_une_racine_sans_userdata_est_ignoree(tmp_path: Path) -> None:
    (tmp_path / ".local" / "share" / "Steam").mkdir(parents=True)

    assert paths.discover_installs(tmp_path) == ()


def test_le_pseudo_compte_zero_et_les_residus_sont_ecartes(tmp_path: Path) -> None:
    _account(tmp_path, ".local", "share", "Steam", account_id="0")
    _account(tmp_path, ".local", "share", "Steam", account_id="111")
    # Dossier sans `config/` : un résidu, pas une session.
    (tmp_path / ".local" / "share" / "Steam" / "userdata" / "222").mkdir()
    # Dossier non numérique : jamais un identifiant de compte.
    (tmp_path / ".local" / "share" / "Steam" / "userdata" / "anonymous").mkdir()

    accounts = paths.discover_accounts(tmp_path)

    assert [account.account_id for account in accounts] == ["111"]


def test_les_chemins_dun_compte(tmp_path: Path) -> None:
    _account(tmp_path, ".local", "share", "Steam", account_id="111")

    (account,) = paths.discover_accounts(tmp_path)

    assert account.shortcuts_file.name == "shortcuts.vdf"
    assert account.grid_dir.name == "grid"
    assert account.grid_dir.parent == account.config_dir


def test_un_chemin_est_retraduit_pour_le_steam_flatpak(tmp_path: Path) -> None:
    """Dans le bac à sable, `~/.var/app/<id>/` EST `~/` : un chemin absolu écrit
    dans le VDF doit être donné dans la vue de Steam, pas dans la nôtre."""
    install = paths.SteamInstall(
        root=tmp_path / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
        flatpak=True,
    )
    host = install.root / "userdata" / "111" / "config" / "grid" / "42_icon.png"

    seen = install.as_steam_sees(host, home=tmp_path)

    assert seen == tmp_path / ".local/share/Steam/userdata/111/config/grid/42_icon.png"


def test_un_chemin_natif_nest_pas_retraduit(tmp_path: Path) -> None:
    install = paths.SteamInstall(root=tmp_path / ".local" / "share" / "Steam", flatpak=False)
    host = install.root / "userdata" / "111" / "config" / "grid" / "42_icon.png"

    assert install.as_steam_sees(host, home=tmp_path) == host
