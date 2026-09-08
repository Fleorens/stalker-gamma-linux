"""La commande `steam-shortcut` : codes de sortie et messages actionnables."""

from __future__ import annotations

from pathlib import Path

import pytest

from stalker_gamma_linux import output
from stalker_gamma_linux.steam import paths, running, session

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


def _with_accounts(
    monkeypatch: pytest.MonkeyPatch, accounts: tuple[paths.SteamAccount, ...]
) -> None:
    monkeypatch.setattr(session, "discover_accounts", lambda: accounts)


def test_aucun_compte_donne_un_message_actionnable_pas_une_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_accounts(monkeypatch, ())

    code = session.run_steam_shortcut(TARGET)

    assert code == 1
    printed = capsys.readouterr().out
    assert "No Steam account" in printed
    assert "userdata" in printed


def test_ajout_reussi(
    account: paths.SteamAccount, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_accounts(monkeypatch, (account,))

    code = session.run_steam_shortcut(TARGET)

    assert code == 0
    assert account.shortcuts_file.is_file()
    printed = capsys.readouterr().out
    assert "111" in printed
    assert "restart" in printed.lower()


def test_steam_ouvert_refuse_et_dit_quoi_fermer(
    account: paths.SteamAccount, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_accounts(monkeypatch, (account,))
    monkeypatch.setattr(
        running, "steam_process", lambda: running.SteamProcess(pid=42, name="steam")
    )

    code = session.run_steam_shortcut(TARGET)

    assert code == 1
    printed = capsys.readouterr().out
    assert "Quit Steam" in printed
    assert not account.shortcuts_file.exists()


def test_force_passe_outre(account: paths.SteamAccount, monkeypatch: pytest.MonkeyPatch) -> None:
    _with_accounts(monkeypatch, (account,))
    monkeypatch.setattr(
        running, "steam_process", lambda: running.SteamProcess(pid=42, name="steam")
    )

    assert session.run_steam_shortcut(TARGET, force=True) == 0
    assert account.shortcuts_file.is_file()


def test_dry_run_annonce_sans_ecrire(
    account: paths.SteamAccount, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_accounts(monkeypatch, (account,))

    code = session.run_steam_shortcut(TARGET, dry_run=True)

    assert code == 0
    assert not account.shortcuts_file.exists()
    assert "Dry run" in capsys.readouterr().out


def test_retrait(
    account: paths.SteamAccount, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_accounts(monkeypatch, (account,))
    session.run_steam_shortcut(TARGET)
    capsys.readouterr()

    code = session.run_steam_shortcut(remove=True)

    assert code == 0
    assert "removed" in capsys.readouterr().out.lower()


def test_le_flatpak_est_servi_mais_annonce_sa_limite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """L'entrée et l'artwork sont écrits ; le lancement, lui, peut échouer dans le
    bac à sable — l'utilisateur doit savoir d'où viendrait l'échec."""
    root = tmp_path / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam"
    (root / "userdata" / "111" / "config").mkdir(parents=True)
    account = paths.SteamAccount(
        install=paths.SteamInstall(root=root, flatpak=True), account_id="111"
    )
    _with_accounts(monkeypatch, (account,))

    code = session.run_steam_shortcut(TARGET)

    assert code == 0
    assert "sandbox" in capsys.readouterr().out
    assert account.shortcuts_file.is_file()


def test_output_est_bien_le_puits_utilise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garde-fou : les messages passent par `output`, jamais par un `print` nu."""
    _with_accounts(monkeypatch, ())
    seen: list[str] = []
    monkeypatch.setattr(output, "error", lambda message, **_kwargs: seen.append(message))

    session.run_steam_shortcut(TARGET)

    assert seen and "No Steam account" in seen[0]
