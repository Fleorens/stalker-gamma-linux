"""Isolation commune : aucun test ne doit toucher les vrais répertoires XDG."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

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
