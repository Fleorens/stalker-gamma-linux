from pathlib import Path

from stalker_gamma_linux.desktop.entry import render_desktop_entry, render_exec


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
    assert "Name=S.T.A.L.K.E.R. G.A.M.M.A." in lines
    assert "Exec=/bin/stalker-gamma-linux play --target /games/gamma" in lines
    assert "Path=/games/gamma" in lines
    assert "Icon=/icons/stalker-gamma-linux.png" in lines
    assert "Categories=Game;" in lines
    assert "Terminal=false" in lines
    assert entry.endswith("\n")
