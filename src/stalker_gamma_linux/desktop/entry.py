"""Rendu du contenu d'un fichier `.desktop` (spec freedesktop Desktop Entry).

Seul `Exec=` a une syntaxe de quoting/échappement propre (proche d'un shell,
mais pas un shell) : https://specifications.freedesktop.org/desktop-entry-spec/latest/exec-variables.html
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

APP_NAME = "S.T.A.L.K.E.R. G.A.M.M.A."
COMMENT = "Anomaly + le modpack G.A.M.M.A., via Mod Organizer 2 sous Proton"

# Caractères réservés à l'intérieur d'une valeur `Exec=` entre guillemets.
# Le backslash doit être échappé EN PREMIER, sinon les backslashes insérés par
# l'échappement des autres caractères seraient eux-mêmes ré-échappés ensuite.
_RESERVED_INSIDE_QUOTES = ("\\", '"', "`", "$")


def _escape_percent(text: str) -> str:
    """`%` est un préfixe de code de champ (`%f`, `%u`…) : un `%` littéral s'écrit `%%`."""
    return text.replace("%", "%%")


def _quote_exec_arg(arg: str) -> str:
    """Échappe un argument de `Exec=` ; l'entoure de guillemets si nécessaire."""
    arg = _escape_percent(arg)
    needs_quotes = any(char in arg for char in (" ", "\t")) or any(
        char in arg for char in _RESERVED_INSIDE_QUOTES
    )
    if not needs_quotes:
        return arg
    escaped = arg
    for char in _RESERVED_INSIDE_QUOTES:
        escaped = escaped.replace(char, f"\\{char}")
    return f'"{escaped}"'


def render_exec(command: Sequence[str | Path]) -> str:
    """Rend une liste d'arguments en une valeur `Exec=` correctement échappée."""
    return " ".join(_quote_exec_arg(str(part)) for part in command)


def render_desktop_entry(*, command: Sequence[str | Path], working_dir: Path, icon: Path) -> str:
    """Contenu complet du fichier `.desktop` (une entrée `[Desktop Entry]`)."""
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={APP_NAME}",
        f"Comment={COMMENT}",
        f"Exec={render_exec(command)}",
        f"Path={working_dir}",
        f"Icon={icon}",
        "Categories=Game;",
        "Terminal=false",
        "StartupNotify=false",
    ]
    return "\n".join(lines) + "\n"
