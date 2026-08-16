"""Isolation commune : aucun test ne doit toucher les vrais répertoires XDG."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from stalker_gamma_linux.logging_setup import LOGGER_NAME

# Fixe la locale gettext à l'anglais (langue source) pour toute la session de
# test, indépendamment de la machine qui l'exécute (ex. LANG=fr_FR.UTF-8 sur
# le poste de Florian). Doit s'exécuter avant le premier `import` de
# `stalker_gamma_linux.i18n` (résolution figée au niveau module) : une
# variable de niveau module dans ce fichier, chargé par pytest avant la
# collecte des tests du répertoire, est le seul point garanti assez tôt —
# une fixture (même autouse) tournerait après cet import.
os.environ["LANGUAGE"] = "en"


@pytest.fixture(autouse=True)
def _isolate_xdg_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


@pytest.fixture(autouse=True)
def _restore_logging_state() -> Iterator[None]:
    """Restaure l'état global du logging entre les tests.

    `logging_setup.configure_logging` pose des handlers et coupe la propagation
    (`logger.propagate = False`) sur le logger du projet. Sans restauration, le
    premier test qui l'appelle change le comportement de tous les suivants :
    `caplog` ne voit plus rien, puisque les enregistrements ne remontent plus
    jusqu'à son handler.

    Constaté en réel le 2026-08-16, en construisant le paquet AUR : la suite
    passait ici (pytest 9.1) et échouait dans le conteneur Arch (pytest 9.0)
    sur `test_state.py::test_lavertissement_est_journalise`. Le test n'était
    pas faux — il dépendait d'un état laissé par un autre fichier, et d'un
    détail de version de pytest pour survivre.
    """
    logger = logging.getLogger(LOGGER_NAME)
    handlers, level, propagate = logger.handlers[:], logger.level, logger.propagate
    yield
    logger.handlers[:] = handlers
    logger.level = level
    logger.propagate = propagate
