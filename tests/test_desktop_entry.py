from pathlib import Path

import pytest

from stalker_gamma_linux.desktop.entry import render_desktop_entry, render_exec
from stalker_gamma_linux.paths_safety import UnsafeInstallTargetError, validate_install_target


def test_render_exec_leaves_simple_args_untouched() -> None:
    assert render_exec(["play", "--target", "/games/gamma"]) == "play --target /games/gamma"


def test_render_exec_quotes_args_with_spaces() -> None:
    assert render_exec(["/opt/my game/bin", "a b"]) == '"/opt/my game/bin" "a b"'


def test_render_exec_escapes_reserved_characters() -> None:
    assert render_exec(['a"b']) == '"a\\"b"'
    assert render_exec(["a`b"]) == '"a\\`b"'
    assert render_exec(["a$b"]) == '"a\\$b"'
    assert render_exec(["a\\b"]) == '"a\\\\b"'


def test_render_exec_backslash_escaped_before_other_reserved_chars() -> None:
    # Un mauvais ordre d'échappement transformerait `\"` en `\\"` (backslash en trop).
    assert render_exec(['a\\"b']) == '"a\\\\\\"b"'


def test_render_exec_doubles_literal_percent() -> None:
    assert render_exec(["100%"]) == "100%%"


def test_render_exec_accepts_path_objects() -> None:
    assert render_exec([Path("/bin/true"), "arg"]) == "/bin/true arg"


def test_render_desktop_entry_contains_expected_fields() -> None:
    entry = render_desktop_entry(
        command=["/bin/stalker-gamma-linux", "play", "--target", "/games/gamma"],
        working_dir=Path("/games/gamma"),
        icon=Path("/icons/stalker-gamma-linux.png"),
    )

    lines = entry.splitlines()
    assert lines[0] == "[Desktop Entry]"
    assert "Type=Application" in lines
    assert "Name=Play GAMMA (direct)" in lines
    assert "Exec=/bin/stalker-gamma-linux play --target /games/gamma" in lines
    assert "Path=/games/gamma" in lines
    assert "Icon=/icons/stalker-gamma-linux.png" in lines
    assert "Categories=Game;" in lines
    assert "Terminal=false" in lines
    assert entry.endswith("\n")


class TestDesktopEntryInjection:
    """CWE-74 : un `\\n` dans le chemin d'install ouvrait une seconde clé `Exec=`.

    `entry.py` n'échappe volontairement pas les sauts de ligne — le quoting
    `Exec=` de la spec freedesktop couvre `\\ " ` $ %`, et une valeur de clé
    `.desktop` n'a tout simplement aucune façon de représenter un `\\n`. La
    neutralisation se fait donc en amont, à la frontière
    (`paths_safety.validate_install_target`) : ces tests vérifient les deux
    moitiés du contrat.
    """

    @staticmethod
    def _exec_lines(entry: str) -> list[str]:
        return [line for line in entry.splitlines() if line.startswith("Exec=")]

    @pytest.mark.parametrize(
        "target",
        [
            "/games/gamma",
            "/home/user/Jeux préférés/gamma",
            "/games/a b",
            '/games/a"b',
            "/games/a$b",
            "/games/100%",
        ],
    )
    def test_un_chemin_valide_ne_rend_jamais_plus_dun_exec(self, target: str) -> None:
        """Non-régression : quel que soit le chemin accepté à la frontière, un seul `Exec=`."""
        path = validate_install_target(Path(target))

        entry = render_desktop_entry(
            command=["/bin/stalker-gamma-linux", "play", "--target", str(path)],
            working_dir=path,
            icon=Path("/icons/stalker-gamma-linux.png"),
        )

        assert len(self._exec_lines(entry)) == 1

    def test_le_chemin_qui_injectait_un_exec_est_refuse_en_amont(self) -> None:
        """Le payload historique : `Path=` recopiait le `\\n` et publiait un second `Exec=`."""
        payload = Path('/tmp/a\nExec=/bin/sh -c "touch /tmp/pwned"')

        # Sans le garde-fou, `render_desktop_entry` produisait bien 3 lignes `Exec=`.
        unguarded = render_desktop_entry(
            command=["/bin/stalker-gamma-linux", "play", "--target", str(payload)],
            working_dir=payload,
            icon=Path("/icons/stalker-gamma-linux.png"),
        )
        assert len(self._exec_lines(unguarded)) > 1

        with pytest.raises(UnsafeInstallTargetError):
            validate_install_target(payload)
