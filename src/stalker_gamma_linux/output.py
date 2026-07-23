"""Sortie utilisateur des commandes orchestrées (`install`/`update`/`doctor`).

Rendu console via `rich` (progression lisible) doublé d'un enregistrement dans
le logger applicatif (`logging_setup.py`) : la console montre toujours la
progression normale, le fichier de log garde une trace complète quel que soit
`--verbose`.
"""

from __future__ import annotations

import logging
from typing import Protocol

from rich.console import Console

from stalker_gamma_linux.logging_setup import LOGGER_NAME

console = Console()
_logger = logging.getLogger(LOGGER_NAME)


class Reporter(Protocol):
    """Ce que `orchestrator.py` a besoin de rapporter, indépendamment du rendu.

    La CLI utilise `console_reporter` ci-dessous (comportement historique :
    `rich` + logger). La GUI (T08) fournit sa propre implémentation qui pousse
    ces mêmes événements vers ses widgets (fil d'étapes, barre de progression,
    journal repliable) via `gui.worker`, sans dupliquer la logique d'
    `orchestrator.run_install`/`run_update` — seul le rendu change.
    """

    def header(self, message: str) -> None: ...
    def step(self, index: str, message: str) -> None: ...
    def skip(self, index: str, message: str) -> None: ...
    def progress(self, message: str) -> None: ...
    def success(self, message: str) -> None: ...
    def warn(self, message: str) -> None: ...
    def error(self, message: str, *, hint: str | None = None) -> None: ...


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


class ConsoleReporter:
    """`Reporter` par défaut, utilisé par la CLI : délègue aux fonctions ci-dessus."""

    def header(self, message: str) -> None:
        header(message)

    def step(self, index: str, message: str) -> None:
        step(index, message)

    def skip(self, index: str, message: str) -> None:
        skip(index, message)

    def progress(self, message: str) -> None:
        progress(message)

    def success(self, message: str) -> None:
        success(message)

    def warn(self, message: str) -> None:
        warn(message)

    def error(self, message: str, *, hint: str | None = None) -> None:
        error(message, hint=hint)


console_reporter = ConsoleReporter()
