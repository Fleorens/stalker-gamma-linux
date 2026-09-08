"""Refus d'écrire pendant que Steam tourne — le seul échec qui ne se voit pas."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.steam import running
from stalker_gamma_linux.steam.errors import SteamRunningError


def _fake_proc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, comms: dict[str, str]) -> None:
    for pid, comm in comms.items():
        directory = tmp_path / pid
        directory.mkdir()
        (directory / "comm").write_text(f"{comm}\n", encoding="utf-8")
    monkeypatch.setattr(running, "_PROC", tmp_path)


def _no_pgrep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda command: None)


def test_steam_detecte_par_proc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_proc(tmp_path, monkeypatch, {"10": "bash", "42": "steam"})
    _no_pgrep(monkeypatch)

    process = running.steam_process()

    assert process is not None
    assert process.pid == 42


def test_steamwebhelper_compte_aussi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Il survit parfois à la fenêtre : la session Steam n'est pas terminée pour autant."""
    _fake_proc(tmp_path, monkeypatch, {"7": "steamwebhelper"})
    _no_pgrep(monkeypatch)

    assert running.steam_process() is not None


def test_notre_propre_ligne_de_commande_ne_declenche_rien(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`comm` et non la ligne de commande : sinon `steam-shortcut` se bloque lui-même."""
    _fake_proc(tmp_path, monkeypatch, {"99": "stalker-gamma-l"})
    _no_pgrep(monkeypatch)

    assert running.steam_process() is None


def test_repli_sur_pgrep_quand_proc_est_illisible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(running, "_PROC", tmp_path / "absent")
    monkeypatch.setattr(system, "which", lambda command: f"/usr/bin/{command}")
    calls: list[list[str]] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        stdout = "1234\n" if command[-1] == "steam" else ""
        return subprocess.CompletedProcess(command, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(system, "run", fake_run)

    process = running.steam_process()

    assert process is not None
    assert process.pid == 1234
    # `-x` : correspondance sur le nom du processus, jamais sur la ligne de commande.
    assert all("-x" in command for command in calls)


def test_require_closed_leve_avec_un_message_actionnable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_proc(tmp_path, monkeypatch, {"42": "steam"})
    _no_pgrep(monkeypatch)

    with pytest.raises(SteamRunningError) as raised:
        running.require_closed()

    message = str(raised.value)
    assert "42" in message
    assert "--force" in message


def test_force_passe_outre(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_proc(tmp_path, monkeypatch, {"42": "steam"})
    _no_pgrep(monkeypatch)

    running.require_closed(force=True)


def test_pas_de_steam_pas_de_refus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_proc(tmp_path, monkeypatch, {"10": "bash"})
    _no_pgrep(monkeypatch)

    running.require_closed()
