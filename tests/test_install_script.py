"""Fonctions de `install.sh` testées une à une, hors exécution du script.

`install.sh` ne peut pas importer `environment.commands` : il tourne avant que le
venv existe. Ses remèdes par distribution en sont donc des copies, et une copie
diverge en silence. Chaque fonction est extraite du script (de `nom() {` à la
première `}` en début de ligne) puis exécutée seule par bash.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from stalker_gamma_linux.environment.commands import INSTALL_COMMANDS
from stalker_gamma_linux.environment.distro import DistroFamily

INSTALL_SH = Path(__file__).resolve().parent.parent / "install.sh"


def _function(name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", INSTALL_SH.read_text(), re.M | re.S)
    assert match is not None, f"fonction {name} introuvable dans install.sh"
    return match.group(0)


def _run(script: str, env: dict[str, str]) -> str:
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", **env},
        check=True,
    )
    return result.stdout.strip()


# Une distribution réelle par famille, `ID_LIKE` compris pour Ubuntu : c'est lui
# qui la range avec Debian.
_OS_RELEASES = [
    ("ID=fedora\n", DistroFamily.FEDORA),
    ("ID=arch\n", DistroFamily.ARCH),
    ("ID=debian\n", DistroFamily.DEBIAN),
    ('ID=ubuntu\nID_LIKE="debian"\n', DistroFamily.DEBIAN),
]


@pytest.mark.parametrize(
    ("shell_function", "key"),
    [
        ("gtk_install_hint", "gtk-gui"),
        ("build_tools_hint", "build-tools"),
    ],
)
@pytest.mark.parametrize(("os_release", "family"), _OS_RELEASES)
def test_le_remede_du_script_est_celui_de_install_commands(
    tmp_path: Path, shell_function: str, key: str, os_release: str, family: DistroFamily
) -> None:
    release = tmp_path / "os-release"
    release.write_text(os_release)
    script = _function("distro_ids") + _function(shell_function) + shell_function

    hint = _run(script, {"OS_RELEASE": str(release)})

    assert hint == INSTALL_COMMANDS[key].for_family(family)


@pytest.mark.parametrize(
    ("pyvenv_cfg", "expected"),
    [
        # Ce qu'écrit `venv` depuis Python 3.11.
        ("home = /usr/bin\ninclude-system-site-packages = true\nversion = 3.14.6\n", "3.14"),
        # L'ancienne clé, encore présente dans des venvs créés par de vieux Python.
        ("home = /usr/bin\nversion_info = 3.10.12.final.0\n", "3.10"),
        ("home = /usr/bin\n", ""),
    ],
)
def test_venv_python_version_lit_majeure_mineure(
    tmp_path: Path, pyvenv_cfg: str, expected: str
) -> None:
    (tmp_path / "pyvenv.cfg").write_text(pyvenv_cfg)
    script = _function("venv_python_version") + f'venv_python_version "{tmp_path}"'

    assert _run(script, {}) == expected


def test_venv_python_version_sans_pyvenv_cfg_rend_vide_sans_echouer(tmp_path: Path) -> None:
    """Sous `set -euo pipefail`, un `sed` en échec arrêterait le script entier."""
    script = _function("venv_python_version") + f'venv_python_version "{tmp_path}"'

    assert _run(script, {}) == ""
