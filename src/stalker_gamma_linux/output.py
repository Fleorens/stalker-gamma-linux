"""Sortie utilisateur des commandes orchestrées (`install`/`update`/`doctor`).

Rendu console via `rich` (progression lisible) doublé d'un enregistrement dans
le logger applicatif (`logging_setup.py`) : la console montre toujours la
progression normale, le fichier de log garde une trace complète quel que soit
`--verbose`.
"""

from __future__ import annotations

import logging

from rich.console import Console

from stalker_gamma_linux.logging_setup import LOGGER_NAME

console = Console()
_logger = logging.getLogger(LOGGER_NAME)


def header(message: str) -> None:
    console.print(f"[bold]{message}[/bold]")
    _logger.info(message)


def step(index: str, message: str) -> None:
    console.print(f"[cyan]→ {index}[/cyan] {message}")
    _logger.info("étape %s : %s", index, message)


def skip(index: str, message: str) -> None:
    console.print(f"[dim]↷ {index} {message} (déjà fait — reprise)[/dim]")
    _logger.debug("étape sautée %s : %s", index, message)


def progress(message: str) -> None:
    console.print(message)
    _logger.debug(message)


def success(message: str) -> None:
    console.print(f"[bold green]{message}[/bold green]")
    _logger.info(message)


def warn(message: str) -> None:
    console.print(f"[yellow]{message}[/yellow]")
    _logger.warning(message)


def error(message: str, *, hint: str | None = None) -> None:
    console.print(f"[bold red]Erreur[/bold red] : {message}")
    _logger.error(message)
    if hint is not None:
        console.print(f"[yellow]→ {hint}[/yellow]")
        _logger.info("suggestion : %s", hint)
