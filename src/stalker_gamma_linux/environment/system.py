"""Accès système bruts (PATH, sous-processus, disque, fichiers).

Isolé dans ce module pour que les tests puissent monkeypatcher chaque
fonction individuellement, sans jamais toucher la vraie machine.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple


class DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


def which(command: str) -> str | None:
    return shutil.which(command)


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(command, returncode=1, stdout="", stderr=str(error))


def _in_flatpak() -> bool:
    """Vrai si le process tourne dans un bac à sable Flatpak (marqueur standard)."""
    return Path("/.flatpak-info").exists()


def host_which(command: str) -> str | None:
    """`which`, mais résolu sur l'HÔTE quand on tourne dans un Flatpak.

    Le PATH du bac à sable ne voit pas les binaires système de l'hôte (steam,
    vulkaninfo, protontricks…) : sans ça le diagnostic les déclare « manquants »
    alors qu'ils sont bien installés. `flatpak-spawn --host` interroge le vrai
    système. Hors Flatpak, comportement identique à `which`. Nécessite la
    permission `--talk-name=org.freedesktop.Flatpak` (voir le manifeste).
    """
    if not _in_flatpak():
        return which(command)
    result = run(["flatpak-spawn", "--host", "sh", "-c", f"command -v {command}"])
    path = result.stdout.strip()
    return path if result.returncode == 0 and path else None


def host_run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """`run`, mais exécuté sur l'HÔTE quand on tourne dans un Flatpak (cf. host_which)."""
    if not _in_flatpak():
        return run(command)
    return run(["flatpak-spawn", "--host", *command])


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def path_exists(path: Path) -> bool:
    return path.exists()


def disk_usage(path: Path) -> DiskUsage:
    usage = shutil.disk_usage(path)
    return DiskUsage(total=usage.total, used=usage.used, free=usage.free)


def detect_virtualization() -> str | None:
    """Type de virtualisation détecté (ex. "kvm", "oracle", "vmware"), ou None sur bare-metal.

    S'appuie sur `systemd-detect-virt` (exit 0 + un type non "none" = virtualisé).
    Renvoie aussi None si l'outil est absent : on ne peut alors pas conclure, donc
    on reste sur le comportement « machine réelle » (prudent : mieux vaut proposer
    un correctif inutile que masquer un vrai manque de pilote).
    """
    if host_which("systemd-detect-virt") is None:
        return None
    result = host_run(["systemd-detect-virt"])
    virt = result.stdout.strip()
    if result.returncode == 0 and virt and virt != "none":
        return virt
    return None
