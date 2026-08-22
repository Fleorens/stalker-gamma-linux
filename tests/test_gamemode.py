"""GameMode : détection, enveloppe de commande, et câblage jusqu'au lancement."""

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from stalker_gamma_linux.environment import checks, gamemode, system
from stalker_gamma_linux.environment.distro import Distro, DistroFamily
from stalker_gamma_linux.environment.models import Status
from stalker_gamma_linux.mo2 import flat, launch, session
from stalker_gamma_linux.mo2.paths import Mo2Paths
from stalker_gamma_linux.prefix import process
from stalker_gamma_linux.prefix.paths import PrefixPaths

FAMILY = DistroFamily.FEDORA

_BINARIES = {"gamemoderun": "/usr/bin/gamemoderun", "umu-run": "/usr/bin/umu-run"}


def _with_gamemode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "which", lambda cmd: _BINARIES.get(cmd))


def _without_gamemode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        system, "which", lambda cmd: None if cmd == "gamemoderun" else _BINARIES.get(cmd)
    )


def test_wrap_prefixes_command_when_gamemode_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_gamemode(monkeypatch)

    assert gamemode.wrap(["/usr/bin/umu-run", "MO2.exe"]) == [
        "/usr/bin/gamemoderun",
        "/usr/bin/umu-run",
        "MO2.exe",
    ]


def test_wrap_returns_command_untouched_when_gamemode_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without_gamemode(monkeypatch)
    original = ["/usr/bin/umu-run", "MO2.exe"]

    wrapped = gamemode.wrap(original)

    assert wrapped == original
    # Nouvelle liste : l'appelant garde la sienne intacte (jamais de mutation).
    assert wrapped is not original


# --- Lancement -------------------------------------------------------------


def _patch_popen(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _FakeProcess:
        def __init__(self) -> None:
            self.stdout: Iterator[str] = iter(())

        def poll(self) -> int | None:
            return 0

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def factory(command: list[str], **kwargs: Any) -> _FakeProcess:
        captured["command"] = command
        return _FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", factory)
    return captured


def test_run_in_prefix_wraps_the_command_when_gamemode_is_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_gamemode(monkeypatch)
    captured = _patch_popen(monkeypatch)

    process.run_in_prefix(
        "Anomaly.exe",
        paths=PrefixPaths.under(tmp_path),
        proton_path=tmp_path / "GE",
        gamemode=True,
    )

    assert captured["command"][:2] == ["/usr/bin/gamemoderun", "/usr/bin/umu-run"]


def test_run_in_prefix_ignores_gamemode_when_it_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _without_gamemode(monkeypatch)
    captured = _patch_popen(monkeypatch)

    process.run_in_prefix(
        "Anomaly.exe",
        paths=PrefixPaths.under(tmp_path),
        proton_path=tmp_path / "GE",
        gamemode=True,
    )

    assert captured["command"][0] == "/usr/bin/umu-run"


def test_install_steps_never_get_gamemode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Les verbs du préfixe et la création de prefix ne sont pas du jeu : rien à
    # optimiser, et surtout pas de gouverneur CPU épinglé pendant un téléchargement.
    _with_gamemode(monkeypatch)
    captured = _patch_popen(monkeypatch)

    process.run_in_prefix(
        "createprefix", paths=PrefixPaths.under(tmp_path), proton_path=tmp_path / "GE"
    )

    assert captured["command"][0] == "/usr/bin/umu-run"


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, exe: Path | str, args: Any = (), **kw: Any) -> Path:
        self.calls.append(kw)
        return Path("/logs/fake.log")


def _installed_instance(tmp_path: Path) -> tuple[Mo2Paths, PrefixPaths]:
    mo2 = Mo2Paths.under(tmp_path)
    mo2.instance.mkdir(parents=True)
    mo2.executable.write_text("", encoding="utf-8")
    return mo2, PrefixPaths.under(tmp_path)


def test_launch_game_asks_for_gamemode_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mo2, prefix = _installed_instance(tmp_path)
    recorder = _Recorder()
    monkeypatch.setattr(process, "run_detached", recorder)

    launch.launch_game(mo2, prefix, tmp_path / "GE")

    assert recorder.calls[0]["gamemode"] is True


def test_launch_game_honours_opt_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mo2, prefix = _installed_instance(tmp_path)
    recorder = _Recorder()
    monkeypatch.setattr(process, "run_detached", recorder)

    launch.launch_game(mo2, prefix, tmp_path / "GE", gamemode=False)

    assert recorder.calls[0]["gamemode"] is False


def test_launch_mo2_alone_does_not_ask_for_gamemode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Ouvrir l'interface MO2 n'est pas jouer : `run_in_prefix` reste sur son défaut.
    mo2, prefix = _installed_instance(tmp_path)
    recorder = _Recorder()
    monkeypatch.setattr(process, "run_in_prefix", recorder)

    launch.launch_mo2(mo2, prefix, tmp_path / "GE")

    assert "gamemode" not in recorder.calls[0]


def test_flat_launch_asks_for_gamemode_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    final = tmp_path / "flat"
    final.mkdir()
    (final / flat.FLAT_LAUNCHER).write_text("", encoding="utf-8")
    recorder = _Recorder()
    monkeypatch.setattr(process, "run_detached", recorder)

    flat.launch_flat(final, PrefixPaths.under(tmp_path), tmp_path / "GE")

    assert recorder.calls[0]["gamemode"] is True


# --- Messages et diagnostic ------------------------------------------------


def _group(monkeypatch: pytest.MonkeyPatch, status: gamemode.GroupStatus) -> None:
    monkeypatch.setattr(gamemode, "group_status", lambda: status)


def test_notice_announces_gamemode_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_gamemode(monkeypatch)
    _group(monkeypatch, gamemode.GroupStatus.MEMBER)

    assert "GameMode enabled" in session.gamemode_notice(True)


def test_notice_warns_when_the_cpu_governor_stays_locked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Sans le groupe `gamemode`, le mode s'active mais le gouverneur ne bouge
    # jamais : le silence sur ce point est exactement ce qui fait chercher des
    # heures pourquoi « GameMode est actif » et les FPS identiques.
    _with_gamemode(monkeypatch)
    _group(monkeypatch, gamemode.GroupStatus.MISSING)

    notice = session.gamemode_notice(True)

    assert "governor stays locked" in notice
    assert "doctor" in notice


def test_notice_gives_the_install_command_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    _without_gamemode(monkeypatch)
    monkeypatch.setattr(
        session, "detect_distro", lambda: Distro(family=FAMILY, pretty_name="Fedora Linux 44")
    )

    notice = session.gamemode_notice(True)

    assert "not installed" in notice
    assert "sudo dnf install gamemode" in notice


def test_notice_states_the_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_gamemode(monkeypatch)

    assert "disabled" in session.gamemode_notice(False)


# --- Groupe `gamemode` (règle polkit du gouverneur CPU) ---------------------


class _FakeGroup:
    def __init__(self, gid: int, members: list[str]) -> None:
        self.gr_gid = gid
        self.gr_mem = members


class _FakeUser:
    def __init__(self, name: str, gid: int) -> None:
        self.pw_name = name
        self.pw_gid = gid


def _fake_db(
    monkeypatch: pytest.MonkeyPatch,
    group: _FakeGroup | None,
    user: _FakeUser | None = None,
) -> None:
    user = user if user is not None else _FakeUser("florian", 1000)

    def getgrnam(name: str) -> _FakeGroup:
        if group is None or name != gamemode.GAMEMODE_GROUP:
            raise KeyError(name)
        return group

    monkeypatch.setattr(gamemode.grp, "getgrnam", getgrnam)
    monkeypatch.setattr(gamemode, "_passwd_entry", lambda: user)


def test_group_status_not_applicable_without_a_gamemode_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Distribution dont la politique polkit n'utilise pas ce groupe : rien à corriger.
    _fake_db(monkeypatch, None)

    assert gamemode.group_status() is gamemode.GroupStatus.NOT_APPLICABLE


def test_group_status_member_reads_the_system_database(monkeypatch: pytest.MonkeyPatch) -> None:
    # Constaté en réel : polkit résout l'appartenance depuis la base, pas depuis
    # les gids du processus — un `usermod -aG` prend effet sans reconnexion, y
    # compris pour un daemon démarré avant. Se fier à `os.getgroups()` ferait
    # crier au loup sur une machine où le gouverneur bascule déjà.
    _fake_db(monkeypatch, _FakeGroup(972, ["florian"]))

    assert gamemode.group_status() is gamemode.GroupStatus.MEMBER


def test_group_status_member_when_gamemode_is_the_primary_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_db(monkeypatch, _FakeGroup(972, []), _FakeUser("florian", 972))

    assert gamemode.group_status() is gamemode.GroupStatus.MEMBER


def test_group_status_missing_when_the_user_never_joined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_db(monkeypatch, _FakeGroup(972, ["someone-else"]))

    assert gamemode.group_status() is gamemode.GroupStatus.MISSING


def test_doctor_detail_carries_the_usermod_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    _group(monkeypatch, gamemode.GroupStatus.MISSING)

    detail = checks.gamemode_detail()

    assert "sudo usermod -aG gamemode $USER" in detail
    assert "next launch" in detail


def test_check_gamemode_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_gamemode(monkeypatch)
    _group(monkeypatch, gamemode.GroupStatus.MEMBER)

    requirement = checks.check_gamemode(FAMILY)

    assert requirement.status is Status.OK
    # Le daemon est activé à la demande : « inactive » entre deux parties est
    # normal, et le diagnostic doit le dire plutôt que d'envoyer l'utilisateur
    # sur un `systemctl --user enable` inutile.
    assert "on demand" in requirement.detail


def test_check_gamemode_absent_is_optional_and_never_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without_gamemode(monkeypatch)

    requirement = checks.check_gamemode(FAMILY)

    assert requirement.status is Status.OPTIONAL
    assert not requirement.blocks_install
    assert requirement.install_hint == "sudo dnf install gamemode"
