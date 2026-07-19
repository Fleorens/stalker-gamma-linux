"""Test d'intégration optionnel : exécute le vrai binaire `gamma-launcher`.

Exclu par défaut (voir `addopts` dans pyproject.toml). Pour le lancer :
    pytest -m network tests/test_engine_integration.py
Nécessite `gamma-launcher` installé dans le PATH ; sinon il est skippé.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from stalker_gamma_linux.engine.errors import VerificationError
from stalker_gamma_linux.engine.paths import InstallPaths
from stalker_gamma_linux.engine.runner import verify

pytestmark = pytest.mark.network


def test_verify_against_empty_target_fails_with_real_binary(tmp_path: Path) -> None:
    if shutil.which("gamma-launcher") is None:
        pytest.skip("gamma-launcher n'est pas installé dans le PATH")

    paths = InstallPaths.under(tmp_path)
    paths.ensure_directories()

    with pytest.raises(VerificationError):
        verify(paths)
