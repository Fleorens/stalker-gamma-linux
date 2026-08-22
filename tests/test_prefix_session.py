"""Détection d'un préfixe occupé (`prefix.session`) : MO2, le jeu, wineserver."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from stalker_gamma_linux.environment import system
from stalker_gamma_linux.prefix import session
from stalker_gamma_linux.prefix.errors import PrefixBusyError
from stalker_gamma_linux.prefix.paths import PrefixPaths


def _no_proc(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Aucun `/proc` accessible (répertoire absent) : le signal wineserver se dégrade."""
    monkeypatch.setattr(session, "_PROC", tmp_path / "no-such-proc")


def _no_pgrep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: None)


def _fake_proc_dir(tmp_path: Path) -> Path:
    proc = tmp_path / "proc"
    proc.mkdir()
    return proc


def _make_wineserver(proc: Path, pid: int, environ: bytes) -> None:
    pid_dir = proc / str(pid)
    pid_dir.mkdir()
    (pid_dir / "comm").write_text("wineserver\n")
    (pid_dir / "environ").write_bytes(environ)


class TestWineserverSignal:
    """Le plus fiable : couvre « MO2 fermé mais le jeu tourne encore »."""

    def test_detects_wineserver_pointing_at_our_prefix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        proc = _fake_proc_dir(tmp_path)
        environ = b"HOME=/home/x\0WINEPREFIX=" + str(paths.prefix).encode() + b"\0LANG=C\0"
        _make_wineserver(proc, 4242, environ)
        monkeypatch.setattr(session, "_PROC", proc)
        _no_pgrep(monkeypatch)  # les autres signaux ne doivent pas être nécessaires

        hold = session.prefix_in_use(paths)

        assert hold is not None
        assert hold.pid == 4242

    def test_ignores_wineserver_pointing_at_a_different_prefix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        proc = _fake_proc_dir(tmp_path)
        _make_wineserver(proc, 1, b"WINEPREFIX=/somewhere/else\0")
        monkeypatch.setattr(session, "_PROC", proc)
        _no_pgrep(monkeypatch)

        assert session.prefix_in_use(paths) is None

    def test_ignores_non_wineserver_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        proc = _fake_proc_dir(tmp_path)
        pid_dir = proc / "7"
        pid_dir.mkdir()
        (pid_dir / "comm").write_text("bash\n")
        (pid_dir / "environ").write_bytes(b"WINEPREFIX=" + str(paths.prefix).encode() + b"\0")
        monkeypatch.setattr(session, "_PROC", proc)
        _no_pgrep(monkeypatch)

        assert session.prefix_in_use(paths) is None

    def test_ignores_non_numeric_proc_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        proc = _fake_proc_dir(tmp_path)
        (proc / "self").mkdir()
        (proc / "cpuinfo").write_text("")
        monkeypatch.setattr(session, "_PROC", proc)
        _no_pgrep(monkeypatch)

        assert session.prefix_in_use(paths) is None

    def test_tolerates_a_process_disappearing_mid_scan(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`comm`/`environ` peuvent disparaître entre le listing et la lecture."""
        paths = PrefixPaths.under(tmp_path / "install")
        proc = _fake_proc_dir(tmp_path)
        (proc / "999").mkdir()  # ni comm ni environ : process déjà mort
        monkeypatch.setattr(session, "_PROC", proc)
        _no_pgrep(monkeypatch)

        assert session.prefix_in_use(paths) is None

    def test_missing_proc_degrades_to_not_in_use(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        _no_proc(monkeypatch, tmp_path)
        _no_pgrep(monkeypatch)

        assert session.prefix_in_use(paths) is None


def _fake_run(matching_pattern: str, pid: int) -> object:
    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        pattern = command[-1]
        if pattern == matching_pattern:
            return subprocess.CompletedProcess(command, returncode=0, stdout=f"{pid}\n", stderr="")
        return subprocess.CompletedProcess(command, returncode=1, stdout="", stderr="")

    return run


class TestPgrepSignals:
    def test_detects_mod_organizer(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        _no_proc(monkeypatch, tmp_path)
        monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/pgrep")
        monkeypatch.setattr(system, "run", _fake_run(session._MO2_PATTERN, 555))

        hold = session.prefix_in_use(paths)

        assert hold is not None
        assert hold.pid == 555
        assert "Mod Organizer 2" in hold.name

    def test_detects_game_executable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        _no_proc(monkeypatch, tmp_path)
        monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/pgrep")
        monkeypatch.setattr(system, "run", _fake_run(session._GAME_PATTERNS[0], 777))

        hold = session.prefix_in_use(paths)

        assert hold is not None
        assert hold.pid == 777

    def test_pgrep_absent_never_blocks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        _no_proc(monkeypatch, tmp_path)
        _no_pgrep(monkeypatch)

        assert session.prefix_in_use(paths) is None

    def test_nothing_running_is_not_in_use(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        _no_proc(monkeypatch, tmp_path)
        monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/pgrep")
        monkeypatch.setattr(
            system,
            "run",
            lambda command: subprocess.CompletedProcess(
                command, returncode=1, stdout="", stderr=""
            ),
        )

        assert session.prefix_in_use(paths) is None

    def test_pattern_dot_is_escaped(self) -> None:
        """Sans l'échappement, `-f ModOrganizer` matcherait un chemin d'install
        contenant simplement le mot « ModOrganizer » (ex. `--target`)."""
        assert session._MO2_PATTERN == r"ModOrganizer\.exe"

    def test_install_path_containing_mod_organizer_is_not_self_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un process dont la ligne de commande contient « ModOrganizer » (mais pas
        « ModOrganizer.exe ») ne doit pas matcher — ex. notre propre process CLI
        appelé avec `--target /home/user/ModOrganizerBackup`."""
        paths = PrefixPaths.under(tmp_path / "install")
        _no_proc(monkeypatch, tmp_path)
        monkeypatch.setattr(system, "which", lambda cmd: "/usr/bin/pgrep")

        def run(command: list[str]) -> subprocess.CompletedProcess[str]:
            # pgrep -f 'ModOrganizer\.exe' ne matche rien : seul un chemin comme
            # ".../ModOrganizerBackup" est présent sur la machine, jamais suivi
            # de ".exe".
            return subprocess.CompletedProcess(command, returncode=1, stdout="", stderr="")

        monkeypatch.setattr(system, "run", run)

        assert session.prefix_in_use(paths) is None


class TestRequireFree:
    def test_raises_with_pid_and_name_when_busy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        monkeypatch.setattr(
            session,
            "prefix_in_use",
            lambda p: session.ProcessHold(pid=12345, name="Mod Organizer 2", what_to_close="it"),
        )

        with pytest.raises(PrefixBusyError) as excinfo:
            session.require_free(paths, action="repairing the prefix")

        message = str(excinfo.value)
        assert "12345" in message
        assert "Mod Organizer 2" in message
        assert "repairing the prefix" in message
        assert "--force" in message

    def test_force_bypasses_the_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        monkeypatch.setattr(
            session,
            "prefix_in_use",
            lambda p: session.ProcessHold(pid=1, name="Mod Organizer 2", what_to_close="it"),
        )

        session.require_free(paths, action="repairing the prefix", force=True)

    def test_free_prefix_does_not_raise(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = PrefixPaths.under(tmp_path / "install")
        monkeypatch.setattr(session, "prefix_in_use", lambda p: None)

        session.require_free(paths, action="repairing the prefix")
