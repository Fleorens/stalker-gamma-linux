"""Logging applicatif : fichier tournant (toujours détaillé) + console (`--verbose`).

Le fichier capture tout (DEBUG) en continu sous `~/.local/state/` (XDG) pour
qu'un bug puisse être diagnostiqué après coup sans avoir eu `--verbose` au
moment des faits. La console, elle, ne montre les détails internes que sur
demande (`--verbose`) — la progression normale passe par `output.py` (rich),
pas par ce logger.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "stalker_gamma_linux"

_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5


def state_dir() -> Path:
    """`$XDG_STATE_HOME`, ou `~/.local/state` par défaut (spec freedesktop)."""
    override = os.environ.get("XDG_STATE_HOME")
    base = Path(override) if override else Path.home() / ".local" / "state"
    return base / "stalker-gamma-linux"


def log_file() -> Path:
    return state_dir() / "stalker-gamma-linux.log"


def configure_logging(*, verbose: bool = False) -> Path:
    """Configure le logger applicatif. Retourne le chemin du fichier de log."""
    directory = state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = log_file()

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    file_handler = RotatingFileHandler(
        path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console_handler)

    return path
