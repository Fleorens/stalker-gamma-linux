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
