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
    if which("systemd-detect-virt") is None:
        return None
    result = run(["systemd-detect-virt"])
    virt = result.stdout.strip()
    if result.returncode == 0 and virt and virt != "none":
        return virt
    return None
